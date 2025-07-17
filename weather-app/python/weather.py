import requests

def get_weather(location, api_key, mode="city"):
    base_url = "https://api.openweathermap.org/data/2.5/weather"

    if mode == "zip":
        params = {
            "zip": f"{location},us",  # You can make 'us' dynamic later
            "appid": api_key,
            "units": "imperial"
        }
    else:  # default to city
        params = {
            "q": location,
            "appid": api_key,
            "units": "imperial"
        }

    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        data = response.json()

        return {
            "city": data["name"],
            "temp": data["main"]["temp"],
            "feels_like": data["main"]["feels_like"],
            "description": data["weather"][0]["description"],
            "humidity": data["main"]["humidity"],
            "wind_speed": data["wind"]["speed"]
        }

    except requests.exceptions.HTTPError as http_err:
        if response.status_code == 404:
            return {"error": "Location not found."}
        return {"error": f"HTTP error: {http_err}"}
    except Exception as err:
        return {"error": f"Unexpected error: {err}"}
