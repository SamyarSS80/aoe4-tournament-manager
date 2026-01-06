from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.auth.models import AbstractUser
from django.db.models import CheckConstraint, F, Index, Q
from django.db import models

from user.managers import UserManager
from common.models import BaseModel
from user import consts


class User(AbstractUser):
    first_name = None
    last_name = None
    email = None

    username = models.CharField(max_length=150, unique=True)

    aoe_world_profile = models.ForeignKey(
        "aoe_world.AoeWorldProfile",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="users",
    )

    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.username

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["aoe_world_profile"],
                name="uniq_user_aoe_world_profile",
            )
        ]


class UserAvailability(BaseModel):
    user = models.ForeignKey(
        "user.User",
        on_delete=models.CASCADE,
        related_name="availabilities",
    )

    start_day = models.PositiveSmallIntegerField(choices=consts.DAY_OF_WEEK_CHOICES, db_index=True)
    start_time = models.TimeField()

    end_day = models.PositiveSmallIntegerField(choices=consts.DAY_OF_WEEK_CHOICES, db_index=True)
    end_time = models.TimeField()

    start_offset = models.PositiveIntegerField(db_index=True, editable=False)
    end_offset = models.PositiveIntegerField(db_index=True, editable=False)

    class Meta:
        constraints = [
            CheckConstraint(
                check=Q(end_offset__gt=F("start_offset")),
                name="chk_user_availability_end_offset_gt_start_offset",
            ),
            CheckConstraint(
                check=Q(end_offset__lte=F("start_offset") + consts.USER_AVAILABILITY_MAX_SECONDS),
                name="chk_ua_max_span_16h",
            ),
        ]
        indexes = [
            Index(fields=["user"], name="user_availability_user_idx"),
            Index(fields=["user", "start_offset"], name="ua_user_start_off_idx"),
            Index(fields=["user", "end_offset"], name="ua_user_end_off_idx"),
        ]
        ordering = ["user_id", "start_offset", "id"]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.start_day} {self.start_time}-{self.end_day} {self.end_time}"

    @staticmethod
    def _to_offset(day: int, t) -> int:
        return (
            int(day) * 86400
            + (t.hour * 3600)
            + (t.minute * 60)
            + int(getattr(t, "second", 0) or 0)
        )

    def clean(self):
        start_offset = self._to_offset(self.start_day, self.start_time)
        end_offset = self._to_offset(self.end_day, self.end_time)

        if end_offset <= start_offset:
            raise DjangoValidationError(
                {"end_time": ["End must be after start (across the week)."]}
            )

    def save(self, *args, **kwargs):
        self.start_offset = self._to_offset(self.start_day, self.start_time)
        self.end_offset = self._to_offset(self.end_day, self.end_time)
        super().save(*args, **kwargs)
