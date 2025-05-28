import boto3
import json


def get_strava_api_configs():
    client = boto3.client("secretsmanager", region_name="us-west-2")
    response = client.get_secret_value(SecretId="StravaKeys")

    secret = response["SecretString"]
    return json.loads(secret)
