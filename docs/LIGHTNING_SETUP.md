# Lightning payment modes

SatoshiBazaar selects one payment environment when the backend starts. The backend health endpoint and frontend header display the active mode. Payment mode is never chosen by a browser request.

## Alby NWC faucet sandbox (recommended integration demo)

The app uses the pinned async `aionwc==0.2.0` client on the backend. Its inspected API is `NWCClient(uri, timeout=...)`; async `get_info()`, `get_balance()`, `make_invoice(amount_msat, description=..., expiry=...)`, `pay_invoice(invoice)`, `lookup_invoice(payment_hash=...)`, and `list_transactions(limit=...)`. Balances and invoice amounts use integer millisatoshis. The current faucet UI can issue two root relay parameters (`relay=wss://relay.getalby.com&relay=wss://relay2.getalby.com`); older faucet documentation shows the `/v1` relay. Both formats are accepted by the backend and parsed by `aionwc`. No LNbits values are needed in this mode.

Create two separate faucet wallets at [faucet.nwc.dev](https://faucet.nwc.dev), then put the full connection strings in the backend `.env` only:

```dotenv
PAYMENT_MODE=alby_sandbox
ALBY_NWC_BUYER_URL=nostr+walletconnect://<buyer faucet URI>
ALBY_NWC_MERCHANT_URL=nostr+walletconnect://<merchant faucet URI>
```

Use the actual complete URI returned by the faucet (do not include the angle brackets in the value). Never put either URI in a `VITE_*` variable, browser storage, a request, or a transaction record. Restart the backend after setting them. The API checks the two wallet identities and required methods before creating or paying an invoice. It uses the merchant wallet to create an exact-amount invoice, asks the buyer for an explicit payment approval, and checks receipt independently with the merchant wallet. A relay timeout after a buyer payment attempt is marked unknown; refresh status to reconcile, and never retry that invoice payment.

### One faucet-to-faucet payment

1. Generate two independent wallets using the faucet's Create Wallet action (each starts with 10,000 test sats). Keep both connection strings private. Top up the buyer to at least the order amount; the rice example needs 240,000 sats. The faucet documents `POST https://faucet.nwc.dev/wallets/<buyer-alias>/topup?amount=300000` for this purpose.
2. Start SatoshiBazaar, register/sign in as a customer, then run the existing rice request: `I need 10 kg of rice in Dakar for a maximum total of 250,000 sats.` The agents find offers, Risk Guardian checks the offer, and you approve it.
3. Open **Lightning Wallet**. Confirm both faucet wallet aliases and the buyer test balance. Review the merchant invoice amount, BOLT11, and QR code, then press **Approve & pay**.
4. Wait for the merchant-side invoice lookup. The app records a completed transaction only after that lookup reports the matching payment hash and exact msat amount. The UI then displays **TEST PAYMENT — VERIFIED**.
5. Use the faucet's documented top-up action for additional test balance; never use real wallet credentials.

If no faucet credentials are configured, Alby mode reports a configuration error and does not fall back to Demo or LNbits. No actual faucet payment has been made in this environment; see [BUILD_PROGRESS.md](../BUILD_PROGRESS.md).

## Demo

`PAYMENT_MODE=demo` is the default. Invoices are local, non-payable references beginning with `DEMO-SIMULATED-NOT-PAYABLE`. A customer can explicitly simulate payment in the UI. Demo records use the `demo` mode and never contact a wallet or represent real funds.

## Testnet

Use a dedicated LNbits instance connected to a Bitcoin Lightning testnet backend, with a testnet wallet funded only with test coins. Set all three values in the backend `.env`:

```dotenv
PAYMENT_MODE=testnet
LNBITS_TESTNET_URL=https://your-testnet-lnbits.example
LNBITS_TESTNET_INVOICE_KEY=your-testnet-invoice-key
LNBITS_TESTNET_ADMIN_KEY=your-testnet-admin-key
```

LNbits must return `lntb` BOLT11 invoices with the exact requested amount. The backend checks the network and amount before displaying an invoice, then independently asks the same testnet LNbits instance for its status. Merchants submit a testnet invoice for the exact agreed amount; SatoshiBazaar sends it with that wallet's Admin key and only completes the transaction after a second provider status check confirms the outgoing payment.

## Live

Live mode requires a separate production LNbits instance, a production Lightning funding source, and dedicated production keys. Configure these only in the backend environment:

```dotenv
PAYMENT_MODE=live
LNBITS_LIVE_URL=https://your-production-lnbits.example
LNBITS_LIVE_INVOICE_KEY=your-live-invoice-key
LNBITS_LIVE_ADMIN_KEY=your-live-admin-key
```

Live invoices must be mainnet `lnbc` BOLT11 invoices with the exact amount. Live and testnet URLs and keys must be distinct. The invoice and Admin keys are never sent to the frontend.

## Safety and behavior

- Set exactly one `PAYMENT_MODE` value: `demo`, `testnet`, `live`, or `alby_sandbox`; restart the backend after changing it.
- Testnet/live require their own URL, invoice key, and Admin key. Missing configuration returns an error; it never falls back to Demo.
- Old, unclassified payment records are marked `legacy` during SQLite migration and are not relabeled as a current network payment.
- Incoming and outgoing status checks are read independently from LNbits. Pending or failed responses never count as completed.
- LNbits Admin keys are used only by the backend to initiate outgoing merchant payments. Keep every credential out of frontend `VITE_*` settings.
- A timeout while sending a payout is marked `UNKNOWN` and is blocked from automatic retry until reconciled against LNbits, preventing duplicate payouts.
- Alby sandbox sends the buyer payment directly to the merchant faucet wallet's invoice. It does not create a second merchant payout. A payment attempt is persisted before the relay request and cannot be automatically repeated; merchant verification is required before completion.
- Alby connection strings are accepted only when they match the faucet's documented relay and test-wallet identity format, and are never returned by the API.

The implementation uses LNbits' official [Payments API](https://docs.lnbits.com/api/core/payments) for invoice creation, outgoing payments, and payment status checks. A configured provider is not proof that a payment occurred; only a successful status returned and verified by LNbits is recorded as paid.

Alby/NWC references: [NWC protocol documentation](https://docs.nwc.dev/), [Alby NWC Faucet format and API](https://github.com/getAlby/nwc-faucet), [aionwc package API](https://pypi.org/project/aionwc/), and the [Alby JS SDK NWC client documentation](https://github.com/getAlby/js-sdk).
