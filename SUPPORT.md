# Support

## Product and development questions

Use [GitHub Discussions](https://github.com/AhmedOsamaAli/metaHarmonizer/discussions)
when available, or open a [GitHub issue](https://github.com/AhmedOsamaAli/metaHarmonizer/issues/new/choose)
for reproducible non-sensitive bugs and feature requests.

Before filing an issue, review:

- [local setup and troubleshooting](SETUP.md);
- [curator guide](docs/curator-guide.md);
- [production deployment](DEPLOY.md);
- [production operations](docs/production-operations.md).

## Data and privacy boundary

Never attach protected health information, direct identifiers, uploaded study
files, access tokens, webhook URLs, encryption keys, or production logs containing
private metadata to a public issue. Use the private process in [SECURITY.md](SECURITY.md)
for sensitive security reports.

## Service incidents

The public service is monitored by named project operators. GitHub Issues are not
an emergency channel and do not provide a response-time guarantee. Deployment
operators should follow [production operations](docs/production-operations.md).

## Where to send what

| Situation | Channel | Why |
|---|---|---|
| Suspected vulnerability, leaked credential, exposed data | Private process in [SECURITY.md](SECURITY.md) | Must not be public before it is fixed |
| The public service is down, erroring, or losing work | The operator of that instance; for the public deployment use the private report process in [SECURITY.md](SECURITY.md) | Operators are alerted by monitoring; issues are not |
| Reproducible bug in the application | GitHub issue | Needs a tracked, public record |
| "How do I…" about curation | [Curator guide](docs/curator-guide.md), then GitHub Discussions | Usually already answered |
| Self-hosting or deployment problem | [SETUP.md](SETUP.md) / [DEPLOY.md](DEPLOY.md), then a GitHub issue | Environment-specific |

A report that may contain patient metadata belongs in none of the public
channels. Contact the operator of your instance and send only the minimum
detail required.

## Triage ownership and expectations

**Current owner.** The project maintainer triages incoming reports. After the
handover described in [docs/handover.md](docs/handover.md), triage ownership
transfers with the repository, and the operating institution names the
responsible party.

**Targets.** These are best-effort commitments from a small team, not a
commercial support agreement:

| Report type | First response target |
|---|---|
| Suspected security issue | 3 business days to acknowledge, per [SECURITY.md](SECURITY.md) |
| Production incident affecting users | Same working day |
| Bug report | 5 business days to triage and label |
| Question or feature request | Reviewed at the maintainer's next triage pass |

Automated production alerts follow separate and stricter acknowledgement
targets, defined in
[docs/service-level-objectives.md](docs/service-level-objectives.md). A user
report is not a substitute for monitoring: the operator is alerted before most
users would notice.

**What triage does.** Confirm whether the report is reproducible, classify
severity, label it, and either fix it, schedule it, or close it with a reason.
An issue closed without explanation is a triage failure.

**When nobody is on duty.** This project has no 24/7 rota and does not claim
one. Outside working hours the service is protected by automated monitoring,
bounded retries, and a verified rollback path rather than by staffed response.
