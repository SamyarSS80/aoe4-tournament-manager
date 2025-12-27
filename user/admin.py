from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

User = get_user_model()


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        "id",
        "username",
        "aoe_world_code",
        "aoe_world_in_game_name",
        "is_admin",
        "is_staff",
        "is_superuser",
        "is_active",
        "date_joined",
        "last_login",
    )
    list_filter = ("is_admin", "is_staff", "is_superuser", "is_active")
    search_fields = (
        "username",
        "aoe_world_profile__code",
        "aoe_world_profile__in_game_name",
    )
    ordering = ("-id",)

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("AoE World Profile", {"fields": ("aoe_world_profile",)}),
        ("App Permissions", {"fields": ("is_admin",)}),
        ("Django Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
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
                    "is_admin",
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
