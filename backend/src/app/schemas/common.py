from enum import StrEnum


class Role(StrEnum):
    """Papéis da API. Admin nasce por scripts/create_admin.py; customer é o cliente da loja (auto-cadastro)."""

    ADMIN = "admin"
    CUSTOMER = "customer"
