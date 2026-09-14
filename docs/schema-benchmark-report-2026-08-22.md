# Schema benchmark report - 2026-08-22

This report retains the transferable, non-sensitive evidence from three runs of
the real schema engine against ten project-supplied CPTAC tables and the
cBioPortal target preset. The supplied tables and generated row-level mappings
remain outside the repository.

## Method

The runs used the vendored `metaharmonizer` 0.4.1 wheel, offline model caches,
`top_k=5`, and manual mode:

```powershell
cd backend
python -m scripts.eval_schema `
  --tables <project-supplied-source-tables> `
  --schema cbio `
  --out <summary>.csv
```

The harness is [`backend/scripts/eval_schema.py`](../backend/scripts/eval_schema.py).
The engine wheel SHA-256 was
`37ee8fc0d061e1295910e153cce27c88c08d25b3a6aaf68970321239de96cbd3`;
the target alias table SHA-256 was
`960f761c9a8a2a8a84e343e57c7fc5a6e701d31298a3ebf095e2fa6775d47fd1`.
The SHA-256 of the newline-terminated, filename-sorted
`<filename>\t<file-sha256>` source manifest was
`0ef76d4dc7d2ec04df85a0e8a61c8c9087e8069abd27a02bb4e460335646e48a`.

## Results

| Run | Total wall time | Dou.csv (179 columns) | Gillette.csv (67 columns) | Candidates returned |
|---|---:|---:|---:|---:|
| 1 | 211.3 s | 7.4 s | 40.3 s | 569 / 569 |
| 2 | 221.7 s | 5.4 s | 37.2 s | 569 / 569 |
| 3 | 193.8 s | 6.0 s | 38.0 s | 569 / 569 |

The ten inputs contained 569 columns in total. `Dou.csv` was both the widest
and largest file at 179 columns and 213,263 bytes; `Gillette.csv` had the most
data rows at 225. The repeated difference between those two tables confirms
that column count and file size alone do not predict schema-mapping time.

The three generated summary files had these SHA-256 values:

| Summary | SHA-256 |
|---|---|
| Run 1 | `0b56622c3c678ba8ef5ea68b474a9dfde5aa0abcaf1968c5838b85a15d1f1d35` |
| Run 2 | `d0681674688967e18690d76ebc8f26a4313af07ffa3fb7e06076c29e5435f155` |
| Run 3 | `0a3cf8b2c8e51c672aff87148baeff64333655dab576090e1d015b0ea1a5bac6` |

## Limits

Returning a candidate is not the same as returning the correct candidate. These
runs support latency, repeatability, and candidate-production claims only; the
tracked ontology accuracy corpus and regression policy live under
[`backend/benchmarks/ontology/`](../backend/benchmarks/ontology/). No retained
artifact supports a GDC timing or production job-history average, so neither is
presented as repository-verifiable benchmark evidence.
