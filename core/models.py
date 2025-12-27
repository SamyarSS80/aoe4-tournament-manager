from django.db import models

from common.models import BaseModel
from core.utils import rank_image_upload_to

class GameRank(BaseModel):
    name = models.CharField(max_length=32, db_index=True)
    number = models.PositiveSmallIntegerField(default=0, db_index=True)

    image = models.ImageField(
        upload_to=rank_image_upload_to,
        null=True,
        blank=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["name", "number"], name="uniq_game_rank_name_number"),
        ]

    def __str__(self):
        return f"{self.name}_{self.number}" if self.number else self.name
