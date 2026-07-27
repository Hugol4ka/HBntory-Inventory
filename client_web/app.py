import os
import requests
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# URL du Service IA.
# En Docker : fournie par docker-compose (nom de service + port INTERNE).
# En local  : valeur par defaut ci-dessous.
AI_SERVICE_URL = os.getenv("HBN_WEB_CLIENT_URL", "http://localhost:5004")

# Un LLM peut mettre plusieurs secondes a repondre : timeout genereux.
AI_TIMEOUT = 30


@app.route("/")
def index():
    """Serve the public chat page."""
    return render_template("index.html")


@app.route("/ask", methods=["POST"])
def ask():
    """Relay a visitor's question to the AI Query Service."""
    question = request.get_json().get("question")
    if not question:
        return jsonify({"error": "Question cannot be empty"}), 400
    url = f"{AI_SERVICE_URL.rstrip('/')}/query"
    try:
        response = requests.post(url, json={"question": question}, timeout=AI_TIMEOUT)
        response.raise_for_status()
        return jsonify(response.json())
    except requests.RequestException:
        return jsonify({"error": "AI Service unavailable"}), 503


if __name__ == "__main__":
    app.run(debug=True, port=5005)