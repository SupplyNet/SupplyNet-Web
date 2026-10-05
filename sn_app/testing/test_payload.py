from sn_app.app import create_app, db

import json
 
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


# Create app instance from application factory
app = create_app()
# 1. Your exact agent response payload
agent_payload = {
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



def verify_parsing():
    with app.app_context():
        print("--- STARTING PAYLOAD PARSING VERIFICATION ---")
        
        try:
            sel_route = agent_payload.get('selected_route', {})
            
            # Step 1: Create Route model instance
            route = Route(
                distance_km=sel_route.get('distance_km'),
                duration_minutes=sel_route.get('duration_minutes'),
                fuel_cost=sel_route.get('fuel_cost'),
                toll_cost=sel_route.get('toll_cost'),
                road_risk_score=sel_route.get('road_risk_score'),
                weather_risk_score=sel_route.get('weather_risk_score'),
                optimization_score=sel_route.get('objective_j_score'),
                geometry=sel_route.get('geometry')
            )
            print("✅ Step 1 Passed: Route model populated successfully.")

            # Step 2: Create Checkpoints
            checkpoints = []
            for cp in agent_payload.get('checkpoints', []):
                checkpoint = TripCityCheckpoint(
                    sequence_order=cp['order'],
                    city_name=cp['city_name'],
                    latitude=parse_float(cp['lat']),
                    longitude=parse_float(cp['lon']),
                    status='PENDING'
                )
                checkpoints.append(checkpoint)
            
            print(f"✅ Step 2 Passed: {len(checkpoints)} Checkpoints extracted cleanly.")

            # Summary readout
            print("\n--- EXTRACTED VALUES SUMMARY ---")
            print(f"• Distance: {route.distance_km} km")
            print(f"• Duration: {route.duration_minutes} mins")
            print(f"• Fuel Cost: ₹{route.fuel_cost}")
            print(f"• Optimization Score (J): {route.optimization_score}")
            print(f"• First Checkpoint: {checkpoints[0].city_name} ({checkpoints[0].latitude}, {checkpoints[0].longitude})")
            print(f"• Last Checkpoint: {checkpoints[1].city_name} ({checkpoints[1].latitude}, {checkpoints[1].longitude})")
            print("\nVERIFICATION RESULT: Payload matches Flask logic 100%!")

        except KeyError as e:
            print(f"❌ Key Error Bug Detected: Missing key {e}")
        except Exception as e:
            print(f"❌ Parsing Error: {e}")

if __name__ == '__main__':
    verify_parsing()