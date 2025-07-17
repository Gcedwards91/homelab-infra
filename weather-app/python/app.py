from flask import Flask, render_template, request, jsonify
from weather import get_weather

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/weather", methods=["POST"])
def weather():
    data = request.json
    location = data.get("location")
    api_key = data.get("api_key")
    mode = data.get("mode", "city")

    if not location or not api_key:
        return jsonify({"error": "Location and API key are required."}), 400

    weather_data = get_weather(location, api_key, mode)
    return jsonify(weather_data)

if __name__ == "__main__":
    app.run(debug=True)
