from flask import session as flask_session
from functools import wraps
from flask import url_for, redirect

def login_required(fonction):
    @wraps(fonction)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in flask_session:
            return redirect(url_for("login"))
        return fonction(*args, **kwargs)
    return decorated_function