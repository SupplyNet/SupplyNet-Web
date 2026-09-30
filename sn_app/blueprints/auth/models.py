from sn_app.app import db
from flask_login import UserMixin

class Employee(db.Model, UserMixin):
    __tablename__ = 'employees'

    eid = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    
    # Relationship to Note
    notes = db.relationship('Note', backref='employee', lazy=True, cascade="all, delete-orphan")
    
    
    def get_id(self):
        return str(self.eid)

    def __repr__(self):
        return f"<Employee {self.username}>"
    
    
class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    date_created = db.Column(db.DateTime, default=db.func.current_timestamp())

    # Foreign key links note to its user
    user_id = db.Column(db.Integer, db.ForeignKey('employees.eid'), nullable=False)
 
 
    def __repr__(self):
        return f"<Note {self.id} for Employee {self.user_id}>"