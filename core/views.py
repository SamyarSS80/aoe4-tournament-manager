from __future__ import annotations

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404

from rest_framework import mixins
from drf_spectacular.types import OpenApiTypes
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from common.pagination import PageNumberPagination
from core import consts
from core.models import Match, Tournament, TournamentEntrant, TournamentInvite, TournamentParticipant, TournamentStage, \
                        TournamentEntrantMember, TournamentTeamJoinRequest, TournamentAdmin
from core.filter_backends import TournamentParticipantFilterSet, TournamentTeamJoinRequestFilterSet
from core.serializers import *
from core.services import TournamentAdminService, TournamentJoinService, TournamentEntrantService, TournamentTeamJoinRequestService, \
                          TournamentParticipantService
from core.mixins import TournamentChildMixin
from core.tasks import build_tournament_structure_task


@extend_schema_view(
    list=extend_schema(
        summary="List accessible tournaments",
        description=(
            "Retrieve tournaments accessible to the authenticated user.\n\n"
            "**Accessible if:**\n"
            "- You are the owner.\n"
            "- You are an admin.\n"
            "- You joined as a participant (team tournament, not yet in a team).\n"
            "- You are an entrant/team member.\n\n"
            "**Staff:**\n"
            "- `user.is_staff` sees all tournaments.\n"
        ),
        responses={200: TournamentSerializer(many=True)},
        tags=["Tournaments"],
    ),
    public=extend_schema(
        summary="List public tournaments",
        description="Discovery endpoint for tournaments with `visibility=PUBLIC`.",
        responses={200: TournamentSerializer(many=True)},
        tags=["Tournaments"],
    ),
    retrieve=extend_schema(
        summary="Tournament details",
        responses={200: TournamentSerializer},
        tags=["Tournaments"],
    ),
    create=extend_schema(
        summary="Create tournament",
        description="Creates a tournament. The authenticated user becomes the owner.",
        request=TournamentSerializer,
        responses={201: TournamentSerializer},
        tags=["Tournaments"],
    ),
    update=extend_schema(
        summary="Update tournament (PUT)",
        request=TournamentSerializer,
        responses={200: TournamentSerializer},
        tags=["Tournaments"],
    ),
    partial_update=extend_schema(
        summary="Update tournament (PATCH)",
        request=TournamentSerializer,
        responses={200: TournamentSerializer},
        tags=["Tournaments"],
    ),
    destroy=extend_schema(
        summary="Delete tournament",
        responses={204: None},
        tags=["Tournaments"],
    ),
    public_join=extend_schema(
        summary="Join a public tournament",
        description=(
            "**Behavior depends on `team_size`:**\n"
            "- `team_size = 1`: creates a solo entrant immediately.\n"
            "- `team_size > 1`: creates a tournament participant record (not in a team yet).\n\n"
            "**Notes:**\n"
            "- Tournament must be in `REGISTRATION`.\n"
        ),
        request=JoinTournamentSerializer,
        responses={200: JoinTournamentResponseSerializer},
        tags=["Tournaments"],
    ),
    start=extend_schema(
        summary="Start tournament (async)",
        description=(
            "Starts the tournament and triggers async structure generation.\n\n"
            "**Permissions:** owner/admin/staff.\n\n"
            "**Rules checked here (task trigger stays in view):**\n"
            "- Not already RUNNING/FINISHED.\n"
            "- No stages exist yet.\n"
            "- Solo: at least 2 entrants.\n"
            "- Team: at least 2 complete teams (member_count == team_size).\n"
        ),
        request=StartTournamentSerializer,
        responses={202: dict},
        tags=["Tournaments"],
    ),
)
class TournamentViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TournamentSerializer
    pagination_class = PageNumberPagination

    def get_queryset(self):
        qs = Tournament.objects.select_related("owner").order_by("-id")
        user = self.request.user

        if user.is_staff:
            return qs

        participant_tournament_ids = TournamentParticipant.objects.filter(user=user).values_list(
            "tournament_id", flat=True
        )
        entrant_tournament_ids = TournamentEntrant.objects.filter(users=user).values_list(
            "tournament_id", flat=True
        )

        return (
            qs.filter(
                Q(owner=user)
                | Q(admins=user)
                | Q(id__in=participant_tournament_ids)
                | Q(id__in=entrant_tournament_ids)
            )
            .distinct()
            .order_by("-id")
        )

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @action(methods=["get"], detail=False, url_path="public")
    def public(self, request, *args, **kwargs):
        qs = (
            Tournament.objects.select_related("owner")
            .filter(visibility=consts.TournamentVisibility.PUBLIC)
            .order_by("-id")
        )
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        return Response(self.get_serializer(qs, many=True).data, status=status.HTTP_200_OK)

    @action(methods=["post"], detail=True, url_path="public-join")
    def public_join(self, request, *args, **kwargs):
        tournament = get_object_or_404(Tournament.objects.all(), id=self.kwargs.get("pk"))

        serializer = JoinTournamentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        payload = TournamentJoinService.join_public(
            tournament=tournament,
            user=request.user,
        )
        return Response(JoinTournamentResponseSerializer(payload).data, status=status.HTTP_200_OK)

    @action(methods=["post"], detail=True, url_path="start")
    def start(self, request, *args, **kwargs):
        tournament = self.get_object()

        if not TournamentAdminService.can_manage(tournament=tournament, user=request.user):
            raise ValidationError({"detail": "You do not have permission to start this tournament."})

        serializer = StartTournamentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fmt = serializer.validated_data["format"]

        if tournament.status in {consts.TournamentStatus.RUNNING, consts.TournamentStatus.FINISHED}:
            raise ValidationError({"detail": "Tournament already started or finished."})

        if TournamentStage.objects.filter(tournament=tournament).exists():
            raise ValidationError({"detail": "Tournament structure already exists."})

        entrants_qs = (
            TournamentEntrant.objects.filter(tournament=tournament, status=consts.EntrantStatus.ACTIVE)
            .annotate(member_count=Count("memberships", distinct=True))
            .only("id")
        )

        if tournament.team_size > 1:
            if entrants_qs.filter(member_count=tournament.team_size).count() < 2:
                raise ValidationError({"detail": "At least 2 complete teams are required to start this tournament."})
        else:
            if entrants_qs.count() < 2:
                raise ValidationError({"detail": "At least 2 entrants are required to start a tournament."})

        res = build_tournament_structure_task.delay(tournament_id=tournament.id, format=fmt)
        return Response({"detail": "Tournament start initiated.", "task_id": res.id}, status=status.HTTP_202_ACCEPTED)


@extend_schema_view(
    list=extend_schema(
        summary="List tournament admins",
        description=(
            "List admins of a tournament.\n\n"
            "**Access:** owner/admin/participant/entrant member.\n"
        ),
        parameters=[
            OpenApiParameter(
                name="tournament_id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                required=True,
            )
        ],
        responses={200: TournamentAdminSerializer(many=True)},
        tags=["Tournament Admins"],
    ),
    create=extend_schema(
        summary="Add tournament admin (owner/staff only)",
        description=(
            "Add a user as tournament admin.\n\n"
            "**Permissions:** tournament owner OR `user.is_staff`.\n"
        ),
        request=TournamentAdminAddSerializer,
        responses={200: TournamentAdminSerializer},
        tags=["Tournament Admins"],
    ),
    destroy=extend_schema(
        summary="Remove tournament admin (owner/staff only)",
        description=(
            "Remove a user from tournament admins.\n\n"
            "**Permissions:** tournament owner OR `user.is_staff`.\n"
            "**Notes:** owner cannot be removed.\n"
        ),
        parameters=[
            OpenApiParameter(
                name="id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                required=True,
                description="User ID to remove from admins",
            )
        ],
        responses={200: OpenApiTypes.OBJECT},
        tags=["Tournament Admins"],
    ),
)
class TournamentAdminViewSet(TournamentChildMixin, viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = PageNumberPagination
    http_method_names = ["get", "post", "delete", "head", "options"]
    lookup_url_kwarg = "id"
    
    def get_queryset(self):
        if not TournamentAdminService.can_view(tournament=self.tournament, user=self.request.user):
            raise ValidationError({"detail": "You do not have permission to view this tournament."})

        return (
            TournamentAdmin.objects.filter(tournament=self.tournament)
            .select_related("user")
            .order_by("id")
        )

    def list(self, request, tournament_id=None, *args, **kwargs):
        qs = self.get_queryset()
        return Response(TournamentAdminSerializer(qs, many=True).data, status=status.HTTP_200_OK)

    def create(self, request, tournament_id=None, *args, **kwargs):
        serializer = TournamentAdminAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        admin_membership = TournamentAdminService.add_admin_by_id(
            tournament=self.tournament,
            actor=request.user,
            user_id=serializer.validated_data["user_id"],
        )
        return Response(TournamentAdminSerializer(admin_membership).data, status=status.HTTP_200_OK)

    def destroy(self, request, pk=None, tournament_id=None, *args, **kwargs):
        TournamentAdminService.remove_admin_by_id(
            tournament=self.tournament,
            actor=request.user,
            user_id=pk,
        )
        return Response({"detail": "Admin removed."}, status=status.HTTP_200_OK)


@extend_schema_view(
    list=extend_schema(
        summary="List invites",
        description="List invite tokens for a tournament you can manage.",
        parameters=[
            OpenApiParameter(
                name="tournament_id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                required=True,
            )
        ],
        responses={200: TournamentInviteSerializer(many=True)},
        tags=["Tournament Invites"],
    ),
    create=extend_schema(
        summary="Create invite",
        description=(
            "Create an invite token.\n\n"
            "**Permissions:** owner/admin/staff.\n"
        ),
        request=TournamentInviteCreateSerializer,
        responses={201: TournamentInviteSerializer},
        tags=["Tournament Invites"],
    ),
    destroy=extend_schema(
        summary="Deactivate invite",
        description="Deactivate (soft-delete) an invite token by setting `is_active=false`.",
        parameters=[
            OpenApiParameter(
                name="id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                required=True,
                description="Invite ID",
            )
        ],
        responses={204: None},
        tags=["Tournament Invites"],
    ),
    join_private=extend_schema(
        summary="Join a private tournament (invite token)",
        description=(
            "Join a tournament using an invite token.\n\n"
            "**Behavior depends on `team_size`:**\n"
            "- `team_size = 1`: creates a solo entrant immediately.\n"
            "- `team_size > 1`: creates a tournament participant record.\n"
        ),
        request=JoinTournamentByInviteSerializer,
        responses={201: JoinTournamentResponseSerializer},
        tags=["Tournament Invites"],
    ),
)
class TournamentInviteViewSet(TournamentChildMixin, mixins.ListModelMixin, mixins.CreateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TournamentInviteSerializer
    pagination_class = PageNumberPagination
    http_method_names = ["get", "post", "delete", "head", "options"]
    lookup_url_kwarg = "id"

    def get_queryset(self):
        if not TournamentAdminService.can_manage(tournament=self.tournament, user=self.request.user):
            return TournamentInvite.objects.none()

        qs = TournamentInvite.objects.filter(tournament=self.tournament)
        return qs.filter(created_by=self.request.user, is_active=True).order_by("-id")

    def get_serializer_class(self):
        if self.action == "create":
            return TournamentInviteCreateSerializer
        return TournamentInviteSerializer

    def destroy(self, request, *args, **kwargs):
        invite = self.get_object()
        TournamentInvite.objects.filter(id=invite.id).update(is_active=False)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def create(self, request, *args, **kwargs):
        if not TournamentAdminService.can_manage(tournament=self.tournament, user=request.user):
            raise ValidationError(
                {"detail": "You do not have permission to create invites for this tournament."}
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        invite = TournamentJoinService.create_invite(
            tournament=self.tournament,
            created_by=request.user,
            max_uses=serializer.validated_data.get("max_uses"),
            expires_at=serializer.validated_data.get("expires_at"),
        )
        return Response(TournamentInviteSerializer(invite).data, status=status.HTTP_201_CREATED)

    @action(methods=["post"], detail=False, url_path="join-private")
    def join_private(self, request, *args, **kwargs):
        serializer = JoinTournamentByInviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        payload = TournamentJoinService.join_by_invite(
            invite_token=serializer.validated_data["invite_token"],
            user=request.user,
        )
        return Response(
            JoinTournamentResponseSerializer(payload).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema_view(
    list=extend_schema(
        summary="List tournament participants",
        description=(
            "List tournament participants.\n\n"
            "**Filters:**\n"
            "- `not_registered=true`: participants who are **not** in any entrant (team) for this tournament.\n\n"
            "**Access:**\n"
            "- Tournament admin/owner/staff: OK\n"
        ),
        parameters=[
            OpenApiParameter("tournament_id", OpenApiTypes.INT, OpenApiParameter.PATH, required=True),
            OpenApiParameter("registered", OpenApiTypes.BOOL, OpenApiParameter.QUERY, required=False),
        ],
        responses={200: TournamentParticipantSerializer(many=True)},
        tags=["Tournament Participants"],
    ),
    destroy=extend_schema(
        summary="Remove a participant from tournament",
        description=(
            "Remove a player from a tournament.\n\n"
            "**Behavior:**\n"
            "- Always deletes `TournamentParticipant` membership.\n"
            "- Solo tournaments (`team_size=1`): also deletes the player `TournamentEntrant`.\n"
            "- Team tournaments (`team_size>1`): removes the player from any team memberships; "
            "deletes teams that become empty.\n\n"
            "**Permissions:** owner/admin/staff.\n"
        ),
        parameters=[
            OpenApiParameter("tournament_id", OpenApiTypes.INT, OpenApiParameter.PATH, required=True),
            OpenApiParameter("pk", OpenApiTypes.INT, OpenApiParameter.PATH, required=True),
        ],
        responses={204: None},
        tags=["Tournament Participants"],
    ),
    leave=extend_schema(
        summary="Leave tournament",
        description=(
            "Leave the tournament as the authenticated user.\n\n"
            "**Behavior:**\n"
            "- Deletes your `TournamentParticipant` membership.\n"
            "- Solo tournaments (`team_size=1`): deletes your entrant.\n"
            "- Team tournaments (`team_size>1`): removes you from your team; if you were captain, "
            "captaincy is reassigned.\n"
        ),
        parameters=[
            OpenApiParameter("tournament_id", OpenApiTypes.INT, OpenApiParameter.PATH, required=True),
        ],
        responses={204: None},
        tags=["Tournament Participants"],
    ),
)
class TournamentParticipantViewSet(TournamentChildMixin, viewsets.GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = PageNumberPagination
    serializer_class = TournamentParticipantSerializer
    http_method_names = ["get", "post", "head", "options"]

    filter_backends = [DjangoFilterBackend]
    filterset_class = TournamentParticipantFilterSet

    def get_queryset(self):
        if not TournamentAdminService.can_view(tournament=self.tournament, user=self.request.user):
            return TournamentParticipant.objects.none()

        return (
            TournamentParticipant.objects.filter(tournament=self.tournament)
            .select_related("user")
            .order_by("id")
        )

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(self.get_serializer(page, many=True).data)

        return Response(self.get_serializer(qs, many=True).data, status=status.HTTP_200_OK)

    def destroy(self, request, pk=None, *args, **kwargs):
        if not TournamentAdminService.can_manage(tournament=self.tournament, user=request.user):
            raise ValidationError(
                {"detail": "You do not have permission to remove participants from this tournament."}
            )

        participant_id = pk or kwargs.get("id")
        participant = get_object_or_404(
            self.get_queryset(),
            id=int(participant_id),
        )

        TournamentParticipantService.remove_player(
            tournament=self.tournament,
            actor=request.user,
            user=participant.user,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(methods=["post"], detail=False, url_path="leave")
    def leave(self, request, *args, **kwargs):
        TournamentParticipantService.remove_player(
            tournament=self.tournament,
            actor=request.user,
            user=request.user,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    list=extend_schema(
        summary="List team join requests",
        description=(
            "List **pending** team join requests for this tournament.\n\n"
            "**Filters:**\n"
            "- `requests_pending=true`: requests sent by **me**.\n"
            "- `requests_box=true`: requests sent to **my teams** (captain).\n\n"
            "If neither filter is provided, you may get both sets (depending on visibility).\n"
        ),
        parameters=[
            OpenApiParameter("tournament_id", OpenApiTypes.INT, OpenApiParameter.PATH, required=True),
            OpenApiParameter("requests_pending", OpenApiTypes.BOOL, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("requests_box", OpenApiTypes.BOOL, OpenApiParameter.QUERY, required=False),
        ],
        responses={200: TournamentTeamJoinRequestSerializer(many=True)},
        tags=["Team Join Requests"],
    ),
    create=extend_schema(
        summary="Create a team join request",
        description=(
            "Request to join a team (entrant).\n\n"
            "**Rules:**\n"
            "- Tournament must be team-based (`team_size > 1`).\n"
            "- You must have joined the tournament first (participant).\n"
            "- You must not already be in a team.\n"
        ),
        request=TeamJoinRequestCreateSerializer,
        responses={201: TournamentTeamJoinRequestSerializer},
        tags=["Team Join Requests"],
    ),
    respond=extend_schema(
        summary="Respond to a join request",
        description=(
            "Accept or reject a pending join request.\n\n"
            "**Permissions:** captain of the team OR tournament admin/owner/staff.\n"
        ),
        request=TeamJoinRequestRespondSerializer,
        responses={200: TournamentTeamJoinRequestSerializer},
        tags=["Team Join Requests"],
    ),
    destroy=extend_schema(
        summary="Cancel a join request",
        description=(
            "Cancel a **pending** team join request.\n\n"
            "**Permissions:** requester of the request OR tournament admin/owner/staff.\n"
        ),
        parameters=[
            OpenApiParameter("tournament_id", OpenApiTypes.INT, OpenApiParameter.PATH, required=True),
            OpenApiParameter("pk", OpenApiTypes.INT, OpenApiParameter.PATH, required=True),
        ],
        responses={200: TournamentTeamJoinRequestSerializer},
        tags=["Team Join Requests"],
    ),
)
class TournamentTeamJoinRequestViewSet(TournamentChildMixin, viewsets.GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = PageNumberPagination
    serializer_class = TournamentTeamJoinRequestSerializer
    http_method_names = ["get", "post", "delete", "head", "options"]

    filter_backends = [DjangoFilterBackend]
    filterset_class = TournamentTeamJoinRequestFilterSet

    def get_serializer_class(self):
        if self.action == "create":
            return TeamJoinRequestCreateSerializer
        if self.action == "respond":
            return TeamJoinRequestRespondSerializer
        return TournamentTeamJoinRequestSerializer

    def get_queryset(self):
        base_qs = (
            TournamentTeamJoinRequest.objects.filter(
                tournament=self.tournament,
                status=consts.TournamentTeamJoinRequestStatus.PENDING,
            )
            .select_related("entrant", "requester")
            .prefetch_related("entrant__memberships__user")
        )

        if TournamentAdminService.can_manage(tournament=self.tournament, user=self.request.user):
            return base_qs.order_by("-id")

        captain_team_ids = TournamentEntrantMember.objects.filter(
            entrant__tournament=self.tournament,
            user=self.request.user,
            is_captain=True,
        ).values_list("entrant_id", flat=True)

        return base_qs.filter(
            Q(requester=self.request.user) | Q(entrant_id__in=captain_team_ids)
        ).order_by("-id")

    def destroy(self, request, pk=None, *args, **kwargs):
        req = TournamentTeamJoinRequestService.cancel(
            tournament=self.tournament,
            user=request.user,
            request_id=int(pk),
        )
        return Response(TournamentTeamJoinRequestSerializer(req).data, status=status.HTTP_200_OK)

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(TournamentTeamJoinRequestSerializer(page, many=True).data)
        return Response(TournamentTeamJoinRequestSerializer(qs, many=True).data, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        req = TournamentTeamJoinRequestService.create_request(
            tournament=self.tournament,
            user=request.user,
            entrant_id=serializer.validated_data["entrant_id"],
        )
        return Response(TournamentTeamJoinRequestSerializer(req).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="respond")
    def respond(self, request, pk=None, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        req = TournamentTeamJoinRequestService.respond(
            tournament=self.tournament,
            user=request.user,
            request_id=int(pk),
            accept=serializer.validated_data["accept"],
        )
        return Response(TournamentTeamJoinRequestSerializer(req).data, status=status.HTTP_200_OK)


@extend_schema_view(
    list=extend_schema(
        summary="List tournament entrants",
        description="List entrants (teams) of the tournament.",
        parameters=[
            OpenApiParameter("tournament_id", OpenApiTypes.INT, OpenApiParameter.PATH, required=True),
        ],
        responses={200: TournamentEntrantSerializer(many=True)},
        tags=["Tournament Entrants"],
    ),
    create=extend_schema(
        summary="Create entrant",
        description=(
            "Create an entrant (team) in a team-based tournament.\n\n"
            "**Rules:**\n"
            "- Tournament must have `team_size > 1`.\n"
            "- You must have joined the tournament as participant first.\n"
            "- Creator becomes captain.\n"
        ),
        request=CreateEntrantSerializer,
        responses={201: TournamentEntrantSerializer},
        tags=["Tournament Entrants"],
    ),
    retrieve=extend_schema(
        summary="Entrant details",
        parameters=[
            OpenApiParameter("tournament_id", OpenApiTypes.INT, OpenApiParameter.PATH, required=True),
            OpenApiParameter("id", OpenApiTypes.INT, OpenApiParameter.PATH, required=True),
        ],
        responses={200: TournamentEntrantSerializer},
        tags=["Tournament Entrants"],
    ),
    leave=extend_schema(
        summary="Leave a team",
        description=(
            "Leave a tournament team (entrant).\n\n"
            "**Rules:**\n"
            "- Tournament must be team-based (`team_size > 1`).\n"
            "- You must be a member of this team.\n"
            "- If you are captain, captaincy is reassigned to another member.\n"
            "- If the team becomes empty, it is deleted.\n"
            "- You become a tournament participant again (not in a team).\n"
        ),
        parameters=[
            OpenApiParameter("tournament_id", OpenApiTypes.INT, OpenApiParameter.PATH, required=True),
            OpenApiParameter("id", OpenApiTypes.INT, OpenApiParameter.PATH, required=True),
        ],
        responses={204: None},
        tags=["Tournament Entrants"],
    ),
)
class TournamentEntrantViewSet(TournamentChildMixin, viewsets.GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = PageNumberPagination
    serializer_class = TournamentEntrantSerializer
    http_method_names = ["get", "post", "head", "options"]
    lookup_url_kwarg = "id"

    def get_queryset(self):
        if not TournamentAdminService.can_view(tournament=self.tournament, user=self.request.user):
            return TournamentEntrant.objects.none()

        return (
            TournamentEntrant.objects.filter(
                tournament=self.tournament,
                status=consts.EntrantStatus.ACTIVE,
            )
            .annotate(member_count=Count("memberships", distinct=True))
            .prefetch_related("memberships__user")
            .order_by("id")
        )

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(self.get_serializer(page, many=True).data)

        return Response(self.get_serializer(qs, many=True).data, status=status.HTTP_200_OK)

    def retrieve(self, request, pk=None, *args, **kwargs):
        obj = get_object_or_404(self.get_queryset(), id=pk)
        return Response(self.get_serializer(obj).data, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        serializer = CreateEntrantSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        entrant = TournamentEntrantService.create_entrant(
            tournament=self.tournament,
            user=request.user,
            name=serializer.validated_data["name"],
        )

        team = (
            TournamentEntrant.objects.filter(id=entrant.id)
            .annotate(member_count=Count("memberships", distinct=True))
            .prefetch_related("memberships__user")
            .get()
        )
        return Response(self.get_serializer(team).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="leave")
    def leave(self, request, pk=None, *args, **kwargs):
        TournamentEntrantService.leave(
            tournament=self.tournament,
            user=request.user,
            entrant_id=int(pk),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    list=extend_schema(summary="List matches", tags=["Matches"]),
    retrieve=extend_schema(summary="Match details", tags=["Matches"]),
    create=extend_schema(summary="Create match", tags=["Matches"]),
    update=extend_schema(summary="Update match (PUT)", tags=["Matches"]),
    partial_update=extend_schema(summary="Update match (PATCH)", tags=["Matches"]),
    destroy=extend_schema(summary="Delete match", tags=["Matches"]),
)
class MatchViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MatchSerializer
    pagination_class = PageNumberPagination

    def get_queryset(self):
        qs = (
            Match.objects.select_related("stage", "stage__tournament", "entrant1", "entrant2")
            .prefetch_related(
                "entrant1__memberships__user",
                "entrant2__memberships__user",
            )
            .order_by("-id")
        )

        user = self.request.user
        if getattr(user, "is_staff", False):
            return qs

        participant_tournament_ids = TournamentParticipant.objects.filter(user=user).values_list(
            "tournament_id", flat=True
        )
        entrant_tournament_ids = TournamentEntrant.objects.filter(users=user).values_list(
            "tournament_id", flat=True
        )

        return qs.filter(
            Q(stage__tournament__owner=user)
            | Q(stage__tournament__admins=user)
            | Q(stage__tournament_id__in=participant_tournament_ids)
            | Q(stage__tournament_id__in=entrant_tournament_ids)
        ).distinct()
