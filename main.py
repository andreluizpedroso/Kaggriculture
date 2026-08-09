"""Kaggle submission entrypoint.

Thin wrapper -- the real agent logic lives in src/agent.py so it stays
testable/importable locally via `python -m src.simulate`. For submission,
bundle this file together with the `src/` folder into a tar.gz (main.py
at the tar root, per the competition's multi-file submission format):

    tar -czf submission.tar.gz main.py src

NOT YET SUBMITTED -- kept ready here for manual review before running
`kaggle competitions submit kaggriculture -f ... -m "..."`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.agent import agent  # noqa: E402
