"""
Prints the step-by-step decisions from a discovery run's log, so you can check
the step numbers match what artifacts/recorder.py expects before recording.

Run with: python scripts/show_decisions.py evidence/runs/<your_folder>
"""

import json
import sys
from pathlib import Path

run_dir = Path(sys.argv[1])
log_path = run_dir / "discovery_log.jsonl"

with open(log_path, encoding="utf-8") as f:
    for line in f:
        entry = json.loads(line)
        if entry.get("event") != "decision":
            continue
        action = entry["action"]
        print(
            entry["step"], action["type"], action.get("target"),
            "|", action.get("value"), "|", action.get("extract_as"),
        )
