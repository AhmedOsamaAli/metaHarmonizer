# Administrator guide

For administrators of a MetaHarmonizer deployment. Curator tasks (upload,
mapping review, ontology, export) are in the [curator guide](curator-guide.md);
host and server operations are in
[production operations](production-operations.md).

Everything here is reached from **Admin** in the header, which is visible only
to accounts with the `admin` role. The console has five tabs.

| Tab | What it controls |
| --- | --- |
| Users & access | Who can sign in, and with what role |
| Schema versions | Which target schema studies are mapped against |
| Aliases | Column-name synonyms used during schema matching |
| Knowledge | Promoting curator decisions into shared rules |
| Federation | Exchanging curated knowledge with another deployment |

---

## 1. Users & access

Lists every account with its role, status, and last activity.

- **Approve / Reject** — clears a pending registration, or refuses it. Whether
  an account arrives pending depends on `ALLOWED_EMAIL_DOMAINS`: a matching
  domain is auto-approved, anything else waits here. See
  [DEPLOY.md](../DEPLOY.md) for setting that value.
- **Change role** — moves an account between `curator` and `admin`.
- **Approve admin / Reject admin** — a second administrator must confirm a
  promotion to `admin`. This is deliberate: it means one compromised account
  cannot quietly grant itself full control.
- **Activate / Deactivate** — suspends an account without deleting it or its
  studies. Use this rather than deletion when someone leaves.
- **Force logout** — revokes that user's sessions immediately. Use it when a
  laptop is lost or a role is reduced.

Closing registration entirely is a server action, not a console one:

```bash
scripts/registration_mode.sh close --domains "example.org,partner.org"
scripts/registration_mode.sh status
```

Closing stops new self-registrations being approved. It does not disable
existing accounts — deactivate those individually.

## 2. Schema versions

A schema version is the target vocabulary studies are mapped onto. Each study
records the version it used, so results stay reproducible after an update.

- **Upload** a new version to register it without affecting anyone.
- **Diff** compares two versions and shows added, removed, and changed fields.
  Read this before promoting; a removed field silently changes what future
  studies can map to.
- **Promote** makes a version the default for new studies. Existing studies
  keep the version they were mapped with.

Promotion affects only new runs. Re-mapping an existing study against a newer
version means running it again.

## 3. Aliases

Aliases are column-name synonyms. When a source table calls a column `AGE_D`
and the target schema calls it `age_at_diagnosis`, an alias connects them so
schema matching finds it.

- **Add entry** records a synonym for a target field.
- **Remove** deletes a custom alias. Built-in aliases shipped with the schema
  cannot be deleted, only overridden.
- **Export** downloads either the full dictionary (built-in plus custom) or only
  the custom additions. Export the custom set before a migration — it is the
  part that is yours.

Aliases influence matching for subsequent runs. They do not retroactively change
studies already mapped.

## 4. Knowledge — learned decisions

When curators accept or reject the same mapping repeatedly, that agreement is a
candidate rule. This tab promotes those into rules applied to future studies.

- **Accepted mappings** / **Rejected mappings** — candidates awaiting review,
  with how many curators agreed.
- **Promote** applies the rule globally to future studies.
- **Dismiss** removes a candidate without promoting it.
- **Promoted globally** lists active rules; **unpromote** stops one being
  applied.

Promotion is intentionally manual. A rule that is popular is not automatically
correct, and promoting one changes results for every curator, so review the
agreement count before promoting.

## 5. Federation

Federation exchanges curated knowledge — not study data — with another
deployment.

- **Public key** is this deployment's identity. The other side needs it to
  verify what you send.
- **Export** produces a signed bundle of shareable curated knowledge.
- **Import** accepts a bundle from another deployment. It does not apply
  automatically: it lands in a queue.
- **Approve / Reject** each import after review. Approving merges the incoming
  knowledge; rejecting discards it.

Nothing crosses a deployment boundary without an administrator approving it on
the receiving side.

---

## 6. How ontology terms are updated

Ontology terms come from corpora built into the knowledge-base bundle, not from
a live lookup at mapping time. That is what makes a run reproducible and lets
the system work offline.

| Corpus | Source | Refreshed |
| --- | --- | --- |
| NCIt disease | NCI EVS REST | Quarterly, automatically |
| NCIt treatment | NCI EVS REST | Quarterly, automatically |
| UBERON body site | OLS4 | Quarterly, automatically |
| EFO phenotype | Supplied corpus | Carried forward unchanged |

The refresh runs on the first day of January, April, July, and October at 03:00
UTC. It rebuilds the corpora, benchmarks the new bundle against the previous
one, and **republishes only if accuracy has not regressed** and the new bundle
is a superset. A refresh that loses accuracy fails instead of shipping.

To refresh sooner, run the *Knowledge Base Refresh* workflow manually. Full
detail, including the accuracy thresholds, is in
[kb-lifecycle.md](kb-lifecycle.md).

### Which fields receive ontology terms

Value-to-ontology mapping is not applied to every column — only to fields that
route to a controlled vocabulary. The current routing is listed in the
[curator guide](curator-guide.md#which-columns-produce-ontology-terms). If a
target schema names its fields differently, few columns will qualify, and the
Ontology stage will look sparse even though the run succeeded.

---

## 7. Where everything else lives

| Task | Document |
| --- | --- |
| Deploying, upgrading, environment values | [DEPLOY.md](../DEPLOY.md) |
| Backups, restore, monitoring, incidents | [production-operations.md](production-operations.md) |
| Rotating credentials | [credential-rotation.md](credential-rotation.md) |
| Knowledge-base internals and thresholds | [kb-lifecycle.md](kb-lifecycle.md) |
| Capacity limits and growth | [scaling-plan.md](scaling-plan.md) |
| Availability and support targets | [service-level-objectives.md](service-level-objectives.md) |
| Handing the deployment to someone else | [handover.md](handover.md) |
| Curator-facing workflow | [curator-guide.md](curator-guide.md) |

## 8. Audit

Every administrative action — approvals, role changes, promotions, imports — is
recorded with the actor, the action, and the time. Read it from **Activity**.
Audit events are retained for 365 days.
