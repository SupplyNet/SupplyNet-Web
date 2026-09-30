import os
from dotenv import load_dotenv
from urllib.parse import quote_plus
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_bcrypt import Bcrypt

load_dotenv()

db = SQLAlchemy()
login_manager = LoginManager() 
bcrypt = Bcrypt()

def create_app():
    app = Flask(__name__, template_folder='templates')
    
    db_password = quote_plus(os.getenv("DB_PASSWORD", ""))
    app.config['SQLALCHEMY_DATABASE_URI'] = (
        f'mysql+pymysql://avnadmin:{db_password}'
        f'@mysql-385dcef2-priyamjainofficial-5a14.a.aivencloud.com:25845/sndb'
    )
    app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "some-secret-key")
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Initialize extensions with app context
    db.init_app(app)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    
    # ------------------------------------------------------------------
    # Import models for Flask-Migrate tracking
    # ------------------------------------------------------------------
    from sn_app.blueprints.auth.models import User, Note
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

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, user_id)

    # ------------------------------------------------------------------
    # Import and register blueprints
    # ------------------------------------------------------------------
    from sn_app.blueprints.core.routes import core
    from sn_app.blueprints.auth.routes import auth
    from sn_app.blueprints.shipment.routes import shipment

    app.register_blueprint(core, url_prefix='/')
    app.register_blueprint(auth, url_prefix='/auth')
    app.register_blueprint(shipment, url_prefix='/shipment')

    # Initialize Flask-Migrate
    Migrate(app, db)
    
    return app