"""Persist a wearer's saved trips. Callers commit the session."""

from datetime import date
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.trip import UserTrip


class TripService:
    """Read and write ``user_trips`` for one signed-in wearer."""

    async def list_trips(self, db: AsyncSession, user_id: UUID) -> list[UserTrip]:
        """Return the wearer's trips, latest start date first."""
        rows = await db.execute(
            select(UserTrip)
            .where(UserTrip.user_id == user_id)
            .order_by(UserTrip.start_date.desc(), UserTrip.created_at.desc())
        )
        return list(rows.scalars().all())

    async def create_trip(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        destination_city: str,
        start_date: date,
        end_date: date,
        summary_text: str,
        packing_items: list[dict[str, Any]],
    ) -> UserTrip:
        """Stage a new trip and flush it so the id is available."""
        trip = UserTrip(
            id=uuid4(),
            user_id=user_id,
            destination_city=destination_city,
            start_date=start_date,
            end_date=end_date,
            summary_text=summary_text,
            packing_items=packing_items,
        )
        db.add(trip)
        await db.flush()
        return trip

    async def update_checks(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        trip_id: UUID,
        checks: dict[str, bool],
    ) -> UserTrip | None:
        """Set ``checked`` on matching items. Returns None when the trip is not theirs."""
        trip = await self._owned(db, user_id, trip_id)
        if trip is None:
            return None
        updated: list[dict[str, Any]] = []
        for raw in trip.packing_items:
            if not isinstance(raw, dict):
                continue
            row = dict(raw)
            item_id = str(row.get("id", ""))
            if item_id in checks:
                row["checked"] = checks[item_id]
            updated.append(row)
        trip.packing_items = updated
        await db.flush()
        return trip

    async def delete_trip(self, db: AsyncSession, *, user_id: UUID, trip_id: UUID) -> bool:
        """Delete one owned trip. Returns False when it is missing."""
        trip = await self._owned(db, user_id, trip_id)
        if trip is None:
            return False
        await db.delete(trip)
        await db.flush()
        return True

    async def _owned(self, db: AsyncSession, user_id: UUID, trip_id: UUID) -> UserTrip | None:
        """Return the trip only when it belongs to ``user_id``."""
        trip = await db.get(UserTrip, trip_id)
        if trip is None or trip.user_id != user_id:
            return None
        return trip
