"""Termos de uso e aviso de privacidade da loja de demonstração (texto simples, versionado).

Controlador, encarregado e prazos vêm de `settings` (placeholders até o dono definir). Mudou o texto: suba
`TERMS_VERSION` em schemas/shop_auth.py para exigir novo aceite.
"""

from app.config import settings
from app.schemas.shop_account import LegalOut
from app.schemas.shop_auth import TERMS_VERSION

# Terceiros que recebem dados (também entram na exportação, art. 19).
THIRD_PARTIES = [
    {"name": "Provedor SMTP (ex.: Google)", "data": "e-mail e código de verificação (OTP)",
     "purpose": "enviar e-mails de verificação", "country": "EUA (possível transferência internacional)"},
    {"name": "BrasilAPI e ViaCEP (consulta de CEP)",
     "data": "só o CEP digitado (8 dígitos), enviado pelo nosso servidor, sem identificar você",
     "purpose": "preencher o endereço e calcular o frete", "country": "não confirmado (pode ser fora do Brasil)"},
    {"name": "OpenAI", "data": "perguntas do administrador e resultados agregados/pseudonimizados do agente",
     "purpose": "análise de negócio por IA (só administradores; sem dados de contato)", "country": "EUA"},
    {"name": "LangSmith (LangChain)", "data": "nada por padrão: entradas e saídas são ocultadas",
     "purpose": "observabilidade do agente, apenas se ativado", "country": "EUA"},
]  # fmt: skip
ORIGIN = "Dados informados por você no cadastro, nos endereços e nos pedidos; registros técnicos gerados pelo sistema."
PURPOSES = [
    {"purpose": "Criar e manter a conta, verificar o e-mail, processar pedidos simulados e entrega simulada",
     "legal_basis": "Execução de contrato (art. 7º, V)"},
    {"purpose": "Segurança, prevenção a fraude e registros de auditoria (pseudônimos)",
     "legal_basis": "Legítimo interesse (art. 7º, IX)"},
    {"purpose": "Análise de negócio pelo agente, só com dados pseudonimizados e agregados, acesso de administradores",
     "legal_basis": "Legítimo interesse (art. 7º, IX)"},
    {"purpose": "Guardar o cartão para pagar mais rápido (bandeira, 4 últimos dígitos, validade e impressão digital "
                "pseudonimizada; nunca o número completo, o CVV nem o titular), só se você marcar \"salvar cartão\"",
     "legal_basis": "Consentimento (art. 7º, I), revogável a qualquer momento excluindo o cartão"},
]  # fmt: skip

TERMS = (
    "Termos de uso. AVISO DE DEMONSTRAÇÃO: esta é uma loja simulada. Nenhum pedido é real, nenhum produto é "
    "entregue e nenhum pagamento é cobrado. Não informe cartão de crédito verdadeiro: o número completo, o CVV e "
    "o titular nunca são guardados; só se você optar por salvar o cartão guardamos bandeira, 4 últimos dígitos, "
    "validade e uma impressão digital pseudonimizada. É necessário declarar ter 18 anos ou mais "
    "(autodeclaração, sem verificação). Você pode excluir sua conta a qualquer momento."
)


def retention_text() -> str:
    return (
        f"Conta: enquanto existir; contas sem login há {settings.SHOP_RETENTION_INACTIVE_DAYS} dias são anonimizadas; "
        f"contas não verificadas somem em {settings.SHOP_UNVERIFIED_TTL_HOURS} h. Pedidos e pagamentos: "
        f"{settings.SHOP_RETENTION_ORDER_DAYS} dias após a criação. Carrinho: {settings.SHOP_CART_TTL_DAYS} dias. "
        "Cartões salvos: até você excluir o cartão ou a conta. Códigos de verificação: minutos. "
        "Registros de segurança: 90 dias (acesso de administradores: 365 dias). "
        "Após a exclusão da conta: o cadastro é anonimizado (e-mail, apelido e telefone removidos); endereços, "
        "carrinho e cartões salvos são apagados; pedidos e pagamentos perdem o endereço de entrega, a bandeira e "
        "os 4 últimos dígitos, mas mantêm itens, valores e datas (finalidade contábil), ligados só a um "
        "identificador interno, sem nome, e-mail ou telefone."
    )


def privacy_text() -> str:
    third = "; ".join(f"{t['name']} ({t['country']}): {t['data']}" for t in THIRD_PARTIES)
    purposes = " ".join(f"({i}) {p['purpose']}: {p['legal_basis']}." for i, p in enumerate(PURPOSES, 1))
    return (
        "Aviso de privacidade (LGPD, Lei 13.709/2018). Esta loja é uma demonstração, sem pagamento real. "
        f"Controlador: {settings.SHOP_CONTROLLER_NAME}, {settings.SHOP_CONTROLLER_CONTACT}. "
        f"Encarregado (DPO): {settings.SHOP_DPO_NAME}, {settings.SHOP_DPO_EMAIL}. "
        "Dados tratados: e-mail, apelido, telefone (opcional), endereços de entrega, histórico de pedidos e "
        "pagamentos simulados (bandeira e 4 últimos dígitos, nunca o número completo), cartões salvos por opção sua "
        "(bandeira, 4 últimos dígitos, validade e impressão digital pseudonimizada; nunca número completo, CVV ou "
        "titular), registros de segurança. "
        f"Finalidades e bases legais: {purposes} O aceite dos termos é condição para criar a conta e não é "
        'consentimento: a base é contrato. Salvar o cartão depende do seu consentimento, dado ao marcar "salvar '
        'cartão"; você o revoga excluindo o cartão. Qualquer outro tratamento que dependa de consentimento será '
        "pedido à parte e pode ser revogado. "
        f"Compartilhamento e transferência internacional (arts. 33-36): {third}. "
        f"Retenção: {retention_text()} "
        "Seus direitos (art. 18): confirmação e acesso, correção, anonimização, bloqueio ou eliminação, "
        "portabilidade, informação sobre compartilhamento, informação sobre a possibilidade de não consentir e "
        "revogação do consentimento. Na conta: exportar (JSON), corrigir apelido e telefone e excluir. "
        f"Sem acesso à conta, peça pelo e-mail do encarregado ({settings.SHOP_DPO_EMAIL}); respondemos em até "
        "15 dias. Você pode peticionar à Autoridade Nacional de Proteção de Dados (ANPD): gov.br/anpd."
    )


def art19_declaration() -> dict:
    """Metadados da exportação (art. 19): origem, finalidades, terceiros, retenção, canal."""
    return {
        "controller": settings.SHOP_CONTROLLER_NAME,
        "dpo_contact": settings.SHOP_DPO_EMAIL,
        "origin": ORIGIN,
        "purposes": PURPOSES,
        "third_parties": THIRD_PARTIES,
        "retention": retention_text(),
    }


def legal() -> LegalOut:
    return LegalOut(version=TERMS_VERSION, terms=TERMS, privacy=privacy_text())
