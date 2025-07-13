import sys
import os
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import requests
from clients.strava_client import StravaClient


def get_strava_keys(stage):
    strava_client = StravaClient(stage=stage)
    configs = strava_client.get_strava_api_configs()
    # Optionally, handle different stages if needed
    return configs


def register_strava_webhook(stage="staging"):
    strava_keys = get_strava_keys(stage)
    print(strava_keys)
    STRAVA_CLIENT_ID = strava_keys[f"{stage.upper()}_STRAVA_CLIENT_ID"]
    STRAVA_CLIENT_SECRET = strava_keys[f"{stage.upper()}_STRAVA_CLIENT_SECRET"]

    # Use the unified webhook endpoint
    if stage == "prod" or stage == "production":
        STRAVA_CALLBACK_URL = "https://api.workouttracer.com/strava/webhook"
        STRAVA_VERIFY_TOKEN = strava_keys.get("PROD_VERIFY_TOKEN", "")
    else:
        STRAVA_CALLBACK_URL = "https://api.staging.workouttracer.com/strava/webhook"
        STRAVA_VERIFY_TOKEN = strava_keys.get("STAGING_VERIFY_TOKEN", "")

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


def delete_strava_webhook(stage="staging"):
    strava_keys = get_strava_keys(stage)
    STRAVA_CLIENT_ID = strava_keys[f"{stage.upper()}_STRAVA_CLIENT_ID"]
    STRAVA_CLIENT_SECRET = strava_keys[f"{stage.upper()}_STRAVA_CLIENT_SECRET"]

    url = "https://www.strava.com/api/v3/push_subscriptions"
    print("Fetching current Strava webhook subscriptions...")
    response = requests.get(
        url,
        params={
            "client_id": STRAVA_CLIENT_ID,
            "client_secret": STRAVA_CLIENT_SECRET,
        },
    )
    print(f"Status: {response.status_code}")
    try:
        subs = response.json()
        print("Current subscriptions:", subs)
        for sub in subs:
            sub_id = sub.get("id")
            if sub_id:
                print(f"Deleting subscription id: {sub_id}")
                del_resp = requests.delete(
                    f"{url}/{sub_id}",
                    params={
                        "client_id": STRAVA_CLIENT_ID,
                        "client_secret": STRAVA_CLIENT_SECRET,
                    },
                )
                print(f"Delete status: {del_resp.status_code}")
                try:
                    print(del_resp.json())
                except Exception:
                    print(del_resp.text)
    except Exception:
        print(response.text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Strava Webhook Registration Tool")
    parser.add_argument(
        "--stage",
        choices=["staging", "prod"],
        default="staging",
        help="Environment stage",
    )
    parser.add_argument("--create", action="store_true", help="Create/register webhook")
    parser.add_argument("--delete", action="store_true", help="Delete all webhooks")
    args = parser.parse_args()

    if args.create:
        register_strava_webhook(stage=args.stage)
    elif args.delete:
        delete_strava_webhook(stage=args.stage)
    else:
        parser.print_help()
