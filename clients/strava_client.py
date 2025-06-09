import os
from aws_lambda_powertools import Logger
import boto3
from botocore.exceptions import ClientError
import requests
import json
import time
import datetime


class StravaAuthCodeExchangeError(Exception):
    pass


class StravaClient:
    def __init__(self, request_id=None):
        self.logger = Logger(service="workout_tracer_api")
        if request_id:
            self.logger.append_keys(request_id=request_id)

        stage = os.getenv("STAGE", "dev")
        strava_keys = self._get_strava_api_configs()
        self.strava_client_id = strava_keys["STRAVA_CLIENT_ID"]
        self.strava_client_secret = strava_keys["STRAVA_CLIENT_SECRET"]

    def _get_strava_api_configs(self):
        client = boto3.client("secretsmanager", region_name="us-west-2")
        response = client.get_secret_value(SecretId="StravaKeys")

        secret = response["SecretString"]
        return json.loads(secret)

    def get_strava_callback_url(self, auth_code):
        try:
            response = requests.post(
                "https://www.strava.com/oauth/token",
                data={
                    "client_id": self.strava_client_id,
                    "client_secret": self.strava_client_secret,
                    "code": auth_code,
                    "grant_type": "authorization_code",
                },
            )
            response.raise_for_status()
            tokens = response.json()
            athlete = tokens.get("athlete", {})
            if "access_token" not in tokens or not athlete:
                self.logger.error(
                    f"Invalid response from Strava API: Missing access token or athlete data. {tokens}"
                )
                raise StravaAuthCodeExchangeError(
                    "Invalid response from Strava API: Missing access token or athlete data."
                )
            self.logger.info("Successfully exchanged Strava auth code for tokens.")
            return tokens, athlete
        except requests.RequestException as e:
            self.logger.error(f"Error exchanging Strava auth code: {e}")
            raise StravaAuthCodeExchangeError(f"Error exchanging Strava auth code: {e}")

    def get_athlete_activities(
        self, access_token, per_page=200, after=None, before=None
    ):
        """
        Fetches all athlete activities. By default, pulls activities from the last 7 days unless 'after' or 'before' is specified.
        """
        url = "https://www.strava.com/api/v3/athlete/activities"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        all_activities = []
        page = 1
        request_count = 0
        max_requests = 100

        while True:
            params = {
                "page": page,
                "per_page": per_page,
            }
            if after is not None:
                params["after"] = int(after)
            if before is not None:
                params["before"] = int(before)

            try:
                response = requests.get(url, headers=headers, params=params)
                request_count += 1

                if response.status_code == 429:
                    self.logger.warning("⏳ Rate limit hit. Waiting 15 minutes...")
                    time.sleep(15 * 60)
                    continue  # retry same page

                if not response.ok:
                    self.logger.error(
                        f"Request failed (page {page}): {response.status_code}"
                    )
                    self.logger.error(response.text)
                    break

                data = response.json()
                if not data:
                    break  # No more activities

                all_activities.extend(data)
                page += 1

                if request_count >= max_requests:
                    self.logger.warning("Approaching rate limit. Waiting 15 minutes...")
                    time.sleep(15 * 60)
                    request_count = 0  # reset after wait

            except requests.RequestException as e:
                self.logger.error(f"Error fetching athlete activities: {e}")
                raise StravaAuthCodeExchangeError(
                    f"Error fetching athlete activities: {e}"
                )

        return all_activities

    def get_full_activity_by_id(self, access_token, activity_id):
        url = f"https://www.strava.com/api/v3/activities/{activity_id}"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                self.logger.error(f"Activity with ID {activity_id} not found.")
            elif response.status_code == 401:
                self.logger.error("Unauthorized. Check your access token.")
            else:
                self.logger.error(
                    f"Failed to retrieve activity. Status: {response.status_code}"
                )
                self.logger.error(response.text)
        except requests.RequestException as e:
            self.logger.error(f"Error fetching activity by ID: {e}")
            raise StravaAuthCodeExchangeError(f"Error fetching activity by ID: {e}")

        return None

    def refresh_access_token(self, refresh_token):
        """
        Refresh the Strava access token using the refresh token.
        Returns the new token response dict.
        """
        try:
            response = requests.post(
                "https://www.strava.com/oauth/token",
                data={
                    "client_id": self.strava_client_id,
                    "client_secret": self.strava_client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )
            response.raise_for_status()
            tokens = response.json()
            self.logger.info("Successfully refreshed Strava access token.")
            return tokens
        except requests.RequestException as e:
            self.logger.error(f"Error refreshing Strava access token: {e}")
            raise StravaAuthCodeExchangeError(
                f"Error refreshing Strava access token: {e}"
            )
