"""Controlled vocabularies — `docs/data-dictionary.md` §5.

Implemented as `VARCHAR` + named `CHECK` constraint rather than native Postgres
`ENUM` types, per §6 and ADR-020: adding a value to a native enum needs a migration
and removing one is worse, while a CHECK gives identical validation for a one-line
change when a missing value turns up mid-sprint.

`sa.Enum(native_enum=False)` would also satisfy ADR-020, but it auto-names its
constraint. `\\d service_requests` output is a review artifact on this project, so the
constraints are named explicitly (`ck_service_requests_service_type`) via
:func:`check_in`.

The `StrEnum` classes are the single source of truth for these value sets and are
meant to be reused by the data generator, the Pydantic contracts in
`packages/schemas/`, and the eval harness — not just by the DDL.
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import CheckConstraint

# Width for every vocabulary column. The longest value in use is
# `communication_breakdown` (23); 32 leaves room without being sloppy.
VOCAB_LEN = 32


# --------------------------------------------------------------------------- #
# §5 consolidated vocabularies
# --------------------------------------------------------------------------- #


class ServiceType(StrEnum):
    INSTALL = "install"
    REPAIR = "repair"
    MAINTENANCE = "maintenance"
    INSPECTION = "inspection"
    UPGRADE = "upgrade"


class PriorityTier(StrEnum):
    STANDARD = "standard"
    URGENT = "urgent"
    CRITICAL = "critical"


class RequestStatus(StrEnum):
    OPEN = "open"
    DISPATCHED = "dispatched"
    EN_ROUTE = "en_route"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PaymentMethod(StrEnum):
    CREDIT_CARD = "credit_card"
    DIRECT_BILL = "direct_bill"
    ACH = "ach"
    CHECK = "check"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    DISPUTED = "disputed"


class IncidentType(StrEnum):
    MISSED_SLA = "missed_sla"
    WRONG_DISPATCH_INFO = "wrong_dispatch_info"
    REPEAT_VISIT_REQUIRED = "repeat_visit_required"
    TECHNICIAN_CONDUCT = "technician_conduct"
    EQUIPMENT_DAMAGE = "equipment_damage"
    BILLING_DISPUTE = "billing_dispute"
    OTHER = "other"


class IncidentStatus(StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    CLOSED = "closed"


class RootCauseCategory(StrEnum):
    DISPATCH_ERROR = "dispatch_error"
    TECHNICIAN_ERROR = "technician_error"
    EQUIPMENT_FAILURE = "equipment_failure"
    CLIENT_SITE_ISSUE = "client_site_issue"
    COMMUNICATION_BREAKDOWN = "communication_breakdown"
    OTHER = "other"


class ContractTier(StrEnum):
    STANDARD = "standard"
    PRIORITY = "priority"
    ENTERPRISE = "enterprise"


class AccountStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PROSPECT = "prospect"


class TechnicianStatus(StrEnum):
    ACTIVE = "active"
    ON_LEAVE = "on_leave"
    TERMINATED = "terminated"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CancellationReason(StrEnum):
    CLIENT_CANCELLED = "client_cancelled"
    CLIENT_NO_SHOW = "client_no_show"
    RESOURCE_UNAVAILABLE = "resource_unavailable"
    DUPLICATE = "duplicate"
    OTHER = "other"


class ResponseChannel(StrEnum):
    EMAIL_SURVEY = "email_survey"
    SMS_SURVEY = "sms_survey"
    PHONE_FOLLOWUP = "phone_followup"
    PORTAL = "portal"


class UserRole(StrEnum):
    DISPATCHER = "dispatcher"
    SUPERVISOR = "supervisor"
    BILLING_CLERK = "billing_clerk"
    QA_ANALYST = "qa_analyst"


class TrueSentiment(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    MIXED = "mixed"


# --------------------------------------------------------------------------- #
# Vocabularies used by the §2–§4 table definitions but absent from §5's
# consolidated list. Flagged for a data-dictionary correction.
# --------------------------------------------------------------------------- #


class ContactRole(StrEnum):
    """`contacts.contact_role` — §2."""

    SITE_CONTACT = "site_contact"
    BILLING_CONTACT = "billing_contact"
    ACCOUNT_ADMIN = "account_admin"
    OTHER = "other"


class UserStatus(StrEnum):
    """`internal_users.user_status` — §2."""

    ACTIVE = "active"
    INACTIVE = "inactive"


class Skill(StrEnum):
    """`technician_skills.skill` — §2."""

    NETWORK = "network"
    HARDWARE = "hardware"
    CABLING = "cabling"
    SECURITY_SYSTEMS = "security_systems"
    POWER_SYSTEMS = "power_systems"


class Proficiency(StrEnum):
    """`technician_skills.proficiency` — §2."""

    CERTIFIED = "certified"
    EXPERIENCED = "experienced"
    TRAINEE = "trainee"


class ParamGroup(StrEnum):
    """`generation_parameters.param_group` — §4. `world` and `feedback` added by ADR-038."""

    VOLUME = "volume"
    INCIDENTS = "incidents"
    SENTIMENT = "sentiment"
    BILLING = "billing"
    ANOMALIES = "anomalies"
    WORLD = "world"
    FEEDBACK = "feedback"


class HardCaseType(StrEnum):
    """`sentiment_labels.hard_case_type` — §4 (ADR-036, ADR-037).

    Which kind of deliberately hard case a feedback comment is, so failure analysis can
    report accuracy per type. `none` for ordinary comments.
    """

    NONE = "none"
    SARCASTIC = "sarcastic"
    IMPLICIT = "implicit"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def values(vocab: type[StrEnum]) -> tuple[str, ...]:
    """The allowed values of a vocabulary, in declaration order."""
    return tuple(member.value for member in vocab)


def check_in(table: str, column: str, vocab: type[StrEnum]) -> CheckConstraint:
    """A named CHECK restricting `table.column` to `vocab`'s values.

    The table name is passed explicitly rather than derived from a naming
    convention: see the note in `base.py` on why the `ck` convention is omitted.
    Emits e.g. `ck_service_requests_service_type`.
    """
    rendered = ", ".join(f"'{value}'" for value in values(vocab))
    return CheckConstraint(f"{column} IN ({rendered})", name=f"ck_{table}_{column}")


ALL_VOCABULARIES: tuple[type[StrEnum], ...] = (
    ServiceType,
    PriorityTier,
    RequestStatus,
    PaymentMethod,
    PaymentStatus,
    IncidentType,
    IncidentStatus,
    RootCauseCategory,
    ContractTier,
    AccountStatus,
    TechnicianStatus,
    Severity,
    CancellationReason,
    ResponseChannel,
    UserRole,
    TrueSentiment,
    ContactRole,
    UserStatus,
    Skill,
    Proficiency,
    ParamGroup,
    HardCaseType,
)
