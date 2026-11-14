"""Carrinho do cliente (aud=shop). Toda rota filtra por `customer["_id"]`; preço e estoque vêm do servidor."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import get_app_db
from app.api.shop_deps import get_current_customer
from app.core.errors import Conflict
from app.database.repos.geolocation import GeolocationRepo
from app.database.repos.shop_addresses import ShopAddressRepo
from app.database.repos.shop_carts import ShopCartRepo
from app.database.repos.shop_products import ShopProductRepo
from app.schemas.shop_store import (
    CartAddIn,
    CartFreightIn,
    CartMergeIn,
    CartOut,
    CartPatchIn,
    FreightOut,
)
from app.services.freight import FreightService
from app.services.shop_addresses import ShopAddresses
from app.services.shop_cart import ShopCart

router = APIRouter(prefix="/shop/cart", tags=["shop-cart"])

ProductId = Annotated[str, Path(min_length=1, max_length=64)]
ZipQuery = Annotated[str, Query(pattern=r"^\d{5}-?\d{3}$")]


def get_cart(db: AsyncDatabase = Depends(get_app_db)) -> ShopCart:
    return ShopCart(ShopCartRepo(db), ShopProductRepo(db))


@router.get("", response_model=CartOut)
async def read_cart(customer: dict = Depends(get_current_customer), cart: ShopCart = Depends(get_cart)) -> CartOut:
    return await cart.get(customer["_id"])


@router.delete("", response_model=CartOut)
async def clear_cart(customer: dict = Depends(get_current_customer), cart: ShopCart = Depends(get_cart)) -> CartOut:
    return await cart.clear(customer["_id"])


@router.post("/items", response_model=CartOut)
async def add_item(
    body: CartAddIn, customer: dict = Depends(get_current_customer), cart: ShopCart = Depends(get_cart)
) -> CartOut:
    return await cart.add(customer["_id"], body.product_id, body.qty)


@router.patch("/items/{product_id}", response_model=CartOut)
async def patch_item(
    product_id: ProductId,
    body: CartPatchIn,
    customer: dict = Depends(get_current_customer),
    cart: ShopCart = Depends(get_cart),
) -> CartOut:
    return await cart.patch(customer["_id"], product_id, body.qty, body.ack)


@router.delete("/items/{product_id}", response_model=CartOut)
async def delete_item(
    product_id: ProductId, customer: dict = Depends(get_current_customer), cart: ShopCart = Depends(get_cart)
) -> CartOut:
    return await cart.remove(customer["_id"], product_id)


@router.post("/merge", response_model=CartOut)
async def merge(
    body: CartMergeIn, customer: dict = Depends(get_current_customer), cart: ShopCart = Depends(get_cart)
) -> CartOut:
    return await cart.merge(customer["_id"], [(i.product_id, i.qty) for i in body.items])


async def _cart_freight(
    customer: dict, db: AsyncDatabase, cart: ShopCart, zip8: str | None, address_id: str | None
) -> FreightOut:
    weight = await cart.weight_g(customer["_id"])
    if weight is None:
        raise Conflict("Carrinho vazio.")
    state = None
    if address_id is not None:  # 404 uniforme se o endereço é de outro cliente
        address = await ShopAddresses(ShopAddressRepo(db)).get(customer["_id"], address_id)
        zip8, state = address["zip"], address["state"]
    options = await FreightService(GeolocationRepo(db)).options(zip8, weight, state)
    return FreightOut(zip=zip8, options=options)


@router.get("/freight", response_model=FreightOut)
async def cart_freight_by_zip(
    zip: ZipQuery,
    customer: dict = Depends(get_current_customer),
    db: AsyncDatabase = Depends(get_app_db),
    cart: ShopCart = Depends(get_cart),
) -> FreightOut:
    return await _cart_freight(customer, db, cart, zip.replace("-", ""), None)


@router.post("/freight", response_model=FreightOut)
async def cart_freight(
    body: CartFreightIn,
    customer: dict = Depends(get_current_customer),
    db: AsyncDatabase = Depends(get_app_db),
    cart: ShopCart = Depends(get_cart),
) -> FreightOut:
    zip8 = body.zip.replace("-", "") if body.zip else None
    return await _cart_freight(customer, db, cart, zip8, body.address_id)
