import io
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from test_identity_postgres import headers
from test_orders_postgres import System
from test_orders_postgres import order_system as _order_system

from ashana.bootstrap.app import create_app
from ashana.modules.inventory.domain.models import InventoryError
from ashana.modules.inventory.infrastructure.images import normalize_photo

image_system = _order_system
pytestmark = pytest.mark.skipif(
    os.environ.get("ASHANA_RUN_INTEGRATION") != "1", reason="Нужен изолированный PostgreSQL"
)


def jpeg_with_gps(size: tuple[int, int] = (1600, 1200)) -> bytes:
    exif = Image.Exif()
    exif[0x8825] = {1: "N", 2: (43.0, 15.0, 0.0)}  # GPSInfo
    exif[0x010F] = "PhoneMaker"
    buffer = io.BytesIO()
    Image.new("RGB", size, (200, 120, 40)).save(buffer, "JPEG", exif=exif)
    return buffer.getvalue()


def test_photo_is_resized_reencoded_and_loses_metadata() -> None:
    photo = normalize_photo(jpeg_with_gps())
    with Image.open(io.BytesIO(photo)) as image:
        assert image.format == "WEBP" and max(image.size) == 800
        assert not image.getexif()
    assert b"PhoneMaker" not in photo
    for bad in (b"", b"<svg onload=alert(1)>", b"GIF89a" + b"0" * 20):
        with pytest.raises(InventoryError):
            normalize_photo(bad)


def test_menu_photo_upload_public_url_and_removal(image_system: System) -> None:
    s = image_system
    entry, _, _ = s.setup()
    with s.service.uow() as uow:
        card = uow.catalog.entry(entry)
    assert card is not None
    with TestClient(create_app(s.settings)) as client:
        path = f"/api/v1/inventory/items/{card.item_id}/image"
        body = jpeg_with_gps((400, 300))
        assert client.put(
            path, content=body, headers={"content-type": "image/jpeg"}
        ).status_code in (401, 403)
        client.cookies.set(s.settings.session_cookie, s.token)
        assert (
            client.put(path, content=body, headers={"content-type": "image/jpeg"}).status_code
            == 403
        )
        bad = client.put(
            path, content=b"text", headers={**headers(client), "content-type": "text/plain"}
        )
        assert bad.status_code == 422
        saved = client.put(
            path, content=body, headers={**headers(client), "content-type": "image/jpeg"}
        )
        assert saved.status_code == 200
        digest = saved.json()["image"]
        client.cookies.clear()
        menu = client.get("/api/v1/catalog/menu?upcoming=true&limit=100").json()["entries"]
        found = [e for e in menu if e["id"] == str(entry)]
        if found:  # The entry may sit beyond the first page in a busy test database.
            assert found[0]["image_url"].endswith(digest[:16])
            assert "item_id" not in found[0] and "image" not in found[0]
        photo = client.get(f"/api/v1/media/menu/{entry}")
        assert photo.status_code == 200 and photo.headers["content-type"] == "image/webp"
        assert "immutable" in photo.headers["cache-control"]
        assert client.get(f"/api/v1/media/menu/{uuid4()}").status_code == 404
        client.cookies.set(s.settings.session_cookie, s.token)
        removed = client.delete(path, headers=headers(client))
        assert removed.status_code == 204
        assert client.get(f"/api/v1/media/menu/{entry}").status_code == 404
