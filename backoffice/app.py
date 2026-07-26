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
from stock_service import remove_stock, add_stock, get_quantity_of_product_in_branch
from user_service import list_users, create_common_user, soft_delete_user, change_user_password, change_user_branch
from product_api import list_products, ProductAPIError, get_product_details
from flask import render_template, flash, redirect, url_for


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
                if user.role == 'admin':
                    return redirect(url_for("list_users_route"))
                return redirect(url_for("get_stock"))
            else:
                flash("Invalid username or password.", "error")
                return render_template("login.html")
    return render_template("login.html")


@app.route("/logout", methods=["GET"])
def logout():
    flask_session.pop('user_id', None)
    return redirect(url_for('login'))


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
        product_names = {}
        try:
            for product in list_products()["results"]:
                product_names[product["sku"]] = product["name"]
        except ProductAPIError:
            pass
        stock_data = [
            {
                "id_product": item.id_product,
                "name": product_names.get(item.id_product, "Unknown product"),
                "quantity": item.quantity,
            }
            for item in stock_items
        ]
        return render_template("stock.html", branch=branch.name, stock=stock_data, username=user.username)


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
            flash("Quantity must be a valid integer.", "error")
            return redirect(url_for("get_stock"))
        try:
            stock_item = db_session.query(Stock).filter_by(id_product=id_product, id_branch=user.branch_id).first()

            if not stock_item:
                stock_item = Stock(id_product=id_product, id_branch=user.branch_id, quantity=0)
                db_session.add(stock_item)

            add_stock(db_session, stock_item, quantity)
            flash(f"Added {quantity} of product {id_product}.", "success")
            return redirect(url_for("get_stock"))
        except (ValueError, TypeError) as e:
            flash(str(e), "error")
            return redirect(url_for("get_stock"))

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
            flash("Quantity must be a valid integer.", "error")
            return redirect(url_for("get_stock"))
        try:
            stock_item = db_session.query(Stock).filter_by(id_product=id_product, id_branch=user.branch_id).first()

            if not stock_item:
                flash(f"Product {id_product} not found in this branch.", "error")
                return redirect(url_for("get_stock"))

            remove_stock(db_session, stock_item, quantity)
            flash(f"Removed {quantity} of product {id_product} from branch {user.branch_id}.", "success")
            return redirect(url_for("get_stock"))
        except (ValueError, TypeError) as e:
            flash(str(e), "error")
            return redirect(url_for("get_stock"))


@app.route("/users", methods=["GET"])
@login_required
@admin_required
def list_users_route():
    with Session(engine) as db_session:
        users = list_users(db_session)
        branches = db_session.query(Branch).all()
        branch_names = {b.id: b.name for b in branches} 
        users_data = []
        for user in users:
            users_data.append({
                "id": user.id,
                "username": user.username,
                "branch_name": branch_names.get(user.branch_id),
                "is_active": user.is_active,
                "role": user.role
            })
        branches_data = [{"id": b.id, "name": b.name} for b in branches]
        current = db_session.query(User).filter_by(id=flask_session.get('user_id')).first()
        return render_template("users.html", users=users_data, branches=branches_data, username=current.username)


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
            flash("Branch ID must be a valid integer.", "error")
            return redirect(url_for("list_users_route"))
        try:
            user = create_common_user(db_session, username, password, branch_id)
            flash(f"User {user.username} created successfully.", "success")
            return redirect(url_for("list_users_route"))
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("list_users_route"))


@app.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_user_route(user_id):
    with Session(engine) as db_session:
        try:
            user = soft_delete_user(db_session, user_id)
            flash(f"User {user.username} deactivated successfully.", "success")
            return redirect(url_for("list_users_route"))
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("list_users_route"))


@app.route("/users/password", methods=["POST"])
@login_required
@admin_required
def change_password_route():
    with Session(engine) as db_session:
        new_password = request.form.get("new_password")
        try:
            user_id = int(request.form.get("user_id"))
        except (ValueError, TypeError):
            flash("User ID must be a valid integer.", "error")
            return redirect(url_for("list_users_route"))
        try:
            user = change_user_password(db_session, user_id, new_password)
            flash(f"Password for user {user.username} changed successfully.", "success")
            return redirect(url_for("list_users_route"))
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("list_users_route"))


@app.route("/users/branch", methods=["POST"])
@login_required
@admin_required
def change_branch_route():
    with Session(engine) as db_session:
        try:
            user_id = int(request.form.get("user_id"))
        except (ValueError, TypeError):
            flash("User ID must be a valid integer.", "error")
            return redirect(url_for("list_users_route"))
        try:
            new_branch_id = int(request.form.get("new_branch_id"))
        except (ValueError, TypeError):
            flash("New branch ID must be a valid integer.", "error")
            return redirect(url_for("list_users_route"))
        try:
            user = change_user_branch(db_session, user_id, new_branch_id)
            flash(f"Branch for user {user.username} changed successfully.", "success")
            return redirect(url_for("list_users_route"))
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("list_users_route"))


if __name__ == "__main__":
    app.run(debug=True)