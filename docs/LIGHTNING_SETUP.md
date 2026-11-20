# Lightning payment modes

SatoshiBazaar selects one payment environment when the backend starts. The backend health endpoint and frontend header display the active mode. Payment mode is never chosen by a browser request.

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

- Set exactly one `PAYMENT_MODE` value: `demo`, `testnet`, or `live`; restart the backend after changing it.
- Testnet/live require their own URL, invoice key, and Admin key. Missing configuration returns an error; it never falls back to Demo.
- Old, unclassified payment records are marked `legacy` during SQLite migration and are not relabeled as a current network payment.
- Incoming and outgoing status checks are read independently from LNbits. Pending or failed responses never count as completed.
- LNbits Admin keys are used only by the backend to initiate outgoing merchant payments. Keep every credential out of frontend `VITE_*` settings.
- A timeout while sending a payout is marked `UNKNOWN` and is blocked from automatic retry until reconciled against LNbits, preventing duplicate payouts.

The implementation uses LNbits' official [Payments API](https://docs.lnbits.com/api/core/payments) for invoice creation, outgoing payments, and payment status checks. A configured provider is not proof that a payment occurred; only a successful status returned and verified by LNbits is recorded as paid.
