import requests
from logger import get_logger

logger = get_logger()

def get_weather(location, api_key, mode="city"):
    base_url = "https://api.openweathermap.org/data/2.5/weather"

    if mode == "zip":
        params = {
            "zip": f"{location},us",
            "appid": api_key,
            "units": "imperial"
        }
    else:
        params = {
            "q": location,
            "appid": api_key,
            "units": "imperial"
        }

    # Redact the API key before logging
    safe_params = params.copy()
    if "appid" in safe_params:
        safe_params["appid"] = "***REDACTED***"

    try:
        logger.info({
            "event": "request_sent",
            "mode": mode,
            "location": location,
            "params": safe_params
        })

        response = requests.get(base_url, params=params)
        response.raise_for_status()
        data = response.json()

        logger.info({
            "event": "response_received",
            "status_code": response.status_code,
            "city": data.get("name"),
            "summary": data.get("weather", [{}])[0].get("description")
        })

        return {
            "city": data["name"],
            "temp": data["main"]["temp"],
            "feels_like": data["main"]["feels_like"],
            "description": data["weather"][0]["description"],
            "humidity": data["main"]["humidity"],
            "wind_speed": data["wind"]["speed"]
        }

    except requests.exceptions.HTTPError as http_err:
        logger.error({
            "event": "http_error",
            "status_code": response.status_code,
            "message": str(http_err)
        })
        if response.status_code == 404:
            return {"error": "Location not found."}
        return {"error": f"HTTP error: {http_err}"}

    except Exception as err:
        logger.error({
            "event": "general_error",
            "message": str(err)
        })
        return {"error": f"Unexpected error: {err}"}
