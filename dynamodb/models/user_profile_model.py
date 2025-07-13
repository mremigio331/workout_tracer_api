from pydantic import BaseModel, EmailStr, field_validator
from datetime import datetime
from typing import Optional
from boto3.dynamodb.types import TypeDeserializer


class UserProfileModel(BaseModel):
    user_id: str
    email: EmailStr
    name: str
    created_at: str
    public_profile: bool = False
    beta_featues: bool = False
    distance_unit: str = "Imperial"  # "Imperial" for miles/feet, "Metric" for km/m

    @field_validator("distance_unit")
    def validate_distance_unit(cls, v):
        # Accept both legacy and new values, normalize to "Imperial" or "Metric"
        valid = {
            "imperial": "Imperial",
            "metric": "Metric",
            "Imperial": "Imperial",
            "Metric": "Metric",
            "miles": "Imperial",
            "Miles": "Imperial",
            "kilometers": "Metric",
            "Kilometers": "Metric",
        }
        if v not in valid:
            raise ValueError("distance_unit must be 'Imperial' or 'Metric'")
        return valid[v]
