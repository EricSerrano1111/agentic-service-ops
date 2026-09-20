"""Core operational tables — `docs/data-dictionary.md` §3.

service_requests, archived_requests, incidents, service_feedback.

Indexes follow §9 "Indexing considerations for the MCP tools". Note that §9 also
lists `service_feedback(request_id)`; that column carries a UNIQUE constraint, whose
backing btree index already serves those lookups, so no second index is declared.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, surrogate_pk, tz_timestamp
from .enums import (
    VOCAB_LEN,
    CancellationReason,
    IncidentStatus,
    IncidentType,
    PaymentMethod,
    PaymentStatus,
    PriorityTier,
    RequestStatus,
    ResponseChannel,
    RootCauseCategory,
    ServiceType,
    Severity,
    check_in,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .ground_truth import SentimentLabel
    from .reference import Account, Contact, InternalUser, Location, Technician


class ServiceRequest(Base):
    """Field service engagements — the system's records table."""

    __tablename__ = "service_requests"
    __table_args__ = (
        check_in("service_requests", "service_type", ServiceType),
        check_in("service_requests", "priority_tier", PriorityTier),
        check_in("service_requests", "request_status", RequestStatus),
        check_in("service_requests", "payment_method", PaymentMethod),
        check_in("service_requests", "cancellation_reason", CancellationReason),
        CheckConstraint(
            "equipment_unit_count > 0", name="ck_service_requests_equipment_unit_count_positive"
        ),
        # Not in §8. The SLA matrix in §2 only ever yields 30–480, so a non-positive
        # window is always a generator bug and should fail loudly at insert time.
        CheckConstraint(
            "sla_window_minutes > 0", name="ck_service_requests_sla_window_minutes_positive"
        ),
        # §8: cancelled_at IS NOT NULL ⟺ request_status = 'cancelled'.
        CheckConstraint(
            "(cancelled_at IS NOT NULL) = (request_status = 'cancelled')",
            name="ck_service_requests_cancelled_at_matches_status",
        ),
        # Not in §8, which is silent on the reason column. Closes the same gap: a
        # cancellation reason on a non-cancelled request is meaningless.
        CheckConstraint(
            "cancellation_reason IS NULL OR request_status = 'cancelled'",
            name="ck_service_requests_cancellation_reason_requires_cancelled",
        ),
        # §8: no self-reference. IS DISTINCT FROM rather than <> so a NULL parent
        # (the common case) passes rather than evaluating to NULL.
        CheckConstraint(
            "parent_request_id IS DISTINCT FROM request_id",
            name="ck_service_requests_parent_not_self",
        ),
        Index(None, "scheduled_datetime"),
        Index(None, "account_id", "scheduled_datetime"),
        Index(None, "request_status"),
        Index(None, "parent_request_id"),
    )

    request_id: Mapped[int] = surrogate_pk()
    reservation_number: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("accounts.account_id"), nullable=False
    )
    location_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("locations.location_id"), nullable=False
    )
    contact_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("contacts.contact_id"), nullable=False
    )
    service_type: Mapped[str] = mapped_column(String(VOCAB_LEN), nullable=False)
    priority_tier: Mapped[str] = mapped_column(String(VOCAB_LEN), nullable=False)
    equipment_unit_count: Mapped[int] = mapped_column(Integer, nullable=False)
    scheduled_datetime: Mapped[dt.datetime] = tz_timestamp()
    #: Snapshotted from the account's contract tier at creation time (ADR-017), never
    #: joined live — a tier change must not retroactively re-judge past requests.
    sla_window_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    assigned_technician_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("technicians.technician_id"), nullable=True
    )
    #: Requested method; what actually settled lives in
    #: `archived_requests.payment_method_final`.
    payment_method: Mapped[str] = mapped_column(String(VOCAB_LEN), nullable=False)
    request_status: Mapped[str] = mapped_column(String(VOCAB_LEN), nullable=False)
    #: Self-reference for repeat visits — the denominator of first-time-fix rate (§6).
    parent_request_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("service_requests.request_id"), nullable=True
    )
    #: The SLA clock start (§6) — *not* `scheduled_datetime`. Requests never
    #: dispatched have no SLA outcome.
    dispatched_at: Mapped[dt.datetime | None] = tz_timestamp(nullable=True)
    cancelled_at: Mapped[dt.datetime | None] = tz_timestamp(nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(VOCAB_LEN), nullable=True)
    created_at: Mapped[dt.datetime] = tz_timestamp(server_now=True)
    updated_at: Mapped[dt.datetime] = tz_timestamp(server_now=True)
    created_by_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("internal_users.user_id"), nullable=False
    )

    account: Mapped[Account] = relationship(back_populates="service_requests")
    location: Mapped[Location] = relationship()
    contact: Mapped[Contact] = relationship()
    assigned_technician: Mapped[Technician | None] = relationship()
    created_by_user: Mapped[InternalUser] = relationship(back_populates="service_requests")
    parent_request: Mapped[ServiceRequest | None] = relationship(
        remote_side=lambda: [ServiceRequest.request_id],
        back_populates="child_requests",
    )
    child_requests: Mapped[list[ServiceRequest]] = relationship(back_populates="parent_request")
    archive: Mapped[ArchivedRequest | None] = relationship(back_populates="request")
    incidents: Mapped[list[Incident]] = relationship(back_populates="request")
    feedback: Mapped[ServiceFeedback | None] = relationship(back_populates="request")


class ArchivedRequest(Base):
    """Completed requests with final billing.

    **0..1** with `service_requests`, not 1:1 — cancelled requests never archive.
    Reporting and forecast joins must be outer joins or they will silently undercount.

    `total_invoice` is deliberately not stored: §3 defines it as
    `(labor_charge + parts_charge) * (1 + surcharge_rate)`, computed in the reporting
    MCP tool so it cannot drift from its inputs. `sla_met` is likewise derived (§6).
    """

    __tablename__ = "archived_requests"
    __table_args__ = (
        check_in("archived_requests", "payment_method_final", PaymentMethod),
        check_in("archived_requests", "payment_status", PaymentStatus),
        CheckConstraint("labor_charge >= 0", name="ck_archived_requests_labor_charge_non_negative"),
        CheckConstraint("parts_charge >= 0", name="ck_archived_requests_parts_charge_non_negative"),
        CheckConstraint(
            "surcharge_rate >= 0 AND surcharge_rate <= 1",
            name="ck_archived_requests_surcharge_rate_range",
        ),
        Index(None, "completed_at"),
    )

    request_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("service_requests.request_id"), primary_key=True
    )
    completed_at: Mapped[dt.datetime] = tz_timestamp()
    technician_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("technicians.technician_id"), nullable=False
    )
    labor_charge: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    parts_charge: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    #: Stored as a rate, e.g. 0.0300 for 3% (§6).
    surcharge_rate: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    payment_method_final: Mapped[str] = mapped_column(String(VOCAB_LEN), nullable=False)
    payment_status: Mapped[str] = mapped_column(String(VOCAB_LEN), nullable=False)
    #: Last-4 or transaction reference only — never a full card or account number (§9).
    payment_reference: Mapped[str | None] = mapped_column(String(50), nullable=True)
    archived_at: Mapped[dt.datetime] = tz_timestamp(server_now=True)
    updated_at: Mapped[dt.datetime] = tz_timestamp(server_now=True)

    request: Mapped[ServiceRequest] = relationship(back_populates="archive")
    technician: Mapped[Technician] = relationship()


class Incident(TimestampMixin, Base):
    """Quality events requiring investigation. 1:many with a request.

    `incident_notes` is internal staff writing, not the customer's words. It is never
    fed to the sentiment agent — enforced structurally by `app_sentiment` holding no
    grant on this table at all (§7), not by code convention.

    The original invoice amount is deliberately absent: it is reachable via
    `request_id → archived_requests`, and a second copy would drift.
    """

    __tablename__ = "incidents"
    __table_args__ = (
        check_in("incidents", "incident_type", IncidentType),
        check_in("incidents", "incident_status", IncidentStatus),
        check_in("incidents", "severity", Severity),
        check_in("incidents", "root_cause_category", RootCauseCategory),
        CheckConstraint(
            "credit_issued_amount >= 0", name="ck_incidents_credit_issued_amount_non_negative"
        ),
        Index(None, "request_id"),
        Index(None, "incident_type", "reported_at"),
    )

    incident_id: Mapped[int] = surrogate_pk()
    request_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("service_requests.request_id"), nullable=False
    )
    incident_type: Mapped[str] = mapped_column(String(VOCAB_LEN), nullable=False)
    incident_status: Mapped[str] = mapped_column(String(VOCAB_LEN), nullable=False)
    severity: Mapped[str] = mapped_column(String(VOCAB_LEN), nullable=False)
    root_cause_category: Mapped[str | None] = mapped_column(String(VOCAB_LEN), nullable=True)
    #: Nullable — dispatch errors and site issues are not technician-attributable.
    attributed_technician_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("technicians.technician_id"), nullable=True
    )
    reported_at: Mapped[dt.datetime] = tz_timestamp()
    reported_by_contact_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("contacts.contact_id"), nullable=False
    )
    resolved_at: Mapped[dt.datetime | None] = tz_timestamp(nullable=True)
    incident_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    credit_issued_amount: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    created_by_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("internal_users.user_id"), nullable=False
    )

    request: Mapped[ServiceRequest] = relationship(back_populates="incidents")
    attributed_technician: Mapped[Technician | None] = relationship()
    reported_by_contact: Mapped[Contact] = relationship()
    created_by_user: Mapped[InternalUser] = relationship(back_populates="incidents")


class ServiceFeedback(Base):
    """Post-visit customer survey responses — the sentiment agent's sole data source.

    `rating` and `feedback_text` both exist on purpose: the numeric rating is an
    independent cross-check on classification, so a "positive" call on a 1-star review
    is a detectable contradiction for the QA agent (§3).

    `app_reporting` receives column-level SELECT here that excludes `feedback_text`,
    which is how §7's "SELECT (aggregate)" is enforced at the database level.
    """

    __tablename__ = "service_feedback"
    __table_args__ = (
        check_in("service_feedback", "response_channel", ResponseChannel),
        CheckConstraint(
            "rating >= 1 AND rating <= 5", name="ck_service_feedback_rating_range"
        ),  # NULL passes — rating is optional
        Index(None, "submitted_at"),
    )

    feedback_id: Mapped[int] = surrogate_pk()
    #: UNIQUE — at most one survey per completed request.
    request_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("service_requests.request_id"), nullable=False, unique=True
    )
    #: Optional link when the feedback accompanies a logged complaint.
    incident_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("incidents.incident_id"), nullable=True
    )
    submitted_by_contact_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("contacts.contact_id"), nullable=False
    )
    submitted_at: Mapped[dt.datetime] = tz_timestamp()
    rating: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    #: The customer's own words — this is what the sentiment agent reads.
    feedback_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_channel: Mapped[str] = mapped_column(String(VOCAB_LEN), nullable=False)
    created_at: Mapped[dt.datetime] = tz_timestamp(server_now=True)

    request: Mapped[ServiceRequest] = relationship(back_populates="feedback")
    incident: Mapped[Incident | None] = relationship()
    submitted_by_contact: Mapped[Contact] = relationship()
    sentiment_label: Mapped[SentimentLabel | None] = relationship(back_populates="feedback")
