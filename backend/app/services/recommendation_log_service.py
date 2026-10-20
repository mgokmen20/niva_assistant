"""Persist a shown recommendation without putting SQL in the router."""

from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.recommendation import RecommendationLog


class RecommendationLogService:
    """Append one recommendation audit row to an open session."""

    async def record(
        self,
        db: AsyncSession,
        *,
        location_name: str,
        air_temperature: float,
        effective_temperature: float,
        recommended_layers: dict[str, object],
        decision_engine_used: str,
        client_ip_masked: str,
        temperature_band: str,
        user_id: UUID | None = None,
        gender: str = "unspecified",
    ) -> RecommendationLog:
        """Stage a masked recommendation log and flush it.

        The caller commits. ``client_ip_masked`` must already be the nDSG
        prefix; this method does not accept a raw address.

        Args:
            db: Open async session.
            location_name: Place name shown to the wearer.
            air_temperature: Dry-bulb temperature in degrees Celsius.
            effective_temperature: Decision temperature in degrees Celsius.
            recommended_layers: JSON-ready clothing payload.
            decision_engine_used: Provider name, such as ``rule_based``.
            client_ip_masked: Already truncated client address.
            temperature_band: Effective-temperature bucket for this outfit.
            user_id: Signed-in wearer id.
            gender: Wearer segment captured at recommendation time.

        Returns:
            The staged log, including its id.
        """
        entry = RecommendationLog(
            id=uuid4(),
            user_id=user_id,
            location_name=location_name,
            air_temperature=air_temperature,
            effective_temperature=effective_temperature,
            recommended_layers=recommended_layers,
            decision_engine_used=decision_engine_used,
            temperature_band=temperature_band,
            gender=gender,
            client_ip_masked=client_ip_masked,
        )
        db.add(entry)
        await db.flush()
        return entry
