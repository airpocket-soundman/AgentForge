from app.product import SODATERU_APP, active_product


def test_active_product_defaults_to_sodateru_app(monkeypatch):
    monkeypatch.delenv("PRODUCT_ID", raising=False)
    assert active_product() == SODATERU_APP


def test_unknown_product_falls_back_to_sodateru_app(monkeypatch):
    monkeypatch.setenv("PRODUCT_ID", "not_registered")
    assert active_product() == SODATERU_APP
