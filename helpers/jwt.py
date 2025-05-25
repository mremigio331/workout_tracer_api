import base64
import json
from exceptions.jwt_exeptions import InvalidJWTException


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
