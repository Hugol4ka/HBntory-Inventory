from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from models import Base, Branch, User, Stock
import bcrypt
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

# Connection
engine = create_engine("sqlite:///hbntory.db")
Base.metadata.create_all(engine)

# Hash password
password = os.getenv("ADMIN_PASSWORD")
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

north_branch = Branch(
    name="North Branch",
    created_at=datetime.now(),
    updated_at=datetime.now()
)

south_branch = Branch(
    name="South Branch",
    created_at=datetime.now(),
    updated_at=datetime.now()
)

# Create a session and add the admin user to the database
session = Session(engine)
session.add(admin)
session.add(north_branch)
session.add(south_branch)
session.commit()

item1 = Stock(id_product="HB-LAP-1001", id_branch=north_branch.id, quantity=100)
item2 = Stock(id_product="HB-KBD-4102", id_branch=south_branch.id, quantity=50)
item3 = Stock(id_product="HB-LAP-1001", id_branch=south_branch.id, quantity=30)
item4 = Stock(id_product="HB-SSD-7101", id_branch=north_branch.id, quantity=20)

session.add(item1)
session.add(item2)
session.add(item3)
session.add(item4)
session.commit()