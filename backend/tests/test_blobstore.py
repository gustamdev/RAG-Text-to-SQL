import pytest
from fastapi.testclient import TestClient
from shop_helpers import shop  # noqa: F401

from app.services import blobstore
from app.services.blobstore import MAX_BYTES, BlobError, BlobStore

JPG = b"\xff\xd8\xff\xe0" + b"0" * 20
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"0" * 20


@pytest.fixture
def bs(tmp_path):
    return BlobStore(tmp_path, "/media")


def test_put_roundtrip(bs):
    assert bs.put("product-images", "a1.jpg", JPG, "image/jpeg") == "/media/product-images/a1.jpg"
    assert bs.exists("product-images", "a1.jpg")
    assert bs.path_of("product-images", "a1.jpg").read_bytes() == JPG
    bs.put("product-images", "b.png", PNG, "image/png")
    bs.put("product-images", "c.webp", WEBP, "image/webp")
    assert not list(bs.base.rglob("*.tmp"))


@pytest.mark.parametrize(
    ("container", "name"),
    [
        ("product-images", "../x.jpg"),
        ("product-images", "a..b.jpg"),
        ("product-images", "a/b.jpg"),
        ("product-images", "a//b.jpg"),
        ("product-images", "a.gif"),
        ("product-images", "a.svg"),
        ("product-images", "a.JPG"),
        ("product-images", ".hidden.jpg"),
        ("..", "a.jpg"),
        ("a/b", "a.jpg"),
        ("Product", "a.jpg"),
        ("", "a.jpg"),
    ],
)
def test_invalid_names(bs, container, name):
    with pytest.raises(BlobError):
        bs.path_of(container, name)
    assert not bs.exists(container, name)


def test_symlink_escape(tmp_path):
    bs = BlobStore(tmp_path / "base", "/media")
    bs.base.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "a.jpg").write_bytes(JPG)
    (bs.base / "box").symlink_to(outside)
    with pytest.raises(BlobError):
        bs.path_of("box", "a.jpg")


def test_size_limit(bs):
    with pytest.raises(BlobError):
        bs.put("product-images", "a.jpg", JPG + b"0" * MAX_BYTES, "image/jpeg")
    assert not bs.exists("product-images", "a.jpg")


@pytest.mark.parametrize(
    ("name", "data", "ctype"),
    [
        ("a.jpg", PNG, "image/jpeg"),  # magic errado
        ("a.png", b"<html>", "image/png"),
        ("a.webp", b"RIFF\x00\x00\x00\x00WAVE", "image/webp"),
        ("a.jpg", JPG, "image/png"),  # content_type não bate
    ],
)
def test_put_rejects_bad_content(bs, name, data, ctype):
    with pytest.raises(BlobError):
        bs.put("product-images", name, data, ctype)
    assert not bs.exists("product-images", name)


@pytest.fixture
def media(client, tmp_path, monkeypatch):
    monkeypatch.setattr(blobstore.store, "base", tmp_path.resolve())
    blobstore.store.put("product-images", "a1.jpg", JPG, "image/jpeg")
    return client


def test_media_get(media):
    res = media.get("/media/product-images/a1.jpg")
    assert res.status_code == 200
    assert res.content == JPG
    assert res.headers["content-type"] == "image/jpeg"
    assert "immutable" in res.headers["cache-control"]
    assert res.headers["x-content-type-options"] == "nosniff"
    head = media.head("/media/product-images/a1.jpg")
    assert head.status_code == 200
    assert head.content == b""


@pytest.mark.parametrize(
    "path",
    [
        "/media/product-images/nope.jpg",
        "/media/product-images/..%2F..%2Fa.jpg",
        "/media/product-images/%2e%2e",
        "/media/product-images/a1.gif",
        "/media/product-images/",
        "/media/product-images",
        "/media/..%2Fx/a1.jpg",
    ],
)
def test_media_404(media, path):
    res = media.get(path)
    assert res.status_code == 404
    assert str(blobstore.store.base) not in res.text


def test_media_no_write_methods(media):
    assert media.post("/media/product-images/a1.jpg", content=JPG).status_code == 405
    assert media.put("/media/product-images/a1.jpg", content=JPG).status_code == 405
    assert isinstance(media, TestClient)


def test_image_url_in_catalog(shop, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setattr(blobstore.store, "base", tmp_path.resolve())
    blobstore.store.put("product-images", "aaaa0001.jpg", JPG, "image/jpeg")
    shop.product("aaaa0001", image_key="product-images/aaaa0001.jpg")
    shop.product("bbbb0002", image_key="product-images/bbbb0002.jpg")  # arquivo ausente
    shop.product("cccc0003")  # sem campo
    shop.product("dddd0004", image_key="../../etc/passwd")  # chave maliciosa
    get = shop.client.get
    assert get("/api/v1/shop/products/aaaa0001").json()["image_url"] == "/media/product-images/aaaa0001.jpg"
    for pid in ("bbbb0002", "cccc0003", "dddd0004"):
        assert get(f"/api/v1/shop/products/{pid}").json()["image_url"] is None
    items = {i["product_id"]: i["image_url"] for i in get("/api/v1/shop/products").json()["items"]}
    assert items["aaaa0001"] == "/media/product-images/aaaa0001.jpg"
    assert items["bbbb0002"] is None
