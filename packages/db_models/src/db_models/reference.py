"""Reference tables — `docs/data-dictionary.md` §2.

accounts, contacts, locations, technicians, technician_skills, internal_users.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, surrogate_pk, tz_timestamp
from .enums import (
    VOCAB_LEN,
    AccountStatus,
    ContactRole,
    ContractTier,
    Proficiency,
    Skill,
    TechnicianStatus,
    UserRole,
    UserStatus,
    check_in,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .operational import Incident, ServiceRequest


class Account(Base):
    """Client companies being served."""

    __tablename__ = "accounts"
    __table_args__ = (
        check_in("accounts", "account_status", AccountStatus),
        check_in("accounts", "contract_tier", ContractTier),
    )

    account_id: Mapped[int] = surrogate_pk()
    account_code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    account_name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_status: Mapped[str] = mapped_column(String(VOCAB_LEN), nullable=False)
    #: Drives the SLA default matrix the generator snapshots onto each request
    #: (ADR-017) — it is never joined at query time.
    contract_tier: Mapped[str] = mapped_column(String(VOCAB_LEN), nullable=False)
    created_at: Mapped[dt.datetime] = tz_timestamp(server_now=True)

    contacts: Mapped[list[Contact]] = relationship(back_populates="account")
    locations: Mapped[list[Location]] = relationship(back_populates="account")
    service_requests: Mapped[list[ServiceRequest]] = relationship(back_populates="account")


class Contact(Base):
    """People associated with an account.

    No agent role holds any grant on this table (§7) — customer PII never enters an
    LLM context window.
    """

    __tablename__ = "contacts"
    __table_args__ = (check_in("contacts", "contact_role", ContactRole),)

    contact_id: Mapped[int] = surrogate_pk()
    account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("accounts.account_id"), nullable=False
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_role: Mapped[str | None] = mapped_column(String(VOCAB_LEN), nullable=True)

    account: Mapped[Account] = relationship(back_populates="contacts")


class Location(Base):
    """Client sites where a technician is dispatched."""

    __tablename__ = "locations"

    location_id: Mapped[int] = surrogate_pk()
    account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("accounts.account_id"), nullable=False
    )
    site_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    street_address: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    zip_code: Mapped[str] = mapped_column(String(10), nullable=False)

    account: Mapped[Account] = relationship(back_populates="locations")


class Technician(Base):
    """Internal dispatch resources."""

    __tablename__ = "technicians"
    __table_args__ = (check_in("technicians", "technician_status", TechnicianStatus),)

    technician_id: Mapped[int] = surrogate_pk()
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    technician_status: Mapped[str] = mapped_column(String(VOCAB_LEN), nullable=False)
    home_region: Mapped[str | None] = mapped_column(String(100), nullable=True)

    skills: Mapped[list[TechnicianSkill]] = relationship(back_populates="technician")


class TechnicianSkill(Base):
    """One row per technician-skill pair (ADR-016).

    Replaces a delimited `skill_tags` column: substring matching on a delimited list
    is a first-normal-form violation and `LIKE '%network%'` would also match
    `network_admin`.
    """

    __tablename__ = "technician_skills"
    __table_args__ = (
        check_in("technician_skills", "skill", Skill),
        check_in("technician_skills", "proficiency", Proficiency),
    )

    technician_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("technicians.technician_id"), primary_key=True
    )
    skill: Mapped[str] = mapped_column(String(VOCAB_LEN), primary_key=True)
    #: §2 calls this an "optional dimension for later capacity modeling" — that
    #: describes the modeling use, not the value. Every row carries one.
    proficiency: Mapped[str] = mapped_column(String(VOCAB_LEN), nullable=False)

    technician: Mapped[Technician] = relationship(back_populates="skills")


class InternalUser(Base):
    """Dispatch and back-office staff who create records.

    Exists so `created_by_user_id` references something real rather than dangling.
    No agent role holds a grant on this table (§7).
    """

    __tablename__ = "internal_users"
    __table_args__ = (
        check_in("internal_users", "user_role", UserRole),
        check_in("internal_users", "user_status", UserStatus),
    )

    user_id: Mapped[int] = surrogate_pk()
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    user_role: Mapped[str] = mapped_column(String(VOCAB_LEN), nullable=False)
    user_status: Mapped[str] = mapped_column(String(VOCAB_LEN), nullable=False)

    service_requests: Mapped[list[ServiceRequest]] = relationship(back_populates="created_by_user")
    incidents: Mapped[list[Incident]] = relationship(back_populates="created_by_user")
