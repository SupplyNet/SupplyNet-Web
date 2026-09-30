from flask import request, render_template, redirect, url_for, Blueprint, flash
from flask_login import login_user, logout_user, current_user, login_required
import os
from sn_app.app import db, bcrypt
from sn_app.blueprints.auth.models import   User, Note

auth = Blueprint('auth', __name__, template_folder='templates')


@auth.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('auth.dashboard'))
    return render_template('auth/index.html')


# You can set this in your app config or environment variables (e.g., SECRET_COMPANY_CODE="KATARIA2026")


@auth.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        return render_template("auth/signup.html")

    enterprise_name = request.form.get("enterprise_name")
    email = request.form.get("email")
    password = request.form.get("password")
    name = request.form.get("name")
    role = request.form.get("role", "employee")  # Default role if not provided

    # 1. Basic validation for required fields
    if not email or not password or not name:
        flash("Please fill in all required fields.", "danger")
        return redirect(url_for("auth.signup"))

    # 2. Check for existing user by email
    if User.query.filter_by(email=email.lower().strip()).first():
        flash("Email is already registered. Please log in or use another email.", "danger")
        return redirect(url_for("auth.signup"))

    # 3. Hash password and save new user record
    hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")
    new_user = User(
        name=name,
        email=email.lower().strip(),
        password_hash=hashed_password,
        role=role,
        enterprise_name=enterprise_name,
    )

    db.session.add(new_user)
    db.session.commit()

    flash("Account created successfully! Please log in.", "success")
    return redirect(url_for("auth.login"))

@auth.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("auth/login.html")

    email = request.form.get("email")
    password = request.form.get("password")

    # Basic input check
    if not email or not password:
        flash("Please enter both email and password.", "danger")
        return redirect(url_for("auth.login"))

    # Fetch user by email (normalized to lowercase)
    user = User.query.filter_by(email=email.lower().strip()).first()

    # Validate user credentials
    if user and bcrypt.check_password_hash(user.password_hash, password):
        login_user(user)
        flash(f"Welcome back, {user.name}!", "success")
        return redirect(url_for("auth.dashboard"))

    # Generic error message to prevent email enumeration
    flash("Invalid email or password.", "danger")
    return redirect(url_for("auth.login"))

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