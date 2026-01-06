from rest_framework.routers import DefaultRouter

from core.views import MatchViewSet, TournamentAdminViewSet, TournamentEntrantViewSet, TournamentInviteViewSet, TournamentViewSet, \
                       TournamentParticipantViewSet, TournamentTeamJoinRequestViewSet

router = DefaultRouter()

router.register("tournaments", TournamentViewSet, basename="tournaments")

router.register(r"tournaments/(?P<tournament_id>\d+)/admins", TournamentAdminViewSet, basename="tournament-admins")

router.register(r"tournaments/(?P<tournament_id>\d+)/invites", TournamentInviteViewSet, basename="tournament-invites")

router.register(r"tournaments/(?P<tournament_id>\d+)/participants", TournamentParticipantViewSet, basename="tournament-participants")

router.register(r"tournaments/(?P<tournament_id>\d+)/team-join-requests", TournamentTeamJoinRequestViewSet, basename="tournament-team-join-requests")

router.register(r"tournaments/(?P<tournament_id>\d+)/entrants", TournamentEntrantViewSet, basename="tournament-entrants")

router.register("matches", MatchViewSet, basename="matches")

urlpatterns = router.urls
