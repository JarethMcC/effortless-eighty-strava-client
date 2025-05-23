from firebase_functions import https_fn

from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import requests
import json
import logging
import time
import sys

# initialize_app() # Call this if you need to interact with other Firebase services

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables from .env file
# This is primarily for local development.
# In a deployed Google Cloud Function, environment variables
# should be set in the function's configuration.
try:
    from dotenv import load_dotenv
    load_dotenv()
    logger.info("Attempted to load .env file.")
except ImportError:
    logger.warning("dotenv module not found, skipping load_dotenv(). Ensure environment variables are set via cloud configuration for deployment.")
    # Define a no-op function if needed elsewhere, though it's only called once here.
    def load_dotenv():
        pass

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Strava API constants - First try to get them from Firebase Functions config
# Firebase Functions makes config values available as environment variables
# with format: FIREBASE_CONFIG_[SECTION]_[KEY]
STRAVA_CLIENT_ID = os.environ.get('FIREBASE_CONFIG_STRAVA_CLIENT_ID') or os.getenv('STRAVA_CLIENT_ID')
STRAVA_CLIENT_SECRET = os.environ.get('FIREBASE_CONFIG_STRAVA_CLIENT_SECRET') or os.getenv('STRAVA_CLIENT_SECRET')
# For redirect URI, first check for a Firebase config, then environment variable, then use default
FIREBASE_REDIRECT_URI = os.environ.get('FIREBASE_CONFIG_STRAVA_REDIRECT_URI')
STRAVA_AUTHORIZATION_URL = 'https://www.strava.com/oauth/authorize'
STRAVA_TOKEN_URL = 'https://www.strava.com/api/v3/oauth/token'
STRAVA_ACTIVITIES_URL = 'https://www.strava.com/api/v3/athlete/activities'
STRAVA_ATHLETE_ZONES_URL = 'https://www.strava.com/api/v3/athlete/zones'

# Check if we're running in Firebase environment with the config values
logger.info(f"Running with firebase config: {bool(os.environ.get('FIREBASE_CONFIG_STRAVA_CLIENT_ID'))}")

# Check that credentials are loaded
if not STRAVA_CLIENT_ID or not STRAVA_CLIENT_SECRET:
    logger.error("Strava API credentials are missing! Check your environment variables or Firebase function config.")

# Verify redirect URI is registered with Strava
# For Firebase deployment, this should be your frontend's redirect handler URL
# or the function URL if it handles the redirect directly.
EXPECTED_REDIRECT_URI = FIREBASE_REDIRECT_URI or os.getenv('EXPECTED_REDIRECT_URI', 'http://localhost:3000/exchange_token')
logger.info(f"Expected redirect URI: {EXPECTED_REDIRECT_URI}")

@app.route('/api/auth-url', methods=['GET'])
def get_auth_url():
    """Generate and return the Strava authorization URL"""
    redirect_uri = request.args.get('redirect_uri', EXPECTED_REDIRECT_URI) # Use configured or passed redirect_uri
    scopes = request.args.get('scopes', 'read,activity:read_all,profile:read_all')

    logger.info(f"Generating auth URL with redirect_uri: {redirect_uri}, client_id: {STRAVA_CLIENT_ID is not None}")

    if not STRAVA_CLIENT_ID:
        logger.error("STRAVA_CLIENT_ID is not set.")
        return jsonify({"error": "Server configuration error: STRAVA_CLIENT_ID missing"}), 500

    auth_url = f"{STRAVA_AUTHORIZATION_URL}?client_id={STRAVA_CLIENT_ID}&redirect_uri={redirect_uri}&response_type=code&scope={scopes}"
    return jsonify({"url": auth_url})

def make_token_request_with_retry(payload, max_retries=3):
    """Make token request with retry logic"""
    retries = 0
    while retries < max_retries:
        try:
            logger.info(f"Attempting token exchange (attempt {retries+1}/{max_retries})")
            response = requests.post(STRAVA_TOKEN_URL, data=payload, timeout=10)
            return response
        except (requests.ConnectionError, requests.Timeout) as e:
            retries += 1
            if retries < max_retries:
                logger.warning(f"Network error during token exchange: {str(e)}. Retrying...")
                time.sleep(1)  # Wait before retry
            else:
                logger.error(f"Failed to exchange token after {max_retries} attempts: {str(e)}")
                raise
        except Exception as e:
            logger.error(f"Unexpected error during token exchange: {str(e)}")
            raise

@app.route('/api/exchange-token', methods=['POST'])
def exchange_token():
    """Exchange authorization code for access token"""
    try:
        request_data = request.json
        logger.info(f"Token exchange request received: {json.dumps(request_data)}")

        code = request_data.get('code')
        if not code:
            logger.warning("No authorization code provided in request")
            return jsonify({"error": "No authorization code provided"}), 400

        if not STRAVA_CLIENT_ID or not STRAVA_CLIENT_SECRET:
            logger.error("Strava API credentials are not configured on the server.")
            return jsonify({"error": "Server configuration error: API credentials missing"}), 500

        payload = {
            'client_id': STRAVA_CLIENT_ID,
            'client_secret': STRAVA_CLIENT_SECRET,
            'code': code,
            'grant_type': 'authorization_code'
        }

        logger.info(f"Exchanging code for token with payload: {json.dumps({**payload, 'client_secret': '[REDACTED]'})}")

        response = make_token_request_with_retry(payload)

        status_code = response.status_code
        logger.info(f"Token exchange response status: {status_code}")

        if status_code != 200:
            error_msg = f"Strava API error: {status_code}"
            try:
                error_data = response.json()
                logger.error(f"Token exchange error response: {json.dumps(error_data)}")
                error_detail = error_data.get('message', error_data.get('error', json.dumps(error_data)))
                error_msg += f" - {error_detail}"
            except:
                error_body = response.text[:500]
                logger.error(f"Token exchange error body: {error_body}")
                error_msg += f" - {error_body}"

            return jsonify({"error": error_msg}), status_code

        token_data = response.json()
        log_safe_data = {k: v if k not in ('access_token', 'refresh_token') else '[REDACTED]'
                          for k, v in token_data.items()}
        logger.info(f"Token exchange successful: {json.dumps(log_safe_data)}")

        return jsonify(token_data)

    except Exception as e:
        error_msg = f"Exception during token exchange: {str(e)}"
        logger.exception("Token exchange failed")
        return jsonify({"error": error_msg}), 500

@app.route('/api/activities', methods=['GET'])
def get_activities():
    """Get athlete activities"""
    access_token = request.headers.get('Authorization', '').replace('Bearer ', '')

    if not access_token:
        return jsonify({"error": "No access token provided"}), 401

    params = {k: v for k, v in request.args.items()}

    try:
        response = requests.get(
            STRAVA_ACTIVITIES_URL,
            headers={'Authorization': f'Bearer {access_token}'},
            params=params
        )
        response.raise_for_status() # Raises HTTPError for bad responses (4XX or 5XX)
        return jsonify(response.json())
    except requests.RequestException as e:
        logger.error(f"Error fetching activities: {str(e)}")
        # Try to return Strava's error if available
        if e.response is not None:
            try:
                return jsonify(e.response.json()), e.response.status_code
            except ValueError: # If response is not JSON
                return jsonify({"error": str(e)}), e.response.status_code
        return jsonify({"error": str(e)}), 500

@app.route('/api/athlete/zones', methods=['GET'])
def get_athlete_zones():
    """Get athlete zones"""
    access_token = request.headers.get('Authorization', '').replace('Bearer ', '')

    if not access_token:
        return jsonify({"error": "No access token provided"}), 401

    try:
        response = requests.get(
            STRAVA_ATHLETE_ZONES_URL,
            headers={'Authorization': f'Bearer {access_token}'}
        )
        response.raise_for_status()
        return jsonify(response.json())
    except requests.RequestException as e:
        logger.error(f"Error fetching athlete zones: {str(e)}")
        if e.response is not None:
            try:
                return jsonify(e.response.json()), e.response.status_code
            except ValueError:
                return jsonify({"error": str(e)}), e.response.status_code
        return jsonify({"error": str(e)}), 500

@app.route('/api/refresh-token', methods=['POST'])
def refresh_token():
    """Refresh access token using refresh token"""
    try:
        request_data = request.json
        refresh_token_val = request_data.get('refresh_token')

        if not refresh_token_val:
            return jsonify({"error": "No refresh token provided"}), 400

        if not STRAVA_CLIENT_ID or not STRAVA_CLIENT_SECRET:
            logger.error("Strava API credentials are not configured on the server.")
            return jsonify({"error": "Server configuration error: API credentials missing"}), 500

        payload = {
            'client_id': STRAVA_CLIENT_ID,
            'client_secret': STRAVA_CLIENT_SECRET,
            'refresh_token': refresh_token_val,
            'grant_type': 'refresh_token'
        }

        logger.info(f"Refreshing token with payload: {json.dumps({**payload, 'client_secret': '[REDACTED]', 'refresh_token': '[REDACTED]'})}")

        response = make_token_request_with_retry(payload)

        status_code = response.status_code
        logger.info(f"Token refresh response status: {status_code}")

        if status_code != 200:
            error_msg = f"Strava API error: {status_code}"
            try:
                error_data = response.json()
                logger.error(f"Token refresh error response: {json.dumps(error_data)}")
                error_detail = error_data.get('message', error_data.get('error', json.dumps(error_data)))
                error_msg += f" - {error_detail}"
            except:
                error_body = response.text[:500]
                logger.error(f"Token refresh error body: {error_body}")
                error_msg += f" - {error_body}"
            return jsonify({"error": error_msg}), status_code

        token_data = response.json()
        log_safe_data = {k: v if k not in ('access_token', 'refresh_token') else '[REDACTED]'
                          for k, v in token_data.items()}
        logger.info(f"Token refresh successful: {json.dumps(log_safe_data)}")
        return jsonify(token_data)

    except Exception as e:
        error_msg = f"Exception during token refresh: {str(e)}"
        logger.exception("Token refresh failed")
        return jsonify({"error": error_msg}), 500

@app.route('/api/debug-info', methods=['GET'])
def debug_info():
    """Endpoint to check server configuration (no sensitive data)"""
    return jsonify({
        "strava_client_id_set": STRAVA_CLIENT_ID is not None, # Don't expose the ID itself
        "expected_redirect_uri": EXPECTED_REDIRECT_URI,
        "server_time": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    })

# Expose the Flask app as an HTTP function
@https_fn.on_request()  # Decorator without the 'app' keyword argument
def strava_api_handler(request):
    # Process the request through the Flask app
    return app(request.environ, lambda status, headers, body: [status, headers, body])
