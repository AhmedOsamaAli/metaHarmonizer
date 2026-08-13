# MetaHarmonizer Curator Guide

This guide covers the curator workflow on the hosted application at
<https://metaharmonizer.online> and on an equivalent self-hosted instance.

## Before you upload

Upload only de-identified clinical metadata. Do not upload names, contact
details, medical-record numbers, protected health information (PHI), or other
direct patient identifiers. The upload confirmation appears before the browser
previews or sends the selected file. Choosing **Cancel** leaves no file
selected.

Supported inputs are CSV and TSV files. Check the browser preview before
starting: the first row should contain column names and the previewed values
should be split into the expected columns.

## 1. Upload and harmonize

Open **Upload**, select the file, and choose a run mode:

- **Both** maps columns to a target schema and then resolves selected values to
  ontology terms.
- **Schema only** maps column names and skips value-to-ontology resolution.
- **Ontology only** resolves values and skips schema mapping.

For schema mapping, select the target standard shown by the application. For an
ontology run, the optional column selector limits value resolution to the
chosen columns; leaving it empty uses all eligible columns.

Select **Run harmonization**. The job continues on the server if you change
pages or refresh the browser. Its progress remains in the jobs tray. A failed
job shows an error and can be submitted again after correcting the input.

## 2. Review schema mappings

Open **Schema** and select the study. The default **Pending** tab contains
columns that still need a curator decision.

For each proposed mapping:

- **Accept** confirms that the source column should map to the displayed target
  field.
- **Reject** confirms that this proposed mapping should not be used. It does
  not mean the source column is invalid in general.
- **Edit** replaces the proposed target with the curator-selected field and can
  include a note.

Decisions are saved immediately. Accepted, rejected, and edited decisions are
remembered for the curator so repeated columns can be prefilled or rejected on
later studies. An admin must separately promote a learned decision before it
applies globally.

The default **Smart review order** places risky mappings first and keeps
look-alike columns together. Clicking a sortable header cycles through
descending, ascending, and back to smart order. Missing values remain last.

Use the row checkboxes or a look-alike group control to select several pending
rows, then choose **Accept all** or **Reject all**. Batch actions leave the view
on **Pending**.

Keyboard shortcuts:

| Key | Action |
| --- | --- |
| `j` / `k` | Move down / up |
| `a` | Accept focused mapping |
| `r` | Reject focused mapping |
| `e` | Edit focused mapping |
| `x` | Select focused mapping |
| `Enter` | Open details |
| `/` | Focus search |

## 3. Confirm ontology terms

Open **Ontology** after an ontology-capable run. Each matched value shows its
proposed standard term, code, and confidence.

- **Accept** confirms the displayed term and code.
- **Reject** declines that proposed term for the raw value.
- **Edit/Override** searches for and assigns a different term.

Assigning a term to a repeated raw value applies the same correction to all of
its occurrences within that field. The preview shows how accepted terms will
rewrite exported values; the original uploaded file is never modified.

Values under **No ontology match** may be identifiers, names, free text, or
terms absent from the current corpus. Use **Find suggestions** to search the
ontology index. Review each suggestion before applying it; dismissing a
suggestion only removes that suggestion from the current view.

## 4. Check quality and readiness

Open **Quality** to inspect coverage, confidence, stage distribution, and
lowest-confidence pending columns.

The readiness checklist verifies:

1. At least one mapping is accepted.
2. No schema mappings remain pending.
3. Every column has a mapped field.

The first condition blocks export readiness. Pending columns require a decision.
Unmapped columns are identified in the checklist and are dropped from export.
When the banner says **Ready to export**, select **Go to export**.

## 5. Download outputs

Open **Export** and download any required formats before completing the study:

- **Harmonized CSV** contains renamed fields and accepted ontology rewrites.
- **cBioPortal Format** is a tab-separated clinical file with cBioPortal header
  lines.
- **cBioPortal Study Folder (ZIP)** contains metadata and clinical data files
  for validation/import.
- **Mapping Report (JSON)** records mapping proposals and curator decisions.
- **Labeled Dataset (CSV or JSONL)** includes curator-confirmed mappings for
  evaluation or training.

Downloaded data can still contain sensitive source values if the upload was not
properly de-identified. MetaHarmonizer does not certify de-identification.

## 6. Complete the study

After downloading every required output, choose **Complete**. Completion removes
the study from the active work list and cannot be undone from the application.
Do not complete a study until required exports have been downloaded. Incomplete
studies are automatically removed after the configured retention period.

## Troubleshooting

- **A study is not visible on a review page:** wait for the job to finish in the
  jobs tray, then select the study again.
- **A column is unmapped:** inspect its values and alternatives, then edit the
  mapping or accept that it will be omitted from export.
- **An ontology value has no match:** use **Find suggestions**, assign a term
  manually, or leave it unmatched when no standard term is appropriate.
- **An export looks incomplete:** return to **Quality** and review its readiness
  checklist and unmapped-column count.
- **The session expired:** sign in again. Saved curator decisions are stored on
  the server and do not depend on the browser tab remaining open.

## Reporting problems

Use the project's [GitHub Issues](https://github.com/AhmedOsamaAli/metaHarmonizer/issues)
for non-sensitive bugs and feature requests. Never paste or attach PHI, raw
patient metadata, credentials, API tokens, or private exports to a public issue.
For a report that may contain sensitive information, contact the operator of
your MetaHarmonizer instance and provide only the minimum necessary details.

Include the application page, study ID if non-sensitive, approximate time,
expected result, actual result, and reproducible steps. Redact values and file
names that could identify a patient or institution.