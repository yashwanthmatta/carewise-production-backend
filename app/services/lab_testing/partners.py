"""Lab partners and their locations.

A location can be shown to people as a place to get tested only when it belongs to a partner with
a signed (or otherwise authorised) agreement and has been verified. Anything else is an
informational listing at most, and is never bookable. No partner is listed here: real partners are
added by the owner after an agreement, through reviewed onboarding.

LabPartnerAdapter is the interface every partner integration implements (manual onboarding first,
an API later). SyntheticPartner is for tests only.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Partner:
    id: str
    name: str
    kind: str  # independent_lab, regional_lab, national_network, collection_center, mobile_phlebotomy
    agreement_signed: bool = False
    verified_by: str = ""  # who on the team verified the agreement and capabilities
    synthetic: bool = False


@dataclass(frozen=True)
class Location:
    id: str
    partner_id: str
    name: str
    city: str
    state: str
    zip_code: str
    collection_types: tuple[str, ...] = ("walk_in",)
    verified: bool = False
    hours: str = ""  # only partner-confirmed hours
    accessibility: str = ""
    synthetic: bool = False


def bookable(location: Location, partner: Partner) -> bool:
    """Bookable only when the partner has a signed agreement, the location is verified, and both
    belong together. Synthetic data is never bookable outside tests' own synthetic flow."""
    return (
        location.partner_id == partner.id
        and partner.agreement_signed
        and bool(partner.verified_by)
        and location.verified
        and not partner.synthetic
        and not location.synthetic
    )


def listing_kind(location: Location, partner: Partner | None) -> str:
    """How a location may be described: 'partner' only when bookable, else 'informational'."""
    return "partner" if partner is not None and bookable(location, partner) else "informational"


@dataclass(frozen=True)
class Slot:
    location_id: str
    starts_at: datetime  # timezone-aware, from the partner
    partner_slot_id: str


@dataclass
class BookingAck:
    partner_booking_id: str
    confirmed: bool
    raw_status: str = ""


class LabPartnerAdapter(ABC):
    """What every partner integration provides. Nothing is assumed: each call returns what the
    partner itself confirms."""

    partner: Partner

    @abstractmethod
    def slots(self, location_id: str, test_keys: list[str]) -> list[Slot]: ...

    @abstractmethod
    def book(self, slot: Slot, order_id: str) -> BookingAck: ...

    @abstractmethod
    def cancel(self, partner_booking_id: str) -> bool: ...


@dataclass
class SyntheticPartner(LabPartnerAdapter):
    """For tests and demos only. Its slots and bookings are made up, and it is marked synthetic so
    nothing it returns can be shown as a real place or time."""

    partner: Partner = field(default_factory=lambda: Partner(id="synthetic-lab", name="Synthetic Test Lab", kind="independent_lab", synthetic=True))
    fail_booking: bool = False
    cancelled: list[str] = field(default_factory=list)

    def slots(self, location_id, test_keys):
        return [Slot(location_id=location_id, starts_at=datetime.fromisoformat("2030-01-07T09:00:00+00:00"), partner_slot_id="syn-slot-1")]

    def book(self, slot, order_id):
        if self.fail_booking:
            return BookingAck(partner_booking_id="", confirmed=False, raw_status="rejected")
        return BookingAck(partner_booking_id=f"syn-{order_id}", confirmed=True, raw_status="booked")

    def cancel(self, partner_booking_id):
        self.cancelled.append(partner_booking_id)
        return True
