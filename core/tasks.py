import logging

from celery import shared_task
from rest_framework.exceptions import ValidationError

from core.services import MatchSchedulingService, TournamentService

logger = logging.getLogger(__name__)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def build_tournament_structure_task(self, *, tournament_id: int, format: str) -> dict:
    logger.info("build_tournament_structure_task starting", extra={"tournament_id": tournament_id, "format": format})

    res = TournamentService.build_structure(tournament_id=tournament_id, format=format)

    try:
        sched = MatchSchedulingService.schedule_tournament_matches(tournament_id=tournament_id)
    except ValidationError:
        logger.exception("Match scheduling failed", extra={"tournament_id": tournament_id})
        sched = {"tournament_id": tournament_id, "scheduled": 0, "skipped": 0}

    res["scheduling"] = sched
    logger.info("build_tournament_structure_task finished", extra=res)
    return res
