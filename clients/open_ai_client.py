import os
import openai
import re
import json
import boto3
from aws_lambda_powertools import Logger, Metrics
from aws_lambda_powertools.metrics import MetricUnit

stage = os.getenv("STAGE", "dev")
metrics = Metrics(
    namespace=f"WorkoutTracer-{stage.upper()}", service="workout_tracer_api"
)


class OpenAIClient:
    """
    Client for interacting with the OpenAI API.
    """

    def __init__(self, request_id=None, default_model: str = "gpt-4-turbo"):
        self.logger = Logger(service="workout_tracer_api")
        if request_id:
            self.logger.append_keys(request_id=request_id)

        self.api_key = self._get_api_key_from_secrets_manager()
        self.default_model = default_model
        self.client = openai.OpenAI(api_key=self.api_key)

    def _get_api_key_from_secrets_manager(self):
        secret_name = "OpenAI"
        region_name = os.getenv("AWS_REGION", "us-west-2")
        session = boto3.session.Session()
        client = session.client(service_name="secretsmanager", region_name=region_name)
        try:
            get_secret_value_response = client.get_secret_value(SecretId=secret_name)
            secret = get_secret_value_response["SecretString"]
            secret_dict = json.loads(secret)
            self.logger.info(
                "Successfully retrieved OpenAI API key from Secrets Manager"
            )
            return secret_dict.get("api_key")
        except Exception as e:
            self.logger.error(
                f"Error retrieving OpenAI API key from Secrets Manager: {e}"
            )
            metrics.add_metric(
                name="SecretsManagerError", unit=MetricUnit.Count, value=1
            )
            return None

    def get_activity_equivalents(
        self,
        activity_data: dict,
        focus_area: str = "Pacific Northwest",
        model: str = None,
        temperature: float = 0.7,
    ) -> dict:
        """
        Sends a single API request to ChatGPT to generate real-world equivalents
        for distance and elevation for each activity.

        :param activity_data: Dictionary of activity stats with distance in miles and elevation in meters
        :param focus_area: Region to focus on for equivalents
        :param model: OpenAI model to use (default: self.default_model)
        :param temperature: Sampling temperature
        :return: Parsed JSON response from GPT (or empty dict on error)
        """
        model = model or self.default_model

        prompt = (
            "Given the following fitness stats, return a JSON object mapping each activity "
            "to distance and elevation equivalents from real-world landmarks. "
            f"Focus on the {focus_area} first, then the U.S., then the world.\n\n"
        )

        for activity, stats in activity_data.items():
            if not isinstance(activity, str):
                continue
            distance = stats.get("distance", {}).get("miles", 0)
            elevation = stats.get("elevation", {}).get("meters", 0)
            if distance == 0 and elevation == 0:
                continue
            prompt += f"- {activity}: {distance} miles, {elevation} meters elevation\n"

        prompt += (
            "\nFormat your response like this:\n"
            "{\n"
            '  "running": {\n'
            '    "distance_equivalent": [...],\n'
            '    "elevation_equivalent": [...],\n'
            '    "comments": [...]\n'
            "  }, ...\n"
            "}\n"
        )

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that compares fitness activity data to real-world geography.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
            )
            content = response.choices[0].message.content
            metrics.add_metric(name="OpenAISuccess", unit=MetricUnit.Count, value=1)
        except Exception as e:
            self.logger.error(f"OpenAI API call failed: {e}")
            metrics.add_metric(name="OpenAIError", unit=MetricUnit.Count, value=1)
            return {}

        try:
            json_str = re.search(r"\{.*\}", content, re.DOTALL).group(0)
            self.logger.info("Successfully parsed JSON from OpenAI response")
            return json.loads(json_str)
        except Exception as e:
            self.logger.error(f"Failed to parse JSON from GPT response: {e}")
            self.logger.debug(f"Raw GPT output:\n{content}")
            metrics.add_metric(name="OpenAIParseError", unit=MetricUnit.Count, value=1)
            return {}
