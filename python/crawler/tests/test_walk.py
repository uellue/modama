from pathlib import Path


def test_walk(tmp_path):
    listing = [
        ("a/", "d"),
        ("a/a.txt", "f"),
        ("a/b.txt", "f"),
        ("a/d.txt", "f"),
        ("b/", "d"),
        ("b/a.txt", "f"),
        ("b/b.txt", "f"),
        ("b/d.txt", "f"),
        ("a.txt", "f"),
        ("b.txt", "f"),
        ("d.txt", "f"),
    ]

    for path, kind in listing:
        if kind == "f":
            (tmp_path / Path(path)).touch(exist_ok=True)
        elif kind == "d":
            (tmp_path / Path(path)).mkdir(exist_ok=True)
        else:
            raise RuntimeError("WTF")
    ...
