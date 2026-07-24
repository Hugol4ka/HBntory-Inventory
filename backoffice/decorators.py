from flask import session as flask_session
from functools import wraps
from flask import url_for, redirect
from models import User
from sqlalchemy.orm import Session
from database import engine
from flask import abort

def login_required(fonction):
    @wraps(fonction)
    def decorated_function(*args, **kwargs):
        with Session(engine) as session:
            if 'user_id' not in flask_session:
                return redirect(url_for("login"))
            user_id = flask_session.get('user_id')
            user = session.query(User).filter_by(id=user_id).first()
            if not user or not user.is_active:
                return redirect(url_for("login"))
        return fonction(*args, **kwargs)
    return decorated_function


def admin_required(fonction):
    @wraps(fonction)
    def decorated_function(*args, **kwargs):
        with Session(engine) as session:
            if 'user_id' not in flask_session:
                return redirect(url_for("login"))
            user_id = flask_session.get('user_id')
            user = session.query(User).filter_by(id=user_id).first()
        if not user or user.role != 'admin' or not user.is_active:
                return abort(403)
        return fonction(*args, **kwargs)
    return decorated_function   


def common_user_required(fonction):
    @wraps(fonction)
    def decorated_function(*args, **kwargs):
        with Session(engine) as session:
            if 'user_id' not in flask_session:
                return redirect(url_for("login"))
            user_id = flask_session.get('user_id')
            user = session.query(User).filter_by(id=user_id).first()
        if not user or user.role != 'common_user' or not user.is_active:
                return abort(403)
        return fonction(*args, **kwargs)
    return decorated_function