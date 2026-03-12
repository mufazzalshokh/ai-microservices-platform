from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import EmailStr, Field, field_validator

from shared.models import AppModel


class RegisterRequest(AppModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=100)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class LoginRequest(AppModel):
    email: EmailStr
    password: str


class RefreshRequest(AppModel):
    refresh_token: str


class TokenResponse(AppModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(AppModel):
    id: uuid.UUID
    email: str
    is_active: bool
    created_at: datetime
