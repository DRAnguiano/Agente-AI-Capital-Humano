"""G4 — media_guard a nivel del webhook de Chatwoot (agnóstico al canal).

Fixture de payload **de Chatwoot** (no de Telegram): si el evento entrante trae
`attachments`, el webhook responde con el aviso canned y NO extrae, NO encola, NO orquesta.
Parametrizado por canal (telegram/whatsapp) para probar la agnosticidad.

Notas de mocking (decisión 8): `_send_chatwoot_message` es async → fake async;
`run_hr_graph_message` es sync → fake sync (devuelve {} → el webhook corta en `empty_reply`
sin tocar HTTP/BD aguas abajo).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

TOKEN = "test-token"
CHANNELS = ["telegram", "whatsapp"]
MEDIA = [
    [{"file_type": "image", "data_url": "x"}],   # imagen / sticker (Chatwoot lo expone como image)
    [{"file_type": "file", "data_url": "x"}],     # documento / archivo
    [{"file_type": "audio", "data_url": "x"}],     # audio
]


def _payload(*, attachments=None, content="", channel_type="telegram"):
    return {
        "event": "message_created",
        "message_type": "incoming",
        "content": content,
        "id": 123,
        "account": {"id": 1},
        "conversation": {"id": 99, "meta": {"channel": channel_type}},
        "inbox": {"id": 7, "channel_type": channel_type, "name": channel_type.title()},
        "sender": {"id": 555, "name": "Demo"},
        "attachments": attachments or [],
    }


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("CHATWOOT_WEBHOOK_TOKEN", TOKEN)
    monkeypatch.setenv("INBOUND_DEBOUNCE_ENABLED", "false")
    monkeypatch.setenv("WEBHOOK_RATE_LIMIT_ENABLED", "false")

    import app.app as A

    sent: dict = {}

    async def fake_send(account_id, conversation_id, content):  # async: matchea el await
        sent.update(account_id=account_id, conversation_id=conversation_id, content=content)
        return {"ok": True}

    called = {"orchestrator": 0}

    def fake_orchestrator(**kwargs):  # sync: matchea la llamada no-await
        called["orchestrator"] += 1
        return {}  # reply vacío → el webhook corta en empty_reply

    monkeypatch.setattr(A, "_send_chatwoot_message", fake_send)
    monkeypatch.setattr(A, "run_hr_graph_message", fake_orchestrator)

    return TestClient(A.app), sent, called


@pytest.mark.parametrize("channel_type", CHANNELS)
@pytest.mark.parametrize("attachments", MEDIA)
def test_media_guard_blocks(client, channel_type, attachments):
    c, sent, called = client
    r = c.post(
        "/chatwoot/webhook",
        params={"token": TOKEN},
        json=_payload(attachments=attachments, content="", channel_type=channel_type),
    )
    body = r.json()
    assert body["status"] == "media_guard"
    assert body["extracted"] is False and body["enqueued"] is False
    assert "no puedo revisar" in sent["content"]
    assert called["orchestrator"] == 0  # no orquestador, no extracción


@pytest.mark.parametrize("channel_type", CHANNELS)
def test_media_with_caption_blocks(client, channel_type):
    c, sent, called = client
    r = c.post(
        "/chatwoot/webhook",
        params={"token": TOKEN},
        json=_payload(attachments=[{"file_type": "image"}], content="aquí mi licencia", channel_type=channel_type),
    )
    assert r.json()["status"] == "media_guard"
    assert called["orchestrator"] == 0  # caption NO se procesa como fact en v1


def test_media_nested_message_attachments(client):
    """Robustez: attachments anidados en `message.attachments`."""
    c, sent, called = client
    payload = _payload(attachments=[], content="")
    payload["message"] = {"attachments": [{"file_type": "image", "data_url": "x"}]}
    r = c.post("/chatwoot/webhook", params={"token": TOKEN}, json=payload)
    assert r.json()["status"] == "media_guard"
    assert called["orchestrator"] == 0


@pytest.mark.parametrize("attachments", [
    [{"id": 555}],            # solo id (señal típica de adjunto)
    [{"message_id": 9}],       # solo message_id
    [{"extension": "pdf"}],    # solo extensión
    [{"foo": "bar"}],          # dict no vacío atípico → cuenta como media (robustez)
])
def test_media_atypical_attachment_dict(client, attachments):
    """Robustez: cualquier attachment dict no vacío activa media_guard, sin depender de file_type/data_url."""
    c, sent, called = client
    r = c.post("/chatwoot/webhook", params={"token": TOKEN}, json=_payload(attachments=attachments, content=""))
    assert r.json()["status"] == "media_guard"
    assert called["orchestrator"] == 0


def test_empty_attachment_dict_is_not_media(client):
    """Un attachment vacío {} no debe contar como media (evita falsos positivos)."""
    c, sent, called = client
    r = c.post("/chatwoot/webhook", params={"token": TOKEN}, json=_payload(attachments=[{}], content="tengo licencia tipo E"))
    assert r.json()["status"] != "media_guard"
    assert called["orchestrator"] == 1  # flujo normal


def test_text_only_passes(client):
    c, sent, called = client
    r = c.post(
        "/chatwoot/webhook",
        params={"token": TOKEN},
        json=_payload(attachments=[], content="tengo licencia tipo E"),
    )
    assert r.json()["status"] != "media_guard"
    assert called["orchestrator"] == 1  # flujo normal: el orquestador sí corre


def test_debounce_on_media_guard_does_not_enqueue(client, monkeypatch):
    monkeypatch.setenv("INBOUND_DEBOUNCE_ENABLED", "true")
    c, sent, called = client
    r = c.post(
        "/chatwoot/webhook",
        params={"token": TOKEN},
        json=_payload(attachments=[{"file_type": "image"}], content=""),
    )
    # media_guard corta ANTES del branch de debounce → responde y NO encola
    assert r.json()["status"] == "media_guard"
    assert called["orchestrator"] == 0
