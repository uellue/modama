"""Synthetic record texts for the embedding benchmark, as the warehouse embeds them: title, subjects and
descriptions joined by spaces (metadata-warehouse, `get_embedding_text_from_fields`).

  python3 gen_texts.py OUT.jsonl [--n 20000] [--long-share 0.12] [--long-words 480] [--seed 1]

A short text is a title, one to four subjects and a description of one sentence or the crawler's
"plain text document, 1 file, ..." (tens of tokens). A long text has a description of LONG_WORDS words or
more, enough to reach the model's 512 tokens (bench.py counts the tokens with the model's tokenizer and
reports them). LONG_SHARE of the texts are long, placed at random. Deterministic: the same arguments give
the same file. Standard library only. One JSON object per line: {"id", "kind": "short"|"long", "text"}.
"""

import argparse
import json
import random
import statistics
import sys

SAMPLES = [
    "ferritin",
    "apoferritin",
    "gold nanoparticles",
    "graphene",
    "MoS2",
    "perovskite",
    "SrTiO3",
    "zeolite",
    "lamella",
    "Pt/C catalyst",
    "LiNiO2 cathode",
    "GaN nanowires",
]
METHODS = [
    "HAADF-STEM",
    "STEM",
    "TEM",
    "EELS",
    "EDX",
    "4D-STEM",
    "electron diffraction",
    "electron tomography",
    "off-axis holography",
    "cryo-EM",
]
SUBJECTS = [
    "electron microscopy",
    "materials science",
    "condensed matter physics",
    "spectroscopy",
    "crystallography",
    "structural biology",
    "nanotechnology",
    "catalysis",
    "battery materials",
    "semiconductors",
]
WORDS = [
    "beam",
    "dose",
    "tilt",
    "focus",
    "aberration",
    "detector",
    "camera",
    "frame",
    "series",
    "drift",
    "lattice",
    "defect",
    "interface",
    "grain",
    "vacuum",
    "specimen",
    "holder",
    "spectrum",
    "region",
    "particle",
    "thickness",
    "calibration",
    "alignment",
]
SENTENCES = [
    "The {s} was imaged by {m} at {kv} kV with a {w} {w2} of {n} frames.",
    "A total dose of {d} e/A^2 was distributed over {n} frames to limit {w} damage.",
    "Images were recorded on a direct electron detector at a pixel size of {p} A after {w} correction.",
    "The {w} was corrected by cross-correlation before the {w2} series was aligned and summed.",
    "Regions of interest near the {w} of the {s} were selected for {m} at a convergence angle of {a} mrad.",
    "The data set contains {n} raw frames, the gain reference and the {w2} parameters in the metadata file.",
    "Measurements were repeated at {kv} kV to compare the {w} with earlier results on {s}.",
    "Sample preparation followed the protocol for {s}, with a final {w} of about {p} nm.",
]


def sentence(rng: random.Random) -> str:
    return rng.choice(SENTENCES).format(
        s=rng.choice(SAMPLES),
        m=rng.choice(METHODS),
        w=rng.choice(WORDS),
        w2=rng.choice(WORDS),
        kv=rng.choice([60, 80, 120, 200, 300]),
        n=rng.randint(10, 4000),
        d=rng.randint(20, 120),
        p=round(rng.uniform(0.2, 3.0), 2),
        a=round(rng.uniform(10, 35), 1),
    )


def record(rng: random.Random, i: int, long: bool, long_words: int) -> str:
    sample, method = rng.choice(SAMPLES), rng.choice(METHODS)
    if rng.random() < 0.5:
        title = (
            f"{method} of {sample}, {rng.choice(WORDS)} {rng.choice(WORDS)} series {i}"
        )
    else:  # the crawler's records: the path as title
        title = f"{sample.replace(' ', '-')}-{rng.randrange(50):02d}/{method.lower()}_{rng.choice(WORDS)}_{i:06d}.txt"
    subjects = rng.sample(SUBJECTS, rng.randint(1, 4))
    if long:
        parts: list[str] = []
        while sum(len(p.split()) for p in parts) < long_words:
            parts.append(sentence(rng))
        description = " ".join(parts)
    elif rng.random() < 0.5:
        description = sentence(rng)
    else:
        description = f"plain text document, 1 file, {rng.randint(30, 300000)} B, in {sample.replace(' ', '-')}/"
    return " ".join([title, *subjects, description])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out", help="JSONL file to write")
    ap.add_argument(
        "--n", type=int, default=20000, help="number of texts (default 20000)"
    )
    ap.add_argument(
        "--long-share",
        type=float,
        default=0.12,
        help="share of long texts, 0 to 1 (default 0.12)",
    )
    ap.add_argument(
        "--long-words",
        type=int,
        default=480,
        help="words in a long description (default 480)",
    )
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    if not 0 <= a.long_share <= 1:
        ap.error("--long-share must be between 0 and 1")
    rng = random.Random(a.seed)
    chars = []
    longs = 0
    with open(a.out, "w") as f:
        for i in range(a.n):
            long = rng.random() < a.long_share
            text = record(rng, i, long, a.long_words)
            longs += long
            chars.append(len(text))
            f.write(
                json.dumps({"id": i, "kind": "long" if long else "short", "text": text})
                + "\n"
            )
    print(
        f"{a.out}: {a.n} texts, {longs} long; characters min {min(chars)}, median {statistics.median(chars):.0f}, "
        f"max {max(chars)}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
