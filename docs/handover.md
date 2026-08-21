# Handover

This document covers two different things, and keeping them apart matters.

**Interim authority over the demonstrator.** The public instance runs on
personally held accounts. While it runs it should not depend on one person, so a
second operator is given tested access to each service. That is delegation for
continuity, not institutional ownership.

**Commissioning an institutional instance.** The deliverable is the deployment
kit, not the machine. An institution stands up its own instance under its own
accounts: its cloud tenancy, email sender, domain, and administrators are its own
from the start. They are not inherited from the demonstrator, because a personal
cloud tenancy and registrar account cannot sensibly be reassigned.

The repository is the exception. It transfers to the institutional organisation
with its history, releases, and workflows intact.

Project collaboration is not operational authority: a Slack invitation or a
GitHub collaboration role grants no cloud, DNS, database, secret, or recovery
access. Never send credentials or recovery codes through issues, chat, or email.

## Part 1 — Interim authority over the demonstrator

## Current roles

| Role | Current holder | Current authority |
|---|---|---|
| Project owner | Ahmed Osama Ali | GitHub administration, production host, cloud/DNS/provider credentials |
| Scientific mentor | Dr. Sehyun Oh | Scientific review, secondary Slack alert receipt |
| Institutional service owner | Not yet assigned | None |

## Interim access matrix

Each row must be delegated and tested independently. Do not place credentials or
recovery codes in this repository. These are demonstrator accounts; an
institutional instance is commissioned with its own, as Part 2 sets out.

| Service | Purpose | Minimum interim state | Verification | State |
|---|---|---|---|---|
| GitHub repository | Source, PRs, Actions, releases, KB assets | Maintainer initially; administrator only when accepted | Approve a test PR; inspect branch protection, Actions, releases | Pending |
| OCI tenancy/instance | Production VM and block storage | Least-privilege group plus tested console recovery | Sign in with MFA, inspect instance, run read-only health check | Second administrator added 2026-08-20; activation pending |
| SSH host access | Host operations | Named Ed25519 key per operator; no shared private key | Independent login, read-only health command, revocation test | Pending |
| Domain/DNS registrar | `metaharmonizer.online` | Manager or delegated DNS role, with renewal visibility | Sign in, read DNS records, confirm recovery contact | Pending |
| Cloudflare R2 | Encrypted database backups | Bucket-scoped management; encryption key recovery held separately | List backup metadata; scratch restore with approved key access | Pending |
| Slack | Operational alerts | Primary and secondary recipients plus workspace recovery owner | Synthetic alert matrix received and acknowledged | Complete |
| Resend | Verification/reset email | Domain/app collaborator with sender recovery ownership | Send a non-sensitive test email, inspect delivery status | Pending |
| Production database | Application state | Access only through audited host/backup procedures; no public endpoint | Restore latest backup to scratch, compare aggregate counts | Complete |
| Account recovery | GitHub, OCI, DNS second factor | Recovery contacts and codes reachable by two authorized people | Documented recovery drill without exposing codes | Pending |

## Delegation sequence

Order by service:

1. GitHub maintainer access.
2. OCI identity with least privilege; do not use the tenancy-wide Administrators
   group as the first step.
3. Independent SSH key and read-only production verification.
4. DNS, R2, email, and recovery roles.
5. Joint restore, rollback, credential-rotation, and incident drills.

At each step:

- add the new account and its second factor before removing any current access;
- verify it through a separate session and a non-destructive task;
- rotate shared or provider credentials only once the new operator can recover
  them;
- re-run backup restore, alert delivery, deployment health, and rollback checks;
- increase authority only after the recipient accepts responsibility;
- record the state reached and the work still delegated.

## Acceptance checklist

- [ ] Recipient accepts the documented role and response expectations.
- [ ] Two authorized people can recover GitHub, OCI, DNS, R2, email, and Slack.
- [ ] Each operator uses an individual identity, MFA, and individual SSH key.
- [ ] No private key, password, token, webhook, or recovery code is shared in chat.
- [ ] Repository release, production health, logs, backups, and alerts are visible.
- [ ] Backup restore, application rollback, and credential rotation are jointly tested.
- [ ] Billing owner, budget, and escalation contacts are documented privately.
- [ ] Deferred work has an owner and review date.

## Delegation versus collaboration

For ongoing development, Dr. Sehyun can begin as a GitHub maintainer and an OCI
read-only instance operator. Full repository or tenancy administration should
follow only once she or an institution accepts service ownership, billing,
security response, and recovery duties.

The current owner should retain access until all acceptance checks pass. Remove
old authority only after the replacement path has been independently verified.

## Least privilege

Repository access, operational alerts, cloud billing, host SSH, DNS, and backup
recovery are different authorities. Grant only the roles needed for each task.
Do not make every operator a tenancy administrator merely to provide instance
access. Preserve one tested break-glass path under institutional control.

## Required now

- GitHub repository access and protected-branch visibility.
- OCI user, MFA, least-privilege instance access, and tested recovery escalation.
- Separate SSH public key.
- Slack alert receipt (completed for the secondary operator).
- Confirmation of who owns R2, Resend, domain/DNS, billing, and recovery.
- Backup encryption-key custody plan with no key material in Git.

## Part 2 — Commissioning an institutional instance

This is the actual handover. It does not depend on Part 1 and it inherits no
demonstrator account.

### What the institution receives

- the repository, transferred to its organisation with history, releases, and
  workflows intact;
- the Compose deployment files and container definitions;
- `DEPLOY.md`, `SETUP.md`, and the operations runbook;
- the offline knowledge-base bundle with its SHA-256 and provenance;
- the curator manual and the scored usability protocol.

### What the institution supplies

Its own from the start. None of these are transferred.

| Item | Note |
|---|---|
| Cloud tenancy | Any provider; the stack is containers and needs no managed services |
| Production environment file | Built from `.env.example`, with secrets it generates rather than copies |
| Transactional email sender | Its own account and verified sending domain |
| Domain or subdomain | An institutional subdomain is the expected form |
| Administrators | At least two, each with individual identity and MFA |

### Configuration, not code

Moving to an institutional hostname requires no source change.

| Variable | Consumer |
|---|---|
| `DOMAIN` | Caddy virtual host and certificate |
| `ACME_EMAIL` | Certificate contact |
| `APP_BASE_URL` | Links in verification and reset email; also drives `COOKIE_SECURE` |
| `CORS_ORIGINS` | No wildcards in production |
| `EMAIL_FROM` | Verified sender |
| `ALLOWED_EMAIL_DOMAINS` | Auto-approval scope; can be narrowed to the institution |
| `OPS_HEALTH_URL`, `OPS_METRICS_URL`, `REGISTRATION_HEALTH_URL` | Operations checks |
| `E2E_BASE_URL` | CI browser journey |

### Commissioning checklist

- [ ] Repository transferred and CI green in the new organisation, after URLs,
      release assets, webhooks, and deployment remotes have a documented update
      plan.
- [ ] Environment file created with institution-generated secrets.
- [ ] Knowledge-base bundle installed and its checksum verified.
- [ ] TLS issued for the institutional hostname.
- [ ] Two administrators with individual identity and MFA.
- [ ] Backup taken and restored to scratch.
- [ ] Alert delivered and acknowledged.
- [ ] Authenticated browser journey passing against the new hostname.

Demonstrator data is not migrated by default. A database dump and the upload
volume move only if there is a reason to keep them.

## Delegated follow-up work

These items improve institutional maturity but are not reasons to hide or rush
changes into the current release:

- external uptime monitoring and retained metrics dashboards;
- shared object storage and private networking before remote ML workers;
- managed/replicated PostgreSQL and Redis before high-availability claims;
- highly available API and stateful infrastructure;
- institutional privacy, incident-response, and data-processing policies;
- formal RPO/RTO and staffed on-call commitments;
- mixed dashboard and real-ML load testing after infrastructure changes;
- broader component-level frontend coverage and gradual page decomposition;
- independent curator usability review;
- stable release declaration and package publication;
- RFC 86 consent recording if contributions enter a cBioPortal repository.

## Completion record

Part 1 is complete when both operators can independently access the required
services, recovery paths are tested, and current deployment, backup, and alert
checks pass.

Part 2 is complete when the commissioning checklist passes on institution-owned
infrastructure and the receiving institution accepts the known limitations and
the follow-up list. The demonstrator can then be retired.
