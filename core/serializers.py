from datetime import timezone as dt_timezone

from django.utils import timezone
from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from core.models import GameRank, Match, Tournament, TournamentEntrant, TournamentEntrantMember, TournamentInvite, \
                        TournamentTeamJoinRequest, TournamentParticipant, TournamentAdmin
from user.models import User
from core import consts


class SlimUserSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="username", read_only=True)

    class Meta:
        model = User
        fields = ["id", "name"]
        read_only_fields = fields


class GameRankSerializer(serializers.ModelSerializer):
    class Meta:
        model = GameRank
        fields = ["name", "number", "image"]
        read_only_fields = fields


class TournamentSerializer(serializers.ModelSerializer):
    owner = SlimUserSerializer(read_only=True)
    admins = SlimUserSerializer(many=True, read_only=True)

    team_size = serializers.IntegerField(required=False, min_value=1)

    class Meta:
        model = Tournament
        fields = [
            "id", "name", "owner", "admins",
            "visibility", "status", "starts_at", "ends_at",
            "game_gaps", "team_size",
        ]
        read_only_fields = ["id", "owner", "admins", "status"]

    def validate_game_gaps(self, value):
        if value is None:
            return 0
        if value < 0:
            raise serializers.ValidationError("game_gaps must be >= 0.")
        return value

    def validate_team_size(self, value):
        if value is None:
            return 1
        if value < 1:
            raise serializers.ValidationError("team_size must be >= 1.")
        return int(value)

    def create(self, validated_data):
        return Tournament.objects.create(**validated_data)


class SlimTournamentSerializer(serializers.ModelSerializer):
    owner = SlimUserSerializer(read_only=True)

    class Meta:
        model = Tournament
        fields = ["id", "name", "owner"]
        read_only_fields = fields


class TournamentAdminSerializer(serializers.ModelSerializer):
    user = SlimUserSerializer(read_only=True)

    class Meta:
        model = TournamentAdmin
        fields = ["id", "tournament", "user", "created_at"]
        read_only_fields = fields


class TournamentAdminAddSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(min_value=1)


class TournamentEntrantMemberSerializer(serializers.ModelSerializer):
    user = SlimUserSerializer(read_only=True)

    class Meta:
        model = TournamentEntrantMember
        fields = ["id", "user", "is_captain"]
        read_only_fields = fields


class TournamentEntrantSerializer(serializers.ModelSerializer):
    memberships = TournamentEntrantMemberSerializer(many=True, read_only=True)
    member_count = serializers.IntegerField(read_only=True)

    user_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        write_only=True,
        required=False,
        allow_empty=False,
    )

    class Meta:
        model = TournamentEntrant
        fields = ["id", "tournament", "name", "status", "member_count", "memberships", "user_ids"]
        read_only_fields = ["id", "member_count", "memberships"]

    def validate_user_ids(self, value):
        ids = sorted(set([int(x) for x in (value or []) if x]))
        if not ids:
            raise ValidationError("At least one user is required.")
        return ids

    def validate(self, attrs):
        attrs = super().validate(attrs)
        tournament = attrs.get("tournament") or getattr(self.instance, "tournament", None)
        user_ids = attrs.get("user_ids", None)

        if tournament and user_ids is not None:
            max_size = int(getattr(tournament, "team_size", 1) or 1)
            if len(user_ids) > max_size:
                raise ValidationError({"user_ids": [f"Max team size is {max_size}."]})

        return attrs

    def _resolve_users(self, ids: list[int]) -> list[User]:
        users = list(User.objects.filter(id__in=ids).only("id", "username"))
        if len(users) != len(ids):
            raise ValidationError({"user_ids": ["One or more users were not found."]})
        users.sort(key=lambda u: ids.index(u.id))
        return users

    def create(self, validated_data):
        user_ids = validated_data.pop("user_ids", None)

        with transaction.atomic():
            entrant = TournamentEntrant.objects.create(**validated_data)

            if user_ids is not None:
                users = self._resolve_users(user_ids)
                TournamentEntrantMember.objects.bulk_create(
                    [
                        TournamentEntrantMember(entrant=entrant, user=u, is_captain=(i == 0))
                        for i, u in enumerate(users)
                    ],
                    batch_size=1000,
                )

        return entrant


class TournamentEntrantSlimSerializer(serializers.ModelSerializer):
    memberships = TournamentEntrantMemberSerializer(many=True, read_only=True)

    class Meta:
        model = TournamentEntrant
        fields = ["id", "name", "status", "memberships"]
        read_only_fields = fields


class MatchSerializer(serializers.ModelSerializer):
    entrant1 = TournamentEntrantSlimSerializer(read_only=True)
    entrant2 = TournamentEntrantSlimSerializer(read_only=True)

    entrant1_id = serializers.PrimaryKeyRelatedField(
        source="entrant1",
        queryset=TournamentEntrant.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )
    entrant2_id = serializers.PrimaryKeyRelatedField(
        source="entrant2",
        queryset=TournamentEntrant.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Match
        fields = [
            "id",
            "stage",
            "round_number",
            "order",
            "best_of",
            "status",
            "scheduled_at",
            "entrant1",
            "entrant2",
            "entrant1_id",
            "entrant2_id",
            "score1",
            "score2",
            "winner_slot",
        ]
        read_only_fields = ["id", "entrant1", "entrant2"]

    def validate(self, attrs):
        entrant1 = attrs.get("entrant1", getattr(self.instance, "entrant1", None))
        entrant2 = attrs.get("entrant2", getattr(self.instance, "entrant2", None))

        if entrant1 and entrant2 and entrant1 == entrant2:
            raise ValidationError(
                {"entrant2_id": ["entrant2 must be different from entrant1."]}
            )

        return attrs


class StartTournamentSerializer(serializers.Serializer):
    format = serializers.ChoiceField(choices=consts.StageType.CHOICES)


class JoinTournamentSerializer(serializers.Serializer):
    pass


class JoinTournamentByInviteSerializer(serializers.Serializer):
    invite_token = serializers.CharField(required=True, allow_blank=False, trim_whitespace=True)


class JoinTournamentResponseSerializer(serializers.Serializer):
    tournament = SlimTournamentSerializer(read_only=True)
    choose_team = serializers.BooleanField(read_only=True)


class TournamentInviteSerializer(serializers.ModelSerializer):
    tournament = SlimTournamentSerializer(read_only=True)

    class Meta:
        model = TournamentInvite
        fields = ["id", "token", "created_at", "expires_at", "tournament", "is_active"]
        read_only_fields = fields


class TournamentInviteCreateSerializer(serializers.Serializer):
    max_uses = serializers.IntegerField(required=False, min_value=1)
    expires_at = serializers.DateTimeField(required=False)

    def validate_expires_at(self, value):
        if value is None:
            return value

        if timezone.is_naive(value):
            value = timezone.make_aware(value, dt_timezone.utc)

        return value.astimezone(dt_timezone.utc)


class CreateTeamSerializer(serializers.Serializer):
    name = serializers.CharField(required=True, allow_blank=False, trim_whitespace=True)


class TeamJoinRequestCreateSerializer(serializers.Serializer):
    entrant_id = serializers.IntegerField(min_value=1)


class TeamJoinRequestRespondSerializer(serializers.Serializer):
    accept = serializers.BooleanField()


class TournamentTeamJoinRequestSerializer(serializers.ModelSerializer):
    requester = SlimUserSerializer(read_only=True)
    entrant = TournamentEntrantSlimSerializer(read_only=True)

    class Meta:
        model = TournamentTeamJoinRequest
        fields = ["id", "tournament", "entrant", "requester", "status", "responded_at", "created_at"]
        read_only_fields = fields


class CreateEntrantSerializer(serializers.Serializer):
    name = serializers.CharField(required=True, allow_blank=False, trim_whitespace=True)


class TournamentParticipantSerializer(serializers.ModelSerializer):
    user = SlimUserSerializer(read_only=True)

    class Meta:
        model = TournamentParticipant
        fields = [
            "id",
            "user",
            "created_at",
        ]


__all__ = [
    "TournamentSerializer",
    "MatchSerializer",
    "StartTournamentSerializer",

    "TournamentAdminAddSerializer",
    "TournamentAdminSerializer",


    "CreateEntrantSerializer",
    "JoinTournamentByInviteSerializer",
    "JoinTournamentResponseSerializer",
    "JoinTournamentSerializer",

    "TournamentParticipantSerializer",
    "TeamJoinRequestCreateSerializer",
    "TeamJoinRequestRespondSerializer",
    "TournamentInviteCreateSerializer",
    "TournamentInviteSerializer",
    "TournamentTeamJoinRequestSerializer",
    "TournamentEntrantSerializer",
]