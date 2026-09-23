"""SQLAlchemy models for the field service operations schema.

The authoritative specification is `docs/data-dictionary.md`. This package is the
executable form of it, and `Base.metadata` is what Alembic autogenerates against.

Importing this module imports every model, which is what makes `Base.metadata`
complete — `data/migrations/env.py` depends on that.
"""

from __future__ import annotations

from .access_matrix import (
    ALL_GRANTS,
    ALL_ROLES,
    ALL_TABLES,
    COLUMN_SELECT_GRANTS,
    PII_RESTRICTED_TABLES,
    ROLE_ENV_VARS,
    ROLE_FORECAST,
    ROLE_GENERATOR,
    ROLE_QA,
    ROLE_REPORTING,
    ROLE_SENTIMENT,
    SELECT_GRANTS,
    tables_readable_by,
)
from .base import NAMING_CONVENTION, Base, TimestampMixin, metadata_obj
from .enums import (
    ALL_VOCABULARIES,
    VOCAB_LEN,
    AccountStatus,
    CancellationReason,
    ContactRole,
    ContractTier,
    HardCaseType,
    IncidentStatus,
    IncidentType,
    ParamGroup,
    PaymentMethod,
    PaymentStatus,
    PriorityTier,
    Proficiency,
    RequestStatus,
    ResponseChannel,
    RootCauseCategory,
    ServiceType,
    Severity,
    Skill,
    TechnicianStatus,
    TrueSentiment,
    UserRole,
    UserStatus,
    check_in,
    values,
)
from .ground_truth import GenerationParameter, SentimentLabel
from .operational import ArchivedRequest, Incident, ServiceFeedback, ServiceRequest
from .reference import (
    Account,
    Contact,
    InternalUser,
    Location,
    Technician,
    TechnicianSkill,
)

metadata = Base.metadata

__all__ = [
    # base
    "Base",
    "NAMING_CONVENTION",
    "TimestampMixin",
    "metadata",
    "metadata_obj",
    # reference tables (§2)
    "Account",
    "Contact",
    "InternalUser",
    "Location",
    "Technician",
    "TechnicianSkill",
    # operational tables (§3)
    "ArchivedRequest",
    "Incident",
    "ServiceFeedback",
    "ServiceRequest",
    # ground-truth tables (§4)
    "GenerationParameter",
    "SentimentLabel",
    # vocabularies (§5)
    "ALL_VOCABULARIES",
    "VOCAB_LEN",
    "AccountStatus",
    "CancellationReason",
    "ContactRole",
    "ContractTier",
    "HardCaseType",
    "IncidentStatus",
    "IncidentType",
    "ParamGroup",
    "PaymentMethod",
    "PaymentStatus",
    "PriorityTier",
    "Proficiency",
    "RequestStatus",
    "ResponseChannel",
    "RootCauseCategory",
    "ServiceType",
    "Severity",
    "Skill",
    "TechnicianStatus",
    "TrueSentiment",
    "UserRole",
    "UserStatus",
    "check_in",
    "values",
    # access matrix (§7)
    "ALL_GRANTS",
    "ALL_ROLES",
    "ALL_TABLES",
    "COLUMN_SELECT_GRANTS",
    "PII_RESTRICTED_TABLES",
    "ROLE_ENV_VARS",
    "ROLE_FORECAST",
    "ROLE_GENERATOR",
    "ROLE_QA",
    "ROLE_REPORTING",
    "ROLE_SENTIMENT",
    "SELECT_GRANTS",
    "tables_readable_by",
]
