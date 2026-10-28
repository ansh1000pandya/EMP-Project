from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User, ExaminerProfile
from werkzeug.security import generate_password_hash

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('admin.dashboard'))
        elif current_user.role == 'examiner':
            return redirect(url_for('examiner.dashboard'))
        elif current_user.role == 'student':
            return redirect(url_for('student.dashboard'))
    return redirect(url_for('auth.login'))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('auth.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            # Extra check for examiners
            if user.role == 'examiner':
                profile = user.examiner_profile
                if profile is None or profile.status != 'Approved':
                    flash('Your examiner account is pending Admin approval or has been deactivated.', 'warning')
                    return render_template('auth/login.html')

            login_user(user)
            flash(f'Welcome, {user.full_name}!', 'success')
            return redirect(url_for('auth.index'))
        else:
            flash('Invalid username or password.', 'danger')

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Only Examiner and Student can register. Admin is pre-seeded."""
    if current_user.is_authenticated:
        return redirect(url_for('auth.index'))

    if request.method == 'POST':
        username  = request.form.get('username', '').strip()
        email     = request.form.get('email', '').strip()
        full_name = request.form.get('full_name', '').strip()
        password  = request.form.get('password', '')
        role      = request.form.get('role', '')
        department = request.form.get('department', '').strip()
        contact    = request.form.get('contact', '').strip()

        # Basic validation
        if not all([username, email, full_name, password, role]):
            flash('All fields are required.', 'danger')
            return render_template('auth/register.html')

        if role not in ('examiner', 'student'):
            flash('Invalid role selected.', 'danger')
            return render_template('auth/register.html')

        if User.query.filter_by(username=username).first():
            flash('Username already taken.', 'danger')
            return render_template('auth/register.html')

        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return render_template('auth/register.html')

        # Create user
        user = User(
            username=username,
            email=email,
            full_name=full_name,
            role=role
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()   # get user.id before commit

        # If examiner → create pending profile
        if role == 'examiner':
            profile = ExaminerProfile(
                user_id=user.id,
                department=department or None,
                contact=contact or None,
                status='Pending'
            )
            db.session.add(profile)

        db.session.commit()
        flash('Registration successful! Please log in.' +
              (' (Examiner accounts need Admin approval.)' if role == 'examiner' else ''),
              'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')