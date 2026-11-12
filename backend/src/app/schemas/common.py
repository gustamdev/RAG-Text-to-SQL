from enum import StrEnum


class Role(StrEnum):
    """Papéis da API. Só existe admin: não há auto-cadastro, e a conta nasce por scripts/create_admin.py."""

    ADMIN = "admin"
