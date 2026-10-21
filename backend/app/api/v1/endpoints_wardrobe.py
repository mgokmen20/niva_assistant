"""Authenticated wardrobe routes.

The handler checks the bearer and maps a missing garment to 404.
Persistence stays in the wardrobe service.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...schemas.wardrobe_schema import WardrobeItemCreate, WardrobeItemResponse, WardrobeItemUpdate
from ...services.wardrobe_service import WardrobeService
from ..deps import get_current_user_id, get_db

_wardrobe = WardrobeService()

router = APIRouter(prefix="/wardrobe", tags=["wardrobe"])


@router.get("/", response_model=list[WardrobeItemResponse])
async def list_wardrobe_items(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[WardrobeItemResponse]:
    """Return every garment stored for the signed-in wearer."""
    items = await _wardrobe.list_items(db, user_id)
    return [WardrobeItemResponse.model_validate(item) for item in items]


@router.post("/", response_model=WardrobeItemResponse, status_code=status.HTTP_201_CREATED)
async def create_wardrobe_item(
    body: WardrobeItemCreate,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> WardrobeItemResponse:
    """Store one garment for the signed-in wearer."""
    item = await _wardrobe.create_item(
        db,
        user_id=user_id,
        category=body.category,
        thickness=body.thickness,
        color_name=body.color_name,
        style=body.style,
        is_waterproof=body.is_waterproof,
        item_name=body.item_name,
        image_url=body.image_url,
    )
    return WardrobeItemResponse.model_validate(item)


@router.put("/{item_id}", response_model=WardrobeItemResponse)
async def update_wardrobe_item(
    item_id: UUID,
    body: WardrobeItemUpdate,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> WardrobeItemResponse:
    """Replace one garment that belongs to the signed-in wearer."""
    item = await _wardrobe.update_item(
        db,
        user_id=user_id,
        item_id=item_id,
        category=body.category,
        thickness=body.thickness,
        color_name=body.color_name,
        style=body.style,
        is_waterproof=body.is_waterproof,
        item_name=body.item_name,
        image_url=body.image_url,
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wardrobe item was not found.")
    return WardrobeItemResponse.model_validate(item)


@router.patch("/{item_id}/toggle-active", response_model=WardrobeItemResponse)
async def toggle_wardrobe_item(
    item_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> WardrobeItemResponse:
    """Mark one owned garment available or in the laundry."""
    item = await _wardrobe.toggle_active(db, user_id=user_id, item_id=item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wardrobe item was not found.")
    return WardrobeItemResponse.model_validate(item)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_wardrobe_item(
    item_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove one garment that belongs to the signed-in wearer."""
    deleted = await _wardrobe.delete_item(db, user_id=user_id, item_id=item_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wardrobe item was not found.")
