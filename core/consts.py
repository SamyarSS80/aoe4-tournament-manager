class TournamentVisibility:
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"

    CHOICES = (
        (PUBLIC, "Public"),
        (PRIVATE, "Private"),
    )


class TournamentStatus:
    REGISTRATION = "REGISTRATION"
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"

    CHOICES = (
        (REGISTRATION, "Registration"),
        (RUNNING, "Running"),
        (FINISHED, "Finished"),
    )


class TournamentTeamJoinRequestStatus:
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    CANCELED = "CANCELED"

    CHOICES = (
        (PENDING, "Pending"),
        (ACCEPTED, "Accepted"),
        (REJECTED, "Rejected"),
        (CANCELED, "Canceled"),
    )


class EntrantStatus:
    ACTIVE = "ACTIVE"
    DROPPED = "DROPPED"
    DISQUALIFIED = "DISQUALIFIED"

    CHOICES = (
        (ACTIVE, "Active"),
        (DROPPED, "Dropped"),
        (DISQUALIFIED, "Disqualified"),
    )


class StageType:
    LEAGUE = "LEAGUE"
    SINGLE_ELIM = "SINGLE_ELIM"

    CHOICES = (
        (LEAGUE, "League / Round Robin"),
        (SINGLE_ELIM, "Single Elimination"),
    )


class MatchStatus:
    SCHEDULED = "SCHEDULED"
    LIVE = "LIVE"
    FINISHED = "FINISHED"
    CANCELED = "CANCELED"

    CHOICES = (
        (SCHEDULED, "Scheduled"),
        (LIVE, "Live"),
        (FINISHED, "Finished"),
        (CANCELED, "Canceled"),
    )
