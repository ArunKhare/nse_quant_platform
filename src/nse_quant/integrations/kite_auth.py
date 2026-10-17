"""Kite authentication. Headless web endpoints are unofficial and may change."""
import argparse
import base64
import binascii
import json
import logging
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urljoin, urlparse

import pyotp
import requests
from kiteconnect import KiteConnect

from nse_quant.core.settings import Settings, get_settings

logger = logging.getLogger(__name__)
HTTP_TIMEOUT = 10
MAX_AUTH_REDIRECTS = 5
FALLBACK_HOST = "127.0.0.1"
FALLBACK_PORT = 8000

class AuthError(RuntimeError):
    pass


class TokenReceiverHandler(BaseHTTPRequestHandler):
    """Listens for the Zerodha callback redirect and extracts the token regardless of the URI path."""
    def do_GET(self):
        # Dynamically parse parameters out of any URL path structure (e.g., /kite/callback)
        query_params = parse_qs(urlparse(self.path).query)

        if "request_token" in query_params:
            # Safely return the string value instead of a list item array
            self.server.captured_token = query_params["request_token"][0]

            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()

            success_html = """
            <html>
                <head><title>Authentication Success</title></head>
                <body style="font-family: Arial, sans-serif; text-align: center; margin-top: 100px; background-color: #f4f7f6;">
                    <div style="display: inline-block; padding: 40px; background: white; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.05);">
                        <h2 style="color: #2ecc71; margin-bottom: 10px;">✅ Authentication Successful!</h2>
                        <p style="color: #666; font-size: 15px;">Python intercepted the token. You can safely close this browser window.</p>
                    </div>
                </body>
            </html>
            """
            self.wfile.write(bytes(success_html, "utf-8"))
        else:
            # Fallback error response for missing parameters
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(bytes("<html><body><h2>❌ Authentication Failed</h2><p>No request token found in query parameters.</p></body></html>", "utf-8"))

    def log_message(self, format, *args):
        # Suppress server terminal log cluttering
        return


def normalize_totp_secret(raw):
    if not raw:
        raise AuthError("KITE_TOTP_SECRET is missing in .env")
    secret = "".join(raw.split()).upper()
    try:
        decoded = base64.b32decode(secret + "=" * ((8 - len(secret) % 8) % 8))
    except (binascii.Error, ValueError) as exc:
        raise AuthError("KITE_TOTP_SECRET is not valid Base32; use the setup seed, not an OTP or URI") from exc
    if not decoded:
        raise AuthError("KITE_TOTP_SECRET is empty")
    return secret


def extract_request_token(url):
    params = parse_qs(urlparse(url).query)
    if params.get("status", [""])[0] in {"error", "failure", "failed"}:
        raise AuthError("Authorization callback reported failure")
    values = params.get("request_token", [])
    if len(values) > 1:
        raise AuthError("Multiple request tokens in callback")
    return values[0] if values else None


def follow_authorization_redirects(session, login_url):
    current_url = login_url
    for hop in range(MAX_AUTH_REDIRECTS):
        token = extract_request_token(current_url)
        if token:
            return token
        parsed = urlparse(current_url)
        if (parsed.scheme != "https" or parsed.hostname != "kite.zerodha.com"
                or parsed.port not in (None, 443) or parsed.username or parsed.password):
            raise AuthError("Authorization left Kite without a request_token; check app redirect settings")
        response = session.get(current_url, allow_redirects=False, timeout=HTTP_TIMEOUT)
        response.raise_for_status()
        logger.info("Authorization hop %d: HTTP %d, path=%s", hop + 1, response.status_code, parsed.path)
        location = response.headers.get("Location")
        if response.status_code in (301, 302, 303, 307, 308) and location:
            current_url = urljoin(current_url, location)
            continue
        raise AuthError("Authorization requires browser interaction; retry with --manual")
    token = extract_request_token(current_url)
    if token:
        return token
    raise AuthError("Authorization redirect limit reached")


def post_auth(session, path, payload, label):
    # FIXED: Cleaned up the 'https://://zerodha.com' typo causing the InvalidURL crash
    response = session.post("https://kite.zerodha.com" + path, data=payload,
                            allow_redirects=False, timeout=HTTP_TIMEOUT)
    if response.status_code != 200:
        raise AuthError(f"{label} returned HTTP {response.status_code}")
    try:
        result = response.json()
    except ValueError as exc:
        raise AuthError(f"{label} returned non-JSON data") from exc
    if not isinstance(result, dict) or result.get("status") != "success":
        raise AuthError(f"{label} rejected; verify credentials in Kite manually")
    return result.get("data") or {}


def headless_request_token(kite, settings: Settings | None = None):
    settings = settings or get_settings()
    secrets = settings.secrets
    secret = normalize_totp_secret(secrets.kite_totp_secret)
    if not secrets.kite_user_id or not secrets.kite_password:
        raise AuthError("KITE_USER_ID or KITE_PASSWORD is missing")
    logger.info("Initiating headless session acquisition")
    with requests.Session() as session:
        data = post_auth(session, "/api/login", {
            "user_id": secrets.kite_user_id, "password": secrets.kite_password,
        }, "Password validation")
        request_id = data.get("request_id")
        if not request_id:
            raise AuthError("Password response is missing request_id")
        logger.info("Step 1/2: Primary password validation cleared")
        post_auth(session, "/api/twofa", {
            "user_id": secrets.kite_user_id, "request_id": request_id,
            "twofa_value": pyotp.TOTP(secret).now(),
        }, "TOTP validation")
        logger.info("Step 2/2: Two-factor verification cleared")
        return follow_authorization_redirects(session, kite.login_url())


def manual_request_token(kite, settings: Settings | None = None):
    """Starts a dynamic local server matching the Zerodha callback parameters exactly."""
    settings = settings or get_settings()

    host = FALLBACK_HOST
    port = FALLBACK_PORT  # Default explicitly to port 8000 based on your app configuration

    # Attempt to extract target port out of local settings layer if configured
    try:
        redirect_url = getattr(settings.secrets, "kite_redirect_url", None)
        if redirect_url:
            parsed_target = urlparse(redirect_url)
            if parsed_target.port:
                port = parsed_target.port
    except Exception as e: #noqa:BLE001
        logger.warning("Could not parse custom settings port configuration (%s). Using port 8000.", e)

    url = kite.login_url()

    logger.info("Binding local loopback interception server to http://%s:%s", host, port)
    httpd = HTTPServer((host, port), TokenReceiverHandler)
    httpd.captured_token = None

    print("Complete Kite login in your browser. Login URL:", url)
    webbrowser.open(url)

    # Process exactly one request (intercepting the callback matching your custom path)
    httpd.handle_request()
    token = httpd.captured_token
    httpd.server_close()

    if not token:
        raise AuthError("Browser authorization completed but no request_token was captured.")

    logger.info("Successfully intercepted request token via dynamic callback loop.")
    return token

def get_authenticated_kite(mode=None, settings: Settings | None = None):
    settings = settings or get_settings()
    secrets = settings.secrets
    if not secrets.kite_api_key or not secrets.kite_api_secret:
        raise AuthError("KITE_API_KEY or KITE_API_SECRET is missing")
    kite = KiteConnect(api_key=secrets.kite_api_key, timeout=HTTP_TIMEOUT)
    if secrets.kite_access_token:
        kite.set_access_token(secrets.kite_access_token)
        kite.profile()
        return kite
    mode = mode or secrets.kite_auth_mode
    if mode not in {"manual", "headless"}:
        raise AuthError("KITE_AUTH_MODE must be manual or headless")
    request_token = (
        manual_request_token(kite, settings)
        if mode == "manual"
        else headless_request_token(kite, settings)
    )
    payload = kite.generate_session(request_token, api_secret=secrets.kite_api_secret)
    token = payload.get("access_token")
    if not token:
        raise AuthError("Session exchange returned no access token")
    kite.set_access_token(token)
    profile = kite.profile()
    if isinstance(profile, bytes):
        profile = json.loads(profile)
    if not isinstance(profile, dict):
        raise AuthError("Profile response has an unexpected format")
    if secrets.kite_user_id and profile.get("user_id") != secrets.kite_user_id:
        raise AuthError("Authenticated account differs from KITE_USER_ID")
    secrets.kite_access_token = token
    logger.info("Authenticated successfully; access token retained in memory only")
    return kite


def auto_acquire_access_token():
    """Backward-compatible entry point for main.py: return token or None."""
    try:
        kite = get_authenticated_kite()
        return kite.access_token
    except AuthError as exc:
        logger.error("Authentication failed: %s", exc)
    except Exception as exc: #noqa:BLE001
        logger.error("Authentication failed (%s); details suppressed to protect credentials", type(exc).__name__)
    return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--manual", action="store_true")
    args = parser.parse_args()
    try:
        get_authenticated_kite(mode="manual" if args.manual else None)
    except AuthError as exc:
        logger.error("%s", exc)
        raise SystemExit(1)
    except Exception as exc: #noqa:BLE001
        logger.error("Login failed (%s); no credentials logged", type(exc).__name__)
        raise SystemExit(1)
