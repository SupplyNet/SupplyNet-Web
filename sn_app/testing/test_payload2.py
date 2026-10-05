import json
from sn_app.app import create_app, db
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

app = create_app()

USER_ID = "17bf359a-e60c-4903-8af3-e17f57adf9c3"

agent_payload_input = {
    "shipment_id": "amaravati-mumbai-1",
    "status": "PARTIAL",
    "selected_route": {
        "distance_km": 987,
        "duration_minutes": 908,
        "fuel_cost": 29609,
        "toll_cost": 0,
        "road_risk_score": 1.0,
        "weather_risk_score": 1.0,
        "objective_j_score": 6.27,
        "geometry": {
            "type": "LineString",
            "coordinates": [
                [80.516, 16.5131], [80.5711, 16.5551], [80.2239, 16.8399],
                [79.7662, 17.0981], [78.6545, 17.3168], [78.6697, 17.4743],
                [78.5944, 17.5787], [78.2361, 17.536], [76.4937, 17.8663],
                [75.8928, 17.686], [74.5735, 18.3869], [73.8542, 18.5014],
                [73.6254, 18.7475], [73.3516, 18.7622], [73.0776, 19.0379],
                [72.8777, 19.076]
            ]
        }
    },
    "checkpoints": [
        {"order": 1, "city_name": "Amaravati (Origin)", "lat": 16.5131, "lon": 80.516},
        {"order": 2, "city_name": "Mumbai (Destination)", "lat": 19.076, "lon": 72.8777}
    ]
}


def parse_float(val, default=0.0):
    """Safely converts input value to float."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def ingest_agent_response(payload: dict, user_id: str) -> dict:
    with app.app_context():
        print("\n==================================================")
        print("--- INITIATING AGENT PAYLOAD INGESTION & DB PIPELINE ---")
        print("==================================================")
        
        if not isinstance(payload, dict):
            print("❌ Invalid Payload: Expected a JSON/Dict response.")
            return {"success": False, "error": "Payload must be a dictionary"}

        try:
            sel_route = payload.get('selected_route', {})
            checkpoints_data = payload.get('checkpoints', [])

            # Step 1: Safely derive origin and destination coordinates
            origin_lat, origin_lon = None, None
            dest_lat, dest_lon = None, None

            # Primary Extraction: From checkpoints array
            if checkpoints_data:
                first_cp = checkpoints_data[0]
                last_cp = checkpoints_data[-1]
                origin_lat = parse_float(first_cp.get('lat'))
                origin_lon = parse_float(first_cp.get('lon'))
                dest_lat = parse_float(last_cp.get('lat'))
                dest_lon = parse_float(last_cp.get('lon'))

            # Fallback Extraction: From geometry coordinates [lon, lat]
            geometry_obj = sel_route.get('geometry')
            if isinstance(geometry_obj, dict) and geometry_obj.get('coordinates'):
                coords = geometry_obj['coordinates']
                if coords:
                    if origin_lat is None or origin_lon is None:
                        origin_lon, origin_lat = parse_float(coords[0][0]), parse_float(coords[0][1])
                    if dest_lat is None or dest_lon is None:
                        dest_lon, dest_lat = parse_float(coords[-1][0]), parse_float(coords[-1][1])

            # Step 2: Format geometry string properly (avoid double JSON serialization)
            formatted_geometry = (
                json.dumps(geometry_obj) 
                if isinstance(geometry_obj, dict) 
                else geometry_obj
            )

            # Step 3: Instantiate Route with required coordinate parameters
            route = Route(
                origin_lat=origin_lat,
                origin_lon=origin_lon,
                destination_lat=dest_lat,
                destination_lon=dest_lon,
                distance_km=parse_float(sel_route.get('distance_km')),
                duration_minutes=parse_float(sel_route.get('duration_minutes')),
                fuel_cost=parse_float(sel_route.get('fuel_cost')),
                toll_cost=parse_float(sel_route.get('toll_cost')),
                road_risk_score=parse_float(sel_route.get('road_risk_score')),
                weather_risk_score=parse_float(sel_route.get('weather_risk_score')),
                optimization_score=parse_float(sel_route.get('objective_j_score')),
                geometry=formatted_geometry
            )

            # Assign dynamic optional fields if defined on model
            if hasattr(Route, 'user_id'):
                setattr(route, 'user_id', user_id)
            if hasattr(Route, 'shipment_id') and payload.get('shipment_id'):
                setattr(route, 'shipment_id', payload.get('shipment_id'))

            db.session.add(route)
            db.session.flush()
            
            print(f"✅ Route Model Saved to DB (ID: {route.id})")
            print(f"   • Origin: ({origin_lat}, {origin_lon})")
            print(f"   • Destination: ({dest_lat}, {dest_lon})")

            # Step 4: Instantiate Checkpoints linked to route
            created_checkpoints = []
            for cp in checkpoints_data:
                checkpoint_kwargs = {
                    "route_id": route.id,
                    "sequence_order": cp.get('order', 1),
                    "city_name": cp.get('city_name', 'Unknown'),
                    "latitude": parse_float(cp.get('lat')),
                    "longitude": parse_float(cp.get('lon')),
                    "status": 'PENDING'
                }
                
                if hasattr(TripCityCheckpoint, 'user_id'):
                    checkpoint_kwargs['user_id'] = user_id

                checkpoint = TripCityCheckpoint(**checkpoint_kwargs)
                db.session.add(checkpoint)
                created_checkpoints.append(checkpoint)

            print(f"✅ {len(created_checkpoints)} Checkpoints Saved to DB")

            # Step 5: Commit transaction
            db.session.commit()

            print("\n--- DB INSERTION VERIFICATION READOUT ---")
            print(f"• Saved Route Primary Key: {route.id}")
            print(f"• Total Distance: {route.distance_km} km")
            print(f"• Total Fuel Cost: ₹{route.fuel_cost}")
            if created_checkpoints:
                print(f"• Checkpoint 1: {created_checkpoints[0].city_name}")
                print(f"• Checkpoint 2: {created_checkpoints[-1].city_name}")
            print("\n🚀 SUCCESS: Data verified and committed to MySQL!")

            return {
                "success": True,
                "route_id": route.id,
                "checkpoints_count": len(created_checkpoints)
            }

        except Exception as e:
            db.session.rollback()
            print(f"\n❌ DB TRANSACTION FAILED & ROLLED BACK: {e}")
            return {"success": False, "error": str(e)}


if __name__ == '__main__':
    result = ingest_agent_response(payload=agent_payload_input, user_id=USER_ID)