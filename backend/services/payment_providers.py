"""Mode-specific payment providers. Live providers fail closed on configuration/network mismatch."""
from dataclasses import dataclass
import os
import re
from urllib.parse import urlparse
import uuid

import httpx


PAYMENT_MODES = {"demo", "testnet", "live", "alby_sandbox"}


def active_payment_mode() -> str:
    mode = os.getenv("PAYMENT_MODE", "demo").strip().lower()
    if mode not in PAYMENT_MODES:
        raise RuntimeError("PAYMENT_MODE must be exactly demo, testnet, live, or alby_sandbox.")
    return mode


@dataclass(frozen=True)
class ProviderInvoice:
    payment_request: str
    payment_hash: str
    checking_id: str | None
    network: str
    expires_at: object | None = None


@dataclass(frozen=True)
class ProviderPayment:
    status: str
    amount_sats: int | None = None
    checking_id: str | None = None
    payment_hash: str | None = None


def bolt11_network(invoice: str) -> str:
    value = invoice.strip()
    if not value or value.lower() != value and value.upper() != value:
        raise ValueError("Lightning invoice must use a single case.")
    normalized = value.lower()
    if normalized.startswith("lnbcrt"):
        return "regtest"
    if normalized.startswith("lnbc"):
        return "mainnet"
    if normalized.startswith("lntb"):
        return "testnet"
    raise ValueError("Unsupported or invalid BOLT11 network prefix.")


def bolt11_amount_sats(invoice: str) -> int:
    value = invoice.strip().lower()
    bolt11_network(value)
    match = re.match(r"^ln(?:bc|tb|bcrt)([0-9]+[munp]?)?1", value)
    if not match:
        raise ValueError("Invalid BOLT11 human-readable prefix.")
    amount_text = match.group(1) or ""
    if not amount_text:
        raise ValueError("Amountless Lightning invoices are not accepted.")
    suffix = amount_text[-1] if amount_text[-1] in "munp" else ""
    digits = amount_text[:-1] if suffix else amount_text
    if not digits.isdigit():
        raise ValueError("Invalid BOLT11 amount.")
    numerator = int(digits) * {"": 100_000_000_000, "m": 100_000_000, "u": 100_000, "n": 100, "p": 1}[suffix]
    denominator = 10 if suffix == "p" else 1
    if numerator % (denominator * 1000):
        raise ValueError("BOLT11 amount must be an integer number of satoshis.")
    return numerator // (denominator * 1000)


class DemoPaymentProvider:
    mode = "demo"
    network = "simulated"
    configured = True

    def create_invoice(self, amount_sats: int, memo: str, extra: dict) -> ProviderInvoice:
        return ProviderInvoice(
            payment_request=f"DEMO-SIMULATED-NOT-PAYABLE-{uuid.uuid4().hex.upper()}",
            payment_hash=uuid.uuid4().hex,
            checking_id=None,
            network=self.network,
        )

    def check_payment(self, checking_id: str, expected_sats: int) -> ProviderPayment:
        raise RuntimeError("Demo payment status is stored locally, not checked with a network provider.")

    def pay_invoice(self, bolt11: str, expected_sats: int) -> ProviderPayment:
        raise RuntimeError("Demo mode never sends Lightning payments.")


class LNbitsPaymentProvider:
    def __init__(self, mode: str, base_url: str, invoice_key: str, admin_key: str, expected_network: str):
        self.mode = mode
        self.base_url = base_url.rstrip("/")
        self.invoice_key = invoice_key
        self.admin_key = admin_key
        self.network = expected_network
        parsed = urlparse(self.base_url) if self.base_url else None
        local_http = bool(parsed and parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"})
        if self.base_url and (not parsed or parsed.scheme not in {"https", "http"} or not parsed.hostname or (parsed.scheme != "https" and not local_http) or parsed.username or parsed.password):
            raise RuntimeError(f"Invalid LNbits URL for {mode}: use HTTPS (HTTP is allowed only for localhost).")

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.invoice_key and self.admin_key)

    def _require_configured(self):
        if not self.configured:
            raise RuntimeError(f"{self.mode} requires its own LNbits URL, invoice key, and Admin key; no fallback is allowed.")

    def _check_invoice_network(self, bolt11: str, amount_sats: int):
        network = bolt11_network(bolt11)
        if network != self.network:
            raise RuntimeError(f"LNbits returned a {network} invoice while PAYMENT_MODE={self.mode} requires {self.network}.")
        try:
            parsed_amount = bolt11_amount_sats(bolt11)
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        if parsed_amount != amount_sats:
            raise RuntimeError("LNbits returned an invoice with the wrong amount.")

    def create_invoice(self, amount_sats: int, memo: str, extra: dict) -> ProviderInvoice:
        self._require_configured()
        with httpx.Client(timeout=15) as client:
            response = client.post(
                f"{self.base_url}/api/v1/payments",
                headers={"X-Api-Key": self.invoice_key},
                json={"out": False, "amount": amount_sats, "memo": memo, "expiry": 3600, "extra": extra},
            )
            response.raise_for_status()
            data = response.json()
        bolt11 = data.get("payment_request")
        payment_hash = data.get("payment_hash")
        checking_id = data.get("checking_id")
        if not bolt11 or not payment_hash or not checking_id:
            raise RuntimeError("LNbits returned an incomplete invoice response.")
        self._check_invoice_network(bolt11, amount_sats)
        return ProviderInvoice(bolt11, payment_hash, checking_id, self.network)

    def check_payment(self, checking_id: str, expected_sats: int) -> ProviderPayment:
        self._require_configured()
        with httpx.Client(timeout=15) as client:
            response = client.get(f"{self.base_url}/api/v1/payments/{checking_id}", headers={"X-Api-Key": self.invoice_key})
            response.raise_for_status()
            data = response.json()
        details = data.get("details") or {}
        if details.get("checking_id") != checking_id:
            return ProviderPayment("FAILED", checking_id=details.get("checking_id"))
        if data.get("paid"):
            if abs(int(details.get("amount", 0))) != expected_sats or details.get("status", "success").lower() != "success":
                return ProviderPayment("FAILED", amount_sats=abs(int(details.get("amount", 0))), checking_id=checking_id)
            return ProviderPayment("PAID", expected_sats, checking_id, details.get("payment_hash"))
        if details.get("status", "").lower() == "failed":
            return ProviderPayment("FAILED", checking_id=checking_id)
        return ProviderPayment("PENDING", checking_id=checking_id)

    def pay_invoice(self, bolt11: str, expected_sats: int) -> ProviderPayment:
        self._require_configured()
        network = bolt11_network(bolt11)
        if network != self.network:
            raise RuntimeError(f"Merchant invoice is {network}; this provider is configured for {self.network}.")
        if bolt11_amount_sats(bolt11) != expected_sats:
            raise RuntimeError("Merchant invoice amount does not equal the agreed payout amount.")
        # LNbits validates and pays the invoice; this mode-specific key is never returned to clients.
        with httpx.Client(timeout=30) as client:
            response = client.post(
                f"{self.base_url}/api/v1/payments",
                headers={"X-Api-Key": self.admin_key},
                json={"out": True, "bolt11": bolt11},
            )
            response.raise_for_status()
            data = response.json()
        if not data.get("checking_id") or not data.get("payment_hash"):
            raise RuntimeError("LNbits returned an incomplete outgoing payment response.")
        return ProviderPayment("PENDING", expected_sats, data["checking_id"], data["payment_hash"])


class TestnetPaymentProvider(LNbitsPaymentProvider):
    def __init__(self):
        super().__init__("testnet", os.getenv("LNBITS_TESTNET_URL", ""), os.getenv("LNBITS_TESTNET_INVOICE_KEY", ""), os.getenv("LNBITS_TESTNET_ADMIN_KEY", ""), "testnet")


class LivePaymentProvider(LNbitsPaymentProvider):
    def __init__(self):
        super().__init__("live", os.getenv("LNBITS_LIVE_URL", ""), os.getenv("LNBITS_LIVE_INVOICE_KEY", ""), os.getenv("LNBITS_LIVE_ADMIN_KEY", ""), "mainnet")


def build_provider(mode: str | None = None):
    selected = mode or active_payment_mode()
    if selected == "demo":
        return DemoPaymentProvider()
    if selected == "alby_sandbox":
        from services.alby_sandbox import AlbySandboxPaymentProvider
        return AlbySandboxPaymentProvider()
    test_url = os.getenv("LNBITS_TESTNET_URL", "").rstrip("/").lower()
    live_url = os.getenv("LNBITS_LIVE_URL", "").rstrip("/").lower()
    test_keys = {os.getenv("LNBITS_TESTNET_INVOICE_KEY", ""), os.getenv("LNBITS_TESTNET_ADMIN_KEY", "")} - {""}
    live_keys = {os.getenv("LNBITS_LIVE_INVOICE_KEY", ""), os.getenv("LNBITS_LIVE_ADMIN_KEY", "")} - {""}
    if test_url and live_url and test_url == live_url:
        raise RuntimeError("Testnet and live LNbits URLs must be distinct to prevent network mixing.")
    if test_keys & live_keys:
        raise RuntimeError("Testnet and live LNbits credentials must be distinct to prevent wallet mixing.")
    if selected == "testnet":
        return TestnetPaymentProvider()
    if selected == "live":
        return LivePaymentProvider()
    raise RuntimeError("PAYMENT_MODE must be exactly demo, testnet, live, or alby_sandbox.")
