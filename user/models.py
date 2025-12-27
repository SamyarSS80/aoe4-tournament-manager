from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.crypto import get_random_string

from user.managers import UserManager


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

    is_admin = models.BooleanField(default=False)

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
