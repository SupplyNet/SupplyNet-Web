# SupplyNet: Telematics GPS Simulation & Shipment Architecture Guide

This document explains the end-to-end architecture of SupplyNet's real-world GPS telematics simulation, multi-objective route optimization, Flask blueprint orchestration, database synchronization, and Google Maps live tracking UI.

---

## 📑 Table of Contents
1. [High-Level Architecture & Data Flow](#1-high-level-architecture--data-flow)
2. [FastAPI Simulation & Optimization Engine (`main3.py`)](#2-fastapi-simulation--optimization-engine-main3py)
3. [Flask Shipment Blueprint Routes (`routes.py`)](#3-flask-shipment-blueprint-routes-routespy)
4. [Database Models & Persistence (`models.py`)](#4-database-models--persistence-modelspy)
5. [Frontend Live Telematics UI (`shipment_detail.html`)](#5-frontend-live-telematics-ui-shipment_detailhtml)
6. [Simulation Lifecycle & State Transitions](#6-simulation-lifecycle--state-transitions)
7. [Server Switching: Local vs Vercel Cloud](#7-server-switching-local-vs-vercel-cloud)
8. [API Endpoint Reference](#8-api-endpoint-reference)

---

## 1. High-Level Architecture & Data Flow

```mermaid
graph TD
    User["Enterprise User / Logistics Dispatcher"]
    UI["Frontend: shipment_detail.html (Google Maps + Gauges)"]
    Flask["Flask App (sn_app / Port 5000)"]
    MySQL[("Aiven MySQL Database")]
    FastAPI["FastAPI Engine (main3.py or Vercel Cloud)"]

    User -->|1. Create Shipment| Flask
    Flask -->|2. POST /api/v1/optimize-route| FastAPI
    FastAPI -->|3. Route Geometry + Checkpoints| Flask
    Flask -->|4. Save Shipment, Route & Checkpoints| MySQL

    User -->|5. Click Start Live Transit| UI
    UI -->|6. POST /shipment/:id/start-transit| Flask
    Flask -->|7. POST /api/v1/simulations| FastAPI
    FastAPI -->|8. In-Memory Simulation Initialized| Flask
    Flask -->|9. Returns simulation_id| UI

    loop Every 2 Seconds (Live Telemetry Tick)
        UI -->|10. POST /shipment/:id/telemetry-tick| Flask
        Flask -->|11. POST /api/v1/simulations/:truck/tick| FastAPI
        FastAPI -->|12. Advance Lat, Lon, Bearing, Progress| Flask
        Flask -->|13. INSERT into gps_updates table| MySQL
        Flask -->|14. Returns Synchronized Telemetry JSON| UI
        UI -->|15. Rotate Truck Marker, Update Gauges & Polyline| User
    end

    FastAPI -.->|When Progress >= 100%| Flask
    Flask -->|Update Status: DELIVERED| MySQL
    UI -->|Display 'Shipment Delivered'| User
```

---

## 2. FastAPI Simulation & Optimization Engine (`main3.py`)

The FastAPI service operates as an autonomous, high-frequency telematics and logistics calculation agent. It simulates what physical on-vehicle GPS hardware (like Teltonika or Garmin black boxes) and routing engines do in real life.

### Key Responsibilities:
1. **Multi-Objective Route Optimization (`/api/v1/optimize-route`)**:
   - Calculates highway road distances and expected driving duration based on payload weight and national highway winding factors.
   - Computes commercial diesel consumption according to gross vehicle weight ($GVW$) and axle friction limits.
   - Calculates national highway toll fees based on axle count.
   - Computes dynamic safety risk scores and composite objective index $J(r) = \text{Cost} + \text{Time} + \text{Risk}$.
   - Constructs detailed GeoJSON `LineString` coordinate arrays.
   - Generates sequential corridor checkpoints (e.g. *Chandigarh* $\to$ *Delhi NCR* $\to$ *Agra* $\to$ *Gwalior* $\to$ *Jhansi* $\to$ *Nagpur* $\to$ *Raipur* $\to$ *Visakhapatnam*).

2. **Real-World GPS Telematics Physics (`GPSSimulation` class)**:
   - **Segmented Road Traversal**: Divides route geometry into individual segments and computes Haversine distances between all consecutive coordinates.
   - **Incremental Position Interpolation**: Computes $\Delta d = \text{speed} \times \Delta t$ and advances the vehicle continuously along the route line.
   - **True Compass Bearing / Heading**: Calculates the exact compass heading angle ($0^\circ - 360^\circ$ e.g., $170^\circ \text{ SSE}$) using spherical trigonometry:
     $$\theta = \text{atan2}(\sin \Delta \lambda \cos \phi_2, \cos \phi_1 \sin \phi_2 - \sin \phi_1 \cos \phi_2 \cos \Delta \lambda)$$
   - **Elevation / Altitude Profiling**: Linear altitude interpolation when 3D GPS data is provided.
   - **Dual Speed & Coordinate Convention**: Returns both `lat`/`lon` and `latitude`/`longitude`, and both `speed_kmh` and `speed_kmph` to guarantee zero-mismatch compatibility across relational databases and UI scripts.

3. **In-Memory & Persistent Caching (`RouteStore`)**:
   - Stores computed routes in `routes.json` with multi-key indexing (`route_id` and `shipment_id`).
   - Features **auto-revival**: if `uvicorn` reloads or the server restarts, queries to `_get_simulation` seamlessly re-instantiate the vehicle from persistent route cache rather than returning a 404 error.

---

## 3. Flask Shipment Blueprint Routes (`routes.py`)

Located at `sn_app/blueprints/shipment/routes.py`, this blueprint serves as the secure enterprise layer connecting the MySQL database, authenticated users, and the FastAPI simulation server.

### Key Route Handlers:

1. **`create_shipment` (`POST /shipment/create`)**:
   - Verifies the selected truck belongs to the authenticated user.
   - Creates the `Shipment` and `CargoDocument` records in MySQL.
   - Sends the cargo weight, truck constraints, and coordinates to FastAPI's `/api/v1/optimize-route`.
   - Saves the resulting GeoJSON geometry into the `routes` table as `PRIMARY` active route.
   - Generates and saves the sequential `trip_city_checkpoints` (`PENDING`).

2. **`get_shipment_detail` (`GET /shipment/<shipment_id>`)**:
   - Loads the shipment and its associated truck, active route, ordered checkpoints, and recent GPS updates.
   - Injects `fastapi_url` into the template context based on `FASTAPI_AGENT_URL`.

3. **`start_transit` (`POST /shipment/<shipment_id>/start-transit`)**:
   - Gathers the active route geometry and truck specifications.
   - Calls FastAPI `POST /api/v1/simulations`.
   - Transitions shipment status to `EN_ROUTE` in MySQL.
   - Returns the active `simulation_id`.
   - If the vehicle is already running (HTTP 409), automatically reconnects to the ongoing simulation without failing.

4. **`telemetry_tick` (`POST /shipment/<shipment_id>/telemetry-tick`)**:
   - **Backend Proxy & Sync Engine**: Acts as a reliable proxy between the frontend JavaScript and FastAPI.
   - Ticks the simulation forward by `advance_seconds`.
   - Auto-recovers the simulation if FastAPI restarted.
   - Persists a new row in the `gps_updates` table.
   - Monitors completion: when `route_progress_percent >= 100`, automatically updates `Shipment.status = 'DELIVERED'` in MySQL.

5. **`record_gps_update` (`POST /shipment/<shipment_id>/record-gps`)**:
   - Direct endpoint for telematics webhooks to insert GPS ping records (`latitude`, `longitude`, `speed_kmph`, `heading`, `source='FASTAPI_SIMULATOR'`).

---

## 4. Database Models & Persistence (`models.py`)

All models inherit from SQLAlchemy and are defined in `sn_app/blueprints/shipment/models.py`:

| Table Name | Model Class | Core Fields & Purpose |
| :--- | :--- | :--- |
| `trucks` | `Truck` | `id`, `registration_number`, `truck_type`, `capacity_tons`, `gvw_kg`, `axle_count`, `active` |
| `shipments` | `Shipment` | `id`, `user_id`, `truck_id`, `cargo_type`, `total_weight_kg`, `origin_lat/lon`, `destination_lat/lon`, `priority`, `status` (`CREATED`, `EN_ROUTE`, `DELIVERED`) |
| `cargo_documents` | `CargoDocument` | `supplier_gstin`, `recipient_gstin`, `invoice_number`, `hsn_code`, `consignment_value` |
| `routes` | `Route` | `shipment_id`, `route_type`, `is_active`, `distance_km`, `duration_minutes`, `fuel_cost`, `toll_cost`, `road_risk_score`, `weather_risk_score`, `optimization_score`, `geometry` (GeoJSON `LineString`) |
| `trip_city_checkpoints` | `TripCityCheckpoint` | `shipment_id`, `sequence_order`, `city_name`, `latitude`, `longitude`, `status` (`PENDING`, `PASSED`, `BYPASSED`) |
| `gps_updates` | `GPSUpdate` | `shipment_id`, `truck_id`, `latitude`, `longitude`, `speed_kmph`, `heading` (compass bearing), `timestamp`, `source` |
| `disruptions` | `Disruption` | Tracks real-world road blocks, weather disruptions, and protests for dynamic rerouting. |
| `reroute_logs` | `RerouteLog` | Audit log recording agentic reasoning when bypassing blocked cities. |

---

## 5. Frontend Live Telematics UI (`shipment_detail.html`)

The tracking page provides an interactive logistics cockpit:

### Map Visualization:
- **Google Maps Integration**: Direct integration with **Google Roads** and **Google Hybrid Satellite** tile layers, switchable via the map layer control in the top-right corner.
- **Dynamic Rotating Truck Marker**: Custom SVG commercial truck icon enclosed within an animated radar pulse ring. Rotates smoothly in real time to match the vehicle's compass bearing ($\theta$).
- **Dual Polyline Path**:
  - **Breadcrumbs Line (Emerald Green)**: Dynamically appends coordinates to draw the path already driven.
  - **Planned Line (Dashed Blue)**: Shows the remaining corridor to destination.
- **Controls**:
  - **Follow Truck**: Auto-centers and pans the map as the truck moves.
  - **Fit Route**: Zooms the viewport to fit the full corridor.

### Real-Time KPI Ribbon:
1. **Live Speed Gauge**: Shows current speed (km/h) with cruising state tags.
2. **Trip Progress**: Live percentage with an animated gradient shimmer bar.
3. **Distance Covered vs Remaining**: Shows exact kilometers completed and left.
4. **Dynamic ETA**: Automatically recalculates hours and minutes remaining based on speed and remaining distance.
5. **Compass & Heading**: Shows live degrees and 16-point cardinal direction (e.g. `170° SSE`) with a rotating needle dial.
6. **Fuel & Carbon Footprint**: Real-time liters of diesel burned and estimated kg of $\text{CO}_2$ emitted.

### Highway Waypoint Tracker:
- Sequential vertical timeline of all corridor cities.
- As the truck passes each city's latitude, the node automatically turns green (`PASSED`) and updates the remaining distance to the next approaching waypoint.

### Simulation Controls:
- **Speed Multiplier**: Choose between `1x`, `2x`, `5x`, or `10x` travel speed to simulate long cross-country journeys in seconds.
- **Pause / Resume**: Pause the simulation at any moment and resume.
- **Live Stream Terminal**: Rolling console log displaying the latest 15 GPS pings with timestamps, coordinates, and database confirmation.

---

## 6. Simulation Lifecycle & State Transitions

```
[ CREATED ]
    │
    ▼ (User clicks "🚀 Start Live Transit")
[ EN_ROUTE ] ────► Polling starts (/telemetry-tick every 2s)
    │                  │
    │                  ├──► Truck moves along polyline
    │                  ├──► Heading angle calculated (0° - 360°)
    │                  ├──► Passed checkpoints mark 'PASSED'
    │                  └──► New row inserted into 'gps_updates' table
    │
    ▼ (route_progress_percent >= 100%)
[ DELIVERED ] ───► Polling stops, status badge updates to blue 'DELIVERED'
```

---

## 7. Server Switching: Local vs Vercel Cloud

SupplyNet supports switching between local simulation (`http://localhost:8000`) and the cloud deployment (`https://testingserver-supplynet.vercel.app`) using a single environment variable:

### To Use the Vercel Cloud Server:
In `.env` (or `sn_app/.env`):
```ini
FASTAPI_AGENT_URL="https://testingserver-supplynet.vercel.app"
```

### To Use Local FastAPI Server:
In `.env`:
```ini
FASTAPI_AGENT_URL="http://localhost:8000"
```

*Note: Restarting `run.py` is not required for template rendering, but restarting ensures all backend background tasks pick up the new URL.*

---

## 8. API Endpoint Reference

### FastAPI Simulator (`main3.py`):
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Health check returning status and active simulation count. |
| `POST` | `/api/v1/optimize-route` | Computes distance, costs, risks, checkpoints, and GeoJSON geometry. |
| `POST` | `/api/v1/routes/register` | Syncs pre-computed routes from MySQL into FastAPI memory. |
| `POST` | `/api/v1/simulations` | Starts a GPS telematics simulation for a vehicle/truck ID. |
| `GET` | `/api/v1/simulations/{id}` | Fetches current snapshot state (coordinates, progress, speed). |
| `POST` | `/api/v1/simulations/{id}/tick` | Advances the simulation by `advance_seconds` (default: 30s). |
| `POST` | `/api/v1/simulations/{id}/pause` | Pauses the vehicle motion. |
| `POST` | `/api/v1/simulations/{id}/resume` | Resumes the vehicle motion. |
| `POST` | `/api/v1/simulations/{id}/stop` | Terminates simulation task. |
| `GET` | `/api/v1/simulations/{id}/history` | Returns breadcrumb history list of all GPS updates. |

### Flask Web Application (`sn_app`):
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/shipment/create` | Creates shipment, optimizes route, saves checkpoints in MySQL. |
| `GET` | `/shipment/<id>` | Renders the live telematics tracking dashboard. |
| `POST` | `/shipment/<id>/start-transit` | Calls FastAPI `/api/v1/simulations` and marks shipment `EN_ROUTE`. |
| `POST` | `/shipment/<id>/telemetry-tick` | Advances simulation, logs ping to MySQL, and checks for trip arrival. |
| `POST` | `/shipment/<id>/record-gps` | Records raw GPS updates from external telematics sources. |
| `POST` | `/shipment/<id>/reroute` | Triggered by disruption agent to bypass blocked cities. |
