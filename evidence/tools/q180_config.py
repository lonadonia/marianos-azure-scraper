"""Narrow the qualification's configuration copy (C:/m6/q180/config) to TEST_PLAN_180 Amendment 3's scope."""
from pathlib import Path

p = Path(r"C:\m6\q180\config\collector.yaml")
t = p.read_bytes().decode("utf-8")
block_start = t.index("  marianos-53100502-pickup:")
block_end = t.index("  marianos-53100503-instore:")
block = t[block_start:block_end]
reps = [
    (
        "    categories: []                 # CSV row numbers counted from 0 (Coupons = 0, Produce = 1); empty = every row\n",
        "    categories: [23, 24, 25, 26]   # QUALIFICATION SCOPE (TEST_PLAN_180 Amendment 3), not full coverage\n",
    ),
    (
        "      max_credits_per_run: null\n",
        "      max_credits_per_run: 95      # qualification: Oxylabs submissions per run (Amendment 3)\n",
    ),
]
for a, b in reps:
    assert block.count(a) == 1, a
    block = block.replace(a, b)
t = t[:block_start] + block + t[block_end:]
p.write_bytes(t.encode("utf-8"))
print("ok")
