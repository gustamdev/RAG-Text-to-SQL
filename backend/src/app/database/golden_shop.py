"""Golden dataset sintético da loja simulada (E7): perguntas sobre as views `shop_*_view`, sem PII.

Mesmo formato dos documentos de `golden_data` (question, answer, context, is_approved) mais
`tables`, as views que a consulta correta usa. Os números são fictícios: servem de roteiro
para a regressão manual (tests/test_golden_regression.py), não de valor esperado exato.
"""

SHOP_GOLDEN = [
    {
        "question": "Qual foi o último pedido feito na loja?",
        "answer": "O último pedido tem status paid, total de R$ 189,90 e foi feito no dia mais recente de shop_orders_view.",
        "tables": ["shop_orders_view"],
    },
    {
        "question": "Qual a receita da loja por UF de destino?",
        "answer": "Soma de total_cents (em reais) dos pedidos paid, shipped e delivered, agrupada por destination_state, do maior para o menor.",
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
        "answer": "Soma de qty por category em shop_order_items_view, restrita aos pedidos pagos, em ordem decrescente.",
        "tables": ["shop_order_items_view", "shop_orders_view"],
    },
]

for _row in SHOP_GOLDEN:
    _row.update(context="sem contexto disponível", is_approved=True)
