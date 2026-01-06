from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.validators import UniqueValidator

from aoe_world.serializers import AoeWorldProfileSerializer
from aoe_world.services import AoeWorldAPIService
from jwt_token import jwt_handler
from user import consts
from user.models import User, UserAvailability


class DayNameField(serializers.Field):
    def to_representation(self, value):
        try:
            return consts.INT_TO_DAY_NAME[int(value)]
        except Exception:
            return None

    def to_internal_value(self, data):
        raw = (data or "").strip().lower()
        if raw not in consts.DAY_NAME_TO_INT:
            raise serializers.ValidationError(
                f"Invalid day. Valid values: {', '.join(consts.VALID_DAY_NAMES)}."
            )
        return consts.DAY_NAME_TO_INT[raw]


class PlainTimeField(serializers.TimeField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("format", "%H:%M:%S")
        kwargs.setdefault("input_formats", ["%H:%M:%S", "%H:%M:%S.%f", "iso-8601"])
        super().__init__(*args, **kwargs)

    def to_internal_value(self, data):
        if isinstance(data, str):
            raw = data.strip()

            if "T" in raw:
                raw = raw.split("T", 1)[1]

            if raw.endswith("Z") or raw.endswith("z"):
                raw = raw[:-1]

            # strip timezone offset if present (e.g. +00:00, -03:30)
            if "+" in raw:
                raw = raw.split("+", 1)[0]
            else:
                # careful: times don't start with '-', so any '-' likely offset
                if "-" in raw[1:]:
                    left, right = raw.split("-", 1)
                    if ":" in right:
                        raw = left

            data = raw

        return super().to_internal_value(data)


class UsernamePasswordLoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(username=attrs["username"], password=attrs["password"])
        if not user:
            raise serializers.ValidationError(
                {"detail": "Invalid username or password."}
            )

        token = jwt_handler.create_token(
            user_id=user.id, username=user.username, is_refresh=False
        )
        refresh_token = jwt_handler.create_token(
            user_id=user.id, username=user.username, is_refresh=True
        )

        return {"token": token, "refresh_token": refresh_token}


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(
        validators=[
            UniqueValidator(
                queryset=User.objects.all(),
                message="A user with this username already exists.",
            )
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
            raise serializers.ValidationError(
                {"code": ["code must be a numeric AoE4World profile_id."]}
            )

        profile_id = int(raw)

        try:
            profile_payload = AoeWorldAPIService.get_player_profile(profile_id)
        except NotFound:
            raise serializers.ValidationError(
                {"code": ["AoE4World player not found (invalid code)."]}
            )

        in_game_name = (profile_payload.get("name") or "").strip()
        if not in_game_name:
            raise serializers.ValidationError(
                {"code": ["AoE4World returned no in-game name for this player."]}
            )

        aoe_profile = AoeWorldAPIService.upsert_profile_from_player_profile(
            profile_id=profile_id,
            profile=profile_payload,
        )

        if User.objects.filter(aoe_world_profile=aoe_profile).exists():
            raise serializers.ValidationError(
                {"code": ["A user with this code already exists."]}
            )

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


class UserAvailabilitySerializer(serializers.ModelSerializer):
    start_day = DayNameField()
    end_day = DayNameField()

    start_time = PlainTimeField()
    end_time = PlainTimeField()

    class Meta:
        model = UserAvailability
        fields = ["id", "user", "start_day", "start_time", "end_day", "end_time"]
        read_only_fields = ["id", "user"]

    def validate(self, attrs):
        instance = getattr(self, "instance", None)

        start_day = attrs.get("start_day", getattr(instance, "start_day", None))
        end_day = attrs.get("end_day", getattr(instance, "end_day", None))
        start_time = attrs.get("start_time", getattr(instance, "start_time", None))
        end_time = attrs.get("end_time", getattr(instance, "end_time", None))

        if (
            start_day is None
            or end_day is None
            or start_time is None
            or end_time is None
        ):
            return attrs

        start_offset = (
            int(start_day) * 86400
            + (start_time.hour * 3600)
            + (start_time.minute * 60)
            + int(getattr(start_time, "second", 0) or 0)
        )
        end_offset = (
            int(end_day) * 86400
            + (end_time.hour * 3600)
            + (end_time.minute * 60)
            + int(getattr(end_time, "second", 0) or 0)
        )

        if end_offset <= start_offset:
            raise serializers.ValidationError(
                {"end_time": ["End must be after start (across the week)."]}
            )

        if (end_offset - start_offset) > int(consts.USER_AVAILABILITY_MAX_SECONDS):
            raise serializers.ValidationError(
                {
                    "detail": f"Availability span cannot exceed {consts.USER_AVAILABILITY_MAX_HOURS} hours."
                }
            )

        return attrs

    def create(self, validated_data):
        raise NotImplementedError(
            "Use UserAvailabilityViewSet.create() which calls UserAvailabilityService."
        )

    def update(self, instance, validated_data):
        raise NotImplementedError(
            "Use UserAvailabilityViewSet.update() which calls UserAvailabilityService."
        )
