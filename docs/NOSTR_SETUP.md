# Nostr setup

1. Set `NOSTR_RELAY_URLS` to a comma-separated list of `wss://` relay URLs in the backend environment.
2. Create a merchant account and profile, then create a local product.
3. Install/use a browser NIP-07 extension such as Alby or nos2x. The private key remains in the extension.
4. In Merchant Portal, choose **Sign & publish**. The browser signs the unsigned listing; the API checks the signature, canonical event ID, content against saved inventory, and merchant ownership.
5. Publication is shown only after at least one relay sends a positive `OK` acknowledgement. Relay errors are reported per relay.
6. In Marketplace, choose **Discover Nostr** to retrieve and cryptographically verify matching kind 30078 events.

The app uses kind 30078 with `d` and `t=satoshibazaar` tags and JSON content schema `satoshibazaar/listing/v1`. Relay listings are external claims: their stock is not reserved locally and merchant identity is not automatically trusted. Relay behavior has not been live-tested in this environment.
