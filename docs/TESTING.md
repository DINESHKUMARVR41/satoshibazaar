# Testing

Run backend tests from `backend`:

```powershell
python -m pytest tests -q
```

Run frontend production build from `frontend`:

```powershell
npm.cmd run build
```

Backend tests cover bcrypt/JWT authentication, role enforcement, NIP-01 event ID and Schnorr signature verification, mocked relay acknowledgement/failure behavior, mocked LNbits invoice/status responses, amount and identity mismatch handling, inventory reservation, and the authenticated demo purchase scenario. Mocks verify application handling; they do not prove external provider availability. Live Nostr and LNbits tests require network access, relays, and LNbits credentials.

The Gemini SDK is optional and kept out of the default Windows dependency install. Install `backend/requirements-ai.txt` separately only when enabling `GEMINI_API_KEY`.
