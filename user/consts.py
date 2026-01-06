DAY_OF_WEEK_CHOICES = [
    (0, "Monday"),
    (1, "Tuesday"),
    (2, "Wednesday"),
    (3, "Thursday"),
    (4, "Friday"),
    (5, "Saturday"),
    (6, "Sunday"),
]

DAY_NAME_TO_INT = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

INT_TO_DAY_NAME = {v: k for k, v in DAY_NAME_TO_INT.items()}
INT_TO_DAY_LABEL = {k: v for k, v in DAY_OF_WEEK_CHOICES}

VALID_DAY_NAMES = sorted(DAY_NAME_TO_INT.keys())

USER_AVAILABILITY_MAX_HOURS = 16
USER_AVAILABILITY_MAX_SECONDS = USER_AVAILABILITY_MAX_HOURS * 60 * 60
