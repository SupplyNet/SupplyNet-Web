from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
import os
from dotenv import load_dotenv
from urllib.parse import quote_plus

load_dotenv()

db = SQLAlchemy()
login_manager = LoginManager() 
bcrypt = Bcrypt()

def create_app():
    app = Flask(__name__, template_folder='templates')
    db_password = quote_plus(os.getenv("DB_PASSWORD", ""))
    app.config['SQLALCHEMY_DATABASE_URI'] = (
    f'mysql+pymysql://avnadmin:{db_password}'
    f'@mysql-385dcef2-priyamjainofficial-5a14.a.aivencloud.com:25845/sndb')
    app.config['SECRET_KEY'] = 'some-secret-key'
    
    db.init_app(app)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    
    #import and register all blueprints
    from sn_app.blueprints.core.routes import core
    from sn_app.blueprints.auth.routes import auth
    
    from sn_app.blueprints.auth.models import User
    from sn_app.blueprints.auth.models import Note
    
    @login_manager.user_loader
    def load_user(eid):
        return User.query.get(eid)
    

    app.register_blueprint(core, url_prefix='/')
    #app.register_blueprint(todos, url_prefix='/todos')
    #app.register_blueprint(people, url_prefix='/people')
    app.register_blueprint(auth, url_prefix='/auth')
    
    migrate = Migrate(app,db)
    
    return app
    