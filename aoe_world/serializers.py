from rest_framework import serializers

from aoe_world.models import AoeWorldProfile
from core.serializers import GameRankSerializer


class AoeWorldPlayerCodeInputSerializer(serializers.Serializer):
    code = serializers.CharField(required=True, allow_blank=False, trim_whitespace=True)

    def validate_code(self, value: str) -> str:
        v = (value or "").strip()
        if not v.isdigit():
            raise serializers.ValidationError("code must be a numeric AoE4World profile_id.")
        return v


class AoeWorldPlayerDetailsSerializer(serializers.Serializer):
    code = serializers.CharField(read_only=True)
    in_game_name = serializers.CharField(read_only=True)

    avatars = serializers.DictField(child=serializers.URLField(allow_null=True), read_only=True)
    country = serializers.CharField(allow_null=True, read_only=True)

    elo_solo = serializers.IntegerField(allow_null=True, read_only=True)
    elo_team = serializers.IntegerField(allow_null=True, read_only=True)

    hidden_elos = serializers.DictField(child=serializers.IntegerField(allow_null=True), read_only=True)

    rank_solo = GameRankSerializer(allow_null=True, read_only=True)
    rank_team = GameRankSerializer(allow_null=True, read_only=True)


class AoeWorldProfileSerializer(serializers.ModelSerializer):
    hidden_elos = serializers.SerializerMethodField()
    avatars = serializers.SerializerMethodField()

    rank_solo = GameRankSerializer(read_only=True, allow_null=True)
    rank_team = GameRankSerializer(read_only=True, allow_null=True)

    class Meta:
        model = AoeWorldProfile
        fields = [
            "code",
            "in_game_name",
            "avatars",
            "country",
            "elo_solo",
            "elo_team",
            "hidden_elos",
            "rank_solo",
            "rank_team",
        ]
        read_only_fields = fields

    def get_hidden_elos(self, obj: AoeWorldProfile):
        return {
            "1v1": obj.hidden_elo_1v1,
            "2v2": obj.hidden_elo_2v2,
            "3v3": obj.hidden_elo_3v3,
            "4v4": obj.hidden_elo_4v4,
        }

    def get_avatars(self, obj: AoeWorldProfile):
        return {
            "small": obj.avatar_small,
            "medium": obj.avatar_medium,
            "full": obj.avatar_full,
        }


__all__ = [
    "AoeWorldPlayerCodeInputSerializer",
    "AoeWorldPlayerDetailsSerializer",
    "AoeWorldProfileSerializer",
]
