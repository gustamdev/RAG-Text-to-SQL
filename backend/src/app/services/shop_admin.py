"""Backoffice da loja: clientes e pedidos com PII mascarada. Nunca devolve e-mail, telefone, CEP ou nome completos."""

from pymongo.asynchronous.database import AsyncDatabase

from app.core.timeutil import iso
from app.database.repos.shop_audit import ShopAuditRepo
from app.database.repos.shop_customers import ShopCustomerRepo
from app.database.repos.shop_orders import ShopOrderRepo
from app.schemas.shop_account import AdminCustomerRow, AdminOrderRow, AdminPage
from app.services.mail import mask_email
from app.services.shop_auth_service import pseudo


def mask_phone(phone: str | None) -> str | None:
    return f"{'*' * (len(phone) - 2)}{phone[-2:]}" if phone else None


def mask_zip(zip_code: str | None) -> str | None:
    return f"{zip_code[:3]}*****" if zip_code else None


def mask_name(name: str | None) -> str | None:
    return " ".join(f"{part[0]}***" for part in name.split()) if name else None


ADMIN_AUDIT_DAYS = 365


class ShopAdmin:
    def __init__(self, db: AsyncDatabase):
        self.customers = ShopCustomerRepo(db)
        self.orders = ShopOrderRepo(db)
        self.audit = ShopAuditRepo(db)

    async def _audit(self, event: str, admin_id: str, ip: str, page: int, purpose: str) -> None:
        """Grava ANTES de ler: sem registro, sem acesso (a exceção propaga e a leitura não acontece)."""
        meta = {"page": page, "purpose": purpose}
        await self.audit.add(event, pseudo(admin_id), pseudo(f"ip:{ip}"), meta, ADMIN_AUDIT_DAYS)

    async def customer_page(
        self, admin_id: str, ip: str, page: int, size: int, purpose: str = "suporte"
    ) -> AdminPage[AdminCustomerRow]:
        await self._audit("admin_view_customers", admin_id, ip, page, purpose)
        rows, total = await self.customers.page((page - 1) * size, size)
        items = [
            AdminCustomerRow(
                id=c["_id"],
                email=mask_email(c["email"]),
                phone=mask_phone(c.get("phone")),
                nickname=mask_name(c.get("nickname")),
                created_at=iso(c["created_at"]),
                deleted=bool(c.get("deleted_at")),
            )
            for c in rows
        ]
        return AdminPage[AdminCustomerRow](items=items, total=total, page=page, page_size=size)

    async def order_page(
        self, admin_id: str, ip: str, page: int, size: int, purpose: str = "suporte"
    ) -> AdminPage[AdminOrderRow]:
        await self._audit("admin_view_orders", admin_id, ip, page, purpose)
        rows, total = await self.orders.admin_page((page - 1) * size, size)
        items = [
            AdminOrderRow(
                order_id=o["order_id"],
                customer_id=o["customer_id"],
                state=o["state"],
                total_cents=o["total_cents"],
                created_at=iso(o["created_at"]),
                recipient=mask_name((o.get("address") or {}).get("recipient")),
                zip=mask_zip((o.get("address") or {}).get("zip")),
                city=(o.get("address") or {}).get("city"),
                state_uf=(o.get("address") or {}).get("state"),
            )
            for o in rows
        ]
        return AdminPage[AdminOrderRow](items=items, total=total, page=page, page_size=size)
