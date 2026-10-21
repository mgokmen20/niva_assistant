"""Clothing the wearer owns.

Rows belong to one account. They describe a garment the wardrobe can
later match to a recommendation. They do not change the thermal engine.
"""

from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String, false as sql_false, true as sql_true
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from .base import Base
from .user import User

WARDROBE_CATEGORIES: tuple[str, ...] = (
    "T-Shirt",
    "Sweater",
    "Pants",
    "Outerwear",
    "Shorts",
    "Accessory",
)
WARDROBE_THICKNESSES: tuple[str, ...] = ("Thin", "Normal", "Thick", "Thermal")
WARDROBE_STYLES: tuple[str, ...] = ("Casual", "Sport", "Formal", "Outdoor")


def _sql_in(column: str, values: tuple[str, ...]) -> str:
    """Build a fixed IN check. Values are constants, not request data."""
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


class WardrobeItem(Base):
    """One garment saved by a signed-in wearer."""

    __tablename__ = "wardrobe_items"
    __table_args__ = (
        CheckConstraint(_sql_in("category", WARDROBE_CATEGORIES), name="ck_wardrobe_items_category"),
        CheckConstraint(_sql_in("thickness", WARDROBE_THICKNESSES), name="ck_wardrobe_items_thickness"),
        CheckConstraint(_sql_in("style", WARDROBE_STYLES), name="ck_wardrobe_items_style"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    thickness: Mapped[str] = mapped_column(String(16), nullable=False)
    color_name: Mapped[str] = mapped_column(String(40), nullable=False)
    style: Mapped[str] = mapped_column(String(16), nullable=False)
    is_waterproof: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=sql_false(),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=sql_true(),
    )
    item_name: Mapped[str] = mapped_column(String(120), nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    user: Mapped[User] = relationship(back_populates="wardrobe_items")

    def __repr__(self) -> str:
        """Return an id-only representation so logs omit garment details."""
        return f"WardrobeItem(id={self.id!s})"
