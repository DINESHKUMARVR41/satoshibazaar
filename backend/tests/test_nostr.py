import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from coincurve import PrivateKey  # noqa: E402
from services.nostr_service import NostrService  # noqa: E402


def signed_listing():
    key = PrivateKey()
    pubkey = key.public_key_xonly.format().hex()
    event = {
        "pubkey": pubkey,
        "created_at": 1700000000,
        "kind": 30078,
        "tags": [["d", "satoshibazaar-product-1"], ["t", "satoshibazaar"], ["location", "Dakar"]],
        "content": '{"schema":"satoshibazaar/listing/v1","merchant_name":"Test","product":"Rice","category":"Grains","price_sats":100,"quantity_available":5,"location":"Dakar"}',
    }
    event["id"] = NostrService.calculate_event_id(event)
    event["sig"] = key.sign_schnorr(bytes.fromhex(event["id"])).hex()
    return event


def test_nip01_event_id_and_schnorr_signature_verify():
    event = signed_listing()
    assert NostrService.validate_event(event) == (True, "verified")


def test_nip01_rejects_tampered_id_content_and_signature():
    event = signed_listing()
    bad_id = {**event, "id": "0" * 64}
    assert not NostrService.validate_event(bad_id)[0]
    bad_content = {**event, "content": event["content"] + " "}
    assert not NostrService.validate_event(bad_content)[0]
    bad_sig = {**event, "sig": "0" * 128}
    assert not NostrService.validate_event(bad_sig)[0]


def test_relay_failure_does_not_hide_local_only_status(monkeypatch):
    monkeypatch.delenv("NOSTR_RELAY_URLS", raising=False)
    monkeypatch.delenv("NOSTR_RELAY_URL", raising=False)
    service = NostrService()
    events, relays = service.fetch_events()
    assert events == []
    assert relays == []
    assert service.status()["connectivity"] == "not_configured"


def test_invalid_relay_does_not_break_local_discovery(monkeypatch):
    monkeypatch.setenv("NOSTR_RELAY_URLS", "wss://relay.invalid")
    monkeypatch.delenv("NOSTR_RELAY_URL", raising=False)
    service = NostrService()
    monkeypatch.setattr(service, "_fetch_relay", lambda *_args: (_ for _ in ()).throw(TimeoutError()))
    events, relays = service.fetch_events()
    assert events == []
    assert relays == [{"relay": "wss://relay.invalid", "connected": False, "error": "TimeoutError"}]


def test_publish_reports_only_relay_acknowledgements(monkeypatch):
    service = NostrService()
    service.relays = ["wss://relay.one", "wss://relay.two"]
    monkeypatch.setattr(service, "_exchange", lambda relay, *_args: {"relay": relay, "acknowledged": relay.endswith("one"), "message": "accepted" if relay.endswith("one") else "blocked: policy"})
    acknowledgements = service.publish_event(signed_listing())
    assert sum(bool(item["acknowledged"]) for item in acknowledgements) == 1
    assert {item["relay"] for item in acknowledgements} == set(service.relays)
