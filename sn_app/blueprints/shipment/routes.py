from flask import request, render_template, redirect, url_for, Blueprint, flash, jsonify
from flask_login import login_user, logout_user, current_user, login_required
import os
import requests
from sn_app.app import db, bcrypt
from sn_app.blueprints.auth.models import   User, Note


from sn_app.blueprints.shipment.models import (
    Truck,
    Shipment,
    CargoDocument,
    Route,
    TripCityCheckpoint,
    GPSUpdate,
    Disruption,
    RerouteLog
)

shipment = Blueprint(
    'shipment',
    __name__,
    template_folder='templates'  
)

#FASTAPI_AGENT_URL = os.getenv("FASTAPI_AGENT_URL", "http://localhost:8000")
FASTAPI_AGENT_URL = os.getenv("FASTAPI_AGENT_URL", "https://testingserver-supplynet.vercel.app/")

# ----------------------------------------------------------------------
# CREATE SHIPMENT & CALL INITIAL ROUTE OPTIMIZATION AGENT
# ----------------------------------------------------------------------
@shipment.route('/create', methods=['GET', 'POST'])
@login_required
def create_shipment():
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form

        # 1. Fetch & Verify Selected Truck
        truck_id = data.get('truck_id')
        truck = db.session.get(Truck, truck_id) if truck_id else None
        
        if not truck or truck.user_id != current_user.id:
            if request.is_json:
                return jsonify({"error": "Unauthorized or invalid truck selected"}), 400
            flash("Unauthorized or invalid truck selected.", "danger")
            return redirect(url_for('shipment.create_shipment'))

        # Helper function to parse numbers cleanly
        def parse_float(val, default=None):
            try:
                return float(val) if val is not None and str(val).strip() != '' else default
            except (ValueError, TypeError):
                return default

        try:
            # 2. Create Base Shipment Record
            new_shipment = Shipment(
                user_id=current_user.id,
                truck_id=truck.id,
                cargo_type=data.get('cargo_type', '').strip(),
                total_weight_kg=parse_float(data.get('total_weight_kg'), 0.0),
                origin_lat=parse_float(data.get('origin_lat')),
                origin_lon=parse_float(data.get('origin_lon')),
                destination_lat=parse_float(data.get('destination_lat')),
                destination_lon=parse_float(data.get('destination_lon')),
                origin_pin=data.get('origin_pin', '').strip() or None,
                destination_pin=data.get('destination_pin', '').strip() or None,
                priority=data.get('priority', 'MEDIUM'),
                consignment_value=parse_float(data.get('consignment_value')),
                status='CREATED'
            )
            db.session.add(new_shipment)
            db.session.flush()  # Generates string UUID for new_shipment.id

            # 3. Create Cargo Documentation Record
            cargo_doc = CargoDocument(
                shipment_id=new_shipment.id,
                supplier_gstin=data.get('supplier_gstin', '').strip() or None,
                recipient_gstin=data.get('recipient_gstin', '').strip() or None,
                invoice_number=data.get('invoice_number', '').strip() or None,
                hsn_code=data.get('hsn_code', '').strip() or None,
                consignment_value=parse_float(data.get('consignment_value')),
                transporter_doc_no=data.get('transporter_doc_no', '').strip() or None
            )
            db.session.add(cargo_doc)
            db.session.commit()

        except Exception as e:
            db.session.rollback()
            if request.is_json:
                return jsonify({"error": f"Failed to save shipment: {str(e)}"}), 500
            flash(f"Error saving shipment: {str(e)}", "danger")
            return redirect(url_for('shipment.create_shipment'))

        # 4. Call FastAPI Optimization Agent
        opt_payload = {
            "shipment_id": new_shipment.id,
            "priority": new_shipment.priority,
            "constraints": {
                "gvw_kg": parse_float(truck.gvw_kg, 0.0),
                "axle_count": truck.axle_count or 2,
                "height_m": parse_float(truck.height_m, 0.0),
                "width_m": parse_float(truck.width_m, 0.0)
            },
            "origin": {
                "lat": float(new_shipment.origin_lat),
                "lon": float(new_shipment.origin_lon),
                "pin": new_shipment.origin_pin
            },
            "destination": {
                "lat": float(new_shipment.destination_lat),
                "lon": float(new_shipment.destination_lon),
                "pin": new_shipment.destination_pin
            },
            "cargo": {
                "type": new_shipment.cargo_type,
                "weight_kg": float(new_shipment.total_weight_kg or 0),
                "value": float(new_shipment.consignment_value or 0)
            }
        }

        try:
            resp = requests.post(f"{FASTAPI_AGENT_URL}/api/v1/optimize-route", json=opt_payload, timeout=15)
            
            if resp.status_code == 200:
                opt_data = resp.json()
                sel_route = opt_data.get('selected_route', {})

                # Save Primary Optimized Route
                active_route = Route(
                    shipment_id=new_shipment.id,
                    route_type='PRIMARY',
                    is_active=True,
                    origin_lat=new_shipment.origin_lat,
                    origin_lon=new_shipment.origin_lon,
                    destination_lat=new_shipment.destination_lat,
                    destination_lon=new_shipment.destination_lon,
                    distance_km=parse_float(sel_route.get('distance_km')),
                    duration_minutes=parse_float(sel_route.get('duration_minutes')),
                    fuel_cost=parse_float(sel_route.get('fuel_cost')),
                    toll_cost=parse_float(sel_route.get('toll_cost')),
                    road_risk_score=parse_float(sel_route.get('road_risk_score')),
                    weather_risk_score=parse_float(sel_route.get('weather_risk_score')),
                    optimization_score=parse_float(sel_route.get('objective_j_score')),
                    geometry=sel_route.get('geometry')  # Standard JSON payload for MySQL
                )
                db.session.add(active_route)

                # Save Planned Checkpoints
                for cp in opt_data.get('checkpoints', []):
                    checkpoint = TripCityCheckpoint(
                        shipment_id=new_shipment.id,
                        sequence_order=cp['order'],
                        city_name=cp['city_name'],
                        latitude=parse_float(cp['lat']),
                        longitude=parse_float(cp['lon']),
                        status='PENDING'
                    )
                    db.session.add(checkpoint)

                db.session.commit()
                flash("Shipment created and route successfully optimized!", "success")
            else:
                flash(f"Shipment created, but optimization service returned status {resp.status_code}.", "warning")

        except Exception as e:
            db.session.rollback()
            print(f"Error calling optimization agent: {str(e)}")
            flash("Shipment created, but optimization agent was unreachable.", "warning")

        # Response handling for JSON vs HTML Form submission
        if request.is_json:
            return jsonify({
                "message": "Shipment created & optimized", 
                "shipment_id": new_shipment.id
            }), 201
        trucks = Truck.query.filter_by(user_id=current_user.id, active=True).all()
        user_shipments = Shipment.query.filter_by(user_id=current_user.id).order_by(Shipment.created_at.desc()).all()
        return render_template('shipment/shipments.html', trucks=trucks, shipments=user_shipments)
        

   # GET Request: Render directory with user's shipments and active trucks for the modal form
    trucks = Truck.query.filter_by(user_id=current_user.id, active=True).all()
    user_shipments = Shipment.query.filter_by(user_id=current_user.id).order_by(Shipment.created_at.desc()).all()
    
    return render_template('shipment/shipments.html', trucks=trucks, shipments=user_shipments)

@shipment.route('/manage', methods=['GET'])
@login_required
def manage_shipments():
    # Fetch user's active trucks and shipments with route details
    trucks = Truck.query.filter_by(user_id=current_user.id, active=True).all()
    user_shipments = Shipment.query.filter_by(user_id=current_user.id).order_by(Shipment.created_at.desc()).all()
    
    return render_template('shipment/manage_shipments.html', shipments=user_shipments, trucks=trucks)


# Updating shipment status
@shipment.route('/shipments/<shipment_id>/status', methods=['POST'])
@login_required
def update_shipment_status(shipment_id):
    shipment_obj = Shipment.query.filter_by(id=shipment_id, user_id=current_user.id).first_or_404()
    new_status = request.form.get('status')
    
    if new_status in ['CREATED', 'EN_ROUTE', 'REROUTED', 'DELIVERED', 'CANCELLED']:
        shipment_obj.status = new_status
        db.session.commit()
        flash(f"Shipment status updated to {new_status}.", "info")
    else:
        flash("Invalid status selection.", "danger")

    trucks = Truck.query.filter_by(user_id=current_user.id, active=True).all()
    user_shipments = Shipment.query.filter_by(user_id=current_user.id).order_by(Shipment.created_at.desc()).all()
    return render_template('shipment/shipments.html', trucks=trucks, shipments=user_shipments)


# 1. Get Shipment Detail Page Route
@shipment.route('/<shipment_id>', methods=['GET'])
def get_shipment_detail(shipment_id):
    shipment = Shipment.query.get_or_404(shipment_id)
    return render_template('shipment/shipment_detail.html', shipment=shipment)







# ----------------------------------------------------------------------
# 2. START TRANSIT & TRIGGER FASTAPI GPS SIMULATOR
# ----------------------------------------------------------------------
@shipment.route('/<shipment_id>/start-transit', methods=['POST'])
@login_required
def start_transit(shipment_id):
    shipment_obj = Shipment.query.filter_by(id=shipment_id, user_id=current_user.id).first_or_404()
    active_route = Route.query.filter_by(shipment_id=shipment_obj.id, is_active=True).first()

    if not active_route or not active_route.geometry:
        return jsonify({"error": "No optimized active route found to simulate."}), 400

    """  # Payload to register simulation in FastAPI's memory
    sim_payload = {
        "route_id": str(active_route.id),
        "vehicle_id": str(shipment_obj.truck_id),
        "auto_start": True
    }"""
    sim_payload = {
    "shipment_id": str(shipment_obj.id),
    "route_id": str(active_route.id),
    "truck_id": str(shipment_obj.truck_id) if shipment_obj.truck_id else None,
    "auto_start": True
        }

    try:
        resp = requests.post(f"{FASTAPI_AGENT_URL}/api/v1/simulations", json=sim_payload, timeout=10)
        
        if resp.status_code in [200, 201]:
            sim_data = resp.json()
            
            # Update shipment status in Flask DB
            shipment_obj.status = 'EN_ROUTE'
            db.session.commit()

            return jsonify({
                "message": "Transit started. GPS simulation running in memory.",
                "shipment_id": str(shipment_obj.id),
                "simulation_id": sim_data.get("id")
            }), 200
        elif resp.status_code == 409:
            return jsonify({"error": "Simulation already running for this truck."}), 409
        else:
            return jsonify({"error": "Failed to start simulation on agent backend."}), 500

    except Exception as e:
        return jsonify({"error": f"Connection error to FastAPI agent: {str(e)}"}), 500


@shipment.route('/<shipment_id>/record-gps', methods=['POST'])
@login_required
def record_gps_update(shipment_id):
    shipment_obj = Shipment.query.filter_by(id=shipment_id, user_id=current_user.id).first_or_404()
    data = request.get_json()

    if not data or 'latitude' not in data or 'longitude' not in data:
        return jsonify({"error": "Invalid GPS payload"}), 400

    # Save incoming coordinate into MySQL gps_updates table
    gps_entry = GPSUpdate(
        shipment_id=shipment_obj.id,
        truck_id=shipment_obj.truck_id,
        latitude=float(data['latitude']),
        longitude=float(data['longitude']),
        speed_kmph=float(data.get('speed_kmph', 60.0)),
        heading=float(data.get('heading', 0.0)),
        source='FASTAPI_SIMULATOR'
    )

    db.session.add(gps_entry)

    # Check if the truck has reached destination (100% route progress)
    if data.get('route_progress_percent') == 100 or data.get('status') == 'COMPLETED':
        shipment_obj.status = 'DELIVERED'

    db.session.commit()

    return jsonify({"message": "GPS update recorded", "gps_id": gps_entry.id}), 201









# ----------------------------------------------------------------------
# 3. DYNAMIC REROUTE CALLBACK (Triggered by Agent Disruption Engine)
# ----------------------------------------------------------------------
@shipment.route('/<shipment_id>/reroute', methods=['POST'])
def trigger_reroute(shipment_id):
    data = request.get_json()
    shipment_obj = db.session.get(Shipment, shipment_id)
    if not shipment_obj:
        return jsonify({"error": "Shipment not found"}), 404

    blocked_city = data.get('blocked_city')
    bypass_city = data.get('bypass_city')

    # Update Checkpoints: Set old to BYPASSED and insert new detour checkpoint
    blocked_cp = TripCityCheckpoint.query.filter_by(shipment_id=shipment_obj.id, city_name=blocked_city).first()
    if blocked_cp:
        blocked_cp.status = 'BYPASSED'
        blocked_seq = blocked_cp.sequence_order

        TripCityCheckpoint.query.filter(
            TripCityCheckpoint.shipment_id == shipment_obj.id,
            TripCityCheckpoint.sequence_order > blocked_seq
        ).update({"sequence_order": TripCityCheckpoint.sequence_order + 1})

        new_cp = TripCityCheckpoint(
            shipment_id=shipment_obj.id,
            sequence_order=blocked_seq + 1,
            city_name=bypass_city,
            latitude=data.get('bypass_lat'),
            longitude=data.get('bypass_lon'),
            status='PENDING'
        )
        db.session.add(new_cp)

    # Deactivate current active route & insert new detour route
    Route.query.filter_by(shipment_id=shipment_obj.id, is_active=True).update({"is_active": False})

    new_route = Route(
        shipment_id=shipment_obj.id,
        route_type='DETOUR',
        is_active=True,
        origin_lat=shipment_obj.origin_lat,
        origin_lon=shipment_obj.origin_lon,
        destination_lat=shipment_obj.destination_lat,
        destination_lon=shipment_obj.destination_lon,
        distance_km=data.get('distance_km'),
        duration_minutes=data.get('duration_minutes'),
        fuel_cost=data.get('fuel_cost'),
        toll_cost=data.get('toll_cost'),
        geometry=data.get('new_geometry'),
        routing_provider='OSRM'
    )
    db.session.add(new_route)

    # Log LLM reasoning
    shipment_obj.status = 'REROUTED'
    reroute_log = RerouteLog(
        shipment_id=shipment_obj.id,
        disruption_id=data.get('disruption_id'),
        affected_city=blocked_city,
        bypass_city=bypass_city,
        llm_reasoning=data.get('reasoning', 'Rerouted due to disruption.')
    )
    db.session.add(reroute_log)
    db.session.commit()

    return jsonify({"message": "Shipment rerouted", "status": shipment_obj.status}), 200

# Adding new truck and loading truck page
@shipment.route('/trucks', methods=['GET', 'POST'])
@login_required
def manage_trucks():
    if request.method == 'POST':
        registration_number = request.form.get('registration_number', '').strip().upper()
        truck_type = request.form.get('truck_type')
        capacity_tons = request.form.get('capacity_tons')
        gvw_kg = request.form.get('gvw_kg')
        axle_count = request.form.get('axle_count')
        height_m = request.form.get('height_m')
        width_m = request.form.get('width_m')

        # Basic Validation
        if not registration_number or not truck_type or not capacity_tons:
            flash("Registration number, truck type, and capacity are required.", "danger")
            return redirect(url_for('shipment.manage_trucks'))

        # Check duplicate registration
        existing_truck = Truck.query.filter_by(registration_number=registration_number).first()
        if existing_truck:
            flash(f"Truck with registration {registration_number} already exists.", "danger")
            return redirect(url_for('shipment.manage_trucks'))

        try:
            new_truck = Truck(
                user_id=current_user.id,
                registration_number=registration_number,
                truck_type=truck_type,
                capacity_tons=float(capacity_tons) if capacity_tons else None,
                gvw_kg=float(gvw_kg) if gvw_kg else None,
                axle_count=int(axle_count) if axle_count else 2,
                height_m=float(height_m) if height_m else None,
                width_m=float(width_m) if width_m else None,
                active=True
            )
            db.session.add(new_truck)
            db.session.commit()
            flash("Truck added successfully!", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error saving truck: {str(e)}", "danger")

        return redirect(url_for('shipment.manage_trucks'))

    # GET Request
    user_trucks = Truck.query.filter_by(user_id=current_user.id).order_by(Truck.created_at.desc()).all()
    return render_template('shipment/trucks.html', trucks=user_trucks)

@shipment.route('/trucks/<truck_id>/toggle', methods=['POST'])
@login_required
def toggle_truck_status(truck_id):
    truck = Truck.query.filter_by(id=truck_id, user_id=current_user.id).first_or_404()
    truck.active = not truck.active
    db.session.commit()
    flash(f"Truck status updated to {'Active' if truck.active else 'Inactive'}.", "info")
    return redirect(url_for('shipment.manage_trucks'))