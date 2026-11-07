"""Configuração comum dos testes."""

import pytest

from desktop import config


@pytest.fixture(autouse=True)
def _no_shape_snap(monkeypatch, request):
    """Os testes de desenho antigos usam traços retos de propósito: sem o reconhecimento
    de formas (D033), que tem testes próprios (marcados com `snap`)."""
    if "snap" not in request.keywords:
        monkeypatch.setattr(config, "SHAPE_SNAP_ENABLED", False)
