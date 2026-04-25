from typing import Optional, List
from pydantic import BaseModel, Field
from dynamodb.models.strava_workout_model import WorkoutLocations


class AppleHealthWorkoutModel(BaseModel):
    # Core fields
    workout_uuid: str
    workout_activity_type: Optional[str] = None
    workout_activity_type_raw: Optional[int] = None
    name: Optional[str] = None
    duration: Optional[float] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    source: str = "apple_health"

    # Statistics
    active_energy_burned: Optional[float] = None
    distance: Optional[float] = None
    swimming_stroke_count: Optional[int] = None
    flights_climbed: Optional[int] = None
    step_count: Optional[int] = None

    # Metadata
    elevation_ascended: Optional[float] = None
    elevation_descended: Optional[float] = None
    average_speed: Optional[float] = None
    maximum_speed: Optional[float] = None
    average_mets: Optional[float] = None
    is_indoor_workout: Optional[bool] = None
    swimming_location_type: Optional[str] = None
    lap_length: Optional[float] = None
    workout_brand_name: Optional[str] = None

    # Heart rate
    average_heartrate: Optional[float] = None
    max_heartrate: Optional[float] = None

    # Route
    summary_polyline: Optional[str] = None
    start_latlng: Optional[List[float]] = None

    # Location enrichment
    locations: WorkoutLocations = Field(default_factory=WorkoutLocations)

    @staticmethod
    def create_pk(user_id: str) -> str:
        return f"USER#{user_id}"

    @staticmethod
    def create_sk(workout_uuid: str) -> str:
        return f"APPLE_HEALTH_WORKOUT#{workout_uuid}"

    def to_strava_format(self) -> dict:
        """Convert Apple Health workout to Strava-compatible format for unified rendering."""
        return {
            "id": self.workout_uuid,
            "name": self.name,
            "type": self.workout_activity_type,
            "sport_type": self.workout_activity_type,
            "start_date": self.start_date,
            "start_date_local": self.start_date,
            "distance": self.distance,
            "total_elevation_gain": self.elevation_ascended,
            "moving_time": int(self.duration) if self.duration else None,
            "elapsed_time": int(self.duration) if self.duration else None,
            "kilojoules": (
                (self.active_energy_burned / 0.239006)
                if self.active_energy_burned
                else None
            ),
            "map": {"summary_polyline": self.summary_polyline},
            "locations": self.locations.dict() if self.locations else None,
            "source": "apple_health",
        }
