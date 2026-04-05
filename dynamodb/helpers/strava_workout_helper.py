from aws_lambda_powertools import Logger
import boto3
from botocore.exceptions import ClientError
from dynamodb.models.strava_workout_model import StravaWorkoutModel
import os
import re
from decimal import Decimal
from datetime import datetime
from typing import Any, List, Dict, Tuple
from constants.general import SERVICE_NAME
from constants.countries import COUNTRIES

# Module-level cache for parsed KML geometries — survives across warm invocations
_KML_GEOMETRY_CACHE: Dict[str, Tuple[List[str], Any]] = (
    {}
)  # kml_file -> (names, STRtree)


class StravaWorkoutHelper:
    """
    Helper class to interact with DynamoDB for Strava workout/activity info.
    """

    def __init__(self, request_id: str = None):
        self.dynamodb = boto3.resource("dynamodb", region_name="us-west-2")
        table_name = os.getenv("TABLE_NAME", "WorkoutTracer-UserTable-Staging")
        self.table = self.dynamodb.Table(table_name)
        self.logger = Logger(service=SERVICE_NAME)
        if request_id:
            self.logger.append_keys(request_id=request_id)
        self.sk = "STRAVA_WORKOUT"
        self._kml_cache: Dict[str, bytes] = {}

    def put_strava_workout(
        self, user_id: int, workout_data: dict
    ) -> tuple[StravaWorkoutModel, str]:
        """
        Create or overwrite a Strava workout in DynamoDB.
        Returns a tuple: (StravaWorkoutModel, "create" or "update")
        Assumes PK is 'USER#{user_id}' and SK is 'STRAVA_WORKOUT#{workout_id}'.
        """
        workout = StravaWorkoutModel(**workout_data)
        workout_id = getattr(workout, "id", None)
        if not workout_id:
            self.logger.error("Workout data must include an 'id' field.")
            raise ValueError("Workout data must include an 'id' field.")

        sk = f"{self.sk}#{workout_id}"
        item = self.convert_floats_to_decimal(workout.dict())
        item["PK"] = f"USER#{user_id}"
        item["SK"] = sk

        try:
            self.logger.info(
                f"Attempting to put workout for user_id={user_id}, workout_id={workout_id}"
            )
            self.logger.debug(f"Incoming workout_data: {workout_data}")

            before_item = self.table.get_item(
                Key={"PK": f"USER#{user_id}", "SK": sk}
            ).get("Item")
            action = "update" if before_item else "create"
            self.table.put_item(Item=item)
            self.logger.debug(
                f"Sucessfully Put Strava workout {workout_id} for {user_id}"
            )

            enrich_sqs_url = os.getenv("ENRICH_SQS_QUEUE_URL")
            if enrich_sqs_url:
                try:
                    import json

                    boto3.client("sqs").send_message(
                        QueueUrl=enrich_sqs_url,
                        MessageBody=json.dumps(
                            {"user_id": user_id, "workout_id": workout_id}
                        ),
                        MessageGroupId=str(user_id),
                    )
                except Exception as e:
                    self.logger.error(
                        f"Failed to enqueue workout {workout_id} for enrichment: {e}"
                    )

            return workout, action
        except ClientError as e:
            self.logger.error(f"Error putting Strava workout for {user_id}: {e}")
            self.logger.error(f"Workout data that caused error: {workout_data}")
            self.logger.error(f"Item that caused error: {item}")
            raise
        except Exception as e:
            self.logger.error(
                f"Unexpected error in put_strava_workout for user_id: {user_id}: {e}"
            )
            self.logger.error(f"Workout data that caused error: {workout_data}")
            self.logger.error(f"Item that caused error: {item}")
            raise

    def get_strava_workout(self, user_id: str, workout_id: int = None) -> dict | None:
        """
        Retrieve Strava workout from DynamoDB and return as a JSON-serializable dict.
        If workout_id is provided, fetch that specific workout.
        """
        try:
            sk = f"{self.sk}#{workout_id}" if workout_id else self.sk
            response = self.table.get_item(Key={"PK": f"USER#{user_id}", "SK": sk})
            item = response.get("Item")
            if not item:
                self.logger.warning(
                    f"No Strava workout found for user_id: {user_id}, workout_id: {workout_id}"
                )
                return None
            item.pop("PK", None)
            item.pop("SK", None)
            return self._decimals_to_floats(item)
        except ClientError as e:
            self.logger.error(
                f"Error retrieving Strava workout: {e.response['Error']['Message']}"
            )
            return None
        except Exception as e:
            self.logger.error(
                f"Unexpected error in get_strava_workout for user_id: {user_id}: {e}"
            )
            return None

    def get_all_workout_ids(self, user_id: str) -> List[int]:
        """
        Retrieve all Strava workout IDs for a user.
        Returns a list of workout IDs.
        """
        try:
            ids = []
            query_kwargs = {
                "KeyConditionExpression": boto3.dynamodb.conditions.Key("PK").eq(
                    f"USER#{user_id}"
                )
                & boto3.dynamodb.conditions.Key("SK").begins_with(f"{self.sk}#"),
                "ProjectionExpression": "SK",
            }
            while True:
                response = self.table.query(**query_kwargs)
                ids.extend(
                    int(item["SK"].split("#")[-1])
                    for item in response.get("Items", [])
                    if "SK" in item
                )
                last_key = response.get("LastEvaluatedKey")
                if not last_key:
                    break
                query_kwargs["ExclusiveStartKey"] = last_key
            return ids
        except ClientError as e:
            self.logger.error(
                f"Error retrieving all Strava workout IDs for user_id {user_id}: {e}"
            )
            return []
        except Exception as e:
            self.logger.error(
                f"Unexpected error in get_all_workout_ids for user_id: {user_id}: {e}"
            )
            return []

    def get_all_workout_locations(self, user_id: str) -> dict:
        """
        Returns a summary of all locations a user has worked out in, broken down
        by sport type and total count.

        Example:
        {
            "locations": {
                "countries": {
                    "United States of America": {"Run": 23, "Walk": 5, "total": 28}
                },
                "states": {
                    "Washington": {"Run": 23, "Walk": 5, "total": 28}
                }
            }
        }
        """
        try:
            summary: Dict[str, Dict[str, Dict[str, int]]] = {
                "countries": {},
                "states": {},
            }
            next_token = None
            while True:
                result = self.get_all_workouts(
                    user_id,
                    next_token=next_token,
                    projection_expression="#loc, sport_type",
                    expression_attribute_names={"#loc": "locations"},
                )
                for workout in result.get("workouts", []):
                    sport_type = workout.get("sport_type") or "Unknown"
                    locations = workout.get("locations") or {}
                    for location_type in ("states", "countries"):
                        for name, visited in (
                            locations.get(location_type) or {}
                        ).items():
                            if not visited:
                                continue
                            entry = summary[location_type].setdefault(
                                name, {"total": 0}
                            )
                            entry[sport_type] = entry.get(sport_type, 0) + 1
                            entry["total"] += 1

                next_token = result.get("next_token")
                if not next_token:
                    break

            return {"locations": summary}
        except ClientError as e:
            self.logger.error(
                f"Error retrieving workout locations for user_id {user_id}: {e}"
            )
            return {"locations": {"countries": {}, "states": {}}}
        except Exception as e:
            self.logger.error(
                f"Unexpected error in get_all_workout_locations for user_id: {user_id}: {e}"
            )
            return {"locations": {"countries": {}, "states": {}}}

    def get_all_workouts(
        self,
        user_id: str,
        limit: int = 500,
        next_token: dict = None,
        projection_expression: str = None,
        expression_attribute_names: dict = None,
    ) -> dict:
        """
        Retrieve up to 'limit' Strava workouts for a user.
        Returns a dict: { "workouts": [...], "next_token": ... }
        If DynamoDB returns a LastEvaluatedKey, it is returned as next_token.
        Optional projection_expression and expression_attribute_names can be
        passed to fetch only specific fields.
        """
        try:
            query_kwargs = {
                "KeyConditionExpression": boto3.dynamodb.conditions.Key("PK").eq(
                    f"USER#{user_id}"
                )
                & boto3.dynamodb.conditions.Key("SK").begins_with(f"{self.sk}#"),
                "Limit": limit,
            }
            if next_token:
                query_kwargs["ExclusiveStartKey"] = next_token
            if projection_expression:
                query_kwargs["ProjectionExpression"] = projection_expression
            if expression_attribute_names:
                query_kwargs["ExpressionAttributeNames"] = expression_attribute_names

            response = self.table.query(**query_kwargs)
            items = response.get("Items", [])
            workouts = [self._decimals_to_floats(item) for item in items]
            result = {"workouts": workouts}
            last_evaluated_key = response.get("LastEvaluatedKey")

            # Debug logging
            self.logger.debug(f"ExclusiveStartKey: {next_token}")
            self.logger.debug(f"LastEvaluatedKey: {last_evaluated_key}")

            # Only return next_token if there are items AND a LastEvaluatedKey
            if items and last_evaluated_key:
                # Guard: If LastEvaluatedKey is same as ExclusiveStartKey, break loop
                if next_token and last_evaluated_key == next_token:
                    self.logger.warning(
                        "LastEvaluatedKey is same as ExclusiveStartKey, breaking pagination loop."
                    )
                    result["next_token"] = None
                else:
                    result["next_token"] = last_evaluated_key
            else:
                result["next_token"] = None
            return result
        except ClientError as e:
            self.logger.error(
                f"Error retrieving all Strava workouts for user_id {user_id}: {e}"
            )
            return {"workouts": [], "next_token": None}
        except Exception as e:
            self.logger.error(
                f"Unexpected error in get_all_workouts for user_id: {user_id}: {e}"
            )
            return {"workouts": [], "next_token": None}

    def delete_strava_workout(self, user_id: str, workout_id: int) -> bool:
        """
        Delete a Strava workout from DynamoDB.
        Returns True if deletion was successful, False otherwise.
        """
        sk = f"{self.sk}#{workout_id}"
        try:
            response = self.table.delete_item(
                Key={"PK": f"USER#{user_id}", "SK": sk}, ReturnValues="ALL_OLD"
            )
            if "Attributes" in response:
                self.logger.info(
                    f"Successfully deleted Strava workout {workout_id} for user_id {user_id}"
                )
                return True
            else:
                self.logger.warning(
                    f"No Strava workout found for user_id: {user_id}, workout_id: {workout_id}"
                )
                return False
        except ClientError as e:
            self.logger.error(
                f"Error deleting Strava workout for user_id {user_id}, workout_id {workout_id}: {e}"
            )
            return False

    def get_location_badges(
        self, workout_polyline: str, kml_file_name: str
    ) -> Dict[str, bool]:
        """
        Given an encoded polyline and a KML file name in S3, returns a dict
        mapping each location name to True/False based on route intersection.
        Uses an STRtree spatial index so only candidate polygons whose bounding
        boxes overlap the route are checked precisely.
        KML bytes are cached on the instance to avoid redundant S3 fetches within
        the same Lambda invocation.
        """
        import polyline as polyline_lib
        from lxml import etree
        from shapely.geometry import LineString, Polygon
        from shapely.ops import unary_union
        from shapely.strtree import STRtree

        try:
            if kml_file_name not in _KML_GEOMETRY_CACHE:
                self.logger.info(f"Building geometry index for {kml_file_name} (cold)")
                if kml_file_name not in self._kml_cache:
                    s3 = boto3.client("s3", region_name="us-west-2")
                    bucket = "workout-tracer-kml-files-851753231474-us-west-2-an"
                    self._kml_cache[kml_file_name] = s3.get_object(
                        Bucket=bucket, Key=kml_file_name
                    )["Body"].read()

                xml_tree = etree.fromstring(self._kml_cache[kml_file_name])
                ns = {"kml": "http://www.opengis.net/kml/2.2"}
                names = []
                geometries = []
                for placemark in xml_tree.findall(".//kml:Placemark", ns):
                    raw_name = placemark.findtext("kml:name", namespaces=ns)
                    name = re.sub(r"<[^>]+>", "", raw_name).strip()
                    if name in COUNTRIES:
                        name = COUNTRIES[name]
                    polys = []
                    for coord_el in placemark.findall(".//kml:coordinates", ns):
                        pts = [
                            (float(x), float(y))
                            for x, y, *_ in (
                                c.split(",") for c in coord_el.text.strip().split()
                            )
                        ]
                        if len(pts) >= 3:
                            polys.append(Polygon(pts))
                    if polys:
                        names.append(name)
                        geometries.append(unary_union(polys))

                _KML_GEOMETRY_CACHE[kml_file_name] = (names, STRtree(geometries))
                self.logger.info(
                    f"Geometry index built for {kml_file_name}: {len(names)} regions"
                )
            else:
                self.logger.info(
                    f"Using cached geometry index for {kml_file_name} (warm)"
                )

            names, spatial_index = _KML_GEOMETRY_CACHE[kml_file_name]
            coords = polyline_lib.decode(workout_polyline)
            line = LineString([(lon, lat) for lat, lon in coords])

            results = {name: False for name in names}
            for idx in spatial_index.query(line, predicate="intersects"):
                results[names[idx]] = True

            matched = [name for name, hit in results.items() if hit]
            self.logger.info(
                f"Location badges matched for kml_file={kml_file_name}: {matched}"
            )
            return results
        except Exception as e:
            self.logger.error(
                f"Error in get_location_badges for kml_file={kml_file_name}: {e}"
            )
            return {}

    def update_workout_locations(
        self, user_id: str, workout_id: int, locations: dict
    ) -> bool:
        """
        Updates only the `locations` field on a stored workout in DynamoDB.
        `locations` should be a dict like {"states": {...}, "countries": {...}}.
        """
        sk = f"{self.sk}#{workout_id}"
        try:
            self.table.update_item(
                Key={"PK": f"USER#{user_id}", "SK": sk},
                UpdateExpression="SET #loc = :locations",
                ExpressionAttributeNames={"#loc": "locations"},
                ExpressionAttributeValues={":locations": locations},
            )
            self.logger.info(
                f"Updated locations for workout {workout_id}, user {user_id}"
            )
            return True
        except ClientError as e:
            self.logger.error(
                f"Error updating locations for workout {workout_id}, user {user_id}: {e}"
            )
            return False
        except Exception as e:
            self.logger.error(
                f"Unexpected error updating locations for workout {workout_id}, user {user_id}: {e}"
            )
            return False

    @staticmethod
    def convert_floats_to_decimal(obj):
        """
        Recursively convert all float values in a dict or list to Decimal,
        and all datetime objects to ISO 8601 strings.
        """
        if isinstance(obj, dict):
            return {
                k: StravaWorkoutHelper.convert_floats_to_decimal(v)
                for k, v in obj.items()
            }
        elif isinstance(obj, list):
            return [StravaWorkoutHelper.convert_floats_to_decimal(v) for v in obj]
        elif isinstance(obj, float):
            return Decimal(str(obj))
        elif isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, Decimal):
            return obj
        else:
            return obj

    @staticmethod
    def _decimals_to_floats(obj):
        """
        Recursively convert all Decimal values in a dict or list to float for JSON serialization.
        """
        if isinstance(obj, dict):
            return {
                k: StravaWorkoutHelper._decimals_to_floats(v) for k, v in obj.items()
            }
        elif isinstance(obj, list):
            return [StravaWorkoutHelper._decimals_to_floats(v) for v in obj]
        elif isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        else:
            return obj

    @staticmethod
    def serialize_model(model: Any) -> dict:
        if model is None:
            return None
        if isinstance(model, dict):
            return {k: StravaWorkoutHelper.serialize_model(v) for k, v in model.items()}
        elif isinstance(model, list):
            return [StravaWorkoutHelper.serialize_model(i) for i in model]
        elif isinstance(model, datetime):
            return model.isoformat()
        elif isinstance(model, Decimal):
            return float(model)
        elif hasattr(model, "dict"):
            return StravaWorkoutHelper.serialize_model(model.dict())
        return model
