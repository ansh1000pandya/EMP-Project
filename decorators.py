from functools import wraps
from flask import abort, flash, redirect, url_for
from flask_login import current_user

def role_required(*roles):
    """Decorator: only users with one of the given roles can access the route."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            if current_user.role not in roles:
                abort(403)          # Forbidden
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def approved_examiner_required(f):
    """Decorator: examiner must be Approved (not Pending or Deactivated)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if current_user.role != 'examiner':
            abort(403)
        profile = current_user.examiner_profile
        if profile is None or profile.status != 'Approved':
            flash('Your examiner account is not yet approved by Admin.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function