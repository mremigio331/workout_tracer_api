from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional
from boto3.dynamodb.types import TypeDeserializer


class UserProfileModel(BaseModel):
    user_id: str
    email: EmailStr
    name: str
    created_at: datetime
    public_profile: bool = False

    strava_id: Optional[str] = None
    strava_access_token: Optional[str] = None
    strava_refresh_token: Optional[str] = None
    strava_token_expires_at: Optional[int] = None
    strava_connected_at: Optional[datetime] = None
    strava_sync_enabled: bool = False

    def to_dynamodb(self) -> dict:
        item = {
            "PK": f"#USER:{self.user_id}",
            "SK": "PROFILE",
            "email": self.email,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
            "public_profile": self.public_profile,
        }

        if self.strava_id:
            item["strava_id"] = {"S": self.strava_id}
        if self.strava_access_token:
            item["strava_access_token"] = {"S": self.strava_access_token}
        if self.strava_refresh_token:
            item["strava_refresh_token"] = {"S": self.strava_refresh_token}
        if self.strava_token_expires_at is not None:
            item["strava_token_expires_at"] = {"N": str(self.strava_token_expires_at)}
        if self.strava_connected_at:
            item["strava_connected_at"] = {"S": self.strava_connected_at.isoformat()}
        if self.strava_sync_enabled:
            item["strava_sync_enabled"] = {"BOOL": self.strava_sync_enabled}

        return item

    @classmethod
    def from_dynamodb(cls, item: dict) -> "UserProfileModel":
        """Converts a raw DynamoDB item into a UserProfileModel instance"""
        return cls(
            user_id=item["PK"]["S"].replace("#USER:", ""),
            email=item["email"]["S"],
            name=item["name"]["S"],
            created_at=datetime.fromisoformat(item["created_at"]["S"]),
            public_profile=item.get("public_profile", {}).get("BOOL", False),
            strava_id=item.get("strava_id", {}).get("S"),
            strava_access_token=item.get("strava_access_token", {}).get("S"),
            strava_refresh_token=item.get("strava_refresh_token", {}).get("S"),
            strava_token_expires_at=(
                int(item["strava_token_expires_at"]["N"])
                if "strava_token_expires_at" in item
                else None
            ),
            strava_connected_at=(
                datetime.fromisoformat(item["strava_connected_at"]["S"])
                if "strava_connected_at" in item
                else None
            ),
            strava_sync_enabled=item.get("strava_sync_enabled", {}).get("BOOL", False),
        )
