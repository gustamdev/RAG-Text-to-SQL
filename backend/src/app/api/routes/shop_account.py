"""Conta do cliente (aud=shop). E4: endereços. Pedidos, perfil e LGPD entram na E6."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import get_app_db
from app.api.shop_deps import get_current_customer
from app.database.repos.shop_addresses import ShopAddressRepo
from app.schemas.shop_store import AddressIn, AddressOut, AddressPatch
from app.services.shop_addresses import ShopAddresses

router = APIRouter(prefix="/shop/account", tags=["shop-account"])

AddressId = Annotated[str, Path(min_length=1, max_length=64)]


def get_addresses(db: AsyncDatabase = Depends(get_app_db)) -> ShopAddresses:
    return ShopAddresses(ShopAddressRepo(db))


@router.get("/addresses", response_model=list[AddressOut])
async def list_addresses(
    customer: dict = Depends(get_current_customer), svc: ShopAddresses = Depends(get_addresses)
) -> list[AddressOut]:
    return await svc.all(customer["_id"])


@router.post("/addresses", response_model=AddressOut, status_code=201)
async def create_address(
    body: AddressIn, customer: dict = Depends(get_current_customer), svc: ShopAddresses = Depends(get_addresses)
) -> AddressOut:
    return await svc.create(customer["_id"], body)


@router.patch("/addresses/{address_id}", response_model=AddressOut)
async def update_address(
    address_id: AddressId,
    body: AddressPatch,
    customer: dict = Depends(get_current_customer),
    svc: ShopAddresses = Depends(get_addresses),
) -> AddressOut:
    return await svc.update(customer["_id"], address_id, body)


@router.delete("/addresses/{address_id}", status_code=204)
async def delete_address(
    address_id: AddressId, customer: dict = Depends(get_current_customer), svc: ShopAddresses = Depends(get_addresses)
) -> Response:
    await svc.delete(customer["_id"], address_id)
    return Response(status_code=204)
