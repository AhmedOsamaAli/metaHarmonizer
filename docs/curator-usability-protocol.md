# Independent curator usability protocol

The claim under test is narrow and falsifiable:

> A curator who was not involved in building MetaHarmonizer can take an
> unfamiliar metadata file from upload to a validated export using only
> [curator-guide.md](curator-guide.md), without asking the development team a
> question.

Until this has been run and recorded, the honest status is *not demonstrated*.
A walkthrough by the author does not test the documentation; it tests the
author's memory of the product.

## Who should run it

One or two people who curate biomedical metadata, have never used this
application, and were not involved in its development. A colleague who has
watched a demonstration is not a valid participant.

Assign one observer. The observer does not help. The observer's only job is to
record where the participant hesitates, backtracks, or asks a question, because
each of those is a defect in the guide or the interface.

## Setup

- A hosted or self-hosted instance the participant can register on.
- A de-identified CSV or TSV the participant has not seen, roughly 50–500 rows
  with a mix of clearly mappable columns, at least one ambiguous column, and at
  least one column that should not map.
- The curator guide, and nothing else. No demonstration, no screen sharing from
  the team, no verbal walkthrough.

Confirm before starting that the file contains no protected health information.

## Tasks

The participant performs these in order, unaided.

| # | Task | Pass condition |
|---|---|---|
| 1 | Obtain access and sign in | Reaches the signed-in dashboard without assistance |
| 2 | Upload the file and start a run mapping both schema and values | Run appears in the jobs tray and completes |
| 3 | Explain what the badge "S3 Semantic" and a confidence value mean | Explanation matches the guide's meaning |
| 4 | Review pending schema mappings: accept a correct one, correct a wrong one, reject one that should not map | All three decisions persist after a page refresh |
| 5 | Confirm or correct at least three ontology terms, including one with no match | Decisions persist; the participant states what happens to an unmatched value on export |
| 6 | Determine whether the study is ready to export, and say why or why not | Answer matches the readiness checklist |
| 7 | Download the cBioPortal-format export | File downloads and contains the accepted mappings |
| 8 | State what completing the study does, without doing it | Answer matches the guide: it leaves the work list and is not undoable in the application |

## Recording

For each task record: completed unaided (yes/no), time taken, every question
asked, every place the participant looked in the guide and did not find the
answer, and any point at which the interface contradicted the guide.

Record verbatim what the participant said when confused. Paraphrase loses the
signal.

## Pass criteria

The exercise passes when every task is completed unaided by at least one
participant, with no question that the guide should have answered.

A single unanswered question does not fail the product; it identifies a specific
documentation defect to fix. Fix it, then re-run the affected task with a
different participant.

## Recording the result

Add a dated results file under `docs/` naming the participants by role rather
than by name, listing per-task outcomes, defects found, and what was changed in
response. Then update the corresponding answer in the deliverable verification
document to reference it.

Do not mark the usability question as satisfied on the basis of this protocol
existing. It is satisfied by a recorded run.

## Status

**Not yet run.** This requires a participant who is independent of the
development team, so it cannot be completed by the maintainer alone.
