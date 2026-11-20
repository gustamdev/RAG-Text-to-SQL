"""Baixa fotos CC0 (Openverse) para os produtos de data/enriched e grava no blobstore local.

    uv run python scripts/fetch_images.py --dry-run     # só mostra o plano, sem rede
    uv run python scripts/fetch_images.py               # consulta Openverse, baixa e grava

Por TIPO (image_query distinto): busca fotos CC0 cujo título/tags contenham a palavra-chave do tipo, baixa a
miniatura, valida magic bytes JPEG, deduplica por sha256 e grava em `product-images/<sha256[:16]>.jpg`
(app.services.blobstore). Atribui uma foto distinta por produto; repete foto só se faltarem distintas. Tipo sem foto
que case fica com image_key vazio e é listado no fim. Gera image_credits.csv e atualiza image_key nos CSVs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

API = "https://api.openverse.org/v1/images/"
UA = "catalog-fixture-image-fetcher/1.0"
CONTAINER = "product-images"
MAX_BYTES = 2 * 1024 * 1024


def http_get(url: str, retries: int = 4) -> bytes:
    """GET com backoff em 429/5xx (respeita Retry-After)."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or attempt == retries - 1:
                raise
            time.sleep(float(e.headers.get("Retry-After") or 2 ** (attempt + 2)))
        except urllib.error.URLError:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** (attempt + 1))
    raise RuntimeError("unreachable")


GENERIC = {"set", "bag", "case", "box", "kit", "pack", "stand", "holder", "cover", "tool", "pot"}


def keywords(query: str) -> list[str]:
    """Substantivo final do image_query (+ palavra anterior se ele for genérico), sem plural simples."""
    ws = [w.lower() for w in query.split()]
    ws = ws[-2:] if ws[-1] in GENERIC and len(ws) > 1 else ws[-1:]
    return [w[:-3] if w.endswith("ies") else w[:-1] if w.endswith("s") and len(w) > 3 else w for w in ws]


def search(query: str, size: int = 20) -> list[dict]:
    params = {"q": query, "license": "cc0", "category": "photograph", "mature": "false", "page_size": size}
    return json.loads(http_get(f"{API}?{urllib.parse.urlencode(params)}"))["results"]


def matches(item: dict, kws: list[str]) -> bool:
    text = " ".join([item.get("title") or "", *(t.get("name", "") for t in item.get("tags") or [])]).lower()
    return all(k in text for k in kws)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", type=Path, default=ROOT / "data/enriched")
    ap.add_argument("--sleep", type=float, default=2.0, help="pausa entre requisições (rate limit)")
    ap.add_argument("--limit-types", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    products = pd.read_csv(a.dir / "olist_products_dataset.csv", dtype=str, keep_default_na=False)
    need = products.groupby("image_query").size().sort_index()
    queries = list(need.index)[: a.limit_types or None]
    print(f"{len(queries)} tipos, {int(need[queries].sum())} produtos")
    if a.dry_run:
        for q in queries:
            print(f"{need[q]:3d}  {q}  (palavras-chave: {keywords(q)})")
        return

    from app.services.blobstore import store  # import tardio: precisa do settings do app

    seen: set[str] = set()  # sha256 (dedup global)
    credits, photos = [], {}
    for q in queries:
        kw, got = keywords(q), []
        time.sleep(a.sleep)
        try:
            results = search(q)
        except urllib.error.URLError as e:
            print(f"ERRO busca '{q}': {e}")
            continue
        for item in results:
            if len(got) >= need[q]:
                break
            if not matches(item, kw) or not item.get("thumbnail"):
                continue
            time.sleep(a.sleep)
            try:
                data = http_get(item["thumbnail"])
            except urllib.error.URLError:
                continue
            if len(data) > MAX_BYTES or not data.startswith(b"\xff\xd8\xff"):  # só JPEG válido
                continue
            digest = hashlib.sha256(data).hexdigest()
            if digest in seen:
                continue
            blob = f"{digest[:16]}.jpg"
            store.put(CONTAINER, blob, data, "image/jpeg")
            seen.add(digest)
            got.append(blob)
            credits.append((
                f"{CONTAINER}/{blob}", item.get("title"), item.get("creator"),
                item.get("foreign_landing_url") or item.get("url"), item.get("license"), q,
            ))  # fmt: skip
        photos[q] = got
        print(f"{len(got)}/{need[q]}  {q}")

    keys, cursor = [], {}
    for q in products["image_query"]:
        got = photos.get(q) or []
        i = cursor.get(q, 0)
        cursor[q] = i + 1
        keys.append(f"{CONTAINER}/{got[i % len(got)]}" if got else "")  # repete só se faltarem fotos distintas
    products["image_key"] = keys
    products.to_csv(a.dir / "olist_products_dataset.csv", index=False)
    products[["product_id", "product_name", "product_category_name", "image_query", "image_key"]].rename(
        columns={"product_category_name": "category"}
    ).to_csv(a.dir / "image_queries.csv", index=False)
    with open(a.dir / "image_credits.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["blob", "title", "author", "source_url", "license", "image_query"])
        w.writerows(credits)
    missing = [q for q in queries if not photos.get(q)]
    print(f"\nsem foto CC0 que case ({len(missing)} tipos, image_key vazio):")
    print("\n".join(missing))


if __name__ == "__main__":
    main()
