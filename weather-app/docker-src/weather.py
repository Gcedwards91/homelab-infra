import requests
from logger import get_logger

logger = get_logger()


def get_weather(location: str, api_key: str, mode: str = "city") -> dict:
    """Fetch current weather from OpenWeatherMap and return a summary dict."""
    base_url = "https://api.openweathermap.org/data/2.5/weather"

    if mode == "zip":
        params = {"zip": f"{location},us", "appid": api_key, "units": "imperial"}
    else:
        params = {"q": location, "appid": api_key, "units": "imperial"}

    # Redact the API key before logging
    safe_params = {**params, "appid": "***REDACTED***"}

    logger.info(
        "Sending weather request",
        extra={
            "event": "request_sent",
            "mode": mode,
            "location": location,
            "params": safe_params,
        },
    )

    response = None
    try:
        response = requests.get(base_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        logger.info(
            "Weather response received",
            extra={
                "event": "response_received",
                "status_code": response.status_code,
                "city": data.get("name"),
                "summary": data.get("weather", [{}])[0].get("description"),
            },
        )

        return {
            "city": data["name"],
            "temp": data["main"]["temp"],
            "feels_like": data["main"]["feels_like"],
            "description": data["weather"][0]["description"],
            "humidity": data["main"]["humidity"],
            "wind_speed": data["wind"]["speed"],
        }

    except requests.exceptions.HTTPError as http_err:
        status_code = response.status_code if response is not None else None
        logger.error(
            "HTTP error fetching weather",
            extra={
                "event": "http_error",
                "status_code": status_code,
                "detail": str(http_err),
            },
        )
        if status_code == 404:
            return {"error": "Location not found."}
        return {
            "error": f"Weather service error ({status_code}). Check your API key and try again."
        }

    except Exception as err:
        logger.error(
            "Unexpected error fetching weather",
            extra={"event": "general_error", "detail": str(err)},
        )
        return {"error": "An unexpected error occurred. Please try again."}
