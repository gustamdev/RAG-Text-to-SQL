EXPECTED_ROUTES = {
    ("GET", "/docs"),
    ("GET", "/docs/oauth2-redirect"),
    ("GET", "/api/v1/health"),
    ("GET", "/openapi.json"),
    ("GET", "/redoc"),
    # Chat Text-to-SQL (admin)
    ("POST", "/api/v1/chat/questions"),
    ("GET", "/api/v1/chat/questions/{question_id}/events"),
    ("POST", "/api/v1/chat/questions/{question_id}/feedback"),
    # Autenticação (só login de admin; não há cadastro)
    ("POST", "/api/v1/auth/login"),
    ("GET", "/api/v1/auth/me"),
    ("POST", "/api/v1/auth/logout"),
    # Vitrine pública
    ("GET", "/api/v1/products"),
    ("GET", "/api/v1/products/{product_id}"),
    ("GET", "/api/v1/categories"),
    # Loja: identidade (pública até o login completo) e catálogo público
    ("POST", "/api/v1/shop/auth/signup"),
    ("POST", "/api/v1/shop/auth/verify-otp"),
    ("POST", "/api/v1/shop/auth/resend-otp"),
    ("POST", "/api/v1/shop/auth/login"),
    ("POST", "/api/v1/shop/auth/login/verify-otp"),
    ("GET", "/api/v1/shop/products"),
    ("GET", "/api/v1/shop/products/categories"),
    ("GET", "/api/v1/shop/products/suggest"),
    ("GET", "/api/v1/shop/products/{product_id}"),
    ("GET", "/api/v1/shop/products/{product_id}/freight"),
    ("POST", "/api/v1/shop/products/batch"),
    # Loja: exigem cliente autenticado (aud=shop)
    ("GET", "/api/v1/shop/auth/me"),
    ("POST", "/api/v1/shop/auth/logout"),
    ("GET", "/api/v1/shop/cart"),
    ("POST", "/api/v1/shop/cart/items"),
    ("PATCH", "/api/v1/shop/cart/items/{product_id}"),
    ("DELETE", "/api/v1/shop/cart/items/{product_id}"),
    ("DELETE", "/api/v1/shop/cart"),
    ("POST", "/api/v1/shop/cart/merge"),
    ("GET", "/api/v1/shop/cart/freight"),
    ("POST", "/api/v1/shop/cart/freight"),
    ("GET", "/api/v1/shop/account/addresses"),
    ("POST", "/api/v1/shop/account/addresses"),
    ("PATCH", "/api/v1/shop/account/addresses/{address_id}"),
    ("DELETE", "/api/v1/shop/account/addresses/{address_id}"),
    ("POST", "/api/v1/shop/checkout"),
    ("POST", "/api/v1/shop/checkout/{order_id}/pay"),
    ("GET", "/api/v1/shop/orders"),
    ("GET", "/api/v1/shop/orders/{order_id}"),
    ("POST", "/api/v1/shop/orders/{order_id}/cancel"),
    # Backoffice (admin)
    ("GET", "/api/v1/admin/overview"),
    ("GET", "/api/v1/admin/products"),
    ("GET", "/api/v1/admin/products/{product_id}"),
    ("GET", "/api/v1/admin/categories"),
    ("GET", "/api/v1/admin/snapshot"),
    ("POST", "/api/v1/admin/snapshot/refresh"),
}


def _routes(routes, prefix=""):
    # FastAPI >= 0.141 aninha include_router em original_router + include_context.prefix.
    for route in routes:
        child = getattr(route, "original_router", None)
        children = getattr(child, "routes", None) or getattr(route, "routes", None)
        if children:
            context = getattr(route, "include_context", None)
            yield from _routes(children, prefix + getattr(context, "prefix", ""))
        elif getattr(route, "path", ""):
            for method in getattr(route, "methods", None) or ():
                if method not in ("HEAD", "OPTIONS"):
                    yield method, prefix + route.path


def test_public_routes_match_expected(app):
    assert set(_routes(app.routes)) == EXPECTED_ROUTES


PUBLIC_ROUTES = {
    ("GET", "/api/v1/health"),
    ("POST", "/api/v1/auth/login"),
    ("GET", "/api/v1/products"),
    ("GET", "/api/v1/products/{product_id}"),
    ("GET", "/api/v1/categories"),
    ("POST", "/api/v1/shop/auth/signup"),
    ("POST", "/api/v1/shop/auth/verify-otp"),
    ("POST", "/api/v1/shop/auth/resend-otp"),
    ("POST", "/api/v1/shop/auth/login"),
    ("POST", "/api/v1/shop/auth/login/verify-otp"),
    ("GET", "/api/v1/shop/products"),
    ("GET", "/api/v1/shop/products/categories"),
    ("GET", "/api/v1/shop/products/suggest"),
    ("GET", "/api/v1/shop/products/{product_id}"),
    ("GET", "/api/v1/shop/products/{product_id}/freight"),
    ("POST", "/api/v1/shop/products/batch"),
}


def test_only_the_storefront_login_and_health_are_public(app, client, auth_db):
    """Toda rota fora da lista pública exige token: sem credencial nenhuma dá 401 (nunca 200/404/503)."""
    protected = {(method, path) for method, path in _routes(app.routes) if path.startswith("/api/v1/")} - PUBLIC_ROUTES

    for method, path in sorted(protected):
        url = (
            path.replace("{product_id}", "x")
            .replace("{question_id}", "x")
            .replace("{address_id}", "x")
            .replace("{order_id}", "x")
        )
        res = client.request(method, url, json={"question": "oi"})
        assert res.status_code == 401, f"{method} {path} -> {res.status_code}"
