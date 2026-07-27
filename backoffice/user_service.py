import bcrypt
from datetime import datetime
from models import User, Branch


def hash_password(plain_password):
    """Hash a plain-text password with bcrypt."""
    hashed = bcrypt.hashpw(plain_password.encode('utf-8'), bcrypt.gensalt())
    return hashed.decode('utf-8')


def list_users(session):
    """Return all users."""
    return session.query(User).all()


def create_common_user(session, username, plain_password, branch_id):
    """Create a new common user assigned to a branch."""
    if not username or not plain_password:
        raise ValueError("Username and password are required.")

    existing = session.query(User).filter_by(username=username).first()
    if existing:
        raise ValueError(f"Username '{username}' is already taken.")

    branch = session.query(Branch).filter_by(id=branch_id).first()
    if not branch:
        raise ValueError(f"Branch {branch_id} does not exist.")

    user = User(
        username=username,
        password_hash=hash_password(plain_password),
        role="common_user",
        branch_id=branch_id,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    session.add(user)
    session.commit()
    return user


def soft_delete_user(session, user_id):
    """Deactivate a user without deleting the record."""
    user = session.query(User).filter_by(id=user_id).first()
    if not user:
        raise ValueError(f"User {user_id} not found.")
    if user.role == "admin":
        raise ValueError("The admin account cannot be deleted.")
    user.is_active = False
    user.updated_at = datetime.now()
    session.commit()
    return user


def change_user_password(session, user_id, new_plain_password):
    """Change a user's password."""
    user = session.query(User).filter_by(id=user_id).first()
    if not user:
        raise ValueError(f"User {user_id} not found.")
    if not new_plain_password:
            raise ValueError("New password cannot be empty.")
    user.password_hash = hash_password(new_plain_password)
    user.updated_at = datetime.now()
    session.commit()
    return user


def change_user_branch(session, user_id, new_branch_id):
    """Change a user's assigned branch."""
    user = session.query(User).filter_by(id=user_id).first()
    if not user:
        raise ValueError(f"User {user_id} not found.")
    branch = session.query(Branch).filter_by(id=new_branch_id).first()
    if not branch:
        raise ValueError(f"Branch {new_branch_id} does not exist.")
    user.branch_id = new_branch_id
    user.updated_at = datetime.now()
    session.commit()
    return user