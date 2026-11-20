"""Endereços do cliente (máx. SHOP_MAX_ADDRESSES). Só o necessário para entrega; sem telefone nem CPF."""

from app.config import settings
from app.core.errors import Conflict, NotFound
from app.database.repos.geolocation import GeolocationRepo
from app.database.repos.shop_addresses import ShopAddressRepo
from app.schemas.shop_store import AddressIn, AddressOut, AddressPatch
from app.services.zip_lookup import ZipRemote, lookup_zip

NOT_FOUND = "Endereço não encontrado."


def out(doc: dict) -> AddressOut:
    return AddressOut(id=doc["_id"], **{k: doc.get(k) for k in AddressOut.model_fields if k != "id"})


class ShopAddresses:
    def __init__(self, repo: ShopAddressRepo, geo: GeolocationRepo | None = None, remote: ZipRemote | None = None):
        self.repo, self.geo, self.remote = repo, geo, remote

    async def _derive_place(self, fields: dict, zip8: str) -> None:
        """Cidade/UF vêm do CEP quando a API/base offline sabe (o frete usa a UF do endereço: digitada seria burlável);
        CEP desconhecido mantém o digitado."""
        if self.geo is None or self.remote is None:
            return
        if info := await lookup_zip(zip8, self.geo, self.remote):
            fields["city"], fields["state"] = info.city, info.state

    async def all(self, customer_id: str) -> list[AddressOut]:
        return [out(d) for d in await self.repo.for_customer(customer_id)]

    async def get(self, customer_id: str, address_id: str) -> dict:
        doc = await self.repo.get(customer_id, address_id)
        if doc is None:
            raise NotFound(NOT_FOUND)
        return doc

    async def create(self, customer_id: str, body: AddressIn) -> AddressOut:
        limit = f"Limite de {settings.SHOP_MAX_ADDRESSES} endereços atingido."
        count = await self.repo.count(customer_id)
        if count >= settings.SHOP_MAX_ADDRESSES:
            raise Conflict(limit)
        fields = body.model_dump()
        await self._derive_place(fields, fields["zip"])
        fields["is_default"] = fields["is_default"] or count == 0
        doc = await self.repo.insert(customer_id, fields)
        if await self.repo.count(customer_id) > settings.SHOP_MAX_ADDRESSES:  # corrida: recontou e passou, desfaz
            await self.repo.delete(customer_id, doc["_id"])
            await self.repo.normalize_default(customer_id)  # o desfeito podia ser o padrão eleito
            raise Conflict(limit)
        if doc["is_default"]:
            await self.repo.normalize_default(customer_id)
        return out(await self.repo.get(customer_id, doc["_id"]) or doc)

    async def update(self, customer_id: str, address_id: str, body: AddressPatch) -> AddressOut:
        fields = body.model_dump(exclude_unset=True)
        if fields.get("is_default") is False:
            fields.pop("is_default")  # o padrão só muda marcando outro endereço
        if fields.keys() & {"zip", "city", "state"}:
            current = await self.get(customer_id, address_id)
            await self._derive_place(fields, fields.get("zip") or current["zip"])
        doc = await self.repo.update(customer_id, address_id, fields)
        if doc is None:
            raise NotFound(NOT_FOUND)
        if fields.get("is_default"):
            await self.repo.normalize_default(customer_id)
            doc = await self.repo.get(customer_id, address_id) or doc
        return out(doc)

    async def delete(self, customer_id: str, address_id: str) -> None:
        doc = await self.get(customer_id, address_id)
        await self.repo.delete(customer_id, address_id)
        rest = await self.repo.for_customer(customer_id)
        if doc["is_default"] and rest:
            await self.repo.update(customer_id, rest[0]["_id"], {"is_default": True})
