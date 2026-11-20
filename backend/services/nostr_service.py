"""NIP-01 event validation and relay transport. Private signing stays in NIP-07."""
import hashlib
import json
import os
import secrets
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from websockets.sync.client import connect


class NostrService:
    def __init__(self):
        raw = os.getenv("NOSTR_RELAY_URLS", os.getenv("NOSTR_RELAY_URL", ""))
        self.relays = list(dict.fromkeys(url.strip().rstrip("/") for url in raw.split(",") if url.strip()))

    @staticmethod
    def canonical_event_data(event: dict) -> bytes:
        tags = event.get("tags")
        if not isinstance(tags, list) or any(not isinstance(tag, list) or any(not isinstance(value, str) for value in tag) for tag in tags):
            raise ValueError("Nostr event tags must be arrays of strings")
        fields = [0, event["pubkey"], event["created_at"], event["kind"], tags, event["content"]]
        return json.dumps(fields, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    @classmethod
    def calculate_event_id(cls, event: dict) -> str:
        return hashlib.sha256(cls.canonical_event_data(event)).hexdigest()

    @classmethod
    def validate_event(cls, event: dict) -> tuple[bool, str]:
        if not isinstance(event, dict):
            return False, "Event must be a JSON object"
        required = {"id", "pubkey", "created_at", "kind", "tags", "content", "sig"}
        if not required.issubset(event):
            return False, "Event is missing required NIP-01 fields"
        if not isinstance(event["pubkey"], str) or len(event["pubkey"]) != 64 or not _is_hex(event["pubkey"]):
            return False, "Event public key must be 32-byte lowercase hex"
        if not isinstance(event["id"], str) or len(event["id"]) != 64 or not _is_hex(event["id"]):
            return False, "Event id must be 32-byte lowercase hex"
        if not isinstance(event["sig"], str) or len(event["sig"]) != 128 or not _is_hex(event["sig"]):
            return False, "Event signature must be 64-byte lowercase hex"
        if type(event["created_at"]) is not int or event["created_at"] < 0:
            return False, "Event timestamp must be a non-negative integer"
        if type(event["kind"]) is not int or not 0 <= event["kind"] <= 65535:
            return False, "Event kind is outside the NIP-01 range"
        if not isinstance(event["content"], str):
            return False, "Event content must be a string"
        try:
            calculated = cls.calculate_event_id(event)
        except (ValueError, KeyError, TypeError):
            return False, "Event tags or canonical fields are invalid"
        if calculated != event["id"]:
            return False, "Event id does not match canonical event data"
        try:
            from coincurve import PublicKeyXOnly
            verified = PublicKeyXOnly(bytes.fromhex(event["pubkey"])).verify(bytes.fromhex(event["sig"]), bytes.fromhex(event["id"]))
        except (ImportError, ValueError, TypeError):
            return False, "Event Schnorr signature is invalid or secp256k1 is unavailable"
        return (True, "verified") if verified else (False, "Event Schnorr signature verification failed")

    @staticmethod
    def build_unsigned_listing(merchant: dict, product: dict) -> dict:
        now = int(time.time())
        content = json.dumps({
            "schema": "satoshibazaar/listing/v1",
            "merchant_name": merchant["name"],
            "product": product["name"],
            "category": product["category"],
            "price_sats": product["price_sats"],
            "quantity_available": product["quantity_available"],
            "location": merchant["location"],
        }, ensure_ascii=False, separators=(",", ":"))
        tags = [["d", f"satoshibazaar-product-{product['id']}"] , ["t", "satoshibazaar"], ["t", product["category"].lower()], ["location", merchant["location"]]]
        event = {"pubkey": "", "created_at": now, "kind": 30078, "tags": tags, "content": content}
        return event

    def _exchange(self, relay: str, payload: list, expected_event_id: str | None = None, timeout: float = 5.0):
        with connect(relay, open_timeout=timeout, close_timeout=1, max_size=1_000_000) as socket:
            socket.send(json.dumps(payload, separators=(",", ":")))
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                try:
                    response = json.loads(socket.recv(timeout=max(0.2, deadline - time.monotonic())))
                except TimeoutError:
                    break
                if not isinstance(response, list) or not response:
                    continue
                if response[0] == "OK" and expected_event_id and len(response) >= 4 and response[1] == expected_event_id:
                    return {"relay": relay, "acknowledged": bool(response[2]), "message": str(response[3])}
                if response[0] == "EOSE":
                    break
            return {"relay": relay, "acknowledged": False, "message": "Relay did not acknowledge the event before timeout"}

    def publish_event(self, event: dict) -> list[dict]:
        valid, reason = self.validate_event(event)
        if not valid:
            raise ValueError(reason)
        if not self.relays:
            return []
        results = []
        with ThreadPoolExecutor(max_workers=min(4, len(self.relays))) as pool:
            pending = {pool.submit(self._exchange, relay, ["EVENT", event], event["id"]): relay for relay in self.relays}
            for future in as_completed(pending, timeout=8):
                relay = pending[future]
                try:
                    results.append(future.result())
                except Exception as exc:
                    results.append({"relay": relay, "acknowledged": False, "message": type(exc).__name__})
        return results

    def fetch_events(self, limit: int = 50) -> tuple[list[dict], list[dict]]:
        if not self.relays:
            return [], []
        events, states = {}, []
        subscription = secrets.token_hex(8)
        with ThreadPoolExecutor(max_workers=min(4, len(self.relays))) as pool:
            pending = {pool.submit(self._fetch_relay, relay, subscription, limit): relay for relay in self.relays}
            for future in as_completed(pending, timeout=8):
                relay = pending[future]
                try:
                    relay_events = future.result()
                    states.append({"relay": relay, "connected": True, "events": len(relay_events)})
                    for event in relay_events:
                        valid, _ = self.validate_event(event)
                        if valid and _is_listing(event):
                            events[event["id"]] = event
                except Exception as exc:
                    states.append({"relay": relay, "connected": False, "error": type(exc).__name__})
        return list(events.values())[:limit], states

    def _fetch_relay(self, relay: str, subscription: str, limit: int):
        with connect(relay, open_timeout=3, close_timeout=1, max_size=1_000_000) as socket:
            socket.send(json.dumps(["REQ", subscription, {"kinds": [30078], "#t": ["satoshibazaar"], "limit": limit}], separators=(",", ":")))
            found = {}
            deadline = time.monotonic() + 4
            while time.monotonic() < deadline:
                try:
                    frame = json.loads(socket.recv(timeout=max(0.2, deadline - time.monotonic())))
                except TimeoutError:
                    break
                if isinstance(frame, list) and len(frame) >= 3 and frame[0] == "EVENT" and frame[1] == subscription:
                    event = frame[2]
                    if isinstance(event, dict):
                        found[event.get("id", secrets.token_hex(2))] = event
                elif isinstance(frame, list) and frame and frame[0] == "EOSE":
                    break
            socket.send(json.dumps(["CLOSE", subscription], separators=(",", ":")))
            return list(found.values())

    def status(self, probe: bool = False):
        if not probe or not self.relays:
            return {"configured": bool(self.relays), "relays": self.relays, "mode": "nostr" if self.relays else "local_only", "connectivity": "not_checked" if self.relays else "not_configured"}
        states = []
        with ThreadPoolExecutor(max_workers=min(4, len(self.relays))) as pool:
            pending = {pool.submit(self._probe, relay): relay for relay in self.relays}
            for future in as_completed(pending, timeout=6):
                relay = pending[future]
                try:
                    future.result()
                    states.append({"relay": relay, "connected": True})
                except Exception as exc:
                    states.append({"relay": relay, "connected": False, "error": type(exc).__name__})
        return {"configured": True, "relays": states, "mode": "nostr", "connectivity": "connected" if any(item["connected"] for item in states) else "unavailable"}

    @staticmethod
    def _probe(relay: str):
        with connect(relay, open_timeout=3, close_timeout=1, max_size=1_000_000):
            return True


def _is_hex(value: str) -> bool:
    try:
        return value == value.lower() and bytes.fromhex(value).hex() == value
    except ValueError:
        return False


def _is_listing(event: dict) -> bool:
    if event.get("kind") != 30078 or not any(len(tag) >= 2 and tag[0] == "t" and tag[1] == "satoshibazaar" for tag in event.get("tags", [])):
        return False
    try:
        content = json.loads(event["content"])
        return content.get("schema") == "satoshibazaar/listing/v1" and isinstance(content.get("price_sats"), int) and content["price_sats"] > 0
    except (json.JSONDecodeError, TypeError, KeyError):
        return False


nostr_service = NostrService()
