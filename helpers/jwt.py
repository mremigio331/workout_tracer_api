import base64
import json
from exceptions.jwt_exeptions import InvalidJWTException
import configparser
import os
from aws_lambda_powertools import Logger
from starlette.requests import Request as StarletteRequest

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
    # dev_creds.cfg is in the same directory as this file
    cfg_path = os.path.join(os.path.dirname(__file__), "dev_creds.cfg")
    abs_cfg_path = os.path.abspath(cfg_path)
    logger.info(f"Injecting dev token: Reading config from {abs_cfg_path}")
    config.read(abs_cfg_path)
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