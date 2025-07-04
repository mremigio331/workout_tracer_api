import os
from aws_lambda_powertools import Logger
from aws_lambda_powertools.metrics import Metrics, MetricUnit
import boto3
from botocore.exceptions import ClientError
import requests
import json
import time
import datetime
import os

stage = os.getenv("STAGE", "dev")


class StravaAuthCodeExchangeError(Exception):
    pass


class StravaClient:
    def __init__(self, request_id=None):
        self.logger = Logger(service="workout_tracer_api")
        if request_id:
            self.logger.append_keys(request_id=request_id)

        stage = os.getenv("STAGE", "dev")
        self.metrics = Metrics(
            namespace=f"WorkoutTracer-{stage.upper()}", service="workout_tracer_api"
        )

        strava_keys = self.get_strava_api_configs()
        self.strava_client_id = strava_keys[f"{stage.upper()}STRAVA_CLIENT_ID"]
        self.strava_client_secret = strava_keys["{stage.upper()}STRAVA_CLIENT_SECRET"]
        self.callback_url = os.getenv("API_DOMAIN_NAME")
        self.verify_token = strava_keys.get(f"{stage.upper()}_VERIFY_TOKEN")

    def get_strava_api_configs(self):
        client = boto3.client("secretsmanager", region_name="us-west-2")
        response = client.get_secret_value(SecretId="StravaKeys")

        secret = response["SecretString"]
        return json.loads(secret)

    def get_strava_callback_url(self, auth_code):
        self.metrics.add_dimension(name="Endpoint", value="/oauth/token")
        self.metrics.add_metric(name="StravaApiCall", unit=MetricUnit.Count, value=1)
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
            self.metrics.add_metric(
                name="StravaSuccess", unit=MetricUnit.Count, value=1
            )
            return tokens, athlete
        except requests.RequestException as e:
            self.metrics.add_metric(
                name="StravaException", unit=MetricUnit.Count, value=1
            )
            self.logger.error(f"Error exchanging Strava auth code: {e}")
            raise StravaAuthCodeExchangeError(f"Error exchanging Strava auth code: {e}")

    def get_athlete_activities(
        self, access_token, per_page=200, after=None, before=None
    ):
        self.metrics.add_dimension(name="Endpoint", value="/api/v3/athlete/activities")
        self.metrics.add_metric(name="StravaApiCall", unit=MetricUnit.Count, value=1)
        self.logger.info(
            f"Fetching athlete activities with per_page={per_page}, after={after}, before={before}"
        )
        """
        Fetches all athlete activities. By default, pulls all activities unless 'after' or 'before' is specified.
        If 'after' is provided, only activities after that Unix timestamp are returned.
        If 'before' is provided, only activities before that Unix timestamp are returned.
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

            self.logger.debug(f"Requesting page {page} with params: {params}")

            try:
                response = requests.get(url, headers=headers, params=params)
                request_count += 1

                self.logger.debug(
                    f"Received response status: {response.status_code} for page {page}"
                )

                if response.status_code == 429:
                    self.logger.warning("Rate limit hit. Waiting 15 minutes...")
                    time.sleep(15 * 60)
                    continue  # retry same page

                if not response.ok:
                    self.logger.error(
                        f"Request failed (page {page}): {response.status_code}"
                    )
                    self.logger.error(response.text)
                    self.metrics.add_metric(
                        name="StravaException", unit=MetricUnit.Count, value=1
                    )
                    break

                data = response.json()
                self.logger.debug(f"Fetched {len(data)} activities on page {page}")

                if not data:
                    self.logger.info(f"No more activities found after page {page}.")
                    break  # No more activities

                all_activities.extend(data)
                page += 1

                if request_count >= max_requests:
                    self.logger.warning("Approaching rate limit. Waiting 15 minutes...")
                    time.sleep(15 * 60)
                    request_count = 0  # reset after wait

                self.metrics.add_metric(
                    name="StravaSuccess", unit=MetricUnit.Count, value=1
                )
            except requests.RequestException as e:
                self.metrics.add_metric(
                    name="StravaException", unit=MetricUnit.Count, value=1
                )
                self.logger.error(f"Error fetching athlete activities: {e}")
                raise StravaAuthCodeExchangeError(
                    f"Error fetching athlete activities: {e}"
                )

        self.logger.info(f"Total activities fetched: {len(all_activities)}")
        return all_activities

    def get_full_activity_by_id(self, access_token, activity_id):
        self.metrics.add_dimension(name="Endpoint", value="/api/v3/activities")
        self.metrics.add_metric(name="StravaApiCall", unit=MetricUnit.Count, value=1)
        url = f"https://www.strava.com/api/v3/activities/{activity_id}"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                self.metrics.add_metric(
                    name="StravaSuccess", unit=MetricUnit.Count, value=1
                )
                return response.json()
            elif response.status_code == 404:
                self.metrics.add_metric(
                    name="StravaNotFound", unit=MetricUnit.Count, value=1
                )
                self.logger.error(f"Activity with ID {activity_id} not found.")
            elif response.status_code == 401:
                self.metrics.add_metric(
                    name="StravaUnauthorized", unit=MetricUnit.Count, value=1
                )
                self.logger.error("Unauthorized. Check your access token.")
            else:
                self.metrics.add_metric(
                    name="StravaException", unit=MetricUnit.Count, value=1
                )
                self.logger.error(
                    f"Failed to retrieve activity. Status: {response.status_code}"
                )
                self.logger.error(response.text)
        except requests.RequestException as e:
            self.metrics.add_metric(
                name="StravaException", unit=MetricUnit.Count, value=1
            )
            self.logger.error(f"Error fetching activity by ID: {e}")
            raise StravaAuthCodeExchangeError(f"Error fetching activity by ID: {e}")

        return None

    def refresh_access_token(self, refresh_token):
        self.metrics.add_dimension(name="Endpoint", value="/oauth/token")
        self.metrics.add_metric(name="StravaApiCall", unit=MetricUnit.Count, value=1)
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
            self.metrics.add_metric(
                name="StravaSuccess", unit=MetricUnit.Count, value=1
            )

            return tokens
        except requests.RequestException as e:
            self.metrics.add_metric(
                name="StravaException", unit=MetricUnit.Count, value=1
            )

            self.logger.error(f"Error refreshing Strava access token: {e}")
            raise StravaAuthCodeExchangeError(
                f"Error refreshing Strava access token: {e}"
            )

    def create_push_subscription(self, access_token=None):
        self.metrics.add_dimension(name="Endpoint", value="/api/v3/push_subscriptions")
        self.metrics.add_metric(name="StravaApiCall", unit=MetricUnit.Count, value=1)
        """
        Subscribe to Strava push notifications.
        See: https://www.strava.com/api/v3/push_subscriptions
        """
        url = "https://www.strava.com/api/v3/push_subscriptions"
        headers = {
            "Accept": "application/json",
        }
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        data = {
            "client_id": self.strava_client_id,
            "client_secret": self.strava_client_secret,
            "callback_url": f"{self.callback_url}/strava/subscription",
            "verify_token": verify_token,
        }
        try:
            response = requests.post(url, headers=headers, data=data)
            response.raise_for_status()
            self.logger.info("Successfully created Strava push subscription.")
            self.metrics.add_metric(
                name="StravaSuccess", unit=MetricUnit.Count, value=1
            )

            return response.json()
        except requests.RequestException as e:
            self.metrics.add_metric(
                name="StravaException", unit=MetricUnit.Count, value=1
            )

            self.logger.error(f"Error creating Strava push subscription: {e}")
            if hasattr(e, "response") and e.response is not None:
                self.logger.error(f"Response: {e.response.text}")
            raise StravaAuthCodeExchangeError(
                f"Error creating Strava push subscription: {e}"
            )
