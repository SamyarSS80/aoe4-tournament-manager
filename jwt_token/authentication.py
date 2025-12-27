from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.authentication import BaseAuthentication
from rest_framework import exceptions as drf_exceptions

from jwt_token import jwt_handler, exceptions


class JWTAuthentication(BaseAuthentication):
    """
    Authorization: Bearer <access_token>
    """

    def authenticate(self, request):
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return None

        try:
            token_type, token = auth_header.split()
        except ValueError:
            return None

        if token_type.lower() != settings.JWT_AUTH_HEADER_PREFIX.lower():
            return None

        try:
            payload = jwt_handler.verify_token(token, required_type=jwt_handler.TOKEN_TYPE_ACCESS)
            user_id = payload.get("user_id")
            if not user_id:
                raise drf_exceptions.AuthenticationFailed("Invalid token payload")

            User = get_user_model()
            user = User.objects.get(pk=user_id)
            return (user, token)

        except exceptions.ExpiredSignatureError:
            raise drf_exceptions.AuthenticationFailed("Token has expired")
        except exceptions.InvalidTokenError:
            raise drf_exceptions.AuthenticationFailed("Invalid token")
        except get_user_model().DoesNotExist:
            raise drf_exceptions.AuthenticationFailed("User not found")

    def authenticate_header(self, request):
        return f"{settings.JWT_AUTH_HEADER_PREFIX}"
