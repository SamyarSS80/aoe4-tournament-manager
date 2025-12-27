from django.contrib import admin

from core.models import GameRank


@admin.register(GameRank)
class GameRankAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "number", "image")
    search_fields = ("name",)
    ordering = ("name", "number")
