import jwt
from datetime import datetime, timedelta
from django.conf import settings

from . import exceptions


class JWTHandler:
    TOKEN_TYPE_ACCESS = "access"
    TOKEN_TYPE_REFRESH = "refresh"

    def __init__(self):
        self.secret_key = settings.JWT_SECRET_KEY
        self.algorithm = settings.JWT_ALGORITHM
        self.expiration_minutes = settings.JWT_EXPIRATION_MINUTES
        self.refresh_expiration_minutes = settings.JWT_REFRESH_EXPIRATION_MINUTES

    def create_token(self, *, user_id: int, username: str, is_refresh: bool = False) -> str:
        expiration_time = datetime.utcnow() + timedelta(
            minutes=self.refresh_expiration_minutes if is_refresh else self.expiration_minutes
        )

        payload = {
            "user_id": user_id,
            "username": username,
            "exp": expiration_time,
            "iat": datetime.utcnow(),
            "type": self.TOKEN_TYPE_REFRESH if is_refresh else self.TOKEN_TYPE_ACCESS,
        }

        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def verify_token(self, token: str, required_type: str = TOKEN_TYPE_ACCESS) -> dict:
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            if payload.get("type") != required_type:
                raise exceptions.InvalidTokenError("Token type mismatch")
            return payload
        except jwt.ExpiredSignatureError:
            raise exceptions.ExpiredSignatureError("Token has expired")
        except jwt.InvalidTokenError:
            raise exceptions.InvalidTokenError("Invalid token")

    def refresh_token(self, token: str) -> str:
        payload = self.verify_token(token, required_type=self.TOKEN_TYPE_REFRESH)
        return self.create_token(user_id=payload["user_id"], username=payload["username"], is_refresh=False)
