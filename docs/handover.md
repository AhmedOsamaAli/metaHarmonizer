# Authority and Operations Handover

## Purpose

This document separates project collaboration from operational authority. A
Slack invitation or GitHub collaboration role does not grant cloud, DNS,
database, secret, or recovery access.

## Current roles

| Role | Current holder | Current authority |
|---|---|---|
| Project owner | Ahmed Osama Ali | GitHub administration, production host, cloud/DNS/provider credentials |
| Scientific mentor | Dr. Sehyun Oh | Scientific review, secondary Slack alert receipt |
| Institutional service owner | Not yet assigned | None |

## Authority matrix

Each row must be delegated and tested independently. Do not place credentials or
recovery codes in this repository.

| Service | Required role | Delegation evidence | Current state |
|---|---|---|---|
| GitHub repository | Maintainer initially; administrator only when accepted | Invitation accepted, protected branch/Actions/release access tested | Pending for Dr. Sehyun |
| OCI tenancy/instance | Least-privilege group plus tested console recovery | Identity-domain invitation, policy membership, sign-in and instance visibility | Pending |
| SSH host access | Named Ed25519 public key | Independent login, Docker/read-only health command, old-key isolation | Pending |
| Domain/DNS registrar | Manager or delegated DNS role | Sign-in, DNS visibility, recovery contact | Pending |
| Cloudflare R2 backup | Bucket-scoped management/recovery | Bucket visibility, credential rotation path, object listing | Pending |
| Slack alerts | Private channel membership | Synthetic matrix received and acknowledged | Complete for Dr. Sehyun |
| Resend email | Domain/app collaborator | Verified domain visibility and test delivery | Pending |
| GitHub/OCI/provider recovery | Secondary recovery owner | 2FA and recovery path tested without sharing secrets | Pending |

## Recommended delegation order

1. GitHub maintainer access.
2. OCI identity with least privilege; do not use the tenancy-wide Administrators
   group as the first step.
3. Independent SSH key and read-only production verification.
4. DNS, R2, email, and recovery roles.
5. Joint restore, rollback, credential-rotation, and incident drills.
6. Increase authority only after the recipient accepts responsibility.

## Acceptance checklist

- [ ] Recipient accepts the documented role and response expectations.
- [ ] Two authorized people can recover GitHub, OCI, DNS, R2, email, and Slack.
- [ ] Each operator uses an individual identity, MFA, and individual SSH key.
- [ ] No private key, password, token, webhook, or recovery code is shared in chat.
- [ ] Repository release, production health, logs, backups, and alerts are visible.
- [ ] Backup restore, application rollback, and credential rotation are jointly tested.
- [ ] Billing owner, budget, and escalation contacts are documented privately.
- [ ] Deferred work has an owner and review date.

## Authority transfer versus collaboration

For ongoing development, Dr. Sehyun can begin as a GitHub maintainer and OCI
read-only/instance operator. Full repository or tenancy administration should be
transferred only if she or an institution accepts service ownership, billing,
security response, and recovery duties.

The current owner should retain access until all acceptance checks pass. Remove
old authority only after the replacement path has been independently verified.

## Deferred institutional work

The following can be assigned later without blocking continued feature work:

- highly available API/stateful infrastructure;
- external long-term metrics and log retention;
- institutional privacy, incident-response, and data-processing policies;
- formal RPO/RTO and staffed on-call commitments;
- remote worker deployment and object-storage migration;
- organization transfer, stable release declaration, and package publication.# Handover and Authority Transfer

This document separates access that must be transferred now from improvements
that can be delegated after handover. Never send credentials or recovery codes
through issues, chat, or email.

## Required authority transfer

| Service | Current purpose | Minimum handover state | Verification |
|---|---|---|---|
| GitHub repository | Source, PRs, Actions, releases, KB assets | Dr. Sehyun or an institutional maintainer has repository access; a second admin exists before ownership transfer | Review branch protection, approve a test PR, inspect Actions and releases |
| OCI tenancy/instance | Production VM and block storage | Second named operator has least-privilege instance access plus a documented administrator recovery path | Sign in with MFA, inspect instance, perform read-only health check |
| SSH | Host operations | Separate named SSH key for each operator; no shared private key | Open independent session, run non-destructive health command, test revocation procedure |
| Domain and DNS | `metaharmonizer.online` | Institutional owner/recovery contact and renewal visibility | Read DNS records, confirm renewal and recovery path |
| Cloudflare R2 | Encrypted database backups | Second bucket administrator; encryption key recovery held separately | List backup metadata and complete a scratch restore with approved key access |
| Slack | Operational alerts | Primary and secondary recipients plus workspace recovery owner | Receive and acknowledge synthetic alert matrix |
| Resend | Verification/reset email | Second administrator and domain/sender recovery ownership | Send a non-sensitive test email and inspect delivery status |
| Production database | Application state | Access remains through audited host/backup procedures; no public endpoint | Restore latest backup to scratch and compare aggregate counts |
| GitHub/OCI/DNS 2FA | Account recovery | Institution-controlled recovery contacts/codes for at least two authorized people | Documented recovery drill without exposing codes |

## Least privilege

Repository access, operational alerts, cloud billing, host SSH, DNS, and backup
recovery are different authorities. Grant only the roles needed for each task.
Do not make every operator a tenancy administrator merely to provide instance
access. Preserve one tested break-glass path under institutional control.

## Transfer sequence

1. Name the institutional owner and secondary operator.
2. Add new accounts and MFA before removing current access.
3. Verify each new account through a separate session and a non-destructive task.
4. Transfer recovery contacts and billing visibility.
5. Rotate shared/provider credentials after the new owners can recover them.
6. Re-run backup restore, alert delivery, deployment health, and rollback checks.
7. Transfer or fork the repository only after URLs, release assets, webhooks, and
   deployment remotes have a documented update plan.
8. Record the accepted revision and remaining delegated work.

## Required now

- GitHub repository access and protected-branch visibility.
- OCI user, MFA, least-privilege instance access, and tested recovery escalation.
- Separate SSH public key.
- Slack alert receipt (completed for the secondary operator).
- R2, Resend, domain/DNS, billing, and recovery ownership confirmation.
- Backup encryption-key custody plan with no key material in Git.

## Delegated follow-up work

These items improve institutional maturity but are not reasons to hide or rush
changes into the current release:

- external uptime monitoring and retained metrics dashboards;
- shared object storage and private networking before remote ML workers;
- managed/replicated PostgreSQL and Redis before high-availability claims;
- mixed dashboard and real-ML load testing after infrastructure changes;
- broader component-level frontend coverage and gradual page decomposition;
- independent curator usability review;
- repository transfer to an institutional or cBioPortal organization, if accepted;
- RFC 86 consent recording if contributions enter a cBioPortal repository.

## Completion record

The handover is complete only when both operators can independently access the
required services, recovery paths are tested, current deployment/backup/alert
checks pass, and the receiving institution accepts the known limitations and
follow-up list.
