"""Retenção LGPD (arts. 15-16) e reparos pendentes, chamados pelo loop de manutenção em main.py.

Prazos em `settings` (SHOP_RETENTION_*); os padrões são placeholders a validar pelo dono.
"""

import logging
from datetime import datetime, timedelta

from pymongo.asynchronous.database import AsyncDatabase

from app.api.shop_deps import SnapshotRefresher
from app.config import settings
from app.core.timeutil import now
from app.database.repos.shop_customers import ShopCustomerRepo
from app.database.repos.shop_flags import ShopFlagRepo
from app.database.repos.shop_orders import ShopOrderRepo
from app.database.repos.shop_otp import ShopOtpRepo
from app.database.repos.shop_payments import ShopPaymentRepo
from app.services.shop_account import SNAPSHOT_PENDING, ShopAccount

logger = logging.getLogger(__name__)
BATCH = 500


class ShopRetention:
    def __init__(self, db: AsyncDatabase, refresher: SnapshotRefresher):
        self.customers, self.orders, self.payments = ShopCustomerRepo(db), ShopOrderRepo(db), ShopPaymentRepo(db)
        self.otp, self.flags, self.refresher = ShopOtpRepo(db), ShopFlagRepo(db), refresher
        self.account = ShopAccount(db, refresher)

    async def run(self, at: datetime | None = None) -> dict[str, int]:
        """Um passe (em lotes). Devolve contagens; erro em um item não impede os demais."""
        at = at or now()
        counts = {"unverified": 0, "inactive": 0, "orders": 0, "anonymized_accounts": 0, "cleanups": 0}
        while batch := await self.customers.unverified_before(
            at - timedelta(hours=settings.SHOP_UNVERIFIED_TTL_HOURS), BATCH
        ):
            for c in batch:  # apagados saem do filtro: o loop termina
                await self.customers.delete(c["_id"])
                await self.otp.delete_for_email(c["email"])
            counts["unverified"] += len(batch)
        inactive_cutoff = at - timedelta(days=settings.SHOP_RETENTION_INACTIVE_DAYS)
        while batch := await self.customers.inactive_before(inactive_cutoff, BATCH):
            progress = 0
            for c in batch:
                try:
                    if await self.account.erase_inactive(c, inactive_cutoff):  # condicional: quem logou no meio fica
                        counts["inactive"] += 1
                    progress += 1
                except Exception:  # noqa: BLE001 - segue; o próximo passe repete
                    logger.exception("Falha ao anonimizar conta inativa.")
            if not progress:  # lote inteiro falhou: sem isso o loop não termina
                break
        order_cutoff = at - timedelta(days=settings.SHOP_RETENTION_ORDER_DAYS)
        while ids := await self.orders.finished_before(order_cutoff, BATCH):
            await self.payments.delete_for_orders(ids)
            await self.orders.delete_many(ids)
            counts["orders"] += len(ids)
        last = ""
        while batch := await self.customers.deleted_since(order_cutoff, last, BATCH):
            last = batch[-1]["_id"]
            for c in batch:  # exclusão que caiu no meio da limpeza: endereços/carrinho/pedidos ainda lá
                try:
                    counts["cleanups"] += await self.account.retry_cleanup(c)
                except Exception:  # noqa: BLE001 - segue; o próximo passe repete
                    logger.exception("Falha ao repetir limpeza de conta excluída.")
        counts["anonymized_accounts"] = await self.customers.purge_deleted_before(order_cutoff)
        if counts["orders"]:  # contas anonimizadas já pediram o próprio refresh
            await self.refresher.request()
        return counts

    async def retry_snapshot(self) -> bool:
        """Repete o refresh do agente se uma exclusão anterior não conseguiu pedi-lo. True se repetiu."""
        if not await self.flags.is_set(SNAPSHOT_PENDING):
            return False
        await self.flags.clear(SNAPSHOT_PENDING)  # antes: um pedido de exclusão concorrente pode re-marcar
        try:
            await self.refresher.request()
        except Exception:
            await self.flags.set(SNAPSHOT_PENDING)  # recria o marcador; o próximo ciclo tenta de novo
            raise
        return True
