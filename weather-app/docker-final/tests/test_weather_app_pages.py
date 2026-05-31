"""
Integration tests - Phase 2: Weather App Pages.

Mirrors TESTING_CHECKLIST.md sections 2.1 through 2.8.

Prerequisites (automated by CI - or run locally after stack is up):
    cd weather-app/docker-final
    docker compose up -d && sleep 30
    pip install -r requirements-dev.txt
    pytest tests/test_weather_app_pages.py -v

Override the target base URL with the BASE_URL env var:
    BASE_URL=http://192.168.1.50 pytest tests/test_weather_app_pages.py -v
"""

import os

import pytest
import requests as http

BASE_URL = os.environ.get("BASE_URL", "http://localhost")

# Ordered list of (path, human label) for the four main pages.
_PAGES = [
    ("/", "Blog index"),
    ("/about_me", "About Me"),
    ("/resume", "Resume"),
    ("/weather_app", "Weather App"),
]

# Expected navbar href values on every main page.
# Uses prefix matching so /grafana matches /grafana/d/homelab-observability.
_NAVBAR_HREFS = [
    "/about_me",
    "/",
    "/resume",
    "/weather_app",
    "/playground",
    "/grafana",
]


# ---------------------------------------------------------------------------
# 2.1  Page loads
# ---------------------------------------------------------------------------


class TestWeatherAppPageLoads:

    @pytest.mark.parametrize("path,label", _PAGES)
    def test_page_returns_200(self, path, label):
        resp = http.get(f"{BASE_URL}{path}", timeout=10)
        assert (
            resp.status_code == 200
        ), f"{label} ({path}) returned HTTP {resp.status_code}"

    def test_blog_index_has_multiple_posts(self):
        resp = http.get(f"{BASE_URL}/", timeout=10)
        count = resp.text.count('class="blog-post"')
        assert (
            count >= 2
        ), f"Blog index has {count} .blog-post block(s); expected at least 2"

    def test_about_me_has_key_sections(self):
        resp = http.get(f"{BASE_URL}/about_me", timeout=10)
        body = resp.text
        for heading in (
            "In The Beginning",
            "The Pivot",
            "This Project",
            "What's Next",
        ):
            assert (
                heading in body
            ), f"About Me page missing expected section heading: {heading!r}"

    def test_about_me_has_tooltips(self):
        resp = http.get(f"{BASE_URL}/about_me", timeout=10)
        assert (
            'class="has-tooltip"' in resp.text
        ), "About Me page missing .has-tooltip elements"

    def test_resume_has_all_sections(self):
        resp = http.get(f"{BASE_URL}/resume", timeout=10)
        body = resp.text
        for section_id in (
            "section-summary",
            "section-skills",
            "section-experience",
            "section-projects",
            "section-education",
        ):
            assert (
                section_id in body
            ), f"Resume page missing aria-labelledby/id: #{section_id}"

    def test_resume_experience_has_bullet_list(self):
        resp = http.get(f"{BASE_URL}/resume", timeout=10)
        assert 'class="experience-entry__bullets"' in resp.text, (
            "Resume page missing .experience-entry__bullets list "
            "(checklist: bullet points have markers)"
        )

    def test_resume_download_buttons_present(self):
        resp = http.get(f"{BASE_URL}/resume", timeout=10)
        body = resp.text
        assert "Download PDF" in body, "Resume page missing 'Download PDF' text"
        assert "Download DOCX" in body, "Resume page missing 'Download DOCX' text"

    def test_weather_app_form_fields_present(self):
        resp = http.get(f"{BASE_URL}/weather_app", timeout=10)
        body = resp.text
        for field_id in ("location", "api_key", "mode"):
            assert (
                f'id="{field_id}"' in body
            ), f"Weather App form missing field: id={field_id!r}"
        assert 'type="submit"' in body, "Weather App form missing submit button"

    def test_weather_app_location_field_is_required(self):
        resp = http.get(f"{BASE_URL}/weather_app", timeout=10)
        assert "required" in resp.text, (
            "Weather App location input missing 'required' attribute "
            "(checklist: browser-level required field validation)"
        )


# ---------------------------------------------------------------------------
# 2.2  Navbar
# ---------------------------------------------------------------------------


class TestWeatherAppNavbar:

    @pytest.mark.parametrize("path,label", _PAGES)
    def test_all_navbar_hrefs_present(self, path, label):
        resp = http.get(f"{BASE_URL}{path}", timeout=10)
        body = resp.text
        for href in _NAVBAR_HREFS:
            assert (
                f'href="{href}' in body
            ), f"{label} ({path}): navbar missing link href starting with {href!r}"

    @pytest.mark.parametrize("path,label", _PAGES)
    def test_navbar_link_text_present(self, path, label):
        resp = http.get(f"{BASE_URL}{path}", timeout=10)
        body = resp.text
        for link_text in (
            "About Me",
            "Homelab Blog",
            "Resume",
            "Weather App",
            "Playground",
            "Grafana",
        ):
            assert (
                link_text in body
            ), f"{label} ({path}): navbar missing link text {link_text!r}"


# ---------------------------------------------------------------------------
# 2.3 / 2.4  /weather endpoint - input validation and error response shape
# ---------------------------------------------------------------------------


class TestWeatherAppWeatherEndpoint:

    _url = f"{BASE_URL}/weather"

    # --- Input validation (no external calls made) ---

    def test_empty_body_returns_400(self):
        resp = http.post(self._url, json={}, timeout=10)
        assert (
            resp.status_code == 400
        ), f"POST /weather with empty body returned {resp.status_code}"

    def test_missing_api_key_returns_400(self):
        resp = http.post(self._url, json={"location": "Atlanta"}, timeout=10)
        assert (
            resp.status_code == 400
        ), f"POST /weather with location only returned {resp.status_code}"

    def test_missing_location_returns_400(self):
        resp = http.post(self._url, json={"api_key": "somekey"}, timeout=10)
        assert (
            resp.status_code == 400
        ), f"POST /weather with api_key only returned {resp.status_code}"

    def test_non_json_content_type_returns_400(self):
        resp = http.post(
            self._url,
            data="not json",
            headers={"Content-Type": "text/plain"},
            timeout=10,
        )
        assert resp.status_code == 400

    # --- Error response shape ---

    def test_400_response_has_error_key(self):
        resp = http.post(self._url, json={}, timeout=10)
        data = resp.json()
        assert "error" in data, f"400 response body has no 'error' key: {data}"

    def test_400_error_is_user_friendly_not_raw_exception(self):
        resp = http.post(self._url, json={}, timeout=10)
        error_msg = resp.json().get("error", "")
        assert error_msg, "400 error message is empty"
        for leak_token in ("Traceback", "raise ", "Exception", 'File "'):
            assert leak_token not in error_msg, (
                f"400 error response looks like a raw exception - "
                f"token {leak_token!r} found in: {error_msg!r}"
            )

    def test_get_method_not_allowed(self):
        resp = http.get(self._url, timeout=10)
        assert (
            resp.status_code == 405
        ), f"GET /weather should be 405 Method Not Allowed, got {resp.status_code}"

    def test_api_key_not_leaked_in_400_response(self):
        sentinel_key = "test-sentinel-key-must-not-appear-in-response"
        resp = http.post(
            self._url,
            json={"location": "", "api_key": sentinel_key},
            timeout=10,
        )
        assert (
            sentinel_key not in resp.text
        ), "API key value leaked into the error response body"


# ---------------------------------------------------------------------------
# 2.5  Resume download links
# ---------------------------------------------------------------------------


class TestWeatherAppResumePage:

    def test_pdf_link_has_download_attribute(self):
        resp = http.get(f"{BASE_URL}/resume", timeout=10)
        assert (
            "download" in resp.text
        ), "Resume page missing 'download' attribute on download links"

    def test_pdf_link_references_correct_filename(self):
        resp = http.get(f"{BASE_URL}/resume", timeout=10)
        assert (
            "Cliff_Edwards_Resume.pdf" in resp.text
        ), "Resume page missing Cliff_Edwards_Resume.pdf in download link href"

    def test_docx_link_references_correct_filename(self):
        resp = http.get(f"{BASE_URL}/resume", timeout=10)
        assert (
            "Cliff_Edwards_Resume.docx" in resp.text
        ), "Resume page missing Cliff_Edwards_Resume.docx in download link href"


# ---------------------------------------------------------------------------
# 2.8  Health check
# ---------------------------------------------------------------------------


class TestWeatherAppHealthCheck:

    def test_healthz_returns_200(self):
        resp = http.get(f"{BASE_URL}/healthz", timeout=10)
        assert resp.status_code == 200, f"/healthz returned HTTP {resp.status_code}"

    def test_healthz_json_body(self):
        resp = http.get(f"{BASE_URL}/healthz", timeout=10)
        assert resp.json() == {"status": "ok"}, f"/healthz body: {resp.text!r}"

    def test_healthz_x_request_id_header(self):
        resp = http.get(f"{BASE_URL}/healthz", timeout=10)
        assert "X-Request-ID" in resp.headers, (
            "/healthz response missing X-Request-ID header "
            "(set by Flask after_request middleware)"
        )
