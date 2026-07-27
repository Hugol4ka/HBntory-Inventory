from database import engine
from sqlalchemy.orm import Session
from models import Base, Branch, User, Stock
import bcrypt
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

password = os.getenv("ADMIN_PASSWORD")
if not password:
    raise ValueError("ADMIN_PASSWORD environment variable is not set.")


Base.metadata.create_all(engine)
session = Session(engine)

# --- Admin ---
admin = session.query(User).filter_by(username="admin").first()
if not admin:
    password = os.getenv("ADMIN_PASSWORD")
    hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    admin = User(username="admin", role="admin", password_hash=hash,
                 created_at=datetime.now(), updated_at=datetime.now())
    session.add(admin)
    session.commit()
    print("Admin created.")
else:
    print("Admin already exists, skipping.")

# --- Succursales ---
branches = ["North Branch", "South Branch"]
branch_objects = {}

for branch_name in branches:
    branch = session.query(Branch).filter_by(name=branch_name).first()
    if not branch:
        branch = Branch(name=branch_name, created_at=datetime.now(), updated_at=datetime.now())
        session.add(branch)
        session.commit()
        print(f"Branch created: {branch_name}")
    else:
        print(f"Branch already exists: {branch_name}")

    branch_objects[branch_name] = branch

# --- Stock ---

stock_items = [
    {"id_product": "HB-LAP-1001", "branch_name": "North Branch", "quantity": 100},
    {"id_product": "HB-KBD-4102", "branch_name": "South Branch", "quantity": 50},
    {"id_product": "HB-LAP-1001", "branch_name": "South Branch", "quantity": 30},
    {"id_product": "HB-SSD-7101", "branch_name": "North Branch", "quantity": 20}
]

for item_data in stock_items:
    branch_id = branch_objects[item_data["branch_name"]].id
    stock = session.query(Stock).filter_by(
        id_product=item_data["id_product"],
        id_branch=branch_id,
    ).first()
    if not stock:
        stock = Stock(
            id_product=item_data["id_product"],
            id_branch=branch_id,
            quantity=item_data["quantity"],
        )
        session.add(stock)
        session.commit()
        print(f"Stock item created: {item_data}")
    else:
        print(f"Stock item already exists: {item_data}")