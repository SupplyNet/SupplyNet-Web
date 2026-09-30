# blueprintapp/__init__.py 

from flask import Flask
from extensions import db, bcrypt, login_manager # 1. Import uninitialized extensions
from flask_migrate import Migrate

def create_app():
    app = Flask(__name__, instance_relative_config=True) 
    
    # 2. Configuration (use a config class for complex apps)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///./blueprints.db'
    app.config['SECRET_KEY'] = 'a-super-secret-key' # Needed for Flask-Login/sessions
    
    # 3. Initialize/Connect extensions with the app instance
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'users.login' # Set the default login route

    # 4. Import the User model *after* db and login_manager are initialized
    # You should generally define a User model file at a place accessible by both
    from sn_app.blueprints.users.models import User
    
    @login_manager.user_loader
    def load_user(uid):
        # The User model uses the 'db' object which is now initialized
        return User.query.get(uid)

    # 5. Import and register Blueprints
    # Importing routes here is a common way to register the blueprints.
    from sn_app.blueprints.core.routes import core
    from sn_app.blueprints.todos.routes import todos
    from sn_app.blueprints.people.routes import people
    from sn_app.blueprints.users.routes import users
    
    # Register blueprints (bcrypt is NOT passed here)
    app.register_blueprint(core, url_prefix='/')
    app.register_blueprint(todos, url_prefix='/todos')
    app.register_blueprint(people, url_prefix='/people')
    app.register_blueprint(users, url_prefix='/users') # CORRECTED: Removed bcrypt argument
    
    # 6. Initialize Migrate after db is connected and models are imported
    Migrate(app, db) # No need to store in a variable if not used further
    
    return app