from django.db import models

from common.models import BaseModel


class AoeWorldProfile(BaseModel):
    code = models.CharField(max_length=32, unique=True, db_index=True)
    in_game_name = models.CharField(max_length=150)

    avatar_small = models.URLField(max_length=500, null=True, blank=True)
    avatar_medium = models.URLField(max_length=500, null=True, blank=True)
    avatar_full = models.URLField(max_length=500, null=True, blank=True)
    country = models.CharField(max_length=2, null=True, blank=True)

    elo_solo = models.IntegerField(null=True, blank=True)
    elo_team = models.IntegerField(null=True, blank=True)

    hidden_elo_1v1 = models.IntegerField(null=True, blank=True)
    hidden_elo_2v2 = models.IntegerField(null=True, blank=True)
    hidden_elo_3v3 = models.IntegerField(null=True, blank=True)
    hidden_elo_4v4 = models.IntegerField(null=True, blank=True)

    rank_solo = models.ForeignKey("core.GameRank", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    rank_team = models.ForeignKey("core.GameRank", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    def __str__(self):
        return f"{self.code} - {self.in_game_name}"
