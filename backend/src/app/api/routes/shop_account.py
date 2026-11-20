"""Conta do cliente (aud=shop): endereços e direitos do titular (exportar, corrigir, excluir)."""

from fastapi import APIRouter, BackgroundTasks, Depends, Response
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import get_app_db
from app.api.routes.shop_checkout import enforce_write_limit
from app.api.routes.shop_zip import get_zip_remote
from app.api.shop_deps import SnapshotRefresher, get_limited_customer, get_snapshot_refresher
from app.api.shop_params import AddressId, CardId
from app.database.repos.geolocation import GeolocationRepo
from app.database.repos.shop_addresses import ShopAddressRepo
from app.schemas.shop_account import ChangePasswordIn, DeleteAccountIn, ExportOut, ProfileOut, ProfilePatch
from app.schemas.shop_cards import CardIn, CardOut
from app.schemas.shop_store import AddressIn, AddressOut, AddressPatch
from app.services.shop_account import ShopAccount
from app.services.shop_addresses import ShopAddresses
from app.services.shop_cards import ShopCards
from app.services.zip_lookup import ZipRemote

router = APIRouter(prefix="/shop/account", tags=["shop-account"])


def get_addresses(
    db: AsyncDatabase = Depends(get_app_db), remote: ZipRemote = Depends(get_zip_remote)
) -> ShopAddresses:
    return ShopAddresses(ShopAddressRepo(db), GeolocationRepo(db), remote)


@router.get("/addresses", response_model=list[AddressOut])
async def list_addresses(
    customer: dict = Depends(get_limited_customer), svc: ShopAddresses = Depends(get_addresses)
) -> list[AddressOut]:
    return await svc.all(customer["_id"])


@router.post("/addresses", response_model=AddressOut, status_code=201)
async def create_address(
    body: AddressIn, customer: dict = Depends(get_limited_customer), svc: ShopAddresses = Depends(get_addresses)
) -> AddressOut:
    return await svc.create(customer["_id"], body)


@router.patch("/addresses/{address_id}", response_model=AddressOut)
async def update_address(
    address_id: AddressId,
    body: AddressPatch,
    customer: dict = Depends(get_limited_customer),
    svc: ShopAddresses = Depends(get_addresses),
) -> AddressOut:
    return await svc.update(customer["_id"], address_id, body)


@router.delete("/addresses/{address_id}", status_code=204)
async def delete_address(
    address_id: AddressId, customer: dict = Depends(get_limited_customer), svc: ShopAddresses = Depends(get_addresses)
) -> Response:
    await svc.delete(customer["_id"], address_id)
    return Response(status_code=204)


def get_cards(db: AsyncDatabase = Depends(get_app_db)) -> ShopCards:
    return ShopCards(db)


@router.get("/cards", response_model=list[CardOut])
async def list_cards(
    customer: dict = Depends(get_limited_customer), svc: ShopCards = Depends(get_cards)
) -> list[CardOut]:
    return await svc.all(customer["_id"])


@router.post("/cards", response_model=CardOut, status_code=201)
async def create_card(
    body: CardIn,
    response: Response,
    customer: dict = Depends(enforce_write_limit),
    svc: ShopCards = Depends(get_cards),
) -> CardOut:
    card, created = await svc.add(customer["_id"], body)
    if not created:  # mesmo cartão: devolve o já salvo (validade atualizada) com 200
        response.status_code = 200
    return card


@router.delete("/cards/{card_id}", status_code=204)
async def delete_card(
    card_id: CardId, customer: dict = Depends(enforce_write_limit), svc: ShopCards = Depends(get_cards)
) -> Response:
    await svc.delete(customer["_id"], card_id)
    return Response(status_code=204)


def get_account(
    db: AsyncDatabase = Depends(get_app_db), refresher: SnapshotRefresher = Depends(get_snapshot_refresher)
) -> ShopAccount:
    return ShopAccount(db, refresher)


@router.get("/export", response_model=ExportOut)
async def export_data(
    response: Response, customer: dict = Depends(get_limited_customer), svc: ShopAccount = Depends(get_account)
) -> ExportOut:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Disposition"] = 'attachment; filename="meus-dados.json"'
    return await svc.export(customer["_id"])


@router.patch("", response_model=ProfileOut)
async def update_profile(
    body: ProfilePatch, customer: dict = Depends(get_limited_customer), svc: ShopAccount = Depends(get_account)
) -> ProfileOut:
    return await svc.update(customer["_id"], body)


@router.delete("", status_code=204)
async def delete_account(
    body: DeleteAccountIn, customer: dict = Depends(get_limited_customer), svc: ShopAccount = Depends(get_account)
) -> Response:
    await svc.delete(customer["_id"], body)
    return Response(status_code=204)


@router.patch("/password", status_code=204)
async def change_password(
    body: ChangePasswordIn,
    bg: BackgroundTasks,
    customer: dict = Depends(get_limited_customer),
    svc: ShopAccount = Depends(get_account),
) -> Response:
    await svc.change_password(customer["_id"], body, bg.add_task)
    return Response(status_code=204)
