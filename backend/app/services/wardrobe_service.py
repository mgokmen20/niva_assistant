"""Persist a wearer's wardrobe. Callers commit the session."""

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.wardrobe import WardrobeItem


class WardrobeService:
    """Read and write ``wardrobe_items`` for one signed-in wearer."""

    async def list_items(self, db: AsyncSession, user_id: UUID) -> list[WardrobeItem]:
        """Return the wearer's garments, ordered by name."""
        rows = await db.execute(
            select(WardrobeItem)
            .where(WardrobeItem.user_id == user_id)
            .order_by(WardrobeItem.item_name.asc(), WardrobeItem.id.asc())
        )
        return list(rows.scalars().all())

    async def list_active_items(self, db: AsyncSession, user_id: UUID) -> list[WardrobeItem]:
        """Return garments the wearer can use, ordered by name."""
        rows = await db.execute(
            select(WardrobeItem)
            .where(WardrobeItem.user_id == user_id, WardrobeItem.is_active.is_(True))
            .order_by(WardrobeItem.item_name.asc(), WardrobeItem.id.asc())
        )
        return list(rows.scalars().all())

    async def create_item(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        category: str,
        thickness: str,
        color_name: str,
        style: str,
        is_waterproof: bool,
        item_name: str,
        image_url: str | None = None,
    ) -> WardrobeItem:
        """Stage a new garment and flush it so the id is available."""
        item = WardrobeItem(
            id=uuid4(),
            user_id=user_id,
            category=category,
            thickness=thickness,
            color_name=color_name,
            style=style,
            is_waterproof=is_waterproof,
            item_name=item_name,
            image_url=image_url,
        )
        db.add(item)
        await db.flush()
        return item

    async def update_item(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        item_id: UUID,
        category: str,
        thickness: str,
        color_name: str,
        style: str,
        is_waterproof: bool,
        item_name: str,
        image_url: str | None = None,
    ) -> WardrobeItem | None:
        """Replace one owned garment. Returns None when it is not theirs."""
        item = await self._owned(db, user_id, item_id)
        if item is None:
            return None
        item.category = category
        item.thickness = thickness
        item.color_name = color_name
        item.style = style
        item.is_waterproof = is_waterproof
        item.item_name = item_name
        item.image_url = image_url
        await db.flush()
        return item

    async def toggle_active(self, db: AsyncSession, *, user_id: UUID, item_id: UUID) -> WardrobeItem | None:
        """Flip whether the wearer can use this garment. Returns None when it is not theirs."""
        item = await self._owned(db, user_id, item_id)
        if item is None:
            return None
        item.is_active = not item.is_active
        await db.flush()
        return item

    async def delete_item(self, db: AsyncSession, *, user_id: UUID, item_id: UUID) -> bool:
        """Delete one owned garment. Returns False when it is missing."""
        item = await self._owned(db, user_id, item_id)
        if item is None:
            return False
        await db.delete(item)
        await db.flush()
        return True

    async def _owned(self, db: AsyncSession, user_id: UUID, item_id: UUID) -> WardrobeItem | None:
        """Return the garment only when it belongs to ``user_id``."""
        item = await db.get(WardrobeItem, item_id)
        if item is None or item.user_id != user_id:
            return None
        return item
