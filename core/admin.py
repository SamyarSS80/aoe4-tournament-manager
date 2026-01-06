from django.contrib import admin

from core.models import (
    Civilization,
    GameRank,
    Match,
    MatchGame,
    Tournament,
    TournamentAdmin as TournamentAdminMembership,
    TournamentEntrant,
    TournamentEntrantMember,
    TournamentInvite,
    TournamentParticipant,
    TournamentStage,
    TournamentTeamJoinRequest,
)


@admin.register(GameRank)
class GameRankAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "number", "image")
    search_fields = ("name",)
    ordering = ("name", "number")


@admin.register(Civilization)
class CivilizationAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "is_dlc")
    list_filter = ("is_dlc",)
    search_fields = ("name",)
    ordering = ("name",)
    list_per_page = 50


class TournamentAdminInline(admin.TabularInline):
    model = TournamentAdminMembership
    extra = 0
    raw_id_fields = ("user",)
    fields = ("user", "created_at")
    readonly_fields = ("created_at",)


@admin.register(Tournament)
class TournamentModelAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "visibility",
        "status",
        "team_size",
        "owner",
        "starts_at",
        "ends_at",
        "game_gaps",
        "created_at",
    )
    list_filter = ("visibility", "status", "team_size")
    search_fields = ("name", "owner__username")
    ordering = ("-id",)
    raw_id_fields = ("owner",)
    list_select_related = ("owner",)
    inlines = [TournamentAdminInline]


@admin.register(TournamentAdminMembership)
class TournamentAdminMembershipAdmin(admin.ModelAdmin):
    list_display = ("id", "tournament", "user", "created_at")
    search_fields = ("tournament__name", "user__username")
    ordering = ("-id",)
    raw_id_fields = ("tournament", "user")
    list_select_related = ("tournament", "user")


@admin.register(TournamentParticipant)
class TournamentParticipantAdmin(admin.ModelAdmin):
    list_display = ("id", "tournament", "user", "created_at")
    search_fields = ("tournament__name", "user__username")
    ordering = ("-id",)
    raw_id_fields = ("tournament", "user")
    list_select_related = ("tournament", "user")


@admin.register(TournamentInvite)
class TournamentInviteAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "tournament",
        "is_active",
        "uses",
        "max_uses",
        "expires_at",
        "created_by",
        "created_at",
    )
    list_filter = ("is_active",)
    search_fields = ("token", "tournament__name", "created_by__username")
    ordering = ("-id",)
    raw_id_fields = ("tournament", "created_by")
    list_select_related = ("tournament", "created_by")


@admin.register(TournamentTeamJoinRequest)
class TournamentTeamJoinRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "tournament",
        "entrant",
        "requester",
        "status",
        "responded_at",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = ("tournament__name", "entrant__name", "requester__username")
    ordering = ("-id",)
    raw_id_fields = ("tournament", "entrant", "requester")
    list_select_related = ("tournament", "entrant", "requester")


class TournamentEntrantMemberInline(admin.TabularInline):
    model = TournamentEntrantMember
    extra = 0
    raw_id_fields = ("user",)
    fields = ("user", "is_captain", "created_at")
    readonly_fields = ("created_at",)


@admin.register(TournamentEntrant)
class TournamentEntrantAdmin(admin.ModelAdmin):
    list_display = ("id", "tournament", "name", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("name", "tournament__name")
    ordering = ("-id",)
    raw_id_fields = ("tournament",)
    list_select_related = ("tournament",)
    inlines = [TournamentEntrantMemberInline]


@admin.register(TournamentStage)
class TournamentStageAdmin(admin.ModelAdmin):
    list_display = ("id", "tournament", "order", "type", "best_of_default", "created_at")
    list_filter = ("type",)
    search_fields = ("tournament__name",)
    ordering = ("tournament_id", "order", "-id")
    raw_id_fields = ("tournament",)
    list_select_related = ("tournament",)


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "stage",
        "round_number",
        "order",
        "status",
        "scheduled_at",
        "entrant1",
        "entrant2",
        "winner_slot",
    )
    list_filter = ("status",)
    search_fields = (
        "stage__tournament__name",
        "entrant1__name",
        "entrant2__name",
    )
    ordering = ("-id",)
    raw_id_fields = ("stage", "entrant1", "entrant2")
    list_select_related = ("stage", "stage__tournament", "entrant1", "entrant2")


@admin.register(MatchGame)
class MatchGameAdmin(admin.ModelAdmin):
    list_display = ("id", "match", "game_number", "entrant1_civ", "entrant2_civ", "winner_slot")
    list_filter = ("winner_slot",)
    search_fields = (
        "match__stage__tournament__name",
        "entrant1_civ__name",
        "entrant2_civ__name",
    )
    ordering = ("match_id", "game_number", "-id")
    raw_id_fields = ("match", "entrant1_civ", "entrant2_civ")
    list_select_related = ("match", "entrant1_civ", "entrant2_civ")
