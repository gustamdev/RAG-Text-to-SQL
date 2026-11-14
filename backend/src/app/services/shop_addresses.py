"""Endereços do cliente (máx. SHOP_MAX_ADDRESSES). Só o necessário para entrega; sem telefone nem CPF."""

from app.config import settings
from app.core.errors import Conflict, NotFound
from app.database.repos.shop_addresses import ShopAddressRepo
from app.schemas.shop_store import AddressIn, AddressOut, AddressPatch

NOT_FOUND = "Endereço não encontrado."


def out(doc: dict) -> AddressOut:
    return AddressOut(id=doc["_id"], **{k: doc.get(k) for k in AddressOut.model_fields if k != "id"})


class ShopAddresses:
    def __init__(self, repo: ShopAddressRepo):
        self.repo = repo

    async def all(self, customer_id: str) -> list[AddressOut]:
        return [out(d) for d in await self.repo.for_customer(customer_id)]

    async def get(self, customer_id: str, address_id: str) -> dict:
        doc = await self.repo.get(customer_id, address_id)
        if doc is None:
            raise NotFound(NOT_FOUND)
        return doc

    async def create(self, customer_id: str, body: AddressIn) -> AddressOut:
        count = await self.repo.count(customer_id)  # shortcut: sem lock; corrida só entre abas do mesmo cliente
        if count >= settings.SHOP_MAX_ADDRESSES:
            raise Conflict(f"Limite de {settings.SHOP_MAX_ADDRESSES} endereços atingido.")
        fields = body.model_dump()
        fields["is_default"] = fields["is_default"] or count == 0
        doc = await self.repo.insert(customer_id, fields)
        if doc["is_default"]:
            await self.repo.unset_default_except(customer_id, doc["_id"])
        return out(doc)

    async def update(self, customer_id: str, address_id: str, body: AddressPatch) -> AddressOut:
        fields = body.model_dump(exclude_unset=True)
        if fields.get("is_default") is False:
            fields.pop("is_default")  # o padrão só muda marcando outro endereço
        doc = await self.repo.update(customer_id, address_id, fields)
        if doc is None:
            raise NotFound(NOT_FOUND)
        if fields.get("is_default"):
            await self.repo.unset_default_except(customer_id, address_id)
        return out(doc)

    async def delete(self, customer_id: str, address_id: str) -> None:
        doc = await self.get(customer_id, address_id)
        await self.repo.delete(customer_id, address_id)
        rest = await self.repo.for_customer(customer_id)
        if doc["is_default"] and rest:
            await self.repo.update(customer_id, rest[0]["_id"], {"is_default": True})
