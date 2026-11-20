"""Async Alby NWC faucet wallet provider.

The aionwc client owns a WebSocket connection per operation. Its public API uses
integer millisatoshis and returns NIP-47 result dictionaries.
"""
import asyncio
import os
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

from services.payment_providers import ProviderInvoice, ProviderPayment

_runtime_wallet_uris: tuple[str, str] | None = None


def set_runtime_wallet_uris(buyer_uri: str, merchant_uri: str) -> None:
    """Set process-local faucet credentials supplied through the local setup UI."""
    global _runtime_wallet_uris
    _runtime_wallet_uris = (buyer_uri.strip(), merchant_uri.strip())


class AlbySandboxError(RuntimeError):
    def __init__(self, code: str, message: str, *, ambiguous: bool = False):
        super().__init__(message)
        self.code = code
        self.ambiguous = ambiguous


def _valid_faucet_uri(uri: str) -> bool:
    """Recognize the faucet's published nostr+walletconnect URI shape."""
    try:
        parsed = urlparse(uri)
        params = parse_qs(parsed.query, strict_parsing=True)
        relay_values = params["relay"]
        relays = [urlparse(value) for value in relay_values]
        secret_values = params["secret"]
        secret = secret_values[0]
        lud16 = params.get("lud16", [""])[0]
        return bool(
            parsed.scheme == "nostr+walletconnect"
            and re.fullmatch(r"[0-9a-fA-F]{64}", parsed.netloc)
            and parsed.path in {"", "/"}
            and not parsed.fragment
            and len(secret_values) == 1
            and relays
            and all(
                relay.scheme == "wss"
                and relay.hostname in {"relay.getalby.com", "relay2.getalby.com"}
                and relay.path in {"", "/", "/v1"}
                and relay.username is None
                and relay.password is None
                and not relay.fragment
                for relay in relays
            )
            and re.fullmatch(r"[0-9a-fA-F]{64}", secret)
            and re.fullmatch(r"nwc[0-9]+@getalby\.com", lud16, re.IGNORECASE)
        )
    except (KeyError, IndexError, ValueError):
        return False


class AlbySandboxPaymentProvider:
    mode = "alby_sandbox"
    network = "sandbox"
    provider_name = "alby_nwc_sandbox"
    environment = "sandbox"
    timeout_seconds = 32
    required_buyer_methods = {"get_info", "get_balance", "pay_invoice", "lookup_invoice", "list_transactions"}
    required_merchant_methods = {"get_info", "get_balance", "make_invoice", "lookup_invoice", "list_transactions"}

    def __init__(self, client_factory=None):
        buyer_uri, merchant_uri = _runtime_wallet_uris or (
            os.getenv("ALBY_NWC_BUYER_URL", ""),
            os.getenv("ALBY_NWC_MERCHANT_URL", ""),
        )
        self.buyer_uri = buyer_uri.strip()
        self.merchant_uri = merchant_uri.strip()
        self.client_factory = client_factory
        self.buyer_alias = None
        self.merchant_alias = None

    @property
    def configured(self):
        return bool(
            self.buyer_uri and self.merchant_uri
            and _valid_faucet_uri(self.buyer_uri)
            and _valid_faucet_uri(self.merchant_uri)
            and self.buyer_uri != self.merchant_uri
            and urlparse(self.buyer_uri).netloc != urlparse(self.merchant_uri).netloc
        )

    def require_configured(self):
        if not self.buyer_uri or not self.merchant_uri:
            raise AlbySandboxError("MISSING_CREDENTIALS", "Alby sandbox needs both buyer and merchant faucet test-wallet URLs.")
        if not self.configured:
            raise AlbySandboxError("INVALID_SANDBOX_WALLETS", "Alby sandbox accepts two distinct Alby faucet test wallets only.")

    def _client(self, wallet: str):
        self.require_configured()
        if wallet not in {"buyer", "merchant"}:
            raise AlbySandboxError("INVALID_WALLET", "Wallet must be buyer or merchant.")
        factory = self.client_factory
        if factory is None:
            try:
                from aionwc import NWCClient
            except ImportError as exc:
                raise AlbySandboxError("DEPENDENCY_MISSING", "Install the pinned aionwc dependency to use Alby sandbox mode.") from exc
            factory = NWCClient
        # NWCClient(uri) is the documented constructor; the library applies its own request deadline.
        return factory(self.buyer_uri if wallet == "buyer" else self.merchant_uri, timeout=30.0)

    async def _call(self, awaitable, *, ambiguous=False):
        try:
            return await asyncio.wait_for(awaitable, timeout=self.timeout_seconds)
        except asyncio.TimeoutError as exc:
            raise AlbySandboxError("TIMEOUT", "Alby sandbox relay timed out; check invoice status before retrying.", ambiguous=ambiguous) from exc
        except AlbySandboxError:
            raise
        except Exception as exc:
            from aionwc import NWCRelayError, NWCTimeoutError, NWCWalletError
            if isinstance(exc, NWCWalletError):
                code = str(exc.code).upper()
                messages = {
                    "INSUFFICIENT_BALANCE": "Alby sandbox buyer wallet has insufficient test balance.",
                    "PAYMENT_FAILED": "Alby sandbox wallet rejected the test payment.",
                    "NOT_FOUND": "The sandbox wallet could not find that invoice.",
                    "EXPIRED": "The merchant sandbox invoice has expired.",
                }
                raise AlbySandboxError(code, messages.get(code, "Alby sandbox wallet rejected the request.")) from exc
            if isinstance(exc, (NWCTimeoutError, NWCRelayError)):
                request_id = getattr(exc, "request_id", None)
                raise AlbySandboxError(
                    "PAYMENT_UNKNOWN" if ambiguous and request_id else "RELAY_UNAVAILABLE",
                    "Sandbox payment result is unknown; check merchant invoice status before retrying." if ambiguous and request_id else "Alby sandbox relay did not return a wallet response.",
                    ambiguous=bool(ambiguous and request_id),
                ) from exc
            # Never return or log exception text: some transports include URI parameters.
            raise AlbySandboxError("WALLET_ERROR", "Alby sandbox wallet request failed. Check wallet connectivity and permissions.") from exc

    async def status(self):
        self.require_configured()
        buyer_client, merchant_client = self._client("buyer"), self._client("merchant")
        try:
            # The faucet relays may drop one of two simultaneous NWC requests.
            # Check each wallet on its own connection to avoid intermittent status
            # failures immediately before invoice creation.
            buyer = await self._call(buyer_client.get_info())
            merchant = await self._call(merchant_client.get_info())
        except AlbySandboxError as exc:
            raise AlbySandboxError("CONNECTION_FAILED", f"Could not validate both Alby faucet wallets: {exc}") from exc
        if not isinstance(buyer, dict) or not isinstance(merchant, dict):
            raise AlbySandboxError("INVALID_WALLET_INFO", "Alby sandbox returned invalid wallet information.")
        # Alby Hub may report the generic alias "NWC" for every connection. For faucet
        # sub-wallets the unique wallet identity is the faucet-issued lud16 in each URI.
        buyer_expected = parse_qs(urlparse(self.buyer_uri).query).get("lud16", [""])[0].split("@", 1)[0]
        merchant_expected = parse_qs(urlparse(self.merchant_uri).query).get("lud16", [""])[0].split("@", 1)[0]
        if (not re.fullmatch(r"nwc[0-9]+", buyer_expected, re.IGNORECASE)
                or not re.fullmatch(r"nwc[0-9]+", merchant_expected, re.IGNORECASE)):
            raise AlbySandboxError("NOT_A_SANDBOX_WALLET", "Wallet identity is not an Alby faucet test-wallet identity.")
        if buyer_expected.lower() == merchant_expected.lower():
            raise AlbySandboxError("WALLET_SEPARATION_FAILED", "Buyer and merchant must be different faucet wallets.")
        buyer_methods, merchant_methods = set(buyer.get("methods") or []), set(merchant.get("methods") or [])
        missing_buyer = sorted(self.required_buyer_methods - buyer_methods)
        missing_merchant = sorted(self.required_merchant_methods - merchant_methods)
        if missing_buyer or missing_merchant:
            raise AlbySandboxError("UNSUPPORTED_METHODS", "Alby faucet wallet permissions are missing required NWC methods.")
        self.buyer_alias, self.merchant_alias = buyer_expected, merchant_expected
        return {
            "connected": True, "mode": self.mode, "network": self.network,
            "label": "ALBY SANDBOX", "buyer_wallet": {"alias": buyer_expected},
            "merchant_wallet": {"alias": merchant_expected},
        }

    async def balance(self, wallet="buyer"):
        client = self._client(wallet)
        result = await self._call(client.get_balance())
        if type(result) is not int or result < 0:
            raise AlbySandboxError("INVALID_BALANCE", "Alby sandbox returned an invalid balance.")
        return {"balance_msat": result, "balance_sats": result / 1000, "wallet": wallet, "environment": "sandbox"}

    async def create_invoice(self, amount_sats: int, description: str, expiry: int = 3600):
        if type(amount_sats) is not int or amount_sats <= 0:
            raise AlbySandboxError("INVALID_AMOUNT", "Invoice amount must be a positive whole number of sats.")
        result = await self._call(self._client("merchant").make_invoice(amount_sats * 1000, description=description[:256], expiry=expiry))
        if not isinstance(result, dict):
            raise AlbySandboxError("INVALID_INVOICE_RESPONSE", "Alby sandbox returned an invalid invoice response.")
        bolt11, payment_hash = result.get("invoice"), result.get("payment_hash")
        returned_amount = result.get("amount")
        expires = result.get("expires_at")
        if (not isinstance(bolt11, str) or not bolt11.lower().startswith("ln")
                or not isinstance(payment_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", payment_hash)
                or type(returned_amount) is not int or returned_amount != amount_sats * 1000
                or not isinstance(expires, (int, float)) or expires <= datetime.now(timezone.utc).timestamp()):
            raise AlbySandboxError("INVALID_INVOICE_RESPONSE", "Alby sandbox returned an incomplete or wrong-amount invoice.")
        created = result.get("created_at")
        expires_at = datetime.fromtimestamp(expires, timezone.utc) if isinstance(expires, (int, float)) else None
        created_at = datetime.fromtimestamp(created, timezone.utc) if isinstance(created, (int, float)) else datetime.now(timezone.utc)
        return ProviderInvoice(bolt11, payment_hash, payment_hash, self.network, expires_at), created_at

    async def verify_invoice(self, payment_hash: str, expected_sats: int, invoice: str | None = None):
        result = await self._call(self._client("merchant").lookup_invoice(payment_hash=payment_hash))
        if not isinstance(result, dict):
            return ProviderPayment("PENDING", expected_sats, payment_hash, payment_hash)
        returned_hash = result.get("payment_hash")
        amount_msat = result.get("amount")
        if returned_hash != payment_hash or type(amount_msat) is not int or amount_msat != expected_sats * 1000:
            return ProviderPayment("FAILED", checking_id=returned_hash, payment_hash=returned_hash)
        if invoice and result.get("invoice") and result["invoice"].lower() != invoice.lower():
            return ProviderPayment("FAILED", checking_id=payment_hash, payment_hash=returned_hash)
        settled = bool(result.get("preimage") or result.get("settled_at"))
        expires = result.get("expires_at")
        if not settled:
            if isinstance(expires, (int, float)) and expires <= datetime.now(timezone.utc).timestamp():
                return ProviderPayment("EXPIRED", expected_sats, payment_hash, returned_hash)
            return ProviderPayment("PENDING", expected_sats, payment_hash, returned_hash)
        if result.get("type") not in (None, "incoming"):
            return ProviderPayment("FAILED", checking_id=payment_hash, payment_hash=returned_hash)
        return ProviderPayment("PAID", expected_sats, payment_hash, returned_hash)

    async def pay_invoice(self, invoice: str, payment_hash: str, expected_sats: int):
        before = await self.verify_invoice(payment_hash, expected_sats, invoice)
        if before.status == "PAID":
            return before
        if before.status == "FAILED":
            raise AlbySandboxError("INVALID_INVOICE", "Merchant sandbox invoice failed identity or amount validation.")
        if before.status == "EXPIRED":
            raise AlbySandboxError("EXPIRED_INVOICE", "Merchant sandbox invoice has expired.")
        try:
            await self._call(self._client("buyer").pay_invoice(invoice), ambiguous=True)
        except AlbySandboxError as exc:
            if exc.ambiguous:
                try:
                    reconciled = await self.verify_invoice(payment_hash, expected_sats, invoice)
                    if reconciled.status == "PAID":
                        return reconciled
                except AlbySandboxError:
                    pass
                raise AlbySandboxError("PAYMENT_UNKNOWN", "Sandbox payment result is unknown. Refresh merchant verification; do not retry this payment.", ambiguous=True) from exc
            raise
        try:
            return await self.verify_invoice(payment_hash, expected_sats, invoice)
        except AlbySandboxError as exc:
            # The buyer may have paid even when the independent merchant lookup failed.
            raise AlbySandboxError("PAYMENT_UNKNOWN", "Buyer wallet accepted the request, but merchant verification is unavailable. Refresh status; do not retry.", ambiguous=True) from exc

    async def transactions(self, wallet="buyer", limit=25):
        if limit < 1 or limit > 100:
            raise AlbySandboxError("INVALID_LIMIT", "Transaction limit must be between 1 and 100.")
        client = self._client(wallet)
        items = await self._call(client.list_transactions(limit=limit))
        if not isinstance(items, list):
            raise AlbySandboxError("INVALID_TRANSACTIONS", "Alby sandbox returned invalid transaction history.")
        output = []
        for item in items:
            if not isinstance(item, dict) or type(item.get("amount")) is not int:
                continue
            msat = item["amount"]
            output.append({"type": item.get("type"), "payment_hash": item.get("payment_hash"),
                           "amount_msat": msat, "amount_sats": msat / 1000,
                           "created_at": item.get("created_at"), "settled_at": item.get("settled_at"),
                           "status": "PAID" if item.get("preimage") or item.get("settled_at") else "PENDING",
                           "mode": self.mode, "label": "TEST PAYMENT"})
        return output
