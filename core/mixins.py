from rest_framework.exceptions import NotFound
from django.utils.functional import cached_property

from core.models import Tournament, TournamentEntrant


class TournamentChildMixin:
    @cached_property
    def tournament(self) -> Tournament:
        try:
            tournament_id = self.kwargs.get("tournament_id")
            return Tournament.objects.select_related("owner").get(id=tournament_id)
        except Tournament.DoesNotExist:
            raise NotFound("tournament not found")


class EntrantChildMixin(TournamentChildMixin):
    @cached_property
    def entrant(self) -> TournamentEntrant:
        try:
            entrant_id = self.kwargs.get("entrant_id")
            return (
                TournamentEntrant.objects.select_related("tournament")
                .prefetch_related("users")
                .get(id=entrant_id, tournament_id=self.tournament.id)
            )
        except TournamentEntrant.DoesNotExist:
            raise NotFound("entrant not found")