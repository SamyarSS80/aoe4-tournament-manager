import hashlib
import logging
import math
import random
from bisect import bisect_left
from datetime import datetime, timedelta

from django.db import IntegrityError, transaction
from django.utils.crypto import get_random_string
from django.db.models import Count, F, Q
from django.utils import timezone
from django.utils.timezone import now
from rest_framework.exceptions import ValidationError

from core.models import Match, Tournament, TournamentAdmin, TournamentEntrant, TournamentEntrantMember, TournamentInvite, \
                        TournamentStage, TournamentParticipant, TournamentTeamJoinRequest
from user.models import UserAvailability, User
from common.utils import normalize_str_value
from core import consts

logger = logging.getLogger(__name__)


class TournamentHelper:
    @staticmethod
    def deterministic_rng(*, tournament_id: int, format: str) -> random.Random:
        raw = f"{tournament_id}:{format}".encode("utf-8")
        seed = int.from_bytes(hashlib.sha256(raw).digest()[:8], "big", signed=False)
        return random.Random(seed)

    @staticmethod
    def wins_needed(best_of: int) -> int:
        if best_of <= 0 or best_of % 2 == 0:
            raise ValidationError({"detail": "best_of must be a positive odd number."})
        return (best_of // 2) + 1

    @staticmethod
    def next_power_of_two(n: int) -> int:
        if n <= 1:
            return 1
        return 1 << (n - 1).bit_length()

    @staticmethod
    def round_robin_rounds(entrants: list[TournamentEntrant]) -> list[list[tuple[TournamentEntrant, TournamentEntrant]]]:
        items: list[TournamentEntrant | None] = list(entrants)
        if len(items) % 2 == 1:
            items.append(None)

        n = len(items)
        fixed = items[0]
        rest = items[1:]

        rounds: list[list[tuple[TournamentEntrant, TournamentEntrant]]] = []
        for r in range(n - 1):
            current = [fixed] + rest
            pairings: list[tuple[TournamentEntrant, TournamentEntrant]] = []

            for i in range(n // 2):
                a = current[i]
                b = current[-(i + 1)]
                if a is None or b is None:
                    continue

                if r % 2 == 0:
                    pairings.append((a, b))
                else:
                    pairings.append((b, a))

            rounds.append(pairings)
            rest = [rest[-1]] + rest[:-1]

        return rounds

    @staticmethod
    def bracket_seed_positions(size: int) -> list[int]:
        def rec(n: int) -> list[int]:
            if n == 1:
                return [1]
            prev = rec(n // 2)
            out = []
            for s in prev:
                out.append(s)
                out.append(n + 1 - s)
            return out

        return rec(size)


class LeagueFormatService:
    @staticmethod
    def build(*, tournament: Tournament, entrants: list[TournamentEntrant]) -> tuple[TournamentStage, int]:
        if len(entrants) < 2:
            raise ValidationError({"detail": "LEAGUE requires at least 2 entrants."})

        stage = TournamentStage.objects.create(
            tournament=tournament,
            type=consts.StageType.LEAGUE,
            order=0,
            best_of_default=1,
            config={
                "points": {"win": 1, "loss": 0},
                "tiebreakers": ["diff", "wins"],
            },
        )

        rounds = TournamentHelper.round_robin_rounds(entrants)

        matches: list[Match] = []
        for r, pairings in enumerate(rounds, start=1):
            for o, (a, b) in enumerate(pairings, start=0):
                matches.append(
                    Match(
                        stage=stage,
                        round_number=r,
                        order=o,
                        best_of=stage.best_of_default,
                        status=consts.MatchStatus.SCHEDULED, 
                        entrant1=a,
                        entrant2=b,
                    )
                )

        Match.objects.bulk_create(matches, batch_size=1000)
        return stage, len(matches)


class SingleElimFormatService:
    @staticmethod
    def build(*, tournament: Tournament, entrants: list[TournamentEntrant], rng: random.Random) -> tuple[TournamentStage, int]:
        if len(entrants) < 2:
            raise ValidationError(
                {"detail": "SINGLE_ELIM requires at least 2 entrants."}
            )

        rng.shuffle(entrants)

        bracket_size = TournamentHelper.next_power_of_two(len(entrants))
        positions = TournamentHelper.bracket_seed_positions(bracket_size)

        seed_to_entrant = {i + 1: entrants[i] for i in range(len(entrants))}
        ordered = [seed_to_entrant.get(seed) for seed in positions]

        stage = TournamentStage.objects.create(
            tournament=tournament,
            type=consts.StageType.SINGLE_ELIM,
            order=0,
            best_of_default=1,
            config={"bracket_size": bracket_size},
        )

        matches: list[Match] = []
        rounds = int(math.log2(bracket_size))

        for round_number in range(1, rounds + 1):
            num_matches = bracket_size // (2**round_number)
            for order in range(num_matches):
                entrant1 = None
                entrant2 = None

                if round_number == 1:
                    entrant1 = ordered[2 * order]
                    entrant2 = ordered[2 * order + 1]

                matches.append(
                    Match(
                        stage=stage,
                        round_number=round_number,
                        order=order,
                        best_of=stage.best_of_default,
                        status=consts.MatchStatus.SCHEDULED,
                        entrant1=entrant1,
                        entrant2=entrant2,
                    )
                )

        Match.objects.bulk_create(matches, batch_size=1000)

        round1 = list(
            Match.objects.filter(stage=stage, round_number=1)
            .select_related("entrant1", "entrant2")
            .order_by("order")
        )
        if rounds >= 2:
            round2 = list(
                Match.objects.filter(stage=stage, round_number=2)
                .select_related("entrant1", "entrant2")
                .order_by("order")
            )
        else:
            round2 = []

        to_update: list[Match] = []
        for m in round1:
            if m.entrant1 and not m.entrant2:
                m.status = consts.MatchStatus.FINISHED
                m.winner_slot = 1
                m.score1 = TournamentHelper.wins_needed(m.best_of)
                m.score2 = 0
                to_update.append(m)

                if round2:
                    idx = m.order // 2
                    if m.order % 2 == 0:
                        round2[idx].entrant1 = m.entrant1
                        to_update.append(round2[idx])
                    else:
                        round2[idx].entrant2 = m.entrant1
                        to_update.append(round2[idx])

            if m.entrant2 and not m.entrant1:
                m.status = consts.MatchStatus.FINISHED
                m.winner_slot = 2
                m.score1 = 0
                m.score2 = TournamentHelper.wins_needed(m.best_of)
                to_update.append(m)

                if round2:
                    idx = m.order // 2
                    if m.order % 2 == 0:
                        round2[idx].entrant1 = m.entrant2
                        to_update.append(round2[idx])
                    else:
                        round2[idx].entrant2 = m.entrant2
                        to_update.append(round2[idx])

        if to_update:
            Match.objects.bulk_update(
                list({m.id: m for m in to_update if m.id}.values()),
                fields=[
                    "status",
                    "winner_slot",
                    "score1",
                    "score2",
                    "entrant1",
                    "entrant2",
                ],
                batch_size=1000,
            )

        return stage, bracket_size - 1


class TournamentService:
    @staticmethod
    def build_structure(*, tournament_id: int, format: str) -> dict:
        with transaction.atomic():
            tournament = Tournament.objects.select_for_update().get(id=tournament_id)

            if tournament.status in {consts.TournamentStatus.RUNNING, consts.TournamentStatus.FINISHED}:
                raise ValidationError({"detail": "Tournament already started or finished."})

            if TournamentStage.objects.filter(tournament=tournament).exists():
                raise ValidationError({"detail": "Tournament structure already exists."})

            entrants = list(
                TournamentEntrant.objects.filter(tournament=tournament, status=consts.EntrantStatus.ACTIVE)
                .annotate(member_count=Count("memberships", distinct=True))
            )
            required = tournament.team_size
            if required > 1:
                invalid_ids = [e.id for e in entrants if int(getattr(e, "member_count", 0)) != required]
                if invalid_ids:
                    TournamentEntrant.objects.filter(id__in=invalid_ids).delete()
                    entrants = [e for e in entrants if e.id not in set(invalid_ids)]

            if len(entrants) < 2:
                raise ValidationError({"detail": "At least 2 entrants are required to start a tournament."})

            rng = TournamentHelper.deterministic_rng(tournament_id=tournament.id, format=format)

            if format == consts.StageType.LEAGUE:
                stage, match_count = LeagueFormatService.build(tournament=tournament, entrants=entrants)
            elif format == consts.StageType.SINGLE_ELIM:
                stage, match_count = SingleElimFormatService.build(tournament=tournament, entrants=entrants, rng=rng)
            else:
                raise ValidationError({"detail": "Unsupported format."})

            tournament.status = consts.TournamentStatus.RUNNING
            tournament.save(update_fields=["status", "updated_at"])

        logger.info(
            "Built tournament structure",
            extra={"tournament_id": tournament_id, "stage_id": stage.id},
        )
        return {"tournament_id": tournament.id, "stage_id": stage.id, "matches_created": match_count}


class TournamentAdminService:
    @staticmethod
    def is_owner(*, tournament: Tournament, user) -> bool:
        if user.is_staff:
            return True
        
        return tournament.owner_id == user.id

    @staticmethod
    def is_admin(*, tournament: Tournament, user) -> bool:
        if TournamentAdminService.is_owner(tournament=tournament, user=user):
            return True
        return TournamentAdmin.objects.filter(tournament=tournament, user=user).exists()

    @staticmethod
    def can_manage(*, tournament: Tournament, user) -> bool:
        return TournamentAdminService.is_admin(tournament=tournament, user=user)

    @staticmethod
    def can_view(*, tournament: Tournament, user) -> bool:
        if TournamentAdminService.is_admin(tournament=tournament, user=user):
            return True

        if TournamentParticipant.objects.filter(tournament=tournament, user=user).exists():
            return True

        return TournamentEntrantMember.objects.filter(
            entrant__tournament=tournament,
            user=user,
        ).exists()

    @staticmethod
    def can_manage_admins(*, tournament: Tournament, user) -> bool:
        return bool(user.is_staff or tournament.owner_id == user.id)

    @staticmethod
    def _get_user_by_id(*, user_id) -> User:
        if not user_id:
            raise ValidationError({"user_id": ["This field is required."]})

        try:
            uid = int(user_id)
        except (ValueError, TypeError):
            raise ValidationError({"user_id": ["Invalid user_id."]})

        try:
            return User.objects.only("id", "username").get(id=uid)
        except User.DoesNotExist:
            raise ValidationError({"user_id": ["Invalid user_id."]})

    @staticmethod
    def add_admin_by_id(*, tournament: Tournament, actor, user_id) -> TournamentAdmin:
        if not TournamentAdminService.can_manage_admins(tournament=tournament, user=actor):
            raise ValidationError({"detail": "Only the tournament owner or staff can add admins."})

        target = TournamentAdminService._get_user_by_id(user_id=user_id)

        if target.id == tournament.owner_id:
            obj = TournamentAdmin(tournament=tournament, user=target)
            obj.tournament = tournament
            obj.user = target
            return obj

        obj, _ = TournamentAdmin.objects.get_or_create(
            tournament=tournament,
            user=target,
        )
        obj.tournament = tournament
        obj.user = target
        return obj

    @staticmethod
    def remove_admin_by_id(*, tournament: Tournament, actor, user_id) -> None:
        if not TournamentAdminService.can_manage_admins(tournament=tournament, user=actor):
            raise ValidationError({"detail": "Only the tournament owner or staff can remove admins."})

        target = TournamentAdminService._get_user_by_id(user_id=user_id)

        if target.id == tournament.owner_id:
            raise ValidationError({"detail": "Owner cannot be removed from admins."})

        TournamentAdmin.objects.filter(tournament=tournament, user=target).delete()


class TournamentJoinService:
    @staticmethod
    def can_join(*, tournament: Tournament, user) -> None:
        if tournament.status != consts.TournamentStatus.REGISTRATION:
            raise ValidationError({"detail": "Tournament is not currently open for joining."})

        if TournamentParticipant.objects.filter(tournament=tournament, user=user).exists():
            raise ValidationError({"detail": "You have already joined this tournament."})

        if TournamentEntrantMember.objects.filter(entrant__tournament=tournament, user=user).exists():
            raise ValidationError({"detail": "You have already joined this tournament."})
    
    @staticmethod
    def create_invite(tournament, created_by, max_uses=None, expires_at=None) -> TournamentInvite:
        token = get_random_string(48)

        return TournamentInvite.objects.create(
            tournament=tournament,
            token=token,
            created_by=created_by,
            max_uses=max_uses,
            expires_at=expires_at,
            is_active=True,
        )
    
    @staticmethod
    def join_public(tournament, user) -> dict:
        with transaction.atomic():
            return TournamentJoinService._join_user_to_tournament(tournament=tournament, user=user)

    @staticmethod
    def join_by_invite(invite_token, user) -> dict:
        try:
            with transaction.atomic():
                invite = (
                    TournamentInvite.objects.select_for_update()
                    .select_related("tournament")
                    .get(token=invite_token)
                )

                TournamentJoinService._can_use_link(invite=invite)

                payload = TournamentJoinService._join_user_to_tournament(
                    tournament=invite.tournament,
                    user=user,
                )

                TournamentInvite.objects.filter(id=invite.id).update(uses=F("uses") + 1)
                return payload
        except TournamentInvite.DoesNotExist:
            raise ValidationError({"invite_token": ["Invalid invite token."]})

    @staticmethod
    def _join_user_to_tournament(tournament, user) -> dict:
        TournamentJoinService.can_join(tournament=tournament, user=user)

        required = int(tournament.team_size or 1)

        try:
            TournamentParticipant.objects.create(tournament=tournament, user=user)
        except IntegrityError:
            raise ValidationError({"detail": "You have already joined this tournament."})

        entrant = None
        if required == 1:
            entrant_name = normalize_str_value(user.username)

            try:
                entrant = TournamentEntrant.objects.create(tournament=tournament, name=entrant_name)
                TournamentEntrantMember.objects.create(entrant=entrant, user=user, is_captain=True)
            except IntegrityError:
                raise ValidationError({"detail": "You have already joined this tournament."})

        return {
            "tournament": tournament,
            "choose_team": entrant is None,
        }

    @staticmethod
    def _can_use_link(*, invite: TournamentInvite) -> None:
        if not invite.is_active:
            raise ValidationError({"detail": "Invite is not active."})

        if invite.expires_at and invite.expires_at < now():
            raise ValidationError({"detail": "Invite has expired."})

        if invite.max_uses is not None and invite.uses >= invite.max_uses:
            raise ValidationError({"detail": "Invite usage limit reached."})


class TournamentParticipantService:
    @staticmethod
    def remove_player(*, tournament, actor, user) -> None:
        is_self = actor.id == user.id
        if not is_self and not TournamentAdminService.can_manage(tournament=tournament, user=actor):
            raise ValidationError(
                {"detail": "You do not have permission to remove participants from this tournament."}
            )

        required = int(tournament.team_size or 1)

        with transaction.atomic():
            TournamentParticipant.objects.filter(
                tournament=tournament,
                user=user,
            ).delete()

            if required <= 1:
                TournamentEntrant.objects.filter(
                    tournament=tournament,
                    users=user,
                ).delete()
                return

            affected_memberships = list(
                TournamentEntrantMember.objects.filter(
                    entrant__tournament=tournament,
                    user=user,
                ).values("entrant_id", "is_captain")
            )
            if not affected_memberships:
                return

            affected_entrant_ids = [m["entrant_id"] for m in affected_memberships]
            captain_entrant_ids = [m["entrant_id"] for m in affected_memberships if m["is_captain"]]

            TournamentEntrantMember.objects.filter(
                entrant_id__in=affected_entrant_ids,
                user=user,
            ).delete()

            if captain_entrant_ids:
                entrants_with_captain = set(
                    TournamentEntrantMember.objects.filter(
                        entrant_id__in=captain_entrant_ids,
                        is_captain=True,
                    ).values_list("entrant_id", flat=True)
                )
                needs_captain_ids = [e_id for e_id in captain_entrant_ids if e_id not in entrants_with_captain]

                if needs_captain_ids:
                    candidate_rows = (
                        TournamentEntrantMember.objects.select_for_update()
                        .filter(entrant_id__in=needs_captain_ids)
                        .order_by("entrant_id", "id")
                        .values_list("entrant_id", "id")
                    )

                    chosen_member_ids = []
                    seen = set()
                    for entrant_id, member_id in candidate_rows:
                        if entrant_id in seen:
                            continue
                        seen.add(entrant_id)
                        chosen_member_ids.append(member_id)

                    if chosen_member_ids:
                        to_update = list(TournamentEntrantMember.objects.filter(id__in=chosen_member_ids))
                        for m in to_update:
                            m.is_captain = True
                        TournamentEntrantMember.objects.bulk_update(
                            to_update,
                            ["is_captain"],
                            batch_size=500,
                        )

            TournamentEntrant.objects.filter(
                tournament=tournament,
                id__in=affected_entrant_ids,
                memberships__isnull=True,
            ).delete()


class TournamentTeamJoinRequestService:
    @staticmethod
    def cancel(*, tournament, user, request_id) -> TournamentTeamJoinRequest:
        with transaction.atomic():
            req = (
                TournamentTeamJoinRequest.objects.select_for_update()
                .select_related("entrant", "requester")
                .get(id=request_id, tournament=tournament)
            )

            if req.status != consts.TournamentTeamJoinRequestStatus.PENDING:
                raise ValidationError({"detail": "Request is not pending."})

            is_admin = TournamentAdminService.can_manage(tournament=tournament, user=user)
            if not is_admin and req.requester_id != user.id:
                raise ValidationError({"detail": "Only requester or tournament admin can cancel this request."})

            now_ts = timezone.now()
            req.status = consts.TournamentTeamJoinRequestStatus.CANCELED
            req.responded_at = now_ts
            req.save(update_fields=["status", "responded_at", "updated_at"])
            return req
    
    @staticmethod
    def create_request(*, tournament, user, entrant_id) -> TournamentTeamJoinRequest:
        required = tournament.team_size
        if required <= 1:
            raise ValidationError({"detail": "This is a solo tournament. Teams are not allowed."})

        with transaction.atomic():
            if not TournamentParticipant.objects.filter(tournament=tournament, user=user).exists():
                raise ValidationError({"detail": "Join the tournament first."})

            if TournamentEntrantMember.objects.filter(entrant__tournament=tournament, user=user).exists():
                raise ValidationError({"detail": "You are already in a team."})

            entrant = TournamentEntrant.objects.filter(tournament=tournament, id=entrant_id).first()
            if not entrant:
                raise ValidationError({"entrant_id": ["Invalid team for this tournament."]})

            member_count = TournamentEntrantMember.objects.filter(entrant=entrant).count()
            if member_count >= required:
                raise ValidationError({"detail": "Team is already full."})

            obj, _ = TournamentTeamJoinRequest.objects.get_or_create(
                tournament=tournament,
                entrant=entrant,
                requester=user,
                defaults={"status": consts.TournamentTeamJoinRequestStatus.PENDING},
            )

            if obj.status != consts.TournamentTeamJoinRequestStatus.PENDING:
                raise ValidationError({"detail": "You have already requested to join this team."})

            return obj

    @staticmethod
    def respond(*, tournament, user, request_id, accept) -> TournamentTeamJoinRequest:
        required = tournament.team_size

        with transaction.atomic():
            req = (
                TournamentTeamJoinRequest.objects.select_for_update()
                .select_related("entrant", "requester")
                .get(id=request_id, tournament=tournament)
            )

            if req.status != consts.TournamentTeamJoinRequestStatus.PENDING:
                raise ValidationError({"detail": "Request is not pending."})

            is_admin = TournamentAdminService.can_manage(tournament=tournament, user=user)
            is_captain = TournamentEntrantMember.objects.filter(
                entrant=req.entrant,
                user=user,
                is_captain=True,
            ).exists()

            if not is_admin and not is_captain:
                raise ValidationError({"detail": "Only captain or tournament admin can respond to requests."})

            TournamentEntrant.objects.select_for_update().get(id=req.entrant_id)

            if not accept:
                req.status = consts.TournamentTeamJoinRequestStatus.REJECTED
                req.responded_at = timezone.now()
                req.save(update_fields=["status", "responded_at", "updated_at"])
                return req

            if not TournamentParticipant.objects.filter(tournament=tournament, user=req.requester).exists():
                raise ValidationError({"detail": "Requester is not a tournament participant."})

            if TournamentEntrantMember.objects.filter(entrant__tournament=tournament, user=req.requester).exists():
                raise ValidationError({"detail": "Requester is already in a team."})

            member_count = TournamentEntrantMember.objects.filter(entrant=req.entrant).count()
            if member_count >= required:
                raise ValidationError({"detail": "Team is already full."})

            TournamentEntrantMember.objects.create(
                entrant=req.entrant,
                user=req.requester,
                is_captain=False,
            )

            now_ts = timezone.now()
            req.status = consts.TournamentTeamJoinRequestStatus.ACCEPTED
            req.responded_at = now_ts
            req.save(update_fields=["status", "responded_at", "updated_at"])

            TournamentTeamJoinRequest.objects.filter(
                tournament=tournament,
                requester=req.requester,
                status=consts.TournamentTeamJoinRequestStatus.PENDING,
            ).exclude(id=req.id).update(
                status=consts.TournamentTeamJoinRequestStatus.CANCELED,
                responded_at=now_ts,
                updated_at=now_ts,
            )

            return req


class TournamentEntrantService:
    @staticmethod
    def create_entrant(*, tournament, user, name) -> TournamentEntrant:
        required = int(tournament.team_size or 1)
        if required <= 1:
            raise ValidationError({"detail": "This is a solo tournament. Teams are not allowed."})

        entrant_name = normalize_str_value(name)
        with transaction.atomic():
            try:
                TournamentParticipant.objects.select_for_update().get(
                    tournament=tournament,
                    user=user,
                )
            except TournamentParticipant.DoesNotExist:
                raise ValidationError({"detail": "Join the tournament first."})

            if TournamentEntrantMember.objects.filter(
                entrant__tournament=tournament,
                user=user,
            ).exists():
                raise ValidationError({"detail": "You are already in a team."})

            entrant = TournamentEntrant.objects.create(
                tournament=tournament,
                name=entrant_name,
                status=consts.EntrantStatus.ACTIVE,
            )
            TournamentEntrantMember.objects.create(
                entrant=entrant,
                user=user,
                is_captain=True,
            )

            return entrant

    @staticmethod
    def leave(*, tournament, user, entrant_id: int) -> None:
        required = int(tournament.team_size or 1)
        if required <= 1:
            raise ValidationError({"detail": "This is a solo tournament. Teams are not allowed."})

        with transaction.atomic():
            entrant = (
                TournamentEntrant.objects.select_for_update()
                .filter(
                    tournament=tournament,
                    id=entrant_id,
                    status=consts.EntrantStatus.ACTIVE,
                )
                .first()
            )
            if not entrant:
                raise ValidationError({"detail": "Invalid team for this tournament."})

            membership = (
                TournamentEntrantMember.objects.select_for_update()
                .filter(entrant=entrant, user=user)
                .first()
            )
            if not membership:
                raise ValidationError({"detail": "You are not a member of this team."})

            was_captain = bool(membership.is_captain)

            TournamentEntrantMember.objects.filter(id=membership.id).delete()

            now_ts = timezone.now()

            if was_captain:
                replacement = (
                    TournamentEntrantMember.objects.select_for_update()
                    .filter(entrant=entrant)
                    .order_by("id")
                    .first()
                )
                if replacement:
                    TournamentEntrantMember.objects.filter(id=replacement.id).update(
                        is_captain=True,
                        updated_at=now_ts,
                    )

            if not TournamentEntrantMember.objects.filter(entrant=entrant).exists():
                TournamentEntrant.objects.filter(id=entrant.id).delete()


class MatchSchedulingService:
    @staticmethod
    def schedule_tournament_matches(tournament_id: int) -> dict:
        slot_minutes = 15
        base_match_duration_minutes = 60

        with transaction.atomic():
            tournament = (
                Tournament.objects.select_for_update()
                .only("id", "starts_at", "ends_at", "game_gaps")
                .get(id=tournament_id)
            )

            start_at = tournament.starts_at
            end_at = tournament.ends_at

            slots = MatchSchedulingService._build_slots(
                start_at=start_at,
                end_at=end_at,
                slot_minutes=slot_minutes,
            )
            if not slots:
                raise ValidationError(
                    {"detail": "Tournament scheduling window has no available slots."}
                )

            gap_minutes = tournament.game_gaps
            gap_slots = int(math.ceil(gap_minutes / slot_minutes)) if gap_minutes > 0 else 0

            matches = list(
                Match.objects.select_for_update()
                .filter(
                    stage__tournament_id=tournament_id,
                    status=consts.MatchStatus.SCHEDULED,
                    scheduled_at__isnull=True,
                    entrant1__isnull=False,
                    entrant2__isnull=False,
                )
                .select_related("entrant1", "entrant2", "stage")
                .only("id", "entrant1_id", "entrant2_id", "stage_id", "best_of", "stage__order")
                .order_by("id")
            )

            if not matches:
                return {"tournament_id": tournament_id, "scheduled": 0, "skipped": 0}

            entrant_ids: set[int] = set()
            for m in matches:
                entrant_ids.add(m.entrant1_id)
                entrant_ids.add(m.entrant2_id)

            entrant_to_user_id = MatchSchedulingService._resolve_entrant_captains(
                entrant_ids=entrant_ids
            )
            user_ids = set(entrant_to_user_id.values())

            user_avail = list(UserAvailability.objects.filter(user_id__in=user_ids))

            user_to_avail_intervals = MatchSchedulingService._expand_weekly_availability(
                availabilities=user_avail,
                user_ids=user_ids,
                start_at=start_at,
                end_at=end_at,
            )

            match_id_to_duration_minutes: dict[int, int] = {}
            match_id_to_duration_slots: dict[int, int] = {}
            duration_slots_set: set[int] = set()

            for m in matches:
                best_of = m.best_of
                duration_minutes = base_match_duration_minutes * best_of
                duration_slots = int(math.ceil(duration_minutes / slot_minutes))

                match_id_to_duration_minutes[m.id] = duration_minutes
                match_id_to_duration_slots[m.id] = duration_slots
                duration_slots_set.add(duration_slots)

            duration_slots_to_user_available: dict[int, dict[int, list[int]]] = {}
            for duration_slots in sorted(duration_slots_set):
                duration_slots_to_user_available[duration_slots] = (
                    MatchSchedulingService._compute_user_available_start_indices(
                        slots=slots,
                        duration_slots=duration_slots,
                        user_to_intervals=user_to_avail_intervals,
                        slot_minutes=slot_minutes,
                    )
                )

            slot0 = slots[0]
            step = timedelta(minutes=slot_minutes)

            user_to_reserved: dict[int, list[tuple[int, int]]] = {uid: [] for uid in user_ids}

            already_scheduled = list(
                Match.objects.filter(
                    stage__tournament_id=tournament_id,
                    scheduled_at__isnull=False,
                    entrant1__isnull=False,
                    entrant2__isnull=False,
                )
                .filter(Q(entrant1_id__in=entrant_ids) | Q(entrant2_id__in=entrant_ids))
                .only("scheduled_at", "entrant1_id", "entrant2_id", "best_of")
                .order_by("scheduled_at", "id")
            )

            for em in already_scheduled:
                u1 = entrant_to_user_id.get(em.entrant1_id)
                u2 = entrant_to_user_id.get(em.entrant2_id)

                best_of = int(getattr(em, "best_of", 1) or 1)
                duration_minutes = base_match_duration_minutes * max(best_of, 1)
                duration_slots = int(math.ceil(duration_minutes / slot_minutes))

                start_i = MatchSchedulingService._dt_to_slot_index(
                    dt=em.scheduled_at,
                    slot0=slot0,
                    step=step,
                )
                reserve_slots = duration_slots + gap_slots

                MatchSchedulingService._reserve_interval(
                    user_to_reserved=user_to_reserved,
                    user_id=u1,
                    start_i=start_i,
                    reserve_slots=reserve_slots,
                )
                MatchSchedulingService._reserve_interval(
                    user_to_reserved=user_to_reserved,
                    user_id=u2,
                    start_i=start_i,
                    reserve_slots=reserve_slots,
                )

            def overlap_flex(m: Match) -> int:
                u1 = entrant_to_user_id[m.entrant1_id]
                u2 = entrant_to_user_id[m.entrant2_id]
                duration_slots = match_id_to_duration_slots[m.id]
                user_to_available = duration_slots_to_user_available.get(duration_slots, {})
                
                return MatchSchedulingService._count_intersection(user_to_available.get(u1, []), user_to_available.get(u2, []))

            matches.sort(key=lambda m: (getattr(m.stage, "order", 0), overlap_flex(m)))

            scheduled: list[Match] = []

            for m in matches:
                u1 = entrant_to_user_id[m.entrant1_id]
                u2 = entrant_to_user_id[m.entrant2_id]

                duration_minutes = match_id_to_duration_minutes[m.id]
                duration_slots = match_id_to_duration_slots[m.id]
                user_to_available = duration_slots_to_user_available.get(duration_slots, {})

                idx = MatchSchedulingService._pick_best_slot_index(
                    slots=slots,
                    duration_minutes=duration_minutes,
                    duration_slots=duration_slots,
                    gap_slots=gap_slots,
                    end_at=end_at,
                    user1_id=u1,
                    user2_id=u2,
                    user_to_available=user_to_available,
                    user_to_reserved=user_to_reserved,
                    slot_minutes=slot_minutes,
                )

                if idx is None:
                    raise ValidationError(
                        {"detail": "Could not schedule all matches within tournament time range."}
                    )

                m.scheduled_at = slots[idx]
                scheduled.append(m)

                reserve_slots = duration_slots + gap_slots
                MatchSchedulingService._reserve_interval(
                    user_to_reserved=user_to_reserved,
                    user_id=u1,
                    start_i=idx,
                    reserve_slots=reserve_slots,
                )
                MatchSchedulingService._reserve_interval(
                    user_to_reserved=user_to_reserved,
                    user_id=u2,
                    start_i=idx,
                    reserve_slots=reserve_slots,
                )

            if scheduled:
                Match.objects.bulk_update(scheduled, fields=["scheduled_at"], batch_size=1000)

            logger.info(
                "Scheduled tournament matches",
                extra={
                    "tournament_id": tournament_id,
                    "scheduled": len(scheduled),
                },
            )

            return {
                "tournament_id": tournament_id,
                "scheduled": len(scheduled),
                "skipped": 0,
            }

    @staticmethod
    def _build_slots(*, start_at: datetime, end_at: datetime, slot_minutes: int) -> list[datetime]:
        if start_at.tzinfo is None or end_at.tzinfo is None:
            raise ValidationError({"detail": "Tournament times must be timezone-aware."})

        start = start_at.replace(second=0, microsecond=0)
        delta_min = (slot_minutes - (start.minute % slot_minutes)) % slot_minutes
        if delta_min:
            start = start + timedelta(minutes=delta_min)

        out: list[datetime] = []
        cur = start
        while cur < end_at:
            out.append(cur)
            cur = cur + timedelta(minutes=slot_minutes)
        
        return out

    @staticmethod
    def _resolve_entrant_captains(*, entrant_ids: set[int]) -> dict[int, int]:
        if not entrant_ids:
            return {}

        rows = list(
            TournamentEntrantMember.objects.filter(
                entrant_id__in=entrant_ids,
                is_captain=True,
            )
            .values_list("entrant_id", "user_id")
        )

        out: dict[int, int] = {entrant_id: user_id for entrant_id, user_id in rows}

        missing = [eid for eid in entrant_ids if eid not in out]
        if missing:
            raise ValidationError({"detail": f"Entrants missing captain: {', '.join(map(str, missing))}"})

        return out

    @staticmethod
    def _expand_weekly_availability(availabilities, user_ids, start_at, end_at) -> dict[int, list[tuple[datetime, datetime]]]:
        if start_at.tzinfo is None or end_at.tzinfo is None:
            raise ValidationError({"detail": "Tournament times must be timezone-aware."})

        if not user_ids:
            raise ValidationError({"detail": "No users resolved for scheduling (missing captains?)."})

        avail_user_ids = {a.user_id for a in availabilities}
        missing_user_ids = sorted(user_ids - avail_user_ids)
        if missing_user_ids:
            raise ValidationError(
                {"detail": f"Users missing availability: {', '.join(map(str, missing_user_ids))}"}
            )

        tz = timezone.get_current_timezone()
        start_local = start_at.astimezone(tz)
        end_local = end_at.astimezone(tz)

        user_to_intervals: dict[int, list[tuple[datetime, datetime]]] = {uid: [] for uid in user_ids}

        week_start_date = start_local.date() - timedelta(days=start_local.date().weekday())
        week_start_dt = timezone.make_aware(
            datetime.combine(week_start_date, datetime.min.time()),
            tz,
        )

        ws = week_start_dt
        while ws < end_local:
            for a in availabilities:
                s = ws + timedelta(seconds=int(a.start_offset))
                e = ws + timedelta(seconds=int(a.end_offset))

                if s < start_local:
                    s = start_local
                if e > end_local:
                    e = end_local

                if e > s:
                    user_to_intervals[a.user_id].append((s, e))

            ws = ws + timedelta(days=7)

        for uid in user_to_intervals:
            user_to_intervals[uid].sort(key=lambda x: x[0])

        empty_after_clip = sorted(uid for uid, intervals in user_to_intervals.items() if not intervals)
        if empty_after_clip:
            raise ValidationError(
                {"detail": f"Users have no availability within tournament window: {', '.join(map(str, empty_after_clip))}"}
            )

        return user_to_intervals

    @staticmethod
    def _compute_user_available_start_indices(slots, duration_slots, user_to_intervals, slot_minutes) -> dict[int, list[int]]:
        slot0 = slots[0]
        step = timedelta(minutes=slot_minutes)
        duration = step * duration_slots

        out: dict[int, list[int]] = {}
        for user_id, intervals in user_to_intervals.items():
            diff = [0] * (len(slots) + 1)

            for s, e in intervals:
                raw_start = (s - slot0).total_seconds() / step.total_seconds()
                start_i = int(math.ceil(raw_start))
                if start_i < 0:
                    start_i = 0

                raw_end = ((e - duration) - slot0).total_seconds() / step.total_seconds()
                end_i = int(math.floor(raw_end))
                if end_i >= len(slots):
                    end_i = len(slots) - 1

                if end_i < start_i:
                    continue

                diff[start_i] += 1
                diff[end_i + 1] -= 1

            starts: list[int] = []
            cur = 0
            for i in range(len(slots)):
                cur += diff[i]
                if cur > 0:
                    starts.append(i)

            out[user_id] = starts

        return out

    @staticmethod
    def _count_intersection(a: list[int], b: list[int]) -> int:
        i = 0
        j = 0
        c = 0
        while i < len(a) and j < len(b):
            if a[i] == b[j]:
                c += 1
                i += 1
                j += 1
            elif a[i] < b[j]:
                i += 1
            else:
                j += 1
        return c

    @staticmethod
    def _distance_to_list(x: int, items: list[int]) -> int:
        if not items:
            return 0
        pos = bisect_left(items, x)
        candidates = []
        if pos < len(items):
            candidates.append(abs(items[pos] - x))
        if pos > 0:
            candidates.append(abs(items[pos - 1] - x))
        return min(candidates)

    @staticmethod
    def _dt_to_slot_index(dt: datetime, slot0: datetime, step: timedelta) -> int:
        if dt <= slot0:
            return 0
        raw = (dt - slot0).total_seconds() / step.total_seconds()
        return int(math.floor(raw))

    @staticmethod
    def _interval_insert_pos(intervals: list[tuple[int, int]], start_i: int) -> int:
        lo = 0
        hi = len(intervals)
        while lo < hi:
            mid = (lo + hi) // 2
            if intervals[mid][0] < start_i:
                lo = mid + 1
            else:
                hi = mid
        return lo

    @staticmethod
    def _reserve_interval(user_to_reserved, user_id , start_i, reserve_slots) -> None:
        intervals = user_to_reserved.setdefault(user_id, [])
        end_i = start_i + reserve_slots
        pos = MatchSchedulingService._interval_insert_pos(intervals, start_i)
        intervals.insert(pos, (start_i, end_i))

    @staticmethod
    def _fits_reserved_constraints(user_id, start_i, reserve_slots, user_to_reserved) -> bool:
        intervals = user_to_reserved.get(user_id, [])
        if not intervals:
            return True

        end_i = start_i + reserve_slots
        pos = MatchSchedulingService._interval_insert_pos(intervals, start_i)

        if pos > 0:
            _, prev_e = intervals[pos - 1]
            if prev_e > start_i:
                return False

        if pos < len(intervals):
            next_s, _ = intervals[pos]
            if end_i > next_s:
                return False

        return True

    @staticmethod
    def _is_pm(*, dt: datetime) -> bool:
        tz = timezone.get_current_timezone()
        return dt.astimezone(tz).hour >= 12

    @staticmethod
    def _pick_best_slot_index(
        slots, duration_minutes, duration_slots, gap_slots, end_at,
        user1_id, user2_id, user_to_available, user_to_reserved, slot_minutes,
    ) -> int | None:
        reserve_slots = duration_slots + gap_slots
        duration_td = timedelta(minutes=duration_minutes)
        slots_len = len(slots)

        a = user_to_available.get(user1_id, [])
        b = user_to_available.get(user2_id, [])

        i = 0
        j = 0
        while i < len(a) and j < len(b):
            if a[i] == b[j]:
                idx = a[i]
                dt = slots[idx]

                if (
                    (dt + duration_td) <= end_at
                    and MatchSchedulingService._fits_reserved_constraints(
                        user_id=user1_id,
                        start_i=idx,
                        reserve_slots=reserve_slots,
                        user_to_reserved=user_to_reserved,
                    )
                    and MatchSchedulingService._fits_reserved_constraints(
                        user_id=user2_id,
                        start_i=idx,
                        reserve_slots=reserve_slots,
                        user_to_reserved=user_to_reserved,
                    )
                ):
                    return idx

                i += 1
                j += 1
            elif a[i] < b[j]:
                i += 1
            else:
                j += 1

        prefer_pm = bool(a) and bool(b)

        best_any = None
        best_any_cost = None

        best_pm = None
        best_pm_cost = None

        for idx in range(0, slots_len - duration_slots + 1):
            dt = slots[idx]
            if (dt + duration_td) > end_at:
                continue

            if not MatchSchedulingService._fits_reserved_constraints(
                user_id=user1_id,
                start_i=idx,
                reserve_slots=reserve_slots,
                user_to_reserved=user_to_reserved,
            ):
                continue

            if not MatchSchedulingService._fits_reserved_constraints(
                user_id=user2_id,
                start_i=idx,
                reserve_slots=reserve_slots,
                user_to_reserved=user_to_reserved,
            ):
                continue

            cost = (MatchSchedulingService._distance_to_list(idx, a) + MatchSchedulingService._distance_to_list(idx, b)) * slot_minutes

            if best_any_cost is None or cost < best_any_cost:
                best_any_cost = cost
                best_any = idx

            if prefer_pm and MatchSchedulingService._is_pm(dt=dt):
                if best_pm_cost is None or cost < best_pm_cost:
                    best_pm_cost = cost
                    best_pm = idx

        if prefer_pm and best_pm is not None:
            return best_pm
        
        return best_any
