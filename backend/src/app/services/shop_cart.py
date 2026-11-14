"""Carrinho no servidor: guarda só product_id/qty e o preço visto pelo cliente; o resto vem de shop_products."""

from app.config import settings
from app.core.errors import Conflict, NotFound
from app.core.timeutil import iso, now
from app.database.repos.shop_carts import ShopCartRepo
from app.database.repos.shop_products import ShopProductRepo
from app.schemas.shop_store import CartLine, CartOut
from app.services.freight import DEFAULT_WEIGHT_G

NO_STOCK = "Produto sem estoque suficiente."
LIMIT = "Limite de itens do carrinho atingido."
NOT_IN_CART = "Item não está no carrinho."
GONE = "Produto indisponível. Remova do carrinho."


def _view(line: dict, product: dict | None) -> CartLine:
    """Linha da resposta a partir do estado ATUAL do produto. Aviso: out_of_stock > stock_reduced > price_changed."""
    if product is None or product["stock"] < 1:
        return CartLine(
            product_id=line["product_id"],
            title=product["title"] if product else "Produto indisponível",
            category=product["category"] if product else "",
            unit_price_cents=product["price_cents"] if product else 0,
            qty=line["qty"], line_total_cents=0, stock=0, warning="out_of_stock",
        )  # fmt: skip
    qty = min(line["qty"], product["stock"])
    warning = None
    if qty < line["qty"]:
        warning = "stock_reduced"
    elif product["price_cents"] != line["seen_price_cents"]:
        warning = "price_changed"
    return CartLine(
        product_id=line["product_id"], title=product["title"], category=product["category"],
        unit_price_cents=product["price_cents"], qty=qty, line_total_cents=product["price_cents"] * qty,
        stock=product["stock"], warning=warning,
    )  # fmt: skip


class ShopCart:
    def __init__(self, carts: ShopCartRepo, products: ShopProductRepo):
        self.carts, self.products = carts, products

    async def _load(self, customer_id: str) -> tuple[dict | None, list[dict]]:
        doc = await self.carts.get(customer_id)
        return doc, (doc or {}).get("items", [])

    async def _render(self, doc: dict | None, items: list[dict]) -> CartOut:
        found = {p["product_id"]: p for p in await self.products.get_many([i["product_id"] for i in items])}
        lines = [_view(i, found.get(i["product_id"])) for i in items]
        return CartOut(
            items=lines,
            item_count=sum(line.qty for line in lines if line.warning != "out_of_stock"),
            subtotal_cents=sum(line.line_total_cents for line in lines),
            blocked=any(line.warning for line in lines),
            updated_at=iso(doc["updated_at"]) if doc else None,
        )

    async def get(self, customer_id: str) -> CartOut:
        doc, items = await self._load(customer_id)
        return await self._render(doc, items)

    async def _save_render(self, customer_id: str, items: list[dict]) -> CartOut:
        await self.carts.save(customer_id, items)
        return await self.get(customer_id)

    @staticmethod
    def _add(items: list[dict], product: dict, qty: int) -> None:
        """Soma `qty` (teto SHOP_CART_MAX_QTY). Levanta Conflict se faltar estoque ou passar o limite de linhas."""
        line = next((i for i in items if i["product_id"] == product["product_id"]), None)
        want = min((line["qty"] if line else 0) + qty, settings.SHOP_CART_MAX_QTY)
        if want > product["stock"]:
            raise Conflict(NO_STOCK)
        if line:
            line["qty"] = want
            return
        if len(items) >= settings.SHOP_CART_MAX_ITEMS:
            raise Conflict(LIMIT)
        price = product["price_cents"]
        items.append({"product_id": product["product_id"], "qty": want, "added_at": now(), "seen_price_cents": price})

    async def add(self, customer_id: str, product_id: str, qty: int) -> CartOut:
        product = await self.products.get(product_id)
        if product is None:
            raise NotFound("Produto não encontrado.")
        _, items = await self._load(customer_id)
        self._add(items, product, qty)
        return await self._save_render(customer_id, items)

    async def patch(self, customer_id: str, product_id: str, qty: int | None, ack: bool | None) -> CartOut:
        _, items = await self._load(customer_id)
        line = next((i for i in items if i["product_id"] == product_id), None)
        if line is None:
            raise NotFound(NOT_IN_CART)
        product = await self.products.get(product_id)
        if qty is not None:
            if product is None or qty > product["stock"]:
                raise Conflict(NO_STOCK)
            line["qty"] = qty
        if ack:
            if product is None or product["stock"] < 1:
                raise Conflict(GONE)
            line["qty"] = min(line["qty"], product["stock"])
            line["seen_price_cents"] = product["price_cents"]
        return await self._save_render(customer_id, items)

    async def remove(self, customer_id: str, product_id: str) -> CartOut:
        _, items = await self._load(customer_id)
        kept = [i for i in items if i["product_id"] != product_id]
        if len(kept) == len(items):
            raise NotFound(NOT_IN_CART)
        return await self._save_render(customer_id, kept)

    async def clear(self, customer_id: str) -> CartOut:
        await self.carts.clear(customer_id)
        return await self.get(customer_id)

    async def merge(self, customer_id: str, guest: list[tuple[str, int]]) -> CartOut:
        """Itens inválidos, sem estoque ou além dos limites são ignorados (não falha a requisição)."""
        _, items = await self._load(customer_id)
        found = {p["product_id"]: p for p in await self.products.get_many([pid for pid, _ in guest])}
        for pid, qty in guest:
            if pid in found and qty >= 1:
                try:
                    self._add(items, found[pid], qty)
                except Conflict:
                    continue
        return await self._save_render(customer_id, items)

    async def weight_g(self, customer_id: str) -> float | None:
        """Peso total do carrinho (None = vazio). Produto sem peso conta DEFAULT_WEIGHT_G."""
        _, items = await self._load(customer_id)
        if not items:
            return None
        found = {p["product_id"]: p for p in await self.products.get_many([i["product_id"] for i in items])}
        return sum((found.get(i["product_id"], {}).get("weight_g") or DEFAULT_WEIGHT_G) * i["qty"] for i in items)
