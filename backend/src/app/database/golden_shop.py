"""Golden dataset sintético da loja simulada (E7): perguntas sobre as views `shop_*_view`, sem PII.

Mesmo formato dos documentos de `golden_data` (question, answer, context, is_approved) mais
`tables`, as views que a consulta correta usa. Os números são fictícios: servem de roteiro
para a regressão manual (tests/test_golden_regression.py), não de valor esperado exato.
"""

SHOP_GOLDEN = [
    {
        "question": "Qual foi o último pedido feito na loja?",
        "answer": "Pedido mais recente de shop_orders_view (order_date maior), com status e total em reais.",
        "tables": ["shop_orders_view"],
    },
    {
        "question": "Qual a receita da loja por UF de destino?",
        "answer": (
            "Soma de total_cents/100 dos pedidos paid, shipped e delivered, "
            "por destination_state, em ordem decrescente."
        ),
        "tables": ["shop_orders_view"],
    },
    {
        "question": "Quantos pedidos foram recusados no pagamento?",
        "answer": "Contagem dos pedidos com status refused em shop_orders_view.",
        "tables": ["shop_orders_view"],
    },
    {
        "question": "Qual o ticket médio dos pedidos pagos na loja?",
        "answer": "Média de total_cents dividida por 100 dos pedidos paid, shipped e delivered.",
        "tables": ["shop_orders_view"],
    },
    {
        "question": "Quais categorias de produto mais vendem na loja?",
        "answer": "Soma de qty por category em shop_order_items_view, só pedidos pagos, em ordem decrescente.",
        "tables": ["shop_order_items_view", "shop_orders_view"],
    },
    {
        "question": "Quais produtos estão sem estoque?",
        "answer": "Produtos de shop_products_view com in_stock falso (stock = 0): product_id, title e category.",
        "tables": ["shop_products_view"],
    },
    {
        "question": "Quais produtos têm menos de 5 unidades?",
        "answer": "Produtos de shop_products_view com stock menor que 5 e maior que 0, em ordem crescente de stock.",
        "tables": ["shop_products_view"],
    },
    {
        "question": "Quais categorias têm mais produtos esgotados?",
        "answer": "Contagem de produtos com in_stock falso em shop_products_view, por category, em ordem decrescente.",
        "tables": ["shop_products_view"],
    },
    {
        "question": "Quantos pedidos foram cancelados no último mês?",
        "answer": (
            "Contagem de pedidos com status canceled em shop_orders_view e canceled_date dentro dos últimos 30 dias."
        ),
        "tables": ["shop_orders_view"],
    },
    {
        "question": "Quais produtos têm mais cancelamentos?",
        "answer": (
            "Soma de qty por product_id em shop_order_items_view juntando shop_orders_view por order_id, "
            "só status canceled, em ordem decrescente."
        ),
        "tables": ["shop_order_items_view", "shop_orders_view"],
    },
    {
        "question": "Qual o valor total reembolsado?",
        "answer": "Soma de refund_cents dividida por 100 em shop_orders_view (pedidos canceled), com COALESCE para 0.",
        "tables": ["shop_orders_view"],
    },
    {
        "question": "Qual o principal motivo de cancelamento?",
        "answer": "Contagem de pedidos canceled por cancel_reason em shop_orders_view, em ordem decrescente, limite 1.",
        "tables": ["shop_orders_view"],
    },
]

for _row in SHOP_GOLDEN:
    _row.update(context="sem contexto disponível", is_approved=True)
