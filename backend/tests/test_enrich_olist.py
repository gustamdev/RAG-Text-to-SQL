import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "olist"
sys.path.insert(0, str(ROOT / "scripts"))


@pytest.mark.skipif(not SRC.exists(), reason="dataset Olist ausente")
def test_enrich_minimal_scale(tmp_path):
    from enrich_olist import run

    kw = {"products": 80, "customers": 120, "seed": 7, "today": date(2026, 11, 16)}
    a = run(SRC, tmp_path / "a", **kw)  # validate() (FKs, pagamentos, datas, status vs hoje) roda dentro
    b = run(SRC, tmp_path / "b", **kw)
    assert len(a["products"]) == 80 and a["customers"]["customer_unique_id"].nunique() == 120
    assert a["orders"]["order_id"].tolist() == b["orders"]["order_id"].tolist()  # reprodutível
    assert a["orders"]["order_purchase_timestamp"].max().date() <= date(2026, 11, 16)
    assert (tmp_path / "a" / "olist_orders_dataset.csv").exists()
    assert (tmp_path / "a" / "image_queries.csv").exists()
