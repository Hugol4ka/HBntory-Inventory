from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from models import Base, Branch, User, Stock
import bcrypt
from datetime import datetime


# Connection
engine = create_engine("sqlite:///hbntory.db")
Base.metadata.create_all(engine)

# Hash password
password = "admin123"
hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
hash = hash.decode('utf-8') 

# User creation
admin = User(
    username="admin",
    role="admin",
    created_at=datetime.now(),
    updated_at=datetime.now(),
    password_hash=hash
)

# Create a session and add the admin user to the database
session = Session(engine)
session.add(admin)
session.commit()