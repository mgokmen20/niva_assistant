"""Request and response models for a wearer's wardrobe."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

_IMAGE_URL_PREFIXES = ("http://", "https://")

WardrobeCategory = Literal["T-Shirt", "Sweater", "Pants", "Outerwear", "Shorts", "Accessory"]
WardrobeThickness = Literal["Thin", "Normal", "Thick", "Thermal"]
WardrobeStyle = Literal["Casual", "Sport", "Formal", "Outdoor"]


class WardrobeItemCreate(BaseModel):
    """A garment the signed-in wearer wants to store."""

    category: WardrobeCategory
    thickness: WardrobeThickness
    color_name: str = Field(min_length=1, max_length=40)
    style: WardrobeStyle
    is_waterproof: bool = False
    item_name: str = Field(min_length=1, max_length=120)
    image_url: str | None = Field(default=None, max_length=500)

    @field_validator("color_name", "item_name")
    @classmethod
    def strip_text(cls, value: str) -> str:
        """Reject blank text after surrounding whitespace is removed."""
        text = value.strip()
        if text == "":
            raise ValueError("Must not be blank.")
        return text

    @field_validator("image_url")
    @classmethod
    def clean_image_url(cls, value: str | None) -> str | None:
        """Keep a direct http(s) link and treat a blank value as missing."""
        if value is None:
            return None
        text = value.strip()
        if text == "":
            return None
        if not text.lower().startswith(_IMAGE_URL_PREFIXES):
            raise ValueError("Image URL must start with http:// or https://.")
        return text


class WardrobeItemUpdate(WardrobeItemCreate):
    """A full replacement of one stored garment."""


class WardrobeItemResponse(BaseModel):
    """One wardrobe row returned to its owner."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    category: WardrobeCategory
    thickness: WardrobeThickness
    color_name: str
    style: WardrobeStyle
    is_waterproof: bool
    is_active: bool
    item_name: str
    image_url: str | None = None
