EXPECTED_ROUTES = {
    ("GET", "/docs"),
    ("GET", "/docs/oauth2-redirect"),
    ("GET", "/api/v1/health"),
    ("GET", "/openapi.json"),
    ("GET", "/redoc"),
    ("POST", "/api/v1/chat/questions"),
    ("GET", "/api/v1/chat/questions/{question_id}/events"),
    ("POST", "/api/v1/chat/questions/{question_id}/feedback"),
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


def test_public_routes_unchanged(app):
    assert set(_routes(app.routes)) == EXPECTED_ROUTES
