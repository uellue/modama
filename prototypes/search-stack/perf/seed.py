"""Synthetic test files for the indexing benchmark: N small text files in 50 folders under /data/perf-seed/.

Run inside the crawler (test deployment only; the data volume `testdata` is mounted read-write there):
  docker compose exec -T crawler python3 - N < perf/seed.py
Deterministic (fixed seed): the same N gives the same tree. Replaces an earlier /data/perf-seed/.
"""

import random
import shutil
import sys
from pathlib import Path

ROOT = Path("/data/perf-seed")
FOLDERS = 50
SAMPLES = "ferritin gold-nanoparticle graphene MoS2 perovskite SrTiO3 zeolite apoferritin lamella catalyst".split()
METHODS = (
    "haadf stem tem eels edx 4dstem diffraction tomography holography cryo".split()
)
WORDS = (
    "beam dose sample tilt focus aberration detector camera frame series drift lattice defect interface grain "
    "vacuum specimen holder voltage current spectrum map region particle thickness calibration alignment"
).split()

n = int(sys.argv[1])
rng = random.Random(20261111)
shutil.rmtree(ROOT, ignore_errors=True)
for i in range(n):
    k = i % FOLDERS
    folder = ROOT / f"{SAMPLES[k % len(SAMPLES)]}-{k:02d}"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{rng.choice(METHODS)}_{rng.choice(WORDS)}_{i:06d}.txt"
    (folder / name).write_text(
        " ".join(rng.choices(WORDS, k=rng.randint(5, 40))) + "\n"
    )
print(
    f"{n} files in {len({p.parent for p in ROOT.rglob('*.txt')})} folders under {ROOT}"
)
