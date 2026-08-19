# Governance

## Current roles

- **Project owner and repository administrator:** Ahmed Osama Ali.
- **Scientific mentor and secondary operations recipient:** Dr. Sehyun Oh.
- **Future institutional maintainers:** to be named during repository and service
  authority transfer.

A Slack alert-channel invitation is not equivalent to GitHub, cloud, DNS, or
secret-management authority. Each service must be delegated explicitly and
verified independently.

## Decision process

- Routine fixes and minor dependency updates require protected CI and one
  maintainer approval where branch protection requires it.
- Architecture, schema, engine, security, privacy, licensing, and infrastructure
  changes require a written rationale, affected-owner review, migration/rollback
  notes, and targeted validation.
- Scientific mapping policy changes require curator or domain-expert review.
- Emergency security changes may be applied by an authorized administrator and
  documented immediately afterward.

## Releases

A release must identify the source revision, migrations, KB/model bundle,
validation results, known limitations, and rollback target. Moving version
numbers to `1.0.0` requires an explicit stability decision; public availability
alone does not imply API or packaging stability.

## Authority transfer

The transfer procedure and access matrix are maintained in
[docs/handover.md](docs/handover.md). At least two authorized operators should
hold tested recovery paths before the current owner relinquishes sole authority.

## Review cadence

Review maintainers, service ownership, recovery access, alert recipients,
security policy, service objectives, and deferred work at least quarterly and
whenever an operator or institution changes.
