"""Write the replay folder of the probe's complete Mariano's answer (the probe's own tests' SYNTHETIC Classic
envelopes around the saved Vernon Hills pages) so that `classic-probe replay` can be run from the command line.
Run with the probe's venv from its folder:  python -I probe_fixtures180.py OUT_DIR
Offline; nothing is sent. The envelopes are SYNTHETIC (no Classic response exists); the pages inside are real
saved pages of store 53100502, Pickup."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
from tests import test_marianos as tm  # noqa: E402

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
spec: dict[str, list[dict[str, object]]] = {}
for step, rows in tm.complete().items():
    spec[step] = []
    for i, (status, body) in enumerate(rows):
        name = f"{step}_{i}.json"
        (out / name).write_bytes(body)
        spec[step].append({"http_status": status, "body_file": name})
(out / "replay.json").write_text(json.dumps({"label": "SYNTHETIC Classic envelopes around saved Vernon Hills pages",
                                             "steps": spec}, indent=1), "utf-8")
print(json.dumps({k: len(v) for k, v in spec.items()}))
