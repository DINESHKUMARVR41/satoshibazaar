"""Alby Developer Sandbox provider backed by two NIP-47 test wallets."""
import asyncio
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

from services.payment_providers import ProviderInvoice, ProviderPayment


class AlbySandboxError(RuntimeError):
    def __init__(self, code: str, message: str, *, ambiguous: bool = False):
        super().__init__(message)
        self.code = code
        self.ambiguous = ambiguous


def _valid_faucet_uri(uri: str) -> bool:
    """Accept the faucet's documented dummy-wallet identity shape only."""
    try:
        parsed = urlparse(uri)
        params = parse_qs(parsed.query, strict_parsing=True)
        relay = urlparse(params["relay"][0])
        secret = params["secret"][0]
        lud16 = params.get("lud16", [""])[0]
        return bool(
            parsed.scheme == "nostr+walletconnect"
            and parsed.netloc
            and re.fullmatch(r"[0-9a-fA-F]{64}", parsed.netloc)
            and relay.scheme == "wss"
            and relay.hostname == "relay.getalby.com"
            and relay.path == "/v1"
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
    timeout_seconds = 25

    def __init__(self, client_factory=None):
        import os

        self.buyer_uri = os.getenv("ALBY_NWC_BUYER_URL", "").strip()
        self.merchant_uri = os.getenv("ALBY_NWC_MERCHANT_URL", "").strip()
        self.client_factory = client_factory

    @property
    def configured(self):
        return bool(
            self.buyer_uri
            and self.merchant_uri
            and _valid_faucet_uri(self.buyer_uri)
            and _valid_faucet_uri(self.merchant_uri)
            and self.buyer_uri != self.merchant_uri
            and urlparse(self.buyer_uri).netloc != urlparse(self.merchant_uri).netloc
        )

    def require_configured(self):
        if not self.buyer_uri or not self.merchant_uri:
            raise AlbySandboxError("MISSING_CREDENTIALS", "Alby sandbox needs both buyer and merchant test-wallet connection URLs.")
        if not self.configured:
            raise AlbySandboxError(
                "INVALID_SANDBOX_WALLETS",
                "Alby sandbox accepts distinct faucet-issued test wallets only. Check both NWC URLs; production wallet connections are not accepted.",
            )

    def _client(self, wallet: str):
        self.require_configured()
        uri = self.buyer_uri if wallet == "buyer" else self.merchant_uri
        factory = self.client_factory
        if factory is None:
            try:
                from aionwc import NWCClient
            except ImportError as exc:
                raise AlbySandboxError("DEPENDENCY_MISSING", "Install the pinned aionwc dependency to use Alby sandbox mode.") from exc
            factory = NWCClient
        return factory(uri, timeout=self.timeout_seconds)

    async def _call(self, awaitable):
        try:
            return await asyncio.wait_for(awaitable, timeout=self.timeout_seconds + 2)
        except asyncio.TimeoutError as exc:
            raise AlbySandboxError("TIMEOUT", "Alby sandbox wallet request timed out.", ambiguous=True) from exc
        except Exception as exc:
            try:
                from aionwc import NWCRelayError, NWCWalletError
                if isinstance(exc, NWCWalletError):
                    code = str(exc.code).upper()
                    messages = {
                        "INSUFFICIENT_BALANCE": "Alby sandbox buyer wallet has insufficient test balance.",
                        "PAYMENT_FAILED": "Alby sandbox rejected the test payment.",
                        "NOT_FOUND": "The sandbox wallet could not find that invoice.",
                    }
                    raise AlbySandboxError(code, messages.get(code, "Alby sandbox wallet rejected the request.")) from exc
                if isinstance(exc, NWCRelayError):
                    raise AlbySandboxError("RELAY_UNAVAILABLE", "Alby sandbox relay did not return a response.", ambiguous=bool(exc.request_id)) from exc
            except ImportError:
                pass
            if isinstance(exc, AlbySandboxError):
                raise
            # Do not pass arbitrary client errors (which can contain wallet URIs) to logs or API responses.
            raise AlbySandboxError("WALLET_ERROR", "Alby sandbox wallet request failed.") from exc

    async def status(self):
        self.require_configured()
        buyer_client, merchant_client = self._client("buyer"), self._client("merchant")
        buyer, merchant = await asyncio.gather(
            self._call(buyer_client.get_info()),
            self._call(merchant_client.get_info()),
        )
        buyer_alias = str(buyer.get("alias") or "")
        merchant_alias = str(merchant.get("alias") or "")
        # Faucet documentation names dummy wallets with their nwc...@getalby.com identity.
        if buyer_alias and not buyer_alias.lower().startswith("nwc"):
            raise AlbySandboxError("NOT_A_SANDBOX_WALLET", "Buyer wallet identity does not match the Alby faucet test-wallet format.")
        if merchant_alias and not merchant_alias.lower().startswith("nwc"):
            raise AlbySandboxError("NOT_A_SANDBOX_WALLET", "Merchant wallet identity does not match the Alby faucet test-wallet format.")
        buyer_methods = set(buyer.get("methods") or [])
        merchant_methods = set(merchant.get("methods") or [])
        return {
            "connected": True,
            "mode": self.mode,
            "label": "TEST PAYMENT",
            "network": self.network,
            "buyer_wallet": {"alias": buyer_alias or "Alby test wallet", "methods": sorted(buyer_methods)},
            "merchant_wallet": {"alias": merchant_alias or "Alby test wallet", "methods": sorted(merchant_methods)},
            "missing_buyer_methods": sorted({"get_balance", "pay_invoice", "lookup_invoice", "list_transactions"} - buyer_methods),
            "missing_merchant_methods": sorted({"make_invoice", "lookup_invoice", "list_transactions"} - merchant_methods),
        }

    async def balance(self, wallet: str = "buyer"):
        client = self._client(wallet)
        balance_msat = await self._call(client.get_balance())
        if type(balance_msat) is not int or balance_msat < 0:
            raise AlbySandboxError("INVALID_BALANCE", "Alby sandbox returned an invalid wallet balance.")
        return {"balance_msat": balance_msat, "balance_sats": balance_msat / 1000, "wallet": wallet, "environment": "sandbox"}

    async def create_invoice(self, amount_sats: int, description: str, expiry: int = 3600):
        if type(amount_sats) is not int or amount_sats <= 0:
            raise AlbySandboxError("INVALID_AMOUNT", "Invoice amount must be a positive whole number of sats.")
        expected_msat = amount_sats * 1000
        result = await self._call(self._client("merchant").make_invoice(
            expected_msat, description=description[:256], expiry=expiry,
        ))
        invoice = result.get("invoice")
        payment_hash = result.get("payment_hash")
        returned_amount = result.get("amount")
        if not invoice or not payment_hash or type(returned_amount) is not int or returned_amount != expected_msat:
            raise AlbySandboxError("INVALID_INVOICE_RESPONSE", "Alby sandbox returned an incomplete or wrong-amount invoice.")
        expiry_time = result.get("expires_at")
        expires_at = datetime.fromtimestamp(expiry_time, timezone.utc) if isinstance(expiry_time, (int, float)) else None
        created_time = result.get("created_at")
        created_at = datetime.fromtimestamp(created_time, timezone.utc) if isinstance(created_time, (int, float)) else datetime.now(timezone.utc)
        return ProviderInvoice(invoice, payment_hash, payment_hash, self.network, expires_at), created_at

    async def verify_invoice(self, payment_hash: str, expected_sats: int, invoice: str | None = None):
        result = await self._call(self._client("merchant").lookup_invoice(payment_hash=payment_hash))
        returned_hash = result.get("payment_hash")
        amount_msat = result.get("amount")
        if returned_hash != payment_hash or type(amount_msat) is not int or amount_msat != expected_sats * 1000:
            return ProviderPayment("FAILED", checking_id=returned_hash, payment_hash=returned_hash)
        if invoice and result.get("invoice") and result["invoice"].lower() != invoice.lower():
            return ProviderPayment("FAILED", checking_id=payment_hash, payment_hash=returned_hash)
        expiry_time = result.get("expires_at")
        if not result.get("preimage") and not result.get("settled_at"):
            if isinstance(expiry_time, (int, float)) and expiry_time <= datetime.now(timezone.utc).timestamp():
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
            await self._call(self._client("buyer").pay_invoice(invoice))
        except AlbySandboxError as exc:
            if exc.ambiguous:
                # Never retry an NWC payment after a relay timeout; reconcile on merchant wallet first.
                try:
                    reconciled = await self.verify_invoice(payment_hash, expected_sats, invoice)
                    if reconciled.status == "PAID":
                        return reconciled
                except AlbySandboxError:
                    pass
                raise AlbySandboxError("PAYMENT_UNKNOWN", "Sandbox payment outcome is unknown. Check invoice status before any retry.", ambiguous=True) from exc
            raise
        return await self.verify_invoice(payment_hash, expected_sats, invoice)

    async def transactions(self, wallet: str = "buyer", limit: int = 25):
        if limit < 1 or limit > 100:
            raise AlbySandboxError("INVALID_LIMIT", "Transaction limit must be between 1 and 100.")
        client = self._client(wallet)
        result = await self._call(client.list_transactions(limit=limit))
        output = []
        for item in result:
            amount_msat = item.get("amount")
            if type(amount_msat) is not int:
                continue
            output.append({
                "type": item.get("type"),
                "payment_hash": item.get("payment_hash"),
                "amount_msat": amount_msat,
                "amount_sats": amount_msat / 1000,
                "created_at": item.get("created_at"),
                "settled_at": item.get("settled_at"),
                "status": "PAID" if item.get("preimage") or item.get("settled_at") else "PENDING",
                "mode": self.mode,
                "label": "TEST PAYMENT",
            })
        return output
