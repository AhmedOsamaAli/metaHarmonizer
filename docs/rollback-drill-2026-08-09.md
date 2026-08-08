# Application Rollback Drill - 2026-08-09

## Scope

- Environment: production Compose host
- Starting revision: `25e2f00`
- Rollback revision: `8412399`
- Live Alembic revision: `c6d7e8f9a0b1`
- Database downgrade: none
- Persistent-volume restore: none

## Preconditions

The dry-run compatibility check passed because `8412399` contains migration
`c6d7e8f9a0b1`. A separate negative check proved that `0b6a57b`, which does not
contain that migration, is rejected before source or containers change.

Temporary smoke accounts and random passwords were generated entirely on the
host. Passwords were not printed or passed as command-line arguments.

## Result

`scripts/rollback_revision.sh 8412399` completed in 42 seconds. It:

1. detached the checkout at the exact target commit;
2. rebuilt API and web images;
3. republished SPA assets;
4. recreated API, worker, and Caddy;
5. observed healthy API and worker containers;
6. received HTTP 200 from public `/healthz`;
7. completed an authenticated login and found an access token.

Before the successful run, two attempts exposed a public-readiness race after
Caddy recreation. Both triggered automatic recovery to `25e2f00`, leaving API
and worker healthy. The command now retries public health and login checks for
up to 60 seconds after container health succeeds.

The host was then returned to branch `main` at `25e2f00`. Final verification
reported API healthy, worker healthy, public health HTTP 200, and authenticated
login HTTP 200. All temporary accounts and response files were deleted.

## Compatibility Rule Verified

Application-only rollback is allowed only when the target revision contains the
live Alembic head. Older-schema rollback requires a verified backup, explicit
data-loss review, stopped writes, and a separately executed database downgrade
from the newer source revision. The rollback command never downgrades or
restores PostgreSQL automatically.