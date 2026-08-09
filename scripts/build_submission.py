"""Generate a self-contained, single-file main.py for Kaggle submission.

Kaggriculture's own reference kernels validate their submission archive
with `assert members == ["main.py"]` -- a single root file, no
subdirectories. Our first submission used a main.py that imported from a
src/ package via a tar.gz with a nested folder, which failed Kaggle's
server-side "Validation Episode" (see PROGRESS.md). This script merges
src/config.py + src/agent.py into one flat main.py with no imports between
them, so the submission format matches the proven-working pattern.

src/ remains the source of truth for development (tests, simulate.py,
benchmark_references.py, optimize_config.py all import from it normally).
Run this script and re-verify before every submission -- main.py is a
generated artifact, not hand-edited.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "src" / "config.py"
AGENT_PATH = ROOT / "src" / "agent.py"
OUTPUT_PATH = ROOT / "main.py"


def build():
    config_src = CONFIG_PATH.read_text(encoding="utf-8")
    agent_src = AGENT_PATH.read_text(encoding="utf-8")

    # Drop the `from . import config as cfg` line and flatten every
    # `cfg.NAME` reference to `NAME` -- config's constants/functions live in
    # the same module now, so the qualifier is no longer needed.
    agent_src = agent_src.replace("from . import config as cfg\n\n", "")
    agent_src = re.sub(r"\bcfg\.", "", agent_src)

    header = (
        '"""Kaggriculture submission -- GENERATED FILE, do not hand-edit.\n\n'
        "Built by scripts/build_submission.py from src/config.py + src/agent.py\n"
        "(merged into one flat file because Kaggle's submission validator\n"
        'expects a single root-level main.py -- see PROGRESS.md). Edit the\n'
        "source files in src/ and rerun the build script instead.\n"
        '"""\n\n'
    )

    combined = header + config_src.split('"""', 2)[2].lstrip("\n") + "\n\n" + agent_src
    OUTPUT_PATH.write_text(combined, encoding="utf-8")
    print(f"wrote {OUTPUT_PATH} ({len(combined)} chars)")


if __name__ == "__main__":
    build()
