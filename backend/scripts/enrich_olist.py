# ruff: noqa: E501  (tabelas densas; formatação manual)
"""Gera um dataset Olist melhorado, coerente e "vivo" (até --today). Só arquivos; nunca toca no Mongo.

    uv run python scripts/enrich_olist.py --out data/enriched [--today 2026-11-16]

Híbrido: esquema, categorias, vendedores, CEPs, proporção de status/pagamento/scores e comentários vêm do Olist real
(data/olist); produtos (tipo x marca x atributo), clientes, pedidos, pagamentos e reviews são sintéticos.
Reprodutível: mesma --seed e --today geram os mesmos arquivos. "Agora" = --today às 18:00.
O seed_mongo.py só carrega tudo com SEED_YEAR vazio (ou um ano coerente): o dataset cobre ~24 meses.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import random
import re
import sys
import unicodedata
from collections import Counter
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from enrich_catalog import ATTRS, BRANDS, BRANDS_EXTRA, CATEGORY_BLURB, OLIST_ITEMS, PACK, SIZE, TIPOS, VOLT  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SHOP_ORIGIN_ZIP_PREFIX = "01310"
FMT = "%Y-%m-%d %H:%M:%S"
WEEKDAY = [1.1, 1.1, 1.05, 1.05, 1.0, 0.8, 0.85]
MONTH = {1: .85, 2: .85, 3: 1, 4: 1, 5: 1.1, 6: 1.05, 7: 1, 8: 1, 9: 1, 10: 1.05, 11: 1.3, 12: 1.2}  # fmt: skip
HOUR_W = [1, 1, 1, 1, 1, 1, 2, 3, 5, 7, 8, 8, 7, 7, 8, 8, 8, 8, 8, 8, 9, 9, 6, 3]
GIFT = {"brinquedos", "relogios_presentes", "perfumaria", "cool_stuff"}
MAES = {"perfumaria", "beleza_saude", "relogios_presentes", "casa_conforto", "fashion_bolsas_e_acessorios"}
NAMORADOS = {"perfumaria", "relogios_presentes", "fashion_bolsas_e_acessorios", "fashion_calcados"}

FIRST = (
    "Ana Beatriz Bruno Camila Carlos Carolina Daniel Eduardo Fernanda Felipe Gabriel Gabriela Guilherme Helena "
    "Henrique Isabela João Juliana Larissa Leonardo Letícia Lucas Luciana Luiz Marcelo Márcia Mariana Mateus "
    "Mônica Natália Patrícia Paulo Pedro Rafael Rafaela Renata Ricardo Roberto Rodrigo Sandra Sérgio Simone "
    "Tatiane Thiago Vanessa Vinícius Vitória Aline Amanda André Bianca Cláudia Débora Diego Elaine Fábio "
    "Jéssica Joana Laura Marcos Miguel Rita Silvia Tiago Valentina Alice Heitor Davi Sofia"
).split()
LAST = (
    "Silva Santos Oliveira Souza Rodrigues Ferreira Alves Pereira Lima Gomes Costa Ribeiro Martins Carvalho "
    "Almeida Lopes Soares Fernandes Vieira Barbosa Rocha Dias Nascimento Andrade Moreira Nunes Marques Machado "
    "Mendes Freitas Cardoso Ramos Gonçalves Santana Teixeira Araújo Pinto Correia Moura Cavalcanti Monteiro "
    "Campos Azevedo Batista Duarte Farias Miranda Borges Medeiros Siqueira Prado Tavares Peixoto"
).split()
# frequência decrescente (Zipf suave): nomes do começo da lista são mais comuns
FIRST_W = [1 / (i + 4) ** 0.8 for i in range(len(FIRST))]
LAST_W = [1 / (i + 4) ** 0.8 for i in range(len(LAST))]

FALLBACK = {  # só se o Olist real não tiver comentário limpo suficiente
    "good": ["Produto de acordo com a descrição, recomendo.", "Chegou rápido e bem embalado."],
    "mid": ["Produto razoável, esperava um pouco mais."],
    "bad": ["Demorou muito para chegar.", "Não gostei, qualidade abaixo do esperado."],
}


def md5(*parts) -> str:
    return hashlib.md5("-".join(map(str, parts)).encode()).hexdigest()


def haversine_km(a, b) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def bf_date(year: int) -> datetime:
    """Black Friday: 4ª sexta-feira de novembro."""
    d = datetime(year, 11, 1)
    return d + timedelta(days=(4 - d.weekday()) % 7 + 21)


def maes_date(year: int) -> datetime:
    d = datetime(year, 5, 1)
    return d + timedelta(days=(6 - d.weekday()) % 7 + 7)  # 2º domingo de maio


def season_boost(d: datetime) -> set[str]:
    if d.month == 12 and d.day <= 22:
        return GIFT
    if 0 <= (maes_date(d.year) - d).days <= 9:
        return MAES
    if d.month == 6 and d.day <= 12:
        return NAMORADOS
    return set()


def price_factor(d: datetime, start: datetime) -> float:
    """Inflação leve (~4,5% a.a.) x promoções sazonais."""
    f = 1 + 0.045 * (d - start).days / 365
    if abs((d - bf_date(d.year)).days) <= 3:
        f *= 0.87
    elif d.month == 1 and d.day <= 15 or d.month == 3 and 12 <= d.day <= 16:
        f *= 0.95
    return f


# ---------------------------------------------------------------- distribuições reais do Olist
def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()


def _clean(s: str, maxlen: int) -> bool:
    if not 10 <= len(s) <= maxlen or re.search(
        r"\d|@|http|www|[\r\n]|n[aã]o (recebi|chegou)|aguardando|ainda n", s, re.I
    ):
        return False
    return not re.search(r"[A-ZÀ-Ý]", s[1:])  # sem nomes próprios nem siglas


def empirical(src: Path) -> dict:
    o = pd.read_csv(
        src / "olist_orders_dataset.csv", parse_dates=["order_delivered_customer_date", "order_estimated_delivery_date"]
    )
    st = o["order_status"].value_counts(normalize=True)
    deliv = o[o["order_status"] == "delivered"].dropna(subset=["order_delivered_customer_date"])
    late_ids = set(
        deliv.loc[deliv["order_delivered_customer_date"] > deliv["order_estimated_delivery_date"], "order_id"]
    )
    r = pd.read_csv(src / "olist_order_reviews_dataset.csv").drop_duplicates("order_id")
    m = r.merge(o[["order_id", "order_status"]], on="order_id")
    late = m["order_id"].isin(late_ids)
    delivered = m["order_status"] == "delivered"
    p = pd.read_csv(src / "olist_order_payments_dataset.csv")
    cc = p[p["payment_type"] == "credit_card"]
    ptype = p[p["payment_type"] != "not_defined"]["payment_type"].value_counts()
    rev_rate = (r.merge(o[["order_id", "order_status"]], on="order_id")["order_status"].value_counts()
                / o["order_status"].value_counts()).dropna()  # fmt: skip
    msgs = r.dropna(subset=["review_comment_message"])
    titles = r.dropna(subset=["review_comment_title"])
    return {
        "p_cancel": st.get("canceled", 0.006), "p_unavail": st.get("unavailable", 0.006),
        "p_late": len(late_ids) / max(len(deliv), 1),
        "rev_rate": {k: float(rev_rate.get(k, 0.5)) for k in ("delivered", "canceled", "unavailable")},
        "scores": {"late": list(m[delivered & late]["review_score"]), "ok": list(m[delivered & ~late]["review_score"]),
                   "bad": list(m[~delivered]["review_score"])},
        "ptype": (list(ptype.index), list(ptype.values)),
        "inst_small": list(cc[cc["payment_value"] < 50]["payment_installments"]),
        "inst_large": list(cc[cc["payment_value"] >= 50]["payment_installments"]),
        "msg_rate": len(msgs) / len(r), "title_rate": len(titles) / len(r),
        "messages": [(int(s), t) for s, t in zip(msgs["review_score"], msgs["review_comment_message"], strict=True) if _clean(t, 110)],
        "titles": [(int(s), t) for s, t in zip(titles["review_score"], titles["review_comment_title"], strict=True) if _clean(t, 30)],
    }  # fmt: skip


def comment_pools(emp: dict, products: list[dict]) -> dict:
    """Comentários reais sem PII e que não citam os tipos de produto gerados (evita incoerência)."""
    words = lambda s: {w.rstrip("s") for w in re.findall(r"[a-z]{5,}", _norm(s))}  # noqa: E731
    prod = set().union(*(words(p["product_name"]) for p in products))
    df = Counter(w for _, t in emp["messages"] for w in words(t))
    stop = {w for w in prod if df[w] <= 0.01 * len(emp["messages"])}
    keep = [(s, t) for s, t in emp["messages"] if not words(t) & stop]
    tone = lambda s: "good" if s >= 4 else "mid" if s == 3 else "bad"  # noqa: E731
    pools = {k: [t for s, t in keep if tone(s) == k] or FALLBACK[k] for k in FALLBACK}
    titles = {k: [t for s, t in emp["titles"] if tone(s) == k and not words(t) & stop] or [""] for k in FALLBACK}
    return {"msg": pools, "title": titles, "tone": tone}


# ---------------------------------------------------------------- produtos
def build_products(rng: random.Random, n: int, start: datetime, end: datetime) -> list[dict]:
    """Produtos = tipo x marca x atributo (2 variantes por tipo nas categorias grandes). n=0: todos."""
    per_cat: dict[str, list[tuple]] = {}
    for cat, types in TIPOS.items():
        kind = "volt" if cat in VOLT else "size" if cat in SIZE else "pack" if cat in PACK else "cor"
        brands, seen, rows = BRANDS[cat] + BRANDS_EXTRA, set(), []
        for _ in range(2 if OLIST_ITEMS[cat] >= 1000 else 1):
            for t in types:
                for _try in range(30):
                    brand, attr = rng.choice(brands), rng.choice(ATTRS[kind])
                    if (t[0], brand, attr) not in seen:
                        break
                seen.add((t[0], brand, attr))
                rows.append((cat, t, brand, attr))
        per_cat[cat] = rows
    picked, depth = [], 0
    total = sum(map(len, per_cat.values()))
    while len(picked) < (n or total):
        for rows in per_cat.values():
            if depth < len(rows) and len(picked) < (n or total):
                picked.append(rows[depth])
        depth += 1
    products, first_of = [], set()
    for cat, (tipo, query, pmin, pmax, peso, c, h, w), brand, attr in picked:
        name = f"{tipo} {brand} {attr}"
        pid = md5("product", cat, name)
        desc = f"{tipo} da marca {brand}, {attr}. {CATEGORY_BLURB[cat]}"
        if cat not in first_of:  # toda categoria tem ao menos 1 produto ativo durante toda a janela
            first_of.add(cat)
            launch, disc = start - timedelta(days=rng.randint(30, 400)), None
        else:
            if rng.random() < 0.55:
                launch = start - timedelta(days=rng.randint(1, 700))
            else:
                launch = start + (end - start - timedelta(days=30)) * rng.random() ** 0.7
            lo, hi = max(launch, start) + timedelta(days=60), end - timedelta(days=30)
            disc = lo + (hi - lo) * rng.random() if rng.random() < 0.10 and lo < hi else None
        launch = launch.replace(hour=0, minute=0, second=0, microsecond=0)
        disc = disc.replace(hour=0, minute=0, second=0, microsecond=0) if disc else None
        jit = lambda v: max(1, round(v * rng.uniform(0.95, 1.05)))  # noqa: E731
        products.append({
            "product_id": pid, "product_category_name": cat, "product_name_lenght": len(name),
            "product_description_lenght": len(desc), "product_photos_qty": rng.randint(1, 5),
            "product_weight_g": jit(peso), "product_length_cm": jit(c), "product_height_cm": jit(h),
            "product_width_cm": jit(w), "product_name": name, "product_brand": brand,
            "product_description": desc, "image_key": "", "image_query": query,
            "product_created_at": launch.strftime("%Y-%m-%d"),
            "product_discontinued_at": disc.strftime("%Y-%m-%d") if disc else "",
            "_base": max(int(math.exp(rng.uniform(math.log(pmin), math.log(pmax)))), 1) - 0.1,
            "_pop": 1 / (1 + rng.random() * 6), "_launch": launch, "_disc": disc,
        })  # fmt: skip
    return products


# ---------------------------------------------------------------- clientes e calendário
def day_weights(days: list[datetime], rng: random.Random) -> list[float]:
    noise = {(d.year, d.month): rng.lognormvariate(0, 0.08) for d in days}
    out = []
    for i, d in enumerate(days):
        w = (1 + 1.8 * i / len(days)) * WEEKDAY[d.weekday()] * MONTH[d.month] * noise[(d.year, d.month)]
        delta = (d - bf_date(d.year)).days
        w *= 5 if 0 <= delta <= 3 else 1.5 if -7 <= delta < 0 else 1
        w *= 1.3 if d.month == 12 and d.day <= 22 else 1
        w *= 1.8 if 0 <= (maes_date(d.year) - d).days <= 9 else 1
        w *= 1.6 if d.month == 6 and d.day <= 12 else 1
        out.append(w)
    return out


def n_orders(rng: random.Random) -> int:
    """27% nunca voltam; o resto 2 + geométrica, com cauda longa até 15."""
    if rng.random() < 0.27:
        return 1
    n = 2 + int(math.log(1 - rng.random()) / math.log(0.67))
    return min(15, n + (rng.randint(3, 8) if rng.random() < 0.05 else 0))


def order_dates(rng, n, days, weights, end, bfs) -> list[datetime]:
    """Cohort de entrada sazonal, intervalos lognormais, reativação após longa pausa, snap na Black Friday."""
    cur = rng.choices(days, weights)[0]  # shortcut: compradores frequentes iniciados tarde são truncados em "hoje"
    dates, median = [cur], 70 / (1 + 0.12 * n)
    for _ in range(n - 1):
        gap = max(2, rng.lognormvariate(math.log(median), 0.6)) * (rng.uniform(3, 6) if rng.random() < 0.12 else 1)
        cur = cur + timedelta(days=gap)
        for bf in bfs:
            if abs((cur - bf).days) <= 21 and rng.random() < 0.45:
                cur = bf + timedelta(days=rng.randint(-1, 2))
        if cur > end:
            break
        dates.append(cur)
    return dates


def installments(rng, emp, value: float) -> int:
    return rng.choice(emp["inst_small"] if value < 50 else emp["inst_large"])


def generate(  # noqa: C901
    src: Path, n_products: int, n_customers: int, seed: int, today: date, months: int = 24
) -> dict[str, pd.DataFrame]:
    rng = random.Random(seed)
    end = datetime.combine(today, time.min)
    now = datetime.combine(today, time(18, 0))
    start = end - timedelta(days=round(months * 30.44))
    emp = empirical(src)

    geo = pd.read_csv(src / "olist_geolocation_dataset.csv", dtype={"geolocation_zip_code_prefix": str})
    coords = geo.groupby("geolocation_zip_code_prefix")[["geolocation_lat", "geolocation_lng"]].mean()
    coords = {z: (r.geolocation_lat, r.geolocation_lng) for z, r in coords.iterrows()}
    src_cust = pd.read_csv(src / "olist_customers_dataset.csv", dtype={"customer_zip_code_prefix": str})
    src_cust = src_cust[src_cust["customer_zip_code_prefix"].isin(coords)]
    locations = list(src_cust[["customer_zip_code_prefix", "customer_city", "customer_state"]].itertuples(index=False))
    src_sell = pd.read_csv(src / "olist_sellers_dataset.csv", dtype={"seller_zip_code_prefix": str})
    src_sell = src_sell[src_sell["seller_zip_code_prefix"].isin(coords)]
    seller_ids = list(src_sell["seller_id"])
    seller_zip = dict(zip(src_sell["seller_id"], src_sell["seller_zip_code_prefix"], strict=True))

    products = build_products(rng, n_products, start, end)
    pools = comment_pools(emp, products)
    cats = sorted({p["product_category_name"] for p in products})
    by_cat: dict[str, list[dict]] = {c: [] for c in cats}
    cat_sellers = {c: rng.sample(seller_ids, 3) for c in cats}
    for p in products:
        p["_seller"] = rng.choices(cat_sellers[p["product_category_name"]], [0.6, 0.3, 0.1])[0]
        by_cat[p["product_category_name"]].append(p)
    raw = {
        c: max(OLIST_ITEMS[c] / sum(OLIST_ITEMS[k] for k in cats), 0.0006) for c in cats
    }  # piso: toda categoria vende
    target = {c: v / sum(raw.values()) for c, v in raw.items()}
    got: Counter = Counter()

    def cat_weights(boost: set[str]) -> list[float]:
        n = sum(got.values()) + 300  # corrige o desvio acumulado: o mix gerado segue o do Olist
        return [
            target[c] * min(3.0, max(0.3, (target[c] * n + 1) / (got[c] + 1))) * (3 if c in boost else 1) for c in cats
        ]

    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    dweights = day_weights(days, rng)
    bfs = [bf_date(y) for y in range(start.year, end.year + 1)]
    ptypes, pweights = emp["ptype"]

    customers, orders, items, pays, reviews = [], [], [], [], []
    for ci in range(n_customers):
        uid = md5("customer", seed, ci)
        zip_, city, state = rng.choice(locations)
        name = f"{rng.choices(FIRST, FIRST_W)[0]} {rng.choices(LAST, LAST_W)[0]}"
        name += f" {rng.choices(LAST, LAST_W)[0]}" if rng.random() < 0.3 else ""
        prefs = rng.choices(cats, cat_weights(set()), k=2 + (ci % 5 == 0))
        for when in order_dates(rng, n_orders(rng), days, dweights, end, bfs):
            when = when.replace(
                hour=rng.choices(range(24), HOUR_W)[0], minute=rng.randint(0, 59), second=rng.randint(0, 59)
            )
            when = min(when, now - timedelta(minutes=rng.randint(5, 300)))
            oi = len(orders)
            oid, cid = md5("order", seed, oi), md5("cid", seed, oi)
            customers.append((cid, uid, zip_, city, state, name))
            boost = season_boost(when)

            lines: list[dict] = []
            for k in range(rng.choices([1, 2, 3, 4], [0.6, 0.25, 0.1, 0.05])[0]):
                if k and rng.random() < 0.55:
                    cat = lines[0]["product_category_name"]
                elif rng.random() < (0.5 if boost else 0.78):
                    cat = rng.choice(prefs)
                else:
                    cat = rng.choices(cats, cat_weights(boost))[0]
                got[cat] += 1
                live = [p for p in by_cat[cat] if p["_launch"] <= when and (p["_disc"] is None or p["_disc"] > when)]
                pool = [p for p in live if all(p is not q for q in lines)] or live or by_cat[cat][:1]
                lines.append(rng.choices(pool, [p["_pop"] for p in pool])[0])
            lines = list({id(p): p for p in lines}.values())

            rows, total, dist_max = [], 0, 0.0
            for seq, p in enumerate(lines, 1):
                dist = haversine_km(coords[seller_zip[p["_seller"]]], coords[zip_])
                kg = p["product_weight_g"] / 1000
                freight = round(max(5.0, (6 + dist * 0.008 + kg * 2.2 * (1 + dist / 2000)) * rng.uniform(0.9, 1.1)), 2)
                price = round(p["_base"] * price_factor(when, start) * rng.uniform(0.95, 1.05), 2)
                rows.append((seq, p, price, freight))
                total += round(price * 100) + round(freight * 100)
                dist_max = max(dist_max, dist)

            # pagamento (tipos e parcelas reais do Olist); voucher vira pagamento parcial + outro meio
            ptype = rng.choices(ptypes, pweights)[0]
            plist = [(ptype, total)]
            if ptype == "voucher":
                v = round(total * rng.uniform(0.1, 0.6))
                ptype = rng.choice(["credit_card"] * 7 + ["boleto"] * 3)
                plist = [("voucher", v), (ptype, total - v)]
            for s, (t, v) in enumerate(plist, 1):
                pays.append((oid, s, t, installments(rng, emp, v / 100) if t == "credit_card" else 1, v / 100))

            # linha do tempo planejada e estado de hoje
            approved = when + (
                timedelta(hours=rng.uniform(6, 40)) if ptype == "boleto" else timedelta(minutes=rng.uniform(3, 180))
            )
            invoice = approved + timedelta(hours=rng.uniform(1, 20))
            proc = invoice + timedelta(hours=rng.uniform(1, 12))
            carrier = proc + timedelta(days=rng.uniform(0.2, 2.5))
            transit = 2 + dist_max / 400 * rng.uniform(0.7, 1.4)
            delivered = carrier + timedelta(
                days=transit + (rng.uniform(5, 20) if rng.random() < emp["p_late"] else rng.uniform(-0.5, 1.5))
            )
            delivered = max(delivered, carrier + timedelta(hours=12))
            estimated = (
                when + timedelta(days=math.ceil((carrier - when).total_seconds() / 86400 + transit + rng.uniform(4, 9)))
            ).replace(hour=0, minute=0, second=0)  # noqa: E501

            fate, kind, t_end = rng.random(), "normal", None
            if fate < emp["p_cancel"]:
                kind, t_end = "canceled", when + timedelta(days=rng.uniform(0.2, 6))
            elif fate < emp["p_cancel"] + emp["p_unavail"]:
                kind, t_end = "unavailable", approved + timedelta(days=rng.uniform(1, 5))
            ap, ca, de = approved, carrier, delivered
            if kind != "normal" and t_end <= now:
                status, ca, de = kind, None, None
                if kind == "canceled" and (approved > t_end or rng.random() < 0.4):
                    ap = None
            else:
                kind = "normal"
                status = ("created" if now < approved else "approved" if now < invoice else "invoiced" if now < proc
                          else "processing" if now < carrier else "shipped" if now < delivered else "delivered")  # fmt: skip
                ap, ca, de = (approved if now >= approved else None, carrier if now >= carrier else None,
                              delivered if now >= delivered else None)  # fmt: skip
            orders.append((oid, cid, status, when, ap, ca, de, estimated))
            for seq, p, price, freight in rows:
                limit = approved + timedelta(days=rng.uniform(3, 7))
                items.append((oid, seq, p["product_id"], p["_seller"], limit, price, freight))

            # review: chega depois da entrega (ou do cancelamento); pedidos recentes ainda não têm
            if status in emp["rev_rate"] and rng.random() < emp["rev_rate"][status]:
                if status == "delivered":
                    created = (de + timedelta(days=1)).replace(hour=0, minute=0, second=0)
                    sc = emp["scores"]["late" if de > estimated else "ok"]
                else:
                    created = (t_end + timedelta(days=rng.uniform(1, 10))).replace(hour=0, minute=0, second=0)
                    sc = emp["scores"]["bad"]
                answered = created + timedelta(hours=rng.uniform(2, 96))
                if answered <= now:
                    score = rng.choice(sc)
                    tone = pools["tone"](score)
                    msg = rng.choice(pools["msg"][tone]) if rng.random() < emp["msg_rate"] else None
                    title = rng.choice(pools["title"][tone]) or None if rng.random() < emp["title_rate"] else None
                    reviews.append((md5("review", seed, oi), oid, score, title, msg, created, answered))

    T = {}
    T["customers"] = pd.DataFrame(customers, columns=[
        "customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city", "customer_state", "customer_name"])  # fmt: skip
    T["orders"] = pd.DataFrame(orders, columns=[
        "order_id", "customer_id", "order_status", "order_purchase_timestamp", "order_approved_at",
        "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date"])  # fmt: skip
    T["order_items"] = pd.DataFrame(items, columns=[
        "order_id", "order_item_id", "product_id", "seller_id", "shipping_limit_date", "price", "freight_value"])  # fmt: skip
    T["order_payments"] = pd.DataFrame(pays, columns=[
        "order_id", "payment_sequential", "payment_type", "payment_installments", "payment_value"])  # fmt: skip
    T["order_reviews"] = pd.DataFrame(reviews, columns=[
        "review_id", "order_id", "review_score", "review_comment_title", "review_comment_message",
        "review_creation_date", "review_answer_timestamp"])  # fmt: skip
    T["products"] = pd.DataFrame(products).drop(columns=["_base", "_pop", "_seller", "_launch", "_disc"])
    T["sellers"] = src_sell[src_sell["seller_id"].isin(T["order_items"]["seller_id"])]
    used_zips = set(T["customers"]["customer_zip_code_prefix"]) | set(T["sellers"]["seller_zip_code_prefix"])
    T["geolocation"] = geo[geo["geolocation_zip_code_prefix"].isin(used_zips | {SHOP_ORIGIN_ZIP_PREFIX})]
    T["product_category_name_translation"] = pd.read_csv(
        src / "product_category_name_translation.csv", encoding="utf-8-sig"
    )
    T["_now"] = now  # type: ignore[assignment]
    return T


# ---------------------------------------------------------------- validação
def mix_table(T: dict) -> pd.DataFrame:
    m = T["order_items"].merge(T["products"][["product_id", "product_category_name"]], on="product_id")
    gen = m["product_category_name"].value_counts(normalize=True) * 100
    cats = T["products"]["product_category_name"].value_counts()
    olist = pd.Series(OLIST_ITEMS) / sum(OLIST_ITEMS.values()) * 100
    t = (
        pd.DataFrame({"olist_pct": olist, "gerado_pct": gen, "produtos": cats})
        .fillna(0)
        .sort_values("olist_pct", ascending=False)
    )
    t["diff_pp"] = t["gerado_pct"] - t["olist_pct"]
    return t


def validate(T: dict, min_repeat: float = 0.35, check_mix: bool = False) -> None:  # noqa: C901
    now = T["_now"]
    o, c, i, p, r, pr = (
        T[k] for k in ("orders", "customers", "order_items", "order_payments", "order_reviews", "products")
    )
    assert o["order_id"].is_unique and c["customer_id"].is_unique and pr["product_id"].is_unique
    assert not i.duplicated(["order_id", "order_item_id"]).any()
    assert not p.duplicated(["order_id", "payment_sequential"]).any() and r["review_id"].is_unique
    assert set(o["customer_id"]) == set(c["customer_id"]) and set(i["order_id"]) == set(o["order_id"])
    assert set(p["order_id"]) <= set(o["order_id"]) and set(r["order_id"]) <= set(o["order_id"])
    assert set(i["product_id"]) <= set(pr["product_id"]) and set(i["seller_id"]) <= set(T["sellers"]["seller_id"])
    geo_zips = set(T["geolocation"]["geolocation_zip_code_prefix"])
    assert (
        set(c["customer_zip_code_prefix"]) | set(T["sellers"]["seller_zip_code_prefix"]) | {SHOP_ORIGIN_ZIP_PREFIX}
        <= geo_zips
    )
    untranslated = set(pr["product_category_name"]) - set(
        T["product_category_name_translation"]["product_category_name"]
    )
    assert untranslated <= {"pc_gamer", "portateis_cozinha_e_preparadores_de_alimentos"}, untranslated
    cents = (i["price"] * 100).round().astype(int) + (i["freight_value"] * 100).round().astype(int)
    paid = (p["payment_value"] * 100).round().astype(int)
    assert cents.groupby(i["order_id"]).sum().sub(paid.groupby(p["order_id"]).sum()).eq(0).all(), (
        "pagamento != itens+frete"
    )

    d = o.set_index("order_id")
    pu, ap, ca, de = (
        d[k]
        for k in (
            "order_purchase_timestamp",
            "order_approved_at",
            "order_delivered_carrier_date",
            "order_delivered_customer_date",
        )
    )  # noqa: E501
    assert (pu <= now).all() and (ap.dropna() >= pu[ap.notna()]).all()
    both = ap.notna() & ca.notna()
    assert (ca[both] >= ap[both]).all() and (de.dropna() >= ca[de.notna()]).all()
    assert (ca.dropna() <= now).all() and (de.dropna() <= now).all() and (ap.dropna() <= now).all()
    assert (d["order_estimated_delivery_date"] >= pu.dt.normalize()).all()
    s = d["order_status"]
    assert de[s == "delivered"].notna().all() and de[s != "delivered"].isna().all()
    assert ca[s.isin(["shipped", "delivered"])].notna().all() and ap[s == "created"].isna().all()
    assert (r["review_answer_timestamp"] >= r["review_creation_date"]).all() and (
        r["review_answer_timestamp"] <= now
    ).all()
    assert (r["review_creation_date"].values >= pu.loc[r["order_id"]].values).all()
    first = i.merge(pr[["product_id", "product_created_at", "product_discontinued_at"]], on="product_id").merge(
        o[["order_id", "order_purchase_timestamp"]], on="order_id")  # fmt: skip
    day = first["order_purchase_timestamp"].dt.normalize()
    assert (day >= pd.to_datetime(first["product_created_at"])).all(), "venda antes do lançamento"
    disc = pd.to_datetime(first["product_discontinued_at"].replace("", None))
    assert (disc.isna() | (day < disc)).all(), "venda após descontinuação"

    uid = c["customer_unique_id"].value_counts()
    assert (uid >= 2).mean() >= min_repeat, f"recorrentes {(uid >= 2).mean():.0%} < {min_repeat:.0%}"
    assert (c.groupby("customer_unique_id")["customer_zip_code_prefix"].nunique() == 1).all()
    if check_mix:
        assert mix_table(T)["diff_pp"].abs().max() <= 2.0, "mix de categorias fora de 2 p.p. do Olist"
        assert (pr["product_category_name"].value_counts() >= 3).all()


def write(T: dict, out: Path) -> None:
    names = {
        "customers": "olist_customers_dataset.csv", "geolocation": "olist_geolocation_dataset.csv",
        "orders": "olist_orders_dataset.csv", "order_items": "olist_order_items_dataset.csv",
        "order_payments": "olist_order_payments_dataset.csv", "order_reviews": "olist_order_reviews_dataset.csv",
        "products": "olist_products_dataset.csv", "sellers": "olist_sellers_dataset.csv",
        "product_category_name_translation": "product_category_name_translation.csv",
    }  # fmt: skip
    out.mkdir(parents=True, exist_ok=True)
    for key, fname in names.items():
        df = T[key]
        df.sort_values("order_purchase_timestamp" if key == "orders" else df.columns[0]).to_csv(
            out / fname, index=False, date_format=FMT
        )
    T["products"][["product_id", "product_name", "product_category_name", "image_query", "image_key"]].rename(
        columns={"product_category_name": "category"}
    ).to_csv(out / "image_queries.csv", index=False)


def run(src: Path, out: Path, products: int = 0, customers: int = 20000, seed: int = 42,
        today: date | None = None, months: int = 24) -> dict:  # fmt: skip
    T = generate(src, products, customers, seed, today or date.today(), months)
    validate(T, check_mix=not products and customers >= 5000)
    write(T, out)
    return T


def report(T: dict) -> None:
    for k, df in T.items():
        if k != "_now":
            print(f"{k:36s}{len(df):8d}")
    o, c = T["orders"], T["customers"]
    per = c["customer_unique_id"].value_counts()
    print("\npedidos/cliente (n: clientes):", dict(sorted(Counter(per).items())))
    print(f"clientes com 2+ pedidos: {(per >= 2).mean():.1%}  | clientes únicos: {len(per)}")
    month = o["order_purchase_timestamp"].dt.strftime("%Y-%m")
    first = o.merge(c[["customer_id", "customer_unique_id"]], on="customer_id").groupby("customer_unique_id")[
        "order_purchase_timestamp"].min().dt.strftime("%Y-%m")  # fmt: skip
    print("\nmês: pedidos / clientes novos")
    for m, n in month.value_counts().sort_index().items():
        print(f"  {m}  {n:6d}  {int((first == m).sum()):6d}")
    age = pd.cut((T["_now"] - o["order_purchase_timestamp"]).dt.days, [-1, 2, 13, 29, 89, 10**6],
                 labels=["0-2d", "3-13d", "14-29d", "30-89d", "90d+"])  # fmt: skip
    print("\nstatus por idade do pedido:\n", pd.crosstab(age, o["order_status"]).to_string())
    print("\ncategoria x %itens Olist x %itens gerado x nº produtos:\n", mix_table(T).round(2).to_string())
    sold = set(T["order_items"]["product_id"])
    print(f"produtos nunca vendidos: {(~T['products']['product_id'].isin(sold)).sum()} de {len(T['products'])}")
    print("\namostra clientes:\n", c.drop_duplicates("customer_unique_id").head(10).to_string(index=False))
    cols = ["product_id", "product_name", "product_brand", "product_weight_g", "product_created_at", "image_query"]
    print("\namostra produtos:\n", T["products"][cols].head(10).to_string(index=False))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", type=Path, default=ROOT / "data/olist")
    ap.add_argument("--out", type=Path, default=ROOT / "data/enriched")
    ap.add_argument("--products", type=int, default=0, help="0 = todos os produtos gerados")
    ap.add_argument("--customers", type=int, default=20000)
    ap.add_argument("--months", type=int, default=24)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--today", type=date.fromisoformat, default=date.today(), help="YYYY-MM-DD (padrão: hoje)")
    a = ap.parse_args()
    report(run(a.src, a.out, a.products, a.customers, a.seed, a.today, a.months))


if __name__ == "__main__":
    main()
