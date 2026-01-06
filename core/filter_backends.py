from django_filters import rest_framework as filters

from core.models import TournamentEntrantMember


class TournamentParticipantFilterSet(filters.FilterSet):
    registered = filters.BooleanFilter(method="filter_registered")

    def filter_registered(self, qs, name, value):
        view = getattr(self.request, "parser_context", {}).get("view")
        tournament = getattr(view, "tournament", None)
        if tournament is None:
            return qs

        member_user_ids = TournamentEntrantMember.objects.filter(
            entrant__tournament=tournament
        ).values_list("user_id", flat=True)

        if value is True:
            return qs.filter(user_id__in=member_user_ids)

        if value is False:
            return qs.exclude(user_id__in=member_user_ids)

        return qs


class TournamentTeamJoinRequestFilterSet(filters.FilterSet):
    requests_pending = filters.BooleanFilter(method="filter_requests_pending")
    requests_box = filters.BooleanFilter(method="filter_requests_box")

    def filter_requests_pending(self, qs, name, value):
        if not value:
            return qs
        return qs.filter(requester=self.request.user)

    def filter_requests_box(self, qs, name, value):
        if not value:
            return qs

        view = getattr(self.request, "parser_context", {}).get("view")
        tournament = getattr(view, "tournament", None)
        if tournament is None:
            return qs.none()

        captain_team_ids = TournamentEntrantMember.objects.filter(
            entrant__tournament=tournament,
            user=self.request.user,
            is_captain=True,
        ).values_list("entrant_id", flat=True)

        return qs.filter(entrant_id__in=captain_team_ids)
