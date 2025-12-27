from rest_framework import serializers, exceptions as drf_exceptions

from jwt_token import jwt_handler, exceptions


class JsonWebTokenSerializer(serializers.Serializer):
    token = serializers.CharField()

    def validate(self, attrs):
        token = attrs["token"]
        try:
            payload = jwt_handler.verify_token(token, required_type=jwt_handler.TOKEN_TYPE_ACCESS)
        except exceptions.ExpiredSignatureError:
            raise drf_exceptions.ValidationError("Signature has expired.")
        except exceptions.InvalidTokenError:
            raise drf_exceptions.ValidationError("Invalid signature.")
        return payload


class JsonWebTokenRefreshSerializer(serializers.Serializer):
    token = serializers.CharField()

    def validate(self, attrs):
        token = attrs["token"]
        try:
            new_token = jwt_handler.refresh_token(token)
        except exceptions.ExpiredSignatureError:
            raise drf_exceptions.ValidationError("Signature has expired.")
        except exceptions.InvalidTokenError:
            raise drf_exceptions.ValidationError("Invalid signature.")
        return {"token": new_token}
