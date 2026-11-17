"""PRIVATE (workstation): fits one slice's ceiling to what is left in Mariano's envelope before it is launched.

    python -I fit_stage.py KEY LEDGER_STATUS_JSON

The ledger refuses to open a stage whose ceiling exceeds what is left in the envelope, and refuses any reservation
beyond it. A slice must also end with the operator's SIGTERM (resumable) before its ceiling, never at it (a ceiling
stop finalizes the run). When KEY's defined ceiling (max_submissions, at USD 0.0015 a submission) exceeds the room,
the ceiling becomes the room and the slice target the room less 10 (the margin of every R7 slice: two lanes in flight
and the stopper's polling); the definition is rewritten in place and the change printed. Exit 0 when the stage fits
(changed or not), 3 when the room is below 40 submissions (no slice is worth launching: the run stays resumable).
"""

from __future__ import annotations

import json
import math
import sys
from decimal import Decimal
from pathlib import Path

DEFS = Path("[redacted:workstation-path]/ops6/stage_defs.json")
RATE = Decimal("0.0015")
MARGIN = 10
MIN_ROOM = 40


def main() -> int:
    key, status_path = sys.argv[1], Path(sys.argv[2])
    d = json.loads(DEFS.read_bytes().decode("utf-8"))
    st = d["stages"][key]
    led = json.loads(status_path.read_bytes().decode("utf-8"))
    spendable = Decimal(led["projects"]["marianos"]["spendable_in_envelope_usd"])
    room = math.floor(spendable / RATE)
    print(f"{key}: defined ceiling {st['max_submissions']}, target {st.get('slice_target')}; envelope room "
          f"USD {spendable} = {room} submissions")
    if room < MIN_ROOM:
        print(f"REFUSED: {room} submissions left (< {MIN_ROOM}); no slice launched, the run stays resumable")
        return 3
    if st["max_submissions"] <= room:
        print("fits: unchanged")
        return 0
    st["max_submissions"] = room
    if st.get("slice_target"):
        st["slice_target"] = min(st["slice_target"], room - MARGIN)
    st["objective"] = (st["objective"] + f" Ceiling fitted to the envelope's room at launch ({room} submissions left; "
                       f"slice target {st.get('slice_target')}).")
    DEFS.write_bytes((json.dumps(d, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
    print(f"fitted: ceiling {room}, target {st.get('slice_target')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
