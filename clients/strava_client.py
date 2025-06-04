import os
from aws_lambda_powertools import Logger
import boto3
from botocore.exceptions import ClientError
import requests
import json

import boto3
import json


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
