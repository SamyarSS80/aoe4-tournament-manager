from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.validators import UniqueValidator

from aoe_world.serializers import AoeWorldProfileSerializer
from aoe_world.services import AoeWorldAPIService
from jwt_token import jwt_handler
from user.models import User


class UsernamePasswordLoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(username=attrs["username"], password=attrs["password"])
        if not user:
            raise serializers.ValidationError({"detail": "Invalid username or password."})

        token = jwt_handler.create_token(user_id=user.id, username=user.username, is_refresh=False)
        refresh_token = jwt_handler.create_token(user_id=user.id, username=user.username, is_refresh=True)

        return {"token": token, "refresh_token": refresh_token}


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(
        validators=[
            UniqueValidator(queryset=User.objects.all(), message="A user with this username already exists.")
        ]
    )
    password = serializers.CharField(write_only=True, required=True, allow_blank=False)
    code = serializers.CharField(required=True, allow_blank=False, trim_whitespace=True)

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate(self, attrs):
        raw = (attrs.get("code") or "").strip()
        if not raw.isdigit():
            raise serializers.ValidationError({"code": ["code must be a numeric AoE4World profile_id."]})

        profile_id = int(raw)

        try:
            profile_payload = AoeWorldAPIService.get_player_profile(profile_id)
        except NotFound:
            raise serializers.ValidationError({"code": ["AoE4World player not found (invalid code)."]})

        in_game_name = (profile_payload.get("name") or "").strip()
        if not in_game_name:
            raise serializers.ValidationError({"code": ["AoE4World returned no in-game name for this player."]})

        aoe_profile = AoeWorldAPIService.upsert_profile_from_player_profile(
            profile_id=profile_id,
            profile=profile_payload,
        )

        if User.objects.filter(aoe_world_profile=aoe_profile).exists():
            raise serializers.ValidationError({"code": ["A user with this code already exists."]})

        self._aoe_profile = aoe_profile
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        validated_data.pop("code", None)

        user = User(
            username=validated_data["username"],
            aoe_world_profile=self._aoe_profile,
        )
        user.set_password(password)
        user.save()
        return user


class PublicUserSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(source="date_joined", read_only=True)
    aoe_world_profile = AoeWorldProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "aoe_world_profile", "created_at"]
        read_only_fields = fields


class UserSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(source="date_joined", read_only=True)
    password = serializers.CharField(write_only=True, required=False, allow_blank=False)
    aoe_world_profile = AoeWorldProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "password",
            "aoe_world_profile",
            "is_admin",
            "is_staff",
            "created_at",
        ]
        read_only_fields = ["id", "created_at", "aoe_world_profile"]

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)

        for k, v in validated_data.items():
            setattr(instance, k, v)

        if password:
            validate_password(password, user=instance)
            instance.set_password(password)

        instance.save()
        return instance
