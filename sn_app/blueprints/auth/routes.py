from flask import request, render_template, redirect, url_for, Blueprint, flash
from flask_login import login_user, logout_user, current_user, login_required
import os
from sn_app.app import db, bcrypt
from sn_app.blueprints.auth.models import   User, Note
from sn_app.blueprints.shipment.models import (
    Shipment,
    Disruption,
    RerouteLog,
    Truck,
    Route,
    GPSUpdate,
    TripCityCheckpoint,
)

auth = Blueprint('auth', __name__, template_folder='templates')

_ACTIVE_SHIPMENT_STATUSES = frozenset({'CREATED', 'EN_ROUTE', 'REROUTED', 'DELAYED'})


@auth.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('auth.dashboard'))
    return render_template('auth/index.html')


# You can set this in your app config or environment variables (e.g., SECRET_COMPANY_CODE="KATARIA2026")


@auth.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        return render_template("auth/signup.html")

    enterprise_name = request.form.get("enterprise_name")
    email = request.form.get("email")
    password = request.form.get("password")
    name = request.form.get("name")
    role = request.form.get("role", "employee")  # Default role if not provided

    # 1. Basic validation for required fields
    if not email or not password or not name:
        flash("Please fill in all required fields.", "danger")
        return redirect(url_for("auth.signup"))

    # 2. Check for existing user by email
    if User.query.filter_by(email=email.lower().strip()).first():
        flash("Email is already registered. Please log in or use another email.", "danger")
        return redirect(url_for("auth.signup"))

    # 3. Hash password and save new user record
    hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")
    new_user = User(
        name=name,
        email=email.lower().strip(),
        password_hash=hashed_password,
        role=role,
        enterprise_name=enterprise_name,
    )

    db.session.add(new_user)
    db.session.commit()

    flash("Account created successfully! Please log in.", "success")
    return redirect(url_for("auth.login"))

@auth.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("auth/login.html")

    email = request.form.get("email")
    password = request.form.get("password")

    # Basic input check
    if not email or not password:
        flash("Please enter both email and password.", "danger")
        return redirect(url_for("auth.login"))

    # Fetch user by email (normalized to lowercase)
    user = User.query.filter_by(email=email.lower().strip()).first()

    # Validate user credentials
    if user and bcrypt.check_password_hash(user.password_hash, password):
        login_user(user)
        flash(f"Welcome back, {user.name}!", "success")
        return redirect(url_for("auth.dashboard"))

    # Generic error message to prevent email enumeration
    flash("Invalid email or password.", "danger")
    return redirect(url_for("auth.login"))

@auth.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('auth.login'))


@auth.route('/dashboard')
@login_required
def dashboard():
    user_shipments = (
        Shipment.query.filter_by(user_id=current_user.id)
        .order_by(Shipment.created_at.desc())
        .all()
    )

    active_disruptions = (
        Disruption.query.filter_by(status="ACTIVE")
        .order_by(Disruption.start_time.desc())
        .limit(8)
        .all()
    )

    reroute_log_count = (
        RerouteLog.query.join(Shipment)
        .filter(Shipment.user_id == current_user.id)
        .count()
    )
    reroute_logs = (
        RerouteLog.query.join(Shipment)
        .filter(Shipment.user_id == current_user.id)
        .order_by(RerouteLog.created_at.desc())
        .limit(10)
        .all()
    )

    user_trucks = Truck.query.filter_by(user_id=current_user.id).all()
    active_truck_count = sum(1 for t in user_trucks if t.active)

    status_counts = {
        'created': 0,
        'en_route': 0,
        'rerouted': 0,
        'delivered': 0,
        'delayed': 0,
        'cancelled': 0,
        'other': 0,
    }
    high_priority_open = 0
    for s in user_shipments:
        st = (s.status or '').upper()
        if st == 'CREATED':
            status_counts['created'] += 1
        elif st == 'EN_ROUTE':
            status_counts['en_route'] += 1
        elif st == 'REROUTED':
            status_counts['rerouted'] += 1
        elif st == 'DELIVERED':
            status_counts['delivered'] += 1
        elif st == 'DELAYED':
            status_counts['delayed'] += 1
        elif st == 'CANCELLED':
            status_counts['cancelled'] += 1
        else:
            status_counts['other'] += 1
        if (s.priority or '').upper() == 'HIGH' and st not in ('DELIVERED', 'CANCELLED'):
            high_priority_open += 1

    active_shipments_count = sum(
        1 for s in user_shipments if (s.status or '').upper() in _ACTIVE_SHIPMENT_STATUSES
    )

    shipment_ids = [s.id for s in user_shipments]
    active_routes = []
    if shipment_ids:
        active_routes = Route.query.filter(
            Route.shipment_id.in_(shipment_ids),
            Route.is_active.is_(True),
        ).all()

    optimization_scores = [
        float(r.optimization_score)
        for r in active_routes
        if r.optimization_score is not None
    ]
    avg_route_score = (
        round(sum(optimization_scores) / len(optimization_scores), 4)
        if optimization_scores
        else None
    )
    total_planned_km = round(
        sum(float(r.distance_km or 0) for r in active_routes), 1
    )
    total_estimated_cost = round(
        sum(float(r.fuel_cost or 0) + float(r.toll_cost or 0) for r in active_routes), 2
    )

    if not active_disruptions:
        disruption_level = 'clear'
        disruption_summary = 'No active disruptions on monitored corridors.'
    else:
        severities = {(d.severity or '').upper() for d in active_disruptions}
        if 'BLOCKING' in severities or len(active_disruptions) >= 4:
            disruption_level = 'high'
        elif 'HIGH' in severities or len(active_disruptions) >= 2:
            disruption_level = 'elevated'
        else:
            disruption_level = 'moderate'
        disruption_summary = (
            f"{len(active_disruptions)} active alert(s) — "
            f"latest: {active_disruptions[0].type.replace('_', ' ').title()} "
            f"near {active_disruptions[0].affected_city or 'corridor'}"
        )

    focus_id = request.args.get('focus_shipment_id')
    active_shipment = None
    if focus_id:
        active_shipment = Shipment.query.filter_by(
            id=focus_id, user_id=current_user.id
        ).first()
    if not active_shipment and user_shipments:
        for candidate in user_shipments:
            if (candidate.status or '').upper() in ('EN_ROUTE', 'REROUTED', 'DELAYED'):
                active_shipment = candidate
                break
        if not active_shipment:
            active_shipment = user_shipments[0]

    active_route = None
    focus_latest_gps = None
    focus_checkpoints = []
    focus_gps_trail = []
    if active_shipment:
        active_route = Route.query.filter_by(
            shipment_id=active_shipment.id, is_active=True
        ).first()
        focus_latest_gps = (
            GPSUpdate.query.filter_by(shipment_id=active_shipment.id)
            .order_by(GPSUpdate.timestamp.desc())
            .first()
        )
        focus_checkpoints = (
            TripCityCheckpoint.query.filter_by(shipment_id=active_shipment.id)
            .order_by(TripCityCheckpoint.sequence_order.asc())
            .all()
        )
        recent_gps = (
            GPSUpdate.query.filter_by(shipment_id=active_shipment.id)
            .order_by(GPSUpdate.timestamp.desc())
            .limit(25)
            .all()
        )
        focus_gps_trail = list(reversed(recent_gps))

    needs_attention = [
        s for s in user_shipments
        if (s.status or '').upper() in ('REROUTED', 'DELAYED')
        or ((s.status or '').upper() == 'CREATED' and not s.truck_id)
    ][:5]

    return render_template(
        'auth/dashboard.html',
        shipments=user_shipments,
        active_disruptions=active_disruptions,
        reroute_logs=reroute_logs,
        active_shipment=active_shipment,
        active_route=active_route,
        focus_latest_gps=focus_latest_gps,
        focus_checkpoints=focus_checkpoints,
        focus_gps_trail=focus_gps_trail,
        active_shipments_count=active_shipments_count,
        status_counts=status_counts,
        high_priority_open=high_priority_open,
        truck_count=len(user_trucks),
        active_truck_count=active_truck_count,
        avg_route_score=avg_route_score,
        total_planned_km=total_planned_km,
        total_estimated_cost=total_estimated_cost,
        disruption_level=disruption_level,
        disruption_summary=disruption_summary,
        needs_attention=needs_attention,
        reroute_log_count=reroute_log_count,
    )

@auth.route('/new_note', methods=['GET', 'POST'])
@login_required
def new_note():
    if request.method == 'GET':
        return render_template('auth/note.html')

    note_content = request.form.get('note')
    if note_content:
        # Uses current_user.eid (primary key)
        new_note = Note(content=note_content, user_id=current_user.eid)
        db.session.add(new_note)
        db.session.commit()
        flash('Note added successfully!', 'success')

    return redirect(url_for('auth.show_notes'))


@auth.route('/show_notes')
@login_required
def show_notes():
    user_notes = Note.query.filter_by(user_id=current_user.eid).all()
    notes_html = "<ul>"
    for n in user_notes:
        notes_html += f"<li>{n.content} <small>({n.date_created})</small></li>"
    notes_html += "</ul>"

    return f"""
        <a href="{url_for('auth.dashboard')}">Dashboard</a> | 
        <a href="{url_for('auth.logout')}">Logout</a>
        <h3>My Notes</h3>
        {notes_html}
        <br>
        <a href="{url_for('auth.new_note')}">Add another note</a>
    """