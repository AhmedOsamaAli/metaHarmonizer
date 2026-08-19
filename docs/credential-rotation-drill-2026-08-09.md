# Credential Rotation Drill - 2026-08-09

## Automated and isolated checks

- JWT: an old-secret token failed signature validation after rotation; a token
  signed with the new secret decoded successfully.
- Backup encryption: AES-256-GCM encrypt/decrypt round trip passed and tampered
  ciphertext was rejected.
- Federation: both old and new trusted Ed25519 public keys verified during the
  overlap window; an unregistered key failed.
- PostgreSQL 16: a disposable role password was changed; the old password was
  rejected and the replacement password authenticated successfully.
- ACME/Caddy: `Caddyfile.prod` validated successfully with a replacement ACME
  email and test domain.
- SSH: two temporary Ed25519 public keys coexisted with distinct fingerprints;
  the old key was then removed while the new key remained.

The focused backend command reported 12 passed tests. Disposable PostgreSQL,
SSH, and test-file state was removed after verification.

## Provider-side checks still requiring owners

This drill does not claim external-provider acceptance. Production completion
still requires:

- a delivered message using a replacement Resend key and verified sender;
- backup plus scratch restore using replacement R2/S3 credentials;
- a real second SSH operator session before removing the current host key;
- peer-confirmed federation imports during an old/new public-key overlap;
- Caddy renewal/account-log confirmation after changing the real ACME contact.

These checks are credential-owner work tracked outside the public repository;
they are not substitutes for the engineering rotation procedures validated
here. Current operator procedures are in `docs/credential-rotation.md` and
`docs/production-operations.md`.