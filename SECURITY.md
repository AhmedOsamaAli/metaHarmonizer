# Security Policy

## Supported version

Security fixes are applied to the current `main` branch and the latest published
release. Older revisions are not supported unless an institutional deployment
has a separate maintenance agreement.

## Report a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/AhmedOsamaAli/metaHarmonizer/security/advisories/new).
Do not open a public issue for vulnerabilities, credentials, private metadata,
or protected health information.

Include:

- affected revision or deployment;
- reproduction steps and expected impact;
- whether credentials or data may have been exposed;
- a safe contact method for follow-up.

Do not test destructive techniques against the public service or access data that
does not belong to you. We will acknowledge a credible report, preserve evidence,
rotate exposed credentials, and coordinate remediation before disclosure.

Acknowledgement is targeted within three business days. That is a best-effort
commitment from a small team rather than a commercial agreement, and it covers
acknowledgement only; remediation time depends on severity and on whether a fix
requires an upstream dependency. If a report indicates active exposure of
credentials or data, say so explicitly in the first message so it is prioritised.

## Security controls

Protected CI runs dependency audits, secret scanning, CodeQL, container
vulnerability scanning, SBOM generation, and non-root runtime checks. Production
uses HTTPS, role-based access, upload/rate/queue limits, encrypted off-host
backups, and operational alerting. See [DEPLOY.md](DEPLOY.md) and
[production operations](docs/production-operations.md).
