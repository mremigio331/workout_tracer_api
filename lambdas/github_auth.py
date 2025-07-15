import os
import hmac
import hashlib
import base64
import boto3
import json
from aws_lambda_powertools import Logger


class GitHubWebhookAuthorizer:
    def __init__(self):
        self.logger = Logger(service="workout-tracer-github-webhook-authorizer")
        self.secret_name = "GithubToken"
        self.region_name = "us-west-2"

    def get_github_secret(self):
        client = boto3.client("secretsmanager", region_name=self.region_name)
        response = client.get_secret_value(SecretId=self.secret_name)
        secret_dict = json.loads(response["SecretString"])
        return secret_dict["WORKOUT_TRACER_WEBHOOK"]

    def handler(self, event, context):
        request_id = getattr(context, "aws_request_id", None)
        self.logger.append_keys(request_id=request_id)

        headers = event.get("headers", {})
        signature_header = headers.get("X-Hub-Signature-256") or headers.get(
            "x-hub-signature-256"
        )
        self.logger.info(f"Signature from GitHub: {signature_header!r}")

        if not signature_header or not signature_header.startswith("sha256="):
            self.logger.warning("Missing or malformed signature header.")
            return self._deny(event["methodArn"])

        received_sig = signature_header.split("=")[1]

        # Step 1: Get body (decode if base64)
        raw_body = event.get("body", "")
        if event.get("isBase64Encoded"):
            raw_body = base64.b64decode(raw_body)
        else:
            raw_body = raw_body.encode()

        self.logger.info(f"Raw request body: {raw_body[:150]}...")

        # Step 2: Get secret
        secret = self.get_github_secret().encode()

        # Step 3: Compute expected signature
        expected_sig = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()
        self.logger.info(f"Computed signature: sha256={expected_sig}")

        # Step 4: Compare
        if hmac.compare_digest(received_sig, expected_sig):
            self.logger.info("Signature match. Authorized.")
            return self._allow(event["methodArn"])
        else:
            self.logger.warning("Signature mismatch. Denying.")
            return self._deny(event["methodArn"])

    def _allow(self, method_arn):
        return {
            "principalId": "github",
            "policyDocument": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Action": "execute-api:Invoke",
                        "Effect": "Allow",
                        "Resource": method_arn,
                    }
                ],
            },
        }

    def _deny(self, method_arn):
        return {
            "principalId": "unauthorized",
            "policyDocument": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Action": "execute-api:Invoke",
                        "Effect": "Deny",
                        "Resource": method_arn,
                    }
                ],
            },
        }


# Lambda entrypoint
authorizer = GitHubWebhookAuthorizer()


def handler(event, context):
    return authorizer.handler(event, context)
