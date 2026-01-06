from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from user.models import UserAvailability

User = get_user_model()


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        "id",
        "username",
        "aoe_world_code",
        "aoe_world_in_game_name",
        "is_staff",
        "is_superuser",
        "is_active",
        "date_joined",
        "last_login",
    )
    list_filter = ("is_staff", "is_superuser", "is_active")
    search_fields = (
        "username",
        "aoe_world_profile__code",
        "aoe_world_profile__in_game_name",
    )
    ordering = ("-id",)

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("AoE World Profile", {"fields": ("aoe_world_profile",)}),
        ("App Permissions", {"fields": ("is_staff",)}),
        ("Django Permissions", {"fields": ("is_active", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "aoe_world_profile",
                    "password1",
                    "password2",
                    "is_staff",
                    "is_superuser",
                    "is_active",
                ),
            },
        ),
    )

    readonly_fields = ("last_login", "date_joined")

    @admin.display(description="AoE World Code", ordering="aoe_world_profile__code")
    def aoe_world_code(self, obj):
        prof = getattr(obj, "aoe_world_profile", None)
        return getattr(prof, "code", None)

    @admin.display(description="In-game name", ordering="aoe_world_profile__in_game_name")
    def aoe_world_in_game_name(self, obj):
        prof = getattr(obj, "aoe_world_profile", None)
        return getattr(prof, "in_game_name", None)


@admin.register(UserAvailability)
class UserAvailabilityAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "start_day_display",
        "start_time",
        "end_day_display",
        "end_time",
        "created_at",
    )
    list_filter = ("start_day", "end_day")
    search_fields = ("user__username",)
    ordering = ("user_id", "start_offset", "-id")
    raw_id_fields = ("user",)

    @admin.display(description="Start day", ordering="start_day")
    def start_day_display(self, obj):
        return obj.get_start_day_display()

    @admin.display(description="End day", ordering="end_day")
    def end_day_display(self, obj):
        return obj.get_end_day_display()
