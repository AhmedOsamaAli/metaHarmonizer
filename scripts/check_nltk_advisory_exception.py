#!/usr/bin/env python3
"""Guard the narrow pip-audit exception for GHSA-8mgp-746c-j5xp."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from zipfile import BadZipFile, ZipFile

NLTK_REFERENCE = re.compile(r"\bnltk\b", re.IGNORECASE)
PROJECT_SOURCE_ROOTS = (Path("backend/app"), Path("mcp/src"), Path("mcp/tests"))
WHEEL_GLOB = "metaharmonizer-*.whl"


def project_references() -> list[str]:
    references: list[str] = []
    for root in PROJECT_SOURCE_ROOTS:
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="replace")
            if NLTK_REFERENCE.search(text):
                references.append(path.as_posix())
    return references


def wheel_references() -> tuple[list[str], str | None]:
    wheels = sorted(Path("backend/vendor").glob(WHEEL_GLOB))
    if len(wheels) != 1:
        return [], f"expected exactly one {WHEEL_GLOB} under backend/vendor, found {len(wheels)}"

    try:
        with ZipFile(wheels[0]) as archive:
            references = []
            for name in archive.namelist():
                if not name.endswith(".py"):
                    continue
                text = archive.read(name).decode("utf-8", errors="replace")
                if NLTK_REFERENCE.search(text):
                    references.append(f"{wheels[0].as_posix()}!/{name}")
            return references, None
    except (BadZipFile, OSError) as exc:
        return [], f"could not inspect {wheels[0].as_posix()}: {exc}"


def main() -> int:
    references = project_references()
    wheel_matches, error = wheel_references()
    if error:
        print(f"nltk-advisory-exception: {error}", file=sys.stderr)
        return 1

    references.extend(wheel_matches)
    if references:
        print(
            "nltk-advisory-exception: runtime code now references NLTK; "
            "remove or reassess the pip-audit exception:",
            file=sys.stderr,
        )
        for reference in references:
            print(f"  {reference}", file=sys.stderr)
        return 1

    print("nltk-advisory-exception: no runtime NLTK references found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
