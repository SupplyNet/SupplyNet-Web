# blueprintapp/extensions.py 

from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager

# Initialize extensions without passing the 'app' yet
db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()