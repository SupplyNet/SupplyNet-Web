from sn_app.app import db
from flask_login import UserMixin
from datetime import datetime, timezone
import uuid
from sqlalchemy import JSON

class Truck(db.Model):
    __tablename__ = "trucks"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    registration_number = db.Column(db.String(50), unique=True, nullable=False)
    transporter_id = db.Column(db.String(50), nullable=True)
    
    truck_type = db.Column(db.String(50), nullable=True)      # e.g. Container 20ft, Box Truck
    capacity_tons = db.Column(db.Numeric(8, 2), nullable=True)  # Added capacity in tons
    vehicle_category = db.Column(db.String(50), nullable=True)
    body_type = db.Column(db.String(50), nullable=True)
    
    gvw_kg = db.Column(db.Numeric(10, 2), nullable=True)
    axle_count = db.Column(db.Integer, nullable=True)
    length_m = db.Column(db.Numeric(6, 2), nullable=True)
    width_m = db.Column(db.Numeric(6, 2), nullable=True)
    height_m = db.Column(db.Numeric(6, 2), nullable=True)
    active = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    shipments = db.relationship("Shipment", backref="truck", lazy=True)
    gps_updates = db.relationship("GPSUpdate", backref="truck", lazy=True, cascade="all, delete-orphan")


# ----------------------------------------------------------------------
# 3. SHIPMENT MODEL
# ----------------------------------------------------------------------
class Shipment(db.Model):
    __tablename__ = "shipments"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    truck_id = db.Column(db.String(36), db.ForeignKey("trucks.id", ondelete="SET NULL"), nullable=True)

    # Cargo Specific Details
    cargo_type = db.Column(db.String(100), nullable=True)
    total_weight_kg = db.Column(db.Numeric(10, 2), nullable=True)

    # Origin & Destination Coordinates & Postal Codes
    origin_lat = db.Column(db.Numeric(10, 7), nullable=False)
    origin_lon = db.Column(db.Numeric(10, 7), nullable=False)
    destination_lat = db.Column(db.Numeric(10, 7), nullable=False)
    destination_lon = db.Column(db.Numeric(10, 7), nullable=False)
    origin_pin = db.Column(db.String(20), nullable=True)
    destination_pin = db.Column(db.String(20), nullable=True)

    planned_eta = db.Column(db.DateTime, nullable=True)
    priority = db.Column(db.String(50), default="MEDIUM")
    status = db.Column(db.String(50), default="CREATED")  # CREATED, EN_ROUTE, DELAYED, REROUTED, DELIVERED

    consignment_value = db.Column(db.Numeric(12, 2), nullable=True)
    currency = db.Column(db.String(10), default="INR")

    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    cargo_documents = db.relationship("CargoDocument", backref="shipment", cascade="all, delete-orphan", uselist=False)
    routes = db.relationship("Route", backref="shipment", lazy=True, cascade="all, delete-orphan")
    gps_updates = db.relationship("GPSUpdate", backref="shipment", lazy=True, cascade="all, delete-orphan")
    checkpoints = db.relationship("TripCityCheckpoint", backref="shipment", lazy=True, cascade="all, delete-orphan")
    reroute_logs = db.relationship("RerouteLog", backref="shipment", lazy=True, cascade="all, delete-orphan")


# ----------------------------------------------------------------------
# 4. CARGO DOCUMENTATION MODEL
# ----------------------------------------------------------------------
class CargoDocument(db.Model):
    __tablename__ = "cargo_documents"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    shipment_id = db.Column(db.String(36), db.ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False)

    supplier_gstin = db.Column(db.String(20), nullable=True)
    recipient_gstin = db.Column(db.String(20), nullable=True)

    invoice_number = db.Column(db.String(50), nullable=True)
    invoice_date = db.Column(db.Date, nullable=True)

    challan_number = db.Column(db.String(50), nullable=True)
    challan_date = db.Column(db.Date, nullable=True)

    hsn_code = db.Column(db.String(20), nullable=True)
    consignment_value = db.Column(db.Numeric(12, 2), nullable=True)

    transporter_doc_no = db.Column(db.String(50), nullable=True)
    bill_of_lading_no = db.Column(db.String(50), nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


# ----------------------------------------------------------------------
# 5. OSRM ACTIVE / ALTERNATE ROUTES MODEL
# ----------------------------------------------------------------------
class Route(db.Model):
    __tablename__ = "routes"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    shipment_id = db.Column(db.String(36), db.ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False)

    route_type = db.Column(db.String(50), default="PRIMARY")  # PRIMARY, DETOUR, ALTERNATE
    is_active = db.Column(db.Boolean, default=True)

    origin_lat = db.Column(db.Numeric(10, 7), nullable=False)
    origin_lon = db.Column(db.Numeric(10, 7), nullable=False)
    destination_lat = db.Column(db.Numeric(10, 7), nullable=False)
    destination_lon = db.Column(db.Numeric(10, 7), nullable=False)

    distance_km = db.Column(db.Numeric(10, 2), nullable=True)
    duration_minutes = db.Column(db.Numeric(10, 2), nullable=True)

    # Added Optimization & Cost Metrics (From attached spec)
    fuel_cost = db.Column(db.Numeric(10, 2), nullable=True)
    toll_cost = db.Column(db.Numeric(10, 2), nullable=True)
    road_risk_score = db.Column(db.Numeric(5, 4), nullable=True)
    weather_risk_score = db.Column(db.Numeric(5, 4), nullable=True)
    optimization_score = db.Column(db.Numeric(10, 4), nullable=True)  # J(r) value

    geometry = db.Column(db.JSON, nullable=True)  # Detailed GeoJSON coordinate array
    routing_provider = db.Column(db.String(50), default="OSRM")

    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

# ----------------------------------------------------------------------
# 6. TRIP CITY CHECKPOINTS (For City-to-City Detour Routing)
# ----------------------------------------------------------------------
class TripCityCheckpoint(db.Model):
    """
    Stores sequential nodes (cities/junctions) for dynamic micro-rerouting.
    e.g., Chandigarh -> Agra -> Gwalior -> Jhansi -> Visakhapatnam.
    """
    __tablename__ = "trip_city_checkpoints"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    shipment_id = db.Column(db.String(36), db.ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False)

    sequence_order = db.Column(db.Integer, nullable=False)  # 1, 2, 3...
    city_name = db.Column(db.String(100), nullable=False)
    latitude = db.Column(db.Numeric(10, 7), nullable=False)
    longitude = db.Column(db.Numeric(10, 7), nullable=False)

    status = db.Column(db.String(20), default="PENDING")  # PENDING, PASSED, BYPASSED


# ----------------------------------------------------------------------
# 7. HIGH-FREQUENCY GPS TRACKING MODEL
# ----------------------------------------------------------------------
class GPSUpdate(db.Model):
    __tablename__ = "gps_updates"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    shipment_id = db.Column(db.String(36), db.ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False)
    truck_id = db.Column(db.String(36), db.ForeignKey("trucks.id", ondelete="SET NULL"), nullable=True)

    latitude = db.Column(db.Numeric(10, 7), nullable=False)
    longitude = db.Column(db.Numeric(10, 7), nullable=False)

    speed_kmph = db.Column(db.Numeric(5, 2), nullable=True)
    heading = db.Column(db.Numeric(5, 2), nullable=True)

    timestamp = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    source = db.Column(db.String(50), default="TELEMATICS")


# ----------------------------------------------------------------------
# 8. DISRUPTIONS MODEL (Weather, Protests, Accidents)
# ----------------------------------------------------------------------
class Disruption(db.Model):
    __tablename__ = "disruptions"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    type = db.Column(db.String(50), nullable=False)  # WEATHER, PROTEST, ROADBLOCK, ACCIDENT
    severity = db.Column(db.String(20), nullable=False)  # LOW, MEDIUM, HIGH, BLOCKING

    affected_city = db.Column(db.String(100), nullable=True)
    latitude = db.Column(db.Numeric(10, 7), nullable=False)
    longitude = db.Column(db.Numeric(10, 7), nullable=False)
    radius_km = db.Column(db.Numeric(6, 2), default=10.0)

    description = db.Column(db.Text, nullable=True)
    source = db.Column(db.String(50), nullable=True)
    source_reference = db.Column(db.String(255), nullable=True)

    start_time = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    expected_end_time = db.Column(db.DateTime, nullable=True)

    confidence_score = db.Column(db.Numeric(3, 2), default=1.0)
    status = db.Column(db.String(20), default="ACTIVE")  # ACTIVE, RESOLVED

    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# ----------------------------------------------------------------------
# 9. REROUTE AUDIT LOGS MODEL (LLM Decision Audit Trail)
# ----------------------------------------------------------------------
class RerouteLog(db.Model):
    """
    Records agentic decisions when bypassing disrupted cities/nodes.
    """
    __tablename__ = "reroute_logs"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    shipment_id = db.Column(db.String(36), db.ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False)
    disruption_id = db.Column(db.String(36), db.ForeignKey("disruptions.id", ondelete="SET NULL"), nullable=True)

    affected_city = db.Column(db.String(100), nullable=False)
    bypass_city = db.Column(db.String(100), nullable=False)
    llm_reasoning = db.Column(db.Text, nullable=False)

    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))