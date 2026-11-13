"""MRC recognition and extraction, one test per scenario of spec formats/mrc (change em-mrc)."""

from pathlib import Path

import numpy as np
from modama_crawler.testing import recognise
from modama_crawler.walk import walk

from modama_formats_em.mrc import HEADER_BYTES
from modama_formats_em.testing import rchar

from .generate import write


def extracted(ct, tree: Path):
    (d,) = walk(tree, ct.collection.formats).datasets
    (fmt,) = ct.collection.formats
    return fmt.extract(d, str(tree))


def one_file(tmp_path: Path, **kwargs) -> Path:
    tree = tmp_path / "tree"
    tree.mkdir()
    write(tree / "one.mrc", np.zeros((4, 8, 8), dtype=np.float32), **kwargs)
    return tree


def test_a_map_from_emdb(collection_tests, tmp_path):
    (d,) = recognise(collection_tests, "emdb_map", tmp_path).datasets
    assert (d.anchor, d.type, d.format) == (
        "/EMD-3197.map",
        "application/x.mrc",
        "em/mrc",
    )


def test_files_written_by_mrcfile(collection_tests, tmp_path):
    result = recognise(collection_tests, "written_by_mrcfile", tmp_path)
    assert sorted((d.anchor, d.format) for d in result.datasets) == [
        ("/image.mrc", "em/mrc"),
        ("/stack.mrcs", "em/mrc"),
    ]


def test_a_renamed_copy(collection_tests, tmp_path):
    tree = collection_tests.materialise("emdb_map", tmp_path)
    (tree / "EMD-3197.map").rename(tree / "EMD-3197")
    (d,) = walk(tree, collection_tests.collection.formats).datasets
    assert (d.anchor, d.format) == ("/EMD-3197", "em/mrc")


def test_a_linker_map_named_map(collection_tests, tmp_path):
    (d,) = recognise(collection_tests, "misnamed", tmp_path).datasets
    assert (d.anchor, d.type, d.format) == ("/program.map", "text/plain", "")
    assert "no MAP at byte 208" in d.basis


def test_the_header_of_a_map_from_emdb(collection_tests, tmp_path):
    tree = collection_tests.materialise("emdb_map", tmp_path)
    result = extracted(collection_tests, tree)
    assert result.summary == [
        "nx 20",
        "ny 20",
        "nz 20",
        "mode 2",
        "ispg 1",
        "cella.x 228.0",
        "cella.y 228.0",
        "cella.z 228.0",
        "mx 20",
        "my 20",
        "mz 20",
        "::::EMDATABANK.org::::EMD-3197::::",
    ]
    original = result.values["original_metadata"]
    assert original["machst"] == "0x44 0x41 0x00 0x00"
    assert original["map"] == "MAP "
    assert original["label[2]"] == ""
    assert "extra1" not in original and "extra2" not in original
    mapped = result.values["mapped_metadata"]
    assert mapped["kind"] == "volume"
    assert mapped["data_type"] == "float32"
    # mrcfile's float32, unrounded (modama-formats-em README, "Values and units")
    assert mapped["voxel_size"] == [11.399999618530273] * 3


def test_an_image_stack(collection_tests, tmp_path):
    tree = collection_tests.materialise("written_by_mrcfile", tmp_path)
    (tree / "image.mrc").unlink()
    result = extracted(collection_tests, tree)
    assert result.values["mapped_metadata"]["kind"] == "image stack"
    assert "ispg 0" in result.summary


def test_one_image(collection_tests, tmp_path):
    tree = collection_tests.materialise("written_by_mrcfile", tmp_path)
    (tree / "stack.mrcs").unlink()
    result = extracted(collection_tests, tree)
    assert result.values["mapped_metadata"]["kind"] == "image"


def test_a_label_nobody_has_seen_before(collection_tests, tmp_path):
    tree = one_file(tmp_path, labels=["made-up label 42 zz"])
    original = extracted(collection_tests, tree).values["original_metadata"]
    assert original["label[1]"] == "made-up label 42 zz"


def test_a_credential_in_a_label(collection_tests, tmp_path):
    tree = one_file(tmp_path, labels=["--password hunter2"])
    result = extracted(collection_tests, tree)
    assert "label[1]" not in result.values["original_metadata"]
    assert not any("hunter2" in p for p in result.summary)
    assert result.values["mapped_metadata"]["credentials_left_out"] == 1


def test_only_the_header_is_read(collection_tests, tmp_path):
    tree = one_file(tmp_path)
    with (tree / "one.mrc").open("ab") as f:
        f.truncate(1 << 30)  # 1 GiB, sparse
    extracted(collection_tests, tree)  # once first: imports count too
    before = rchar()
    extracted(collection_tests, tree)
    assert rchar() - before <= HEADER_BYTES + 4096
