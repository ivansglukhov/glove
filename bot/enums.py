from enum import StrEnum


class WeaponType(StrEnum):
    FOIL = "foil"
    SABRE = "sabre"
    LONGSWORD = "longsword"
    RAPIER_DAGGER = "rapier_dagger"
    SWORD_BUCKLER = "sword_buckler"


class ReadinessStatus(StrEnum):
    NOT_READY = "not_ready"
    READY = "ready"
    READY_TODAY = "ready_today"
    READY_SOON = "ready_soon"
    ACTIVELY_LOOKING = "actively_looking"


class InvitationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class MatchStatus(StrEnum):
    ACTIVE = "active"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    DISPUTED = "disputed"
    COMPLETED = "completed"
    AUTO_DRAW = "auto_draw"


class ClubKind(StrEnum):
    FENCING = "fencing"
    LONGSWORD = "longsword"
    MIXED = "mixed"
