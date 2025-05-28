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

    def to_dynamodb(self) -> dict:
        item = {
            "PK": f"#USER:{self.user_id}",
            "SK": "PROFILE",
            "email": self.email,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
            "public_profile": self.public_profile,
        }
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
        )
