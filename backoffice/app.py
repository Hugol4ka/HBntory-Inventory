from flask import Flask
from flask import session as flask_session
from sqlalchemy.orm import Session
from database import engine
from models import Base, Branch, User, Stock
import bcrypt
from flask import request
import os
from dotenv import load_dotenv

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

if __name__ == "__main__":
    app.run(debug=True)