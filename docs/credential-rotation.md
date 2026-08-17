# Credential Rotation Runbook

Use a maintenance window for JWT and database rotation. Create replacement
credentials before revoking old credentials, keep a tested recovery path, and
never print secrets in logs or pass them as process arguments. Keep `.env` mode
`0600` and verify `docker compose config` before recreating services.

All production commands use:

```bash
export COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml
```

## Rotation record

For every rotation, record the service, credential identifier or fingerprint,
operator, start/end time, verification result, old-credential revocation time,
and recovery owner. Never record the credential value.

## JWT signing secret

`JWT_SECRET` signs access, refresh, verification, and password-reset JWTs.
Changing it invalidates all existing JWTs immediately. Personal API tokens are
independent hashes and are not affected.

1. Generate a replacement of at least 32 bytes without printing it into shared logs.
2. Revoke active refresh sessions so restoring the old secret cannot resurrect them:

   ```bash
   docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
     -c "UPDATE sessions SET revoked_at = now() WHERE revoked_at IS NULL;"
   ```

3. Replace `JWT_SECRET` atomically in `.env`, preserving mode `0600`.
4. Recreate API and worker and wait for health:

   ```bash
   docker compose up -d --no-deps --force-recreate api worker
   docker compose ps api worker
   curl -fsS "${APP_BASE_URL%/}/healthz"
   ```

5. Log in with a dedicated smoke account and verify an access token is returned.
6. Verify an old token is rejected.

Rollback by restoring the prior secret and recreating services. Revoked session
rows remain revoked, so users still need to sign in again.

## PostgreSQL application password

Compose constructs API, worker, seed, and backup database URLs from
`POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB`. Changing the `.env`
value alone does not alter the existing PostgreSQL role.

1. Keep an authenticated `psql` session open for recovery.
2. Generate a replacement password.
3. Alter the role from inside the database container:

   ```bash
   docker compose exec postgres psql -U mh -d metaharmonizer
   \password mh
   ```

   Type the replacement twice at the PostgreSQL prompts, then use `\q`. Adjust
   the example role/database names if the instance overrides their defaults.

4. Atomically update `POSTGRES_PASSWORD` in `.env`.
5. Recreate API and worker, then verify health and an authenticated login.
6. Run one backup command far enough to prove database authentication succeeds.

If verification fails, use the still-open database session to restore the old
role password, restore `.env`, and recreate API and worker. Do not restart the
PostgreSQL container as a password-rotation mechanism; its initialization
variables do not alter an existing role.

## Resend API key and sender

Email delivery is best-effort; API requests continue when Resend is unavailable.

1. Create a second Resend sending key with the same restricted permissions.
2. Verify `EMAIL_FROM` remains a provider-verified sender.
3. Update `RESEND_API_KEY` and `EMAIL_FROM` in `.env` and recreate API.
4. Send verification and password-reset messages to a scratch account.
5. Confirm delivery in both the application and Resend activity log.
6. Revoke the old key only after successful delivery.

Rollback by restoring the old key while it remains active. Provider delivery
cannot be validated without the Resend owner account.

## Backup storage credentials

Create a new S3-compatible key with access limited to the backup bucket. Update
`BACKUP_R2_ACCESS_KEY_ID` and `BACKUP_R2_SECRET_ACCESS_KEY`, run a manual backup,
confirm the object exists, and restore it into a scratch database before
revoking the old storage key. API/worker restart is unnecessary because the
one-shot backup process reads credentials at launch.

Provider acceptance and object visibility require the bucket-owner credentials.

## Backup encryption key

The AES-256-GCM key is not interchangeable with storage credentials. Every old
backup remains dependent on the key that encrypted it.

1. Produce and retain one final backup with the old key.
2. Archive the old key in institution-controlled cold storage with its backup date range.
3. Generate `backup-new.key` with `scripts.backup_postgres keygen` and mode `0600`.
4. Set numeric ownership to UID/GID 1000 (the non-root application container),
   then atomically replace the mounted `backup.key` without loosening mode `0600`.
5. Produce a new backup and restore it into a scratch database.
6. Retain the old key until every old-key backup expires or is re-encrypted and verified.

Rollback by restoring the archived old key. Never overwrite the only copy.

## ACME contact and Caddy account material

`ACME_EMAIL` is the certificate-account contact. Certificates and ACME account
keys live in the persistent `caddy_data` volume.

1. Update `ACME_EMAIL` in `.env`.
2. Validate configuration with `caddy validate`.
3. Recreate Caddy and verify HTTPS, certificate chain, and renewal logs.
4. Keep `caddy_data` and `caddy_config`; deleting them is not contact rotation.

Rollback by restoring the prior contact and recreating Caddy. Normal certificate
renewal remains automatic.

## SSH operator keys

For each VM, add before removing:

1. Generate an Ed25519 key in the institution password manager or approved workstation.
2. Append the new public key to the operator's `authorized_keys` with a named comment.
3. Open a separate session using only the new private key.
4. Verify repository fetch, Docker access, and a non-destructive health command.
5. Keep that session open while removing the old public key.
6. Prove the old key fails and the new key still succeeds.

Maintain at least two authorized institutional operators and recovery paths. If a
private Git repository uses a separate GitHub deploy key, rotate it independently
with the same add/verify/remove order.

## Federation signing and trusted-peer keys

`FEDERATION_PRIVATE_KEY` is an Ed25519 seed. Peers verify exports with public
keys in their `FEDERATION_TRUSTED_KEYS` lists.

1. Generate a replacement private seed offline and derive its public key.
2. Ask every peer to list both old and new public keys for this instance ID.
3. Verify a bundle signed by each key is accepted during the overlap window.
4. Replace `FEDERATION_PRIVATE_KEY` and recreate API.
5. Export/import a signed scratch bundle with each peer.
6. After `FEDERATION_MAX_BUNDLE_AGE_DAYS` plus clock skew, remove the old public key from peers.
7. Revoke and destroy the old private seed according to institutional policy.

Rollback by restoring the old private seed while peers still trust it. Never
change `FEDERATION_INSTANCE_ID` during key rotation.

## Completion gate

A rotation is complete only when the replacement works, the recovery path is
known, the old credential is revoked or retained under an explicit overlap
policy, monitoring shows no authentication failures, and the credential
inventory identifies two accountable institutional operators.