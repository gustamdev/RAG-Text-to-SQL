"""Gateway de pagamento FAKE e determinístico: nenhum valor é cobrado. Só cartões de teste decidem.

Recebe apenas o PAN e a validade (nunca CVV nem titular) e devolve a decisão com bandeira e últimos 4.
O PAN não é gravado nem logado aqui; quem chama também só guarda `brand`/`last4`. Qualquer cartão fora da
lista de teste recebe a MESMA recusa genérica (sem dizer por quê: não vira oráculo de cartão real).
"""

from dataclasses import dataclass
from datetime import date
from typing import Literal

from app.core.errors import DomainError

TEST_CARDS: dict[str, Literal["approved", "refused", "timeout"]] = {
    "4242424242420001": "approved",
    "4242424242420002": "refused",
    "4242424242420003": "timeout",
}


class InvalidCard(DomainError):
    status_code = 422

    def __init__(self):
        super().__init__("Número de cartão inválido.")


@dataclass(frozen=True)
class GatewayResult:
    status: Literal["approved", "refused", "timeout"]
    brand: str
    last4: str


def luhn_ok(pan: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(pan)):
        d = int(ch)
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def brand_of(pan: str) -> str:
    if pan[0] == "4":
        return "visa"
    if pan[:2] in {"51", "52", "53", "54", "55"} or 2221 <= int(pan[:4]) <= 2720:
        return "mastercard"
    if pan[:2] in {"34", "37"}:
        return "amex"
    return "card"


async def charge(pan: str, exp_month: int, exp_year: int) -> GatewayResult:
    """422 só para número malformado (Luhn); o resto é decisão. O valor cobrado é decidido pelo chamador."""
    test = TEST_CARDS.get(pan)
    if test is None and not luhn_ok(pan):
        raise InvalidCard
    brand, last4 = brand_of(pan), pan[-4:]
    today = date.today()
    if test is None or (exp_year, exp_month) < (today.year, today.month):
        return GatewayResult("refused", brand, last4)
    return GatewayResult(test, brand, last4)


async def charge_saved(
    outcome: Literal["approved", "refused", "timeout"], brand: str, last4: str, exp_month: int, exp_year: int
) -> GatewayResult:
    """Cartão salvo: o PAN não existe mais; vale o resultado fixado no cadastro. Vencido é recusado como no `charge`."""
    if (exp_year, exp_month) < (date.today().year, date.today().month):
        return GatewayResult("refused", brand, last4)
    return GatewayResult(outcome, brand, last4)
