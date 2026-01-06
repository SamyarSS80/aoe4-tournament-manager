from django.db import models
from django.db.models import CheckConstraint, F, Index, Q, UniqueConstraint
from django.utils import timezone

from common.models import BaseModel
from core.utils import rank_image_upload_to, civilization_image_upload_to
from core import consts


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
            models.UniqueConstraint(
                fields=["name", "number"], name="uniq_game_rank_name_number"
            ),
        ]

    def __str__(self):
        return f"{self.name}_{self.number}" if self.number else self.name


class Civilization(BaseModel):
    name = models.CharField(max_length=64, db_index=True)
    is_dlc = models.BooleanField(default=False, db_index=True)

    image = models.ImageField(
        upload_to=civilization_image_upload_to,
        null=True,
        blank=True,
    )

    class Meta:
        constraints = [
            UniqueConstraint(fields=["name"], name="uniq_civilization_name"),
        ]
        indexes = [
            Index(fields=["name"], name="civilization_name_idx"),
            Index(fields=["is_dlc"], name="civilization_is_dlc_idx"),
        ]
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Tournament(BaseModel):
    name = models.CharField(max_length=128, db_index=True)

    owner = models.ForeignKey(
        "user.User",
        on_delete=models.PROTECT,
        related_name="owned_tournaments",
    )

    participants = models.ManyToManyField(
        "user.User",
        through="core.TournamentParticipant",
        related_name="joined_tournaments",
        blank=True,
    )

    admins = models.ManyToManyField(
        "user.User",
        through="core.TournamentAdmin",
        related_name="admin_tournaments",
        blank=True,
    )

    visibility = models.CharField(
        max_length=16,
        choices=consts.TournamentVisibility.CHOICES,
        default=consts.TournamentVisibility.PUBLIC,
        db_index=True,
    )

    status = models.CharField(
        max_length=16,
        choices=consts.TournamentStatus.CHOICES,
        default=consts.TournamentStatus.REGISTRATION,
        db_index=True,
    )

    starts_at = models.DateTimeField(default=timezone.now, db_index=True)
    ends_at = models.DateTimeField()

    game_gaps = models.PositiveSmallIntegerField(default=60)

    team_size = models.PositiveSmallIntegerField(default=1, db_index=True)

    class Meta:
        constraints = [
            CheckConstraint(
                check=Q(ends_at__gte=F("starts_at")),
                name="chk_tournament_end_gte_start",
            ),
        ]
        indexes = [
            Index(fields=["name"], name="tournament_name_idx"),
            Index(fields=["status"], name="tournament_status_idx"),
            Index(fields=["visibility"], name="tournament_visibility_idx"),
            Index(fields=["owner"], name="tournament_owner_idx"),
            Index(fields=["game_gaps"], name="tournament_game_gaps_idx"),
            Index(fields=["team_size"], name="tournament_team_size_idx"),
        ]
        ordering = ["-id"]

    def __str__(self) -> str:
        return self.name


class TournamentParticipant(BaseModel):
    tournament = models.ForeignKey(
        "core.Tournament",
        on_delete=models.CASCADE,
        related_name="participant_memberships",
    )
    user = models.ForeignKey(
        "user.User",
        on_delete=models.CASCADE,
        related_name="tournament_participant_memberships",
    )

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["tournament", "user"],
                name="uniq_tournament_participant_user",
            ),
        ]
        indexes = [
            Index(fields=["tournament"], name="tpart_tourn_idx"),
            Index(fields=["user"], name="tpart_user_idx"),
        ]
        ordering = ["tournament_id", "id"]

    def __str__(self) -> str:
        return f"{self.tournament_id}:{self.user_id}"


class TournamentTeamJoinRequest(BaseModel):
    tournament = models.ForeignKey(
        "core.Tournament",
        on_delete=models.CASCADE,
        related_name="team_join_requests",
    )
    entrant = models.ForeignKey(
        "core.TournamentEntrant",
        on_delete=models.CASCADE,
        related_name="team_join_requests",
    )
    requester = models.ForeignKey(
        "user.User",
        on_delete=models.CASCADE,
        related_name="tournament_team_join_requests",
    )

    status = models.CharField(
        max_length=16,
        choices=consts.TournamentTeamJoinRequestStatus.CHOICES,
        default=consts.TournamentTeamJoinRequestStatus.PENDING,
        db_index=True,
    )

    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["entrant", "requester"],
                name="uniq_tteam_joinreq_entrant_requester",
            ),
        ]
        indexes = [
            Index(fields=["tournament"], name="tteamreq_tourn_idx"),
            Index(fields=["entrant"], name="tteamreq_entrant_idx"),
            Index(fields=["requester"], name="tteamreq_requester_idx"),
            Index(fields=["status"], name="tteamreq_status_idx"),
        ]
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"{self.tournament_id}:{self.entrant_id}:{self.requester_id}:{self.status}"


class TournamentAdmin(BaseModel):
    tournament = models.ForeignKey(
        "core.Tournament",
        on_delete=models.CASCADE,
        related_name="admin_memberships",
    )
    user = models.ForeignKey(
        "user.User",
        on_delete=models.CASCADE,
        related_name="tournament_admin_memberships",
    )

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["tournament", "user"], name="uniq_tournament_admin_user"
            ),
        ]
        indexes = [
            Index(fields=["tournament"], name="tadmin_tourn_idx"),
            Index(fields=["user"], name="tadmin_user_idx"),
        ]
        ordering = ["tournament_id", "id"]

    def __str__(self) -> str:
        return f"{self.tournament_id}:{self.user_id}"


class TournamentInvite(BaseModel):
    tournament = models.ForeignKey(
        "core.Tournament",
        on_delete=models.CASCADE,
        related_name="invites",
    )

    token = models.CharField(max_length=64, unique=True, db_index=True)

    created_by = models.ForeignKey(
        "user.User",
        on_delete=models.PROTECT,
        related_name="created_tournament_invites",
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(default=True, db_index=True)

    max_uses = models.PositiveIntegerField(null=True, blank=True)
    uses = models.PositiveIntegerField(default=0)

    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            Index(fields=["tournament"], name="invite_tournament_idx"),
            Index(fields=["token"], name="invite_token_idx"),
            Index(fields=["is_active"], name="invite_is_active_idx"),
        ]
        constraints = [
            CheckConstraint(
                check=Q(max_uses__isnull=True) | Q(uses__lte=F("max_uses")),
                name="chk_invite_uses_lte_max_uses",
            ),
        ]
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"{self.tournament_id}:{self.id}"


class TournamentEntrant(BaseModel):
    tournament = models.ForeignKey(
        "core.Tournament",
        on_delete=models.CASCADE,
        related_name="entrants",
    )

    name = models.CharField(max_length=128, db_index=True)

    status = models.CharField(
        max_length=16,
        choices=consts.EntrantStatus.CHOICES,
        default=consts.EntrantStatus.ACTIVE,
        db_index=True,
    )

    users = models.ManyToManyField(
        "user.User",
        through="core.TournamentEntrantMember",
        related_name="tournament_entrants",
        blank=True,
    )

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["tournament", "name"], name="uniq_tournament_entrant_name"
            ),
        ]
        indexes = [
            Index(fields=["tournament"], name="entrant_tournament_idx"),
            Index(
                fields=["tournament", "status"], name="entrant_tournament_status_idx"
            ),
        ]
        ordering = ["tournament_id", "id"]

    def __str__(self) -> str:
        return f"{self.tournament_id}:{self.name}"


class TournamentEntrantMember(BaseModel):
    entrant = models.ForeignKey(
        "core.TournamentEntrant",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        "user.User",
        on_delete=models.CASCADE,
        related_name="tournament_entrant_memberships",
    )

    is_captain = models.BooleanField(default=False)

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["entrant", "user"], name="uniq_tournament_entrant_member"
            ),
            UniqueConstraint(
                fields=["entrant"],
                condition=Q(is_captain=True),
                name="uniq_tournament_entrant_captain",
            ),
        ]
        indexes = [
            Index(fields=["entrant"], name="entrant_member_entrant_idx"),
            Index(fields=["user"], name="entrant_member_user_idx"),
        ]
        ordering = ["entrant_id", "-is_captain", "id"]

    def __str__(self) -> str:
        return f"{self.entrant_id}:{self.user_id}"


class TournamentStage(BaseModel):
    tournament = models.ForeignKey(
        "core.Tournament",
        on_delete=models.CASCADE,
        related_name="stages",
    )

    type = models.CharField(max_length=16, choices=consts.StageType.CHOICES, db_index=True)

    order = models.PositiveSmallIntegerField(default=0, db_index=True)

    best_of_default = models.PositiveSmallIntegerField(default=1)
    config = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["tournament", "order"], name="uniq_stage_tournament_order"
            ),
        ]
        indexes = [
            Index(fields=["tournament"], name="stage_tournament_idx"),
            Index(fields=["tournament", "type"], name="stage_tournament_type_idx"),
        ]
        ordering = ["tournament_id", "order", "id"]

    def __str__(self) -> str:
        return f"{self.tournament_id}:{self.order} {self.type}"


class Match(BaseModel):
    stage = models.ForeignKey(
        "core.TournamentStage",
        on_delete=models.CASCADE,
        related_name="matches",
    )

    round_number = models.PositiveSmallIntegerField(default=1, db_index=True)
    order = models.PositiveSmallIntegerField(default=0, db_index=True)

    best_of = models.PositiveSmallIntegerField(default=1)

    status = models.CharField(
        max_length=16,
        choices=consts.MatchStatus.CHOICES,
        default=consts.MatchStatus.SCHEDULED,
        db_index=True,
    )

    scheduled_at = models.DateTimeField(null=True, blank=True)

    entrant1 = models.ForeignKey(
        "core.TournamentEntrant",
        on_delete=models.PROTECT,
        related_name="matches_as_entrant1",
        null=True,
        blank=True,
    )
    entrant2 = models.ForeignKey(
        "core.TournamentEntrant",
        on_delete=models.PROTECT,
        related_name="matches_as_entrant2",
        null=True,
        blank=True,
    )

    score1 = models.PositiveSmallIntegerField(default=0)
    score2 = models.PositiveSmallIntegerField(default=0)
    winner_slot = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="1 or 2 when finished."
    )

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["stage", "round_number", "order"],
                name="uniq_match_stage_round_order",
            ),
            CheckConstraint(
                check=Q(entrant1__isnull=True)
                | Q(entrant2__isnull=True)
                | ~Q(entrant1=F("entrant2")),
                name="chk_match_entrants_distinct",
            ),
        ]
        indexes = [
            Index(fields=["stage"], name="match_stage_idx"),
            Index(fields=["status"], name="match_status_idx"),
            Index(fields=["stage", "round_number"], name="match_stage_round_idx"),
        ]
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"Match {self.pk} ({self.stage_id})"


class MatchGame(BaseModel):
    match = models.ForeignKey(
        "core.Match",
        on_delete=models.CASCADE,
        related_name="games",
    )

    game_number = models.PositiveSmallIntegerField(db_index=True)

    entrant1_civ = models.ForeignKey(
        "core.Civilization",
        on_delete=models.PROTECT,
        related_name="games_as_entrant1_civ",
    )
    entrant2_civ = models.ForeignKey(
        "core.Civilization",
        on_delete=models.PROTECT,
        related_name="games_as_entrant2_civ",
    )

    winner_slot = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["match", "game_number"], name="uniq_match_game_number"
            ),
        ]
        indexes = [
            Index(fields=["match"], name="match_game_match_idx"),
        ]
        ordering = ["match_id", "game_number", "id"]

    def __str__(self) -> str:
        return f"{self.match_id}:G{self.game_number}"
