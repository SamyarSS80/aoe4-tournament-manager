import logging
from datetime import time as dt_time

from django.db import transaction
from rest_framework.exceptions import ValidationError

from user import consts
from user.models import UserAvailability

logger = logging.getLogger(__name__)


class UserAvailabilityService:
    @staticmethod
    def _to_offset(day: int, t) -> int:
        return (
            int(day) * 86400
            + (t.hour * 3600)
            + (t.minute * 60)
            + int(getattr(t, "second", 0) or 0)
        )

    @staticmethod
    def _from_offset(offset: int) -> tuple[int, dt_time]:
        day = int(offset // 86400)
        seconds = int(offset % 86400)

        hour = seconds // 3600
        seconds = seconds % 3600

        minute = seconds // 60
        second = seconds % 60

        return day, dt_time(hour=hour, minute=minute, second=second)

    @staticmethod
    def create_or_merge(*, user, start_day: int, start_time, end_day: int, end_time, instance_id: int | None = None) -> tuple[UserAvailability, bool]:
        new_start = UserAvailabilityService._to_offset(start_day, start_time)
        new_end = UserAvailabilityService._to_offset(end_day, end_time)

        if new_end <= new_start:
            raise ValidationError(
                {"end_time": ["End must be after start (across the week)."]}
            )

        if (new_end - new_start) > int(consts.USER_AVAILABILITY_MAX_SECONDS):
            raise ValidationError(
                {
                    "detail": f"Availability span cannot exceed {consts.USER_AVAILABILITY_MAX_HOURS} hours."
                }
            )

        with transaction.atomic():
            base_qs = UserAvailability.objects.select_for_update().filter(user=user)

            current = None
            if instance_id is not None:
                current = base_qs.filter(id=instance_id).first()
                if not current:
                    raise ValidationError({"detail": "Availability not found."})

            overlaps = (
                base_qs.exclude(id=instance_id)
                .filter(start_offset__lte=new_end, end_offset__gte=new_start)
                .order_by("start_offset", "id")
            )
            overlap_list = list(overlaps)

            if current is not None:
                overlap_list.insert(0, current)

            if overlap_list:
                merged_start = min([new_start] + [x.start_offset for x in overlap_list])
                merged_end = max([new_end] + [x.end_offset for x in overlap_list])

                if (merged_end - merged_start) > int(
                    consts.USER_AVAILABILITY_MAX_SECONDS
                ):
                    raise ValidationError(
                        {
                            "detail": f"Merged availability span cannot exceed {consts.USER_AVAILABILITY_MAX_HOURS} hours."
                        }
                    )

                target = current or overlap_list[0]

                sd, st = UserAvailabilityService._from_offset(merged_start)
                ed, et = UserAvailabilityService._from_offset(merged_end)

                target.start_day = sd
                target.start_time = st
                target.end_day = ed
                target.end_time = et
                target.save(
                    update_fields=[
                        "start_day",
                        "start_time",
                        "end_day",
                        "end_time",
                        "start_offset",
                        "end_offset",
                        "updated_at",
                    ]
                )

                delete_ids = [x.id for x in overlap_list if x.id and x.id != target.id]
                if delete_ids:
                    UserAvailability.objects.filter(
                        user=user, id__in=delete_ids
                    ).delete()

                logger.info(
                    "Merged user availability",
                    extra={
                        "user_id": user.id,
                        "target_id": target.id,
                        "deleted_ids": delete_ids,
                    },
                )
                return target, False

            obj = UserAvailability.objects.create(
                user=user,
                start_day=start_day,
                start_time=start_time,
                end_day=end_day,
                end_time=end_time,
            )

            logger.info(
                "Created user availability",
                extra={"user_id": user.id, "availability_id": obj.id},
            )
            return obj, True
