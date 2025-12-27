from django.contrib import admin

from aoe_world.models import AoeWorldProfile


@admin.register(AoeWorldProfile)
class AoeWorldProfileAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "code",
        "in_game_name",
        "elo_solo",
        "elo_team",
        "rank_solo",
        "rank_team",
        "updated_at",
    )
    search_fields = ("code", "in_game_name")
    readonly_fields = ("created_at", "updated_at")

    list_select_related = ("rank_solo", "rank_team")
