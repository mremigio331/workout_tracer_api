import requests
import json
import argparse


def post_strava_webhook_event(workout_id, strava_id, stage="local"):
    if stage == "prod":
        url = "https://api.workouttracer.com/strava/webhook"
    elif stage == "staging":
        url = "https://api.staging.workouttracer.com/strava/webhook"
    else:
        url = "http://localhost:5000/strava/webhook"

    payload = {
        "aspect_type": "update",
        "event_time": 1751896594,
        "object_id": int(workout_id),
        "object_type": "activity",
        "owner_id": int(strava_id),
        "subscription_id": 0,
        "updates": {},
    }

    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    print(f"POST {url}")
    print("Payload:", json.dumps(payload, indent=2))
    try:
        resp = requests.post(url, headers=headers, json=payload)
        print("Status:", resp.status_code)
        print("Response headers:", resp.headers)
        print("Full Response:")
        print(resp.text)
        if resp.status_code == 403:
            print("Received 403 Forbidden. This usually means:")
            print(
                "- The server is running and reachable, but you are not authorized to access this endpoint."
            )
            print(
                "- If running locally, check if CORS, authentication, or API key requirements are enabled."
            )
            print(
                "- If using FastAPI, ensure you are not blocking non-browser POSTs or requiring a special header/token."
            )
            print("- Check your server logs for more details.")
    except Exception as e:
        print("Request failed:", e)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Force a Strava webhook event POST.")
    parser.add_argument("--workout_id", required=True, help="Workout ID (object_id)")
    parser.add_argument(
        "--strava_id", required=True, help="Strava athlete ID (owner_id)"
    )
    parser.add_argument(
        "--stage",
        default="local",
        help="Stage: prod | staging | local (default: local)",
    )
    args = parser.parse_args()
    post_strava_webhook_event(args.workout_id, args.strava_id, args.stage)
