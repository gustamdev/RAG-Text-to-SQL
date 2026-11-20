"""Parâmetros de rota/consulta compartilhados pelas rotas da loja. `[0-9]` (não `\\d`): `\\d` aceita dígitos unicode."""

from typing import Annotated

from fastapi import Path, Query

ProductId = Annotated[str, Path(min_length=1, max_length=64)]
AddressId = Annotated[str, Path(min_length=1, max_length=64)]
CardId = Annotated[str, Path(min_length=1, max_length=64)]
ZipQuery = Annotated[str, Query(pattern=r"^[0-9]{5}-?[0-9]{3}$", description="CEP com 8 dígitos (aceita hífen).")]
ZipPath = Annotated[str, Path(pattern=r"^[0-9]{8}$", description="CEP com 8 dígitos, sem hífen.")]
