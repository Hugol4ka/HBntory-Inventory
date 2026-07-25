from flask import Flask
from flask import session as flask_session
from sqlalchemy.orm import Session
from database import engine
from models import Base, Branch, User, Stock
import bcrypt
from flask import request
import os
from dotenv import load_dotenv
from decorators import login_required, admin_required, common_user_required
from stock_service import remove_stock, add_stock
from user_service import list_users, create_common_user, soft_delete_user, change_user_password, change_user_branch


load_dotenv()


app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY_FLASK")


@app.route("/login", methods=["GET", "POST"])
def login():
    '''
    Handle user login.'''
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        with Session(engine) as db_session:
            user = db_session.query(User).filter_by(username=username).first()
            if user and user.is_active and bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8')):
                flask_session['user_id'] = user.id
                return "Login successful!"
            else:
                return "Invalid username or password."
    return "Ici is the login page. Please submit your username and password via POST request."


@app.route("/stock", methods=["GET"])
@login_required
@common_user_required
def get_stock():
    '''
    Retrieve stock information for the logged-in user.'''
    with Session(engine) as db_session:
        user_id = flask_session.get('user_id')
        user = db_session.query(User).filter_by(id=user_id).first()
        if not user:
            return "User not found.", 404
        branch = db_session.query(Branch).filter_by(id=user.branch_id).first()
        if not branch:
            return "Branch not found.", 404
        stock_items = db_session.query(Stock).filter_by(id_branch=user.branch_id).all()
        stock_data = [{"id_product": item.id_product, "quantity": item.quantity} for item in stock_items]
        return {"branch": branch.name, "stock": stock_data}, 200


def get_quantity_of_product_in_branch(session, id_product, id_branch):
    """
    Get the quantity of a specific product in a specific branch.

    Args:
        session: The SQLAlchemy session to use for database operations.
        id_product: The ID of the product to check.
        id_branch: The ID of the branch to check.
    """
    stock_item = session.query(Stock).filter_by(id_product=id_product, id_branch=id_branch).first()
    return stock_item.quantity if stock_item else 0


@app.route("/stock/<id_product>", methods=["GET"])
@login_required
@common_user_required
def get_stock_in_branch(id_product):
    """
    Retrieve the quantity of a specific product in the logged-in user's branch.
    """
    with Session(engine) as db_session:
        user = db_session.query(User).filter_by(id=flask_session.get('user_id')).first()
        if not user:
            return "User not found.", 404
        quantity = get_quantity_of_product_in_branch(db_session, id_product, user.branch_id)
        return {"quantity": quantity}, 200


@app.route("/stock", methods=["POST"])
@login_required
@common_user_required
def add_stock_to_branch():
    """
    Add stock to the logged-in user's branch.
    """
    with Session(engine) as db_session:
        user = db_session.query(User).filter_by(id=flask_session.get('user_id')).first()
        if not user:
            return "User not found.", 404

        id_product = request.form.get("id_product")
        try:
            quantity = int(request.form.get("quantity"))
        except (ValueError, TypeError):
            return {"error": "Quantity must be a valid integer."}, 400
        try:
            stock_item = db_session.query(Stock).filter_by(id_product=id_product, id_branch=user.branch_id).first()

            if not stock_item:
                stock_item = Stock(id_product=id_product, id_branch=user.branch_id, quantity=0)
                db_session.add(stock_item)

            add_stock(db_session, stock_item, quantity)
            return {"message": f"Added {quantity} of product {id_product} to branch {user.branch_id}."}, 200
        except (ValueError, TypeError) as e:
            return {"error": str(e)}, 400


@app.route("/stock/remove", methods=["POST"])
@login_required
@common_user_required
def remove_stock_from_branch():
    """
    Remove stock from the logged-in user's branch.
    """
    with Session(engine) as db_session:
        user = db_session.query(User).filter_by(id=flask_session.get('user_id')).first()
        if not user:
            return "User not found.", 404

        id_product = request.form.get("id_product")
        try:
            quantity = int(request.form.get("quantity"))
        except (ValueError, TypeError):
            return {"error": "Quantity must be a valid integer."}, 400
        try:
            stock_item = db_session.query(Stock).filter_by(id_product=id_product, id_branch=user.branch_id).first()

            if not stock_item:
                return {"error": f"Product {id_product} not found in branch {user.branch_id}."}, 404

            remove_stock(db_session, stock_item, quantity)
            return {"message": f"Removed {quantity} of product {id_product} from branch {user.branch_id}."}, 200
        except (ValueError, TypeError) as e:
            return {"error": str(e)}, 400


@app.route("/users", methods=["GET"])
@login_required
@admin_required
def list_users_route():
    with Session(engine) as db_session:
        users = list_users(db_session)
        users_data = []
        for user in users:
            users_data.append({
                "id": user.id,
                "username": user.username,
                "role": user.role,
                "branch_id": user.branch_id,
                "is_active": user.is_active
            })
        return {"users": users_data}, 200


@app.route("/users/create", methods=["POST"])
@login_required
@admin_required
def create_user_route():
    with Session(engine) as db_session:
        username = request.form.get("username")
        password = request.form.get("password")
        try:
            branch_id = int(request.form.get("branch_id"))
        except (ValueError, TypeError):
            return {"error": "Branch ID must be a valid integer."}, 400
        try:
            user = create_common_user(db_session, username, password, branch_id)
            return {"message": f"User {user.username} created successfully.", "user_id": user.id}, 201
        except ValueError as e:
            return {"error": str(e)}, 400


@app.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_user_route(user_id):
    with Session(engine) as db_session:
        try:
            user = soft_delete_user(db_session, user_id)
            return {"message": f"User {user.username} deactivated successfully."}, 200
        except ValueError as e:
            return {"error": str(e)}, 400


@app.route("/users/<int:user_id>/password", methods=["POST"])
@login_required
@admin_required
def change_password_route(user_id):
    with Session(engine) as db_session:
        new_password = request.form.get("new_password")
        try:
            user = change_user_password(db_session, user_id, new_password)
            return {"message": f"Password for user {user.username} changed successfully."}, 200
        except ValueError as e:
            return {"error": str(e)}, 400


@app.route("/users/<int:user_id>/branch", methods=["POST"])
@login_required
@admin_required
def change_branch_route(user_id):
    with Session(engine) as db_session:
        try:
            new_branch_id = int(request.form.get("new_branch_id"))
        except (ValueError, TypeError):
            return {"error": "New branch ID must be a valid integer."}, 400
        try:
            user = change_user_branch(db_session, user_id, new_branch_id)
            return {"message": f"Branch for user {user.username} changed successfully."}, 200
        except ValueError as e:
            return {"error": str(e)}, 400


if __name__ == "__main__":
    app.run(debug=True)