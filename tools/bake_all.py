"""Run every parametric and bespoke baker from a single entry point.

Exists so CI (`.github/workflows/lint.yml`) and contributors have one
command — `python3 -m tools.bake_all` — that rebuilds every committed
deliverable, instead of a shell loop that has to know how to translate
file paths into dotted module names.

Discovery is by glob, matching the conventions in CLAUDE.md:
  - `landscape/grounds/<name>/build_pakset.py` for parametric atlases.
  - `infrastructure/<class>/<asset>/scene.py` for bespoke ones, whose
    `if __name__ == "__main__"` block calls `bake_pakset()`.

`runpy.run_module(..., run_name="__main__")` mirrors `python -m`'s
behaviour exactly, so a baker discovered here behaves the same as if a
contributor had invoked it directly.
"""
from __future__ import annotations

import runpy
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PATTERNS = [
    "landscape/grounds/*/build_pakset.py",
    "infrastructure/*/*/scene.py",
]


def main() -> None:
    for pat in PATTERNS:
        for path in sorted(REPO_ROOT.glob(pat)):
            rel = path.relative_to(REPO_ROOT).with_suffix("")
            mod = ".".join(rel.parts)
            print(f"=== {mod} ===", flush=True)
            runpy.run_module(mod, run_name="__main__")


if __name__ == "__main__":
    main()
