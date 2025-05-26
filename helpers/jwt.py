import base64
import json
from exceptions.jwt_exeptions import InvalidJWTException
import configparser
import os
from aws_lambda_powertools import Logger
from starlette.requests import Request as StarletteRequest
import boto3

logger = Logger(service="workout-tracer-api")


def decode_jwt(token: str) -> dict:
    """
    Decodes a JWT token without verifying the signature.
    Use only for extracting claims; do not trust the data for authentication/authorization.
    """
    try:
        payload = token.split(".")[1]
        # Pad base64 if needed
        padding = "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload + padding)
        return json.loads(decoded)
    except Exception as e:
        raise InvalidJWTException(f"Invalid JWT: {e}")


def inject_dev_token():
    config = configparser.ConfigParser()
    # dev_creds.cfg is in the workout_tracer_api directory (NOT helpers)
    cfg_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dev_creds.cfg")
    logger.info(f"Injecting dev token: Reading config from {cfg_path}")
    config.read(cfg_path)
    id_token = config.get("default", "id_token", fallback=None)
    if id_token:
        orig_init = StarletteRequest.__init__
        def new_init(self, *args, **kwargs):
            scope = args[0]
            headers = list(scope.get("headers", []))
            if not any(k == b"authorization" for k, v in headers):
                headers.append(
                    (b"authorization", f"Bearer {id_token}".encode("latin-1"))
                )
                scope["headers"] = headers
            orig_init(self, *args, **kwargs)
        StarletteRequest.__init__ = new_init
        logger.info("Injecting dev token: Authorization header will be injected into all requests.")
    else:
        logger.warning("Injecting dev token: No id_token found in dev_creds.cfg.")


def update_cognito_user_attributes(
    user_pool_id: str, user_id: str, name: str = None, email: str = None
):
    """
    Update the name and/or email attributes for a user in Cognito User Pool.
    """
    client = boto3.client("cognito-idp", region_name="us-west-2")

    attributes = []
    if name is not None:
        attributes.append({"Name": "name", "Value": name})
    if email is not None:
        attributes.append({"Name": "email", "Value": email})
    if not attributes:
        return

    response = client.admin_update_user_attributes(
        UserPoolId=user_pool_id, Username=user_id, UserAttributes=attributes
    )
    logger.info(f"Updated Cognito user {user_id} attributes: {attributes}")
    return response
