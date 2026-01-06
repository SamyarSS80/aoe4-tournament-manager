import logging
from typing import Any, Optional, Tuple

import requests
from rest_framework.exceptions import NotFound, ValidationError

from aoe_world import consts
from core.models import GameRank
from common.utils import int_or_none, str_to_lower
from aoe_world.models import AoeWorldProfile

logger = logging.getLogger(__name__)


class AoeWorldAPIService:
    BASE_URL = consts.AOE4WORLD_BASE_URL
    TIMEOUT = consts.AOE4WORLD_TIMEOUT
    _session = requests.Session()

    @classmethod
    def get_player_profile(cls, profile_id: int) -> dict:
        path = f"/players/{profile_id}"
        url = f"{cls.BASE_URL}{path}"

        resp = cls._session.get(url, timeout=cls.TIMEOUT, headers={"Accept": "application/json"})
        
        if resp.status_code == 404:
            raise NotFound("AoE4World player not found.")
        if resp.status_code == 429:
            raise ValidationError({"detail": "AoE4World rate limit reached. Please try again later."})
        if resp.status_code >= 400:
            logger.warning(
                "AoE4World error status=%s url=%s body=%s",
                resp.status_code, url, resp.text[:300],
            )
            raise ValidationError({"detail": "AoE4World request failed."})

        return resp.json()

    @staticmethod
    def _parse_rank_level(rank_level: Any) -> Tuple[Optional[str], int]:
        s = str_to_lower(rank_level)
        if not s:
            return None, 0

        if "_" not in s:
            return s, 0

        name, num = s.split("_", 1)
        if not name:
            return None, 0

        return name, int(num) if num.isdigit() else 0

    @classmethod
    def _get_or_create_rank(cls, rank_level: Any) -> Optional[GameRank]:
        name, number = cls._parse_rank_level(rank_level)
        if not name:
            return None
        
        rank, _ = GameRank.objects.get_or_create(name=name, number=number)
        return rank

    @classmethod
    def _rank_dict_no_write(cls, rank_level: Any) -> Optional[dict]:
        name, number = cls._parse_rank_level(rank_level)
        if not name:
            return None

        rank = GameRank.objects.filter(name=name, number=number).only("image").first()

        return {
            "name": name,
            "number": number,
            "image": rank.image if (rank and rank.image) else None,
        }

    @classmethod
    def _extract_profile_fields(cls, profile: dict) -> dict:
        modes = profile.get("modes") or {}
        avatars = profile.get("avatars") or {}

        rm_solo = modes.get("rm_solo") or {}
        rm_team = modes.get("rm_team") or {}

        rm_1v1_elo = modes.get("rm_1v1_elo") or {}
        rm_2v2_elo = modes.get("rm_2v2_elo") or {}
        rm_3v3_elo = modes.get("rm_3v3_elo") or {}
        rm_4v4_elo = modes.get("rm_4v4_elo") or {}

        return {
            "in_game_name": (profile.get("name") or "").strip(),
            "country": profile.get("country"),
            "avatars": {
                "small": avatars.get("small"),
                "medium": avatars.get("medium"),
                "full": avatars.get("full"),
            },

            "elo_solo": int_or_none(rm_solo.get("rating")),
            "elo_team": int_or_none(rm_team.get("rating")),

            "hidden_elos": {
                "1v1": int_or_none(rm_1v1_elo.get("rating")),
                "2v2": int_or_none(rm_2v2_elo.get("rating")),
                "3v3": int_or_none(rm_3v3_elo.get("rating")),
                "4v4": int_or_none(rm_4v4_elo.get("rating")),
            },

            "rank_level_solo": rm_solo.get("rank_level"),
            "rank_level_team": rm_team.get("rank_level"),
        }

    @classmethod
    def get_player_details(cls, *, code: str) -> dict:
        raw = (code or "").strip()
        if not raw.isdigit():
            raise ValidationError({"code": ["code must be a numeric AoE4World profile_id."]})

        profile_id = int(raw)
        profile = cls.get_player_profile(profile_id)

        extracted = cls._extract_profile_fields(profile)

        return {
            "code": str(profile_id),
            "in_game_name": extracted["in_game_name"],

            "avatars": extracted["avatars"],
            "country": extracted["country"],

            "elo_solo": extracted["elo_solo"],
            "elo_team": extracted["elo_team"],
            "hidden_elos": extracted["hidden_elos"],

            "rank_solo": cls._rank_dict_no_write(extracted["rank_level_solo"]),
            "rank_team": cls._rank_dict_no_write(extracted["rank_level_team"]),
        }

    @classmethod
    def upsert_profile_from_player_profile(cls, *, profile_id: int, profile: dict) -> AoeWorldProfile:
        extracted = cls._extract_profile_fields(profile)

        solo_rank_obj = cls._get_or_create_rank(extracted["rank_level_solo"])
        team_rank_obj = cls._get_or_create_rank(extracted["rank_level_team"])

        code = str(profile_id)

        obj, _ = AoeWorldProfile.objects.update_or_create(
            code=code,
            defaults={
                "in_game_name": extracted["in_game_name"],

                "avatar_small": extracted["avatars"]["small"],
                "avatar_medium": extracted["avatars"]["medium"],
                "avatar_full": extracted["avatars"]["full"],
                "country": extracted["country"],

                "elo_solo": extracted["elo_solo"],
                "elo_team": extracted["elo_team"],

                "hidden_elo_1v1": extracted["hidden_elos"]["1v1"],
                "hidden_elo_2v2": extracted["hidden_elos"]["2v2"],
                "hidden_elo_3v3": extracted["hidden_elos"]["3v3"],
                "hidden_elo_4v4": extracted["hidden_elos"]["4v4"],

                "rank_solo": solo_rank_obj,
                "rank_team": team_rank_obj,
            },
        )
        return obj