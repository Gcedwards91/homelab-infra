from unittest.mock import MagicMock, patch

import requests

import weather

_OK_BODY = {
    "name": "Atlanta",
    "main": {"temp": 71.0, "feels_like": 70.0, "humidity": 44},
    "weather": [{"description": "clear sky"}],
    "wind": {"speed": 5.0},
}

_SENTINEL_KEY = "SENTINEL_API_KEY_DO_NOT_LEAK"


def _http_error_response(status_code):
    resp = MagicMock(status_code=status_code)
    resp.raise_for_status.side_effect = requests.exceptions.HTTPError()
    return resp


class TestWeatherAppWeatherClient:
    @patch("weather.requests.get")
    def test_weather_app_success_maps_all_fields(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200)
        mock_get.return_value.json.return_value = _OK_BODY
        mock_get.return_value.raise_for_status.return_value = None
        result = weather.get_weather("Atlanta", "key", "city")
        assert result["city"] == "Atlanta"
        assert result["temp"] == 71.0
        assert result["feels_like"] == 70.0
        assert result["description"] == "clear sky"
        assert result["humidity"] == 44
        assert result["wind_speed"] == 5.0

    @patch("weather.requests.get")
    def test_weather_app_city_mode_builds_q_param(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200)
        mock_get.return_value.json.return_value = _OK_BODY
        mock_get.return_value.raise_for_status.return_value = None
        weather.get_weather("Atlanta", "key", "city")
        call_params = mock_get.call_args[1].get("params", {})
        assert call_params.get("q") == "Atlanta"
        assert "zip" not in call_params

    @patch("weather.requests.get")
    def test_weather_app_zip_mode_builds_zip_param(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200)
        mock_get.return_value.json.return_value = _OK_BODY
        mock_get.return_value.raise_for_status.return_value = None
        weather.get_weather("30301", "key", "zip")
        call_params = mock_get.call_args[1].get("params", {})
        assert call_params.get("zip") == "30301,us"
        assert "q" not in call_params

    @patch("weather.requests.get")
    def test_weather_app_http_404_returns_location_not_found(self, mock_get):
        mock_get.return_value = _http_error_response(404)
        result = weather.get_weather("Nowhere", "key", "city")
        assert result == {"error": "Location not found."}

    @patch("weather.requests.get")
    def test_weather_app_http_500_returns_service_error(self, mock_get):
        mock_get.return_value = _http_error_response(500)
        result = weather.get_weather("Atlanta", _SENTINEL_KEY, "city")
        assert "error" in result
        assert "500" in result["error"]
        assert _SENTINEL_KEY not in result["error"]

    @patch("weather.requests.get")
    def test_weather_app_connection_error_returns_generic(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError()
        result = weather.get_weather("Atlanta", "key", "city")
        assert result == {"error": "An unexpected error occurred. Please try again."}

    @patch("weather.requests.get")
    def test_weather_app_timeout_returns_generic(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout()
        result = weather.get_weather("Atlanta", "key", "city")
        assert result == {"error": "An unexpected error occurred. Please try again."}

    @patch("weather.requests.get")
    def test_weather_app_api_key_never_in_error(self, mock_get):
        mock_get.return_value = _http_error_response(503)
        result = weather.get_weather("Atlanta", _SENTINEL_KEY, "city")
        assert "error" in result
        assert _SENTINEL_KEY not in result["error"]

    @patch("weather.requests.get")
    def test_weather_app_error_has_no_raw_exception_tokens(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError("raw detail")
        result = weather.get_weather("Atlanta", "key", "city")
        error_text = result.get("error", "")
        for token in ("Traceback", "raise ", "Exception", 'File "'):
            assert token not in error_text
