import os
import hmac
import hashlib
import base64

def handler(event, context):
    headers = event["headers"]
    signature = headers.get("x-hub-signature-256")
    body = event.get("body", "")
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode()

    secret = os.environ["GITHUB_SECRET"]
    computed_sig = "sha256=" + hmac.new(
        secret.encode(), body.encode(), hashlib.sha256
    ).hexdigest()

    if hmac.compare_digest(computed_sig, signature or ""):
        return {
            "principalId": "github",
            "policyDocument": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Action": "execute-api:Invoke",
                        "Effect": "Allow",
                        "Resource": event["methodArn"],
                    }
                ],
            },
        }

    return {
        "principalId": "unauthorized",
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "execute-api:Invoke",
                    "Effect": "Deny",
                    "Resource": event["methodArn"],
                }
            ],
        },
    }
