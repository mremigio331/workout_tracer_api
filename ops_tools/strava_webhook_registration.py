import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import requests
from clients.strava_client import StravaClient


def get_strava_keys():
    strava_client = StravaClient()
    return strava_client.get_strava_api_configs()


def register_strava_webhook():
    strava_keys = get_strava_keys()
    print(strava_keys)
    STRAVA_CLIENT_ID = strava_keys["STRAVA_CLIENT_ID"]
    STRAVA_CLIENT_SECRET = strava_keys["STRAVA_CLIENT_SECRET"]

    # Use the unified webhook endpoint
    STRAVA_CALLBACK_URL = "https://api.staging.workouttracer.com/strava/webhook"
    STRAVA_VERIFY_TOKEN = strava_keys["STAGING_VERIFY_TOKEN"]
    url = "https://www.strava.com/api/v3/push_subscriptions"
    payload = {
        "client_id": STRAVA_CLIENT_ID,
        "client_secret": STRAVA_CLIENT_SECRET,
        "callback_url": STRAVA_CALLBACK_URL,
        "verify_token": STRAVA_VERIFY_TOKEN,
    }
    print(f"Registering Strava webhook with payload: {payload}")
    response = requests.post(url, data=payload)
    print(f"Status: {response.status_code}")
    try:
        print(response.json())
    except Exception:
        print(response.text)


if __name__ == "__main__":
    register_strava_webhook()
