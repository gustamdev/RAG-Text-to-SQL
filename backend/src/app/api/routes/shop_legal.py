"""Termos e aviso de privacidade: público, texto simples."""

from fastapi import APIRouter

from app.schemas.shop_account import LegalOut
from app.services.shop_legal import legal

router = APIRouter(prefix="/shop", tags=["shop-legal"])


@router.get("/legal", response_model=LegalOut)
async def get_legal() -> LegalOut:
    return legal()
