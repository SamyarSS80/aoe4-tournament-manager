from rest_framework import serializers

from core.models import GameRank


class GameRankSerializer(serializers.ModelSerializer):
    class Meta:
        model = GameRank
        fields = ["name", "number", "image"]
        read_only_fields = fields
