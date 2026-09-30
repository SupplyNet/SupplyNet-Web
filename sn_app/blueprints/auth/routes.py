from flask import request, render_template, redirect, url_for, Blueprint, flash
from flask_login import login_user, logout_user, current_user, login_required
import os
from sn_app.app import db, bcrypt
from sn_app.blueprints.auth.models import Employee, Note

auth = Blueprint('auth', __name__, template_folder='templates')


@auth.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('auth.dashboard'))
    return render_template('auth/index.html')


# You can set this in your app config or environment variables (e.g., SECRET_COMPANY_CODE="KATARIA2026")
REQUIRED_COMPANY_CODE = os.environ.get('COMPANY_SIGNUP_CODE', 'KATARIA2026')

@auth.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'GET':
        return render_template('auth/signup.html')

    company_code = request.form.get('company_code')
    username = request.form.get('username')
    password = request.form.get('password')
    full_name = request.form.get('full_name', username)

    # 1. Validate Company Code
    if not company_code or company_code != REQUIRED_COMPANY_CODE:
        flash('Invalid Company Passcode. Registration restricted.', 'danger')
        return redirect(url_for('auth.signup'))

    # 2. Check for existing employee username
    if Employee.query.filter_by(username=username).first():
        flash('Username already exists. Please choose another.', 'danger')
        return redirect(url_for('auth.signup'))

    # 3. Hash password and save new employee record
    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
    new_employee = Employee(
        username=username,
        password_hash=hashed_password,
        full_name=full_name
    )

    db.session.add(new_employee)
    db.session.commit()

    flash('Account created successfully! Please log in.', 'success')
    return redirect(url_for('auth.login'))

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('auth/login.html')

    username = request.form.get('username')
    password = request.form.get('password')

    employee = Employee.query.filter_by(username=username).first()

    # Validate against password_hash column
    if employee and bcrypt.check_password_hash(employee.password_hash, password):
        login_user(employee)
        flash(f'Welcome back, {employee.full_name}!', 'success')
        return redirect(url_for('auth.dashboard'))

    flash('Invalid username or password', 'danger')
    return redirect(url_for('auth.login'))


@auth.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('auth.login'))


@auth.route('/dashboard')
@login_required
def dashboard():
    return render_template('auth/dashboard.html')


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