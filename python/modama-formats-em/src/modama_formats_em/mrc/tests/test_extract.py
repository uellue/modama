"""MRC recognition and extraction, one test per scenario of spec formats/mrc (change em-mrc)."""

import json
import logging
import resource
from pathlib import Path

import numpy as np
from modama_crawler.testing import bytes_read, recognise
from modama_crawler.walk import walk

from modama_formats_em.mrc import HEADER_BYTES

from .generate import write

EPU = "FoilHole_4551046_Data_4541935_4541937_20220507_103020.mrc"
FEI2_RECORD = 888
# Byte offsets of main header words (MRC2014): mx, nsymbt, rms
MX, NSYMBT, RMS = 28, 92, 216


def extracted(ct, tree: Path, name: str | None = None):
    """The extraction of the one dataset in `tree`, or of the one named `name`."""
    datasets = walk(tree, ct.collection.formats).datasets
    (d,) = [d for d in datasets if name is None or d.anchor == "/" + name]
    (fmt,) = ct.collection.formats
    return fmt.extract(d, str(tree))


def patched(path: Path, offset: int, data: bytes) -> None:
    """Overwrite bytes of a fixture's copy in place."""
    with path.open("r+b") as f:
        f.seek(offset)
        f.write(data)


def one_file(tmp_path: Path, **kwargs) -> Path:
    tree = tmp_path / "tree"
    tree.mkdir()
    write(tree / "one.mrc", np.zeros((4, 8, 8), dtype=np.float32), **kwargs)
    return tree


# Requirement: MRC files are datasets of em/mrc


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


def test_files_of_an_epu_session(collection_tests, tmp_path):
    result = recognise(collection_tests, "epu_falcon", tmp_path)
    assert sorted((d.anchor, d.format) for d in result.datasets) == [
        ("/" + EPU, "em/mrc"),
        ("/GridSquare_20220505_150431.mrc", "em/mrc"),
    ]


def test_a_renamed_copy(collection_tests, tmp_path):
    tree = collection_tests.materialise("emdb_map", tmp_path)
    (tree / "EMD-3197.map").rename(tree / "EMD-3197")
    (d,) = walk(tree, collection_tests.collection.formats).datasets
    assert (d.anchor, d.format) == ("/EMD-3197", "em/mrc")


# Requirement: A name that lies falls back to the content's type


def test_a_linker_map_named_map(collection_tests, tmp_path):
    (d,) = recognise(collection_tests, "misnamed", tmp_path).datasets
    assert (d.anchor, d.type, d.format) == ("/program.map", "text/plain", "")
    assert "no MAP at byte 208" in d.basis


# Requirement: The MRC header is extracted


def test_the_header_of_a_map_from_emdb(collection_tests, tmp_path):
    tree = collection_tests.materialise("emdb_map", tmp_path)
    result = extracted(collection_tests, tree)
    assert result.summary == [
        "nx 20",
        "ny 20",
        "nz 20",
        "mode 2",
        "::::EMDATABANK.org::::EMD-3197::::",
    ]
    original = result.values["original_metadata"]
    assert original["machst"] == "0x44 0x41 0x00 0x00"
    assert original["map"] == "MAP "
    assert original["cella.x"] == 228.0
    assert original["label[2]"] == ""
    assert "extra1" not in original and "extra2" not in original
    mapped = result.values["mapped_metadata"]
    assert mapped["kind"] == "volume"
    assert mapped["data_type"] == "float32"
    # mrcfile's float32 as it widens it (TEMPLATE.md; @weber 309)
    assert mapped["voxel_size"] == [11.399999618530273] * 3


def test_a_tomogram_from_emdb(collection_tests, tmp_path):
    tree = collection_tests.materialise("emdb_tomogram", tmp_path)
    result = extracted(collection_tests, tree)
    assert result.summary == [
        "nx 700",
        "ny 700",
        "nz 357",
        "mode 0",
        "::::EMDATABANK.org::::EMD-66908::::",
    ]
    mapped = result.values["mapped_metadata"]
    assert (mapped["kind"], mapped["data_type"]) == ("volume", "int8")


def test_a_particle_stack(collection_tests, tmp_path):
    tree = collection_tests.materialise("particle_stack", tmp_path)
    result = extracted(collection_tests, tree)
    assert result.summary == ["nx 540", "ny 540", "nz 69", "mode 2"]
    assert result.values["mapped_metadata"]["kind"] == "image stack"


def test_an_image_stack(collection_tests, tmp_path):
    tree = collection_tests.materialise("written_by_mrcfile", tmp_path)
    result = extracted(collection_tests, tree, "stack.mrcs")
    assert result.values["mapped_metadata"]["kind"] == "image stack"


def test_one_image(collection_tests, tmp_path):
    tree = collection_tests.materialise("written_by_mrcfile", tmp_path)
    result = extracted(collection_tests, tree, "image.mrc")
    assert result.values["mapped_metadata"]["kind"] == "image"


def test_values_that_json_cannot_hold(collection_tests, tmp_path):
    tree = collection_tests.materialise("emdb_map", tmp_path)
    patched(tree / "EMD-3197.map", RMS, np.float32("nan").tobytes())
    patched(tree / "EMD-3197.map", MX, np.int32(0).tobytes())
    result = extracted(collection_tests, tree)
    assert result.values["original_metadata"]["rms"] == "nan"
    assert result.values["original_metadata"]["mx"] == 0
    assert result.values["mapped_metadata"]["voxel_size"][0] == "inf"
    json.dumps(result.values, allow_nan=False)  # as the extraction stores it


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


# Requirement: The first record of an FEI extended header is extracted


def test_an_epu_micrograph_from_a_falcon_camera(collection_tests, tmp_path):
    tree = collection_tests.materialise("epu_falcon", tmp_path)
    result = extracted(collection_tests, tree, EPU)
    assert result.summary == [
        "nx 4096",
        "ny 4096",
        "nz 1",
        "mode 6",
        "TITAN52336460",
        "HT 300000.0 (unit unknown)",
        "Pixel size X 8.674088530780111e-11 (unit unknown)",
        "BM-Falcon",
    ]
    original = result.values["original_metadata"]
    assert original["extended_header.Application"] == "EPU"
    assert original["extended_header.Application version"] == "2.12.1.2782"
    # The file has b"BM-Falcon\x00fC": the text ends at its first NUL
    assert original["extended_header.Detector commercial name"] == "BM-Falcon"
    assert original["extended_header.Direct detector electron counting"] is True
    assert original["extended_header.Bitmask 1"] == 4294955007
    assert "extended_header.Unused range" not in original
    assert "extended_header.Camera param reserved 0" not in original


def test_an_fei1_header_from_epu_1_2(collection_tests, tmp_path):
    tree = collection_tests.materialise("fei1", tmp_path)
    result = extracted(collection_tests, tree)
    assert result.summary == [
        "nx 3710",
        "ny 3838",
        "nz 1",
        "mode 6",
        "TITAN52336320",
        "HT 300000.0 (unit unknown)",
        "Pixel size X 8.537755225024313e-11 (unit unknown)",
        "EF-CCD",
    ]
    original = result.values["original_metadata"]
    assert original["extended_header.Application"] == "Fei EPU"
    assert "extended_header.Scan rotation" not in original


def test_an_epu_movie_with_nearly_empty_records(collection_tests, tmp_path):
    tree = collection_tests.materialise("epu_movie", tmp_path)
    result = extracted(collection_tests, tree)
    assert result.summary == ["nx 4096", "ny 4096", "nz 42", "mode 1"]
    original = result.values["original_metadata"]
    assert original["extended_header.Timestamp"] == 44701.72802132257
    assert original["extended_header.Acquisition time stamp"] == 1653085701042270
    assert original["extended_header.HT"] == 0.0


def test_an_extended_header_that_is_not_of_its_type(collection_tests, tmp_path, caplog):
    tree = collection_tests.materialise("epu_falcon", tmp_path)
    with (tree / EPU).open("r+b") as f:
        f.seek(HEADER_BYTES)
        f.write(b"\0\0\0\0")  # the record's Metadata size
    with caplog.at_level(logging.WARNING, logger="modama_formats_em.mrc"):
        result = extracted(collection_tests, tree, EPU)
    original = result.values["original_metadata"]
    assert original["nx"] == 4096
    assert not any(k.startswith("extended_header.") for k in original)
    assert "extended header is not FEI2" in caplog.text


# Requirement: Only the headers are read


def test_only_the_header_is_read(collection_tests, tmp_path):
    tree = one_file(tmp_path)
    with (tree / "one.mrc").open("ab") as f:
        f.truncate(1 << 30)  # 1 GiB, sparse
    extracted(collection_tests, tree)  # once first: imports count too
    _, read = bytes_read(lambda: extracted(collection_tests, tree))
    assert read <= HEADER_BYTES + 4096


def test_only_the_first_record_is_read(collection_tests, tmp_path):
    tree = collection_tests.materialise("epu_falcon", tmp_path)
    (tree / "GridSquare_20220505_150431.mrc").unlink()
    # The fixture is cut after the first record; its header says 909312 bytes of
    # extended header, as EPU writes it, then the data: 1 GiB, sparse
    with (tree / EPU).open("ab") as f:
        f.truncate(1 << 30)
    extracted(collection_tests, tree)  # once first: imports count too
    _, read = bytes_read(lambda: extracted(collection_tests, tree))
    assert read <= HEADER_BYTES + FEI2_RECORD + 4096


def test_an_extended_header_of_2_gib(collection_tests, tmp_path):
    tree = collection_tests.materialise("epu_falcon", tmp_path)
    patched(tree / EPU, NSYMBT, np.int32(2**31 - 1).tobytes())
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # KiB
    result = extracted(collection_tests, tree, EPU)
    grown = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - peak
    assert grown < 64 * 1024, f"peak memory grew by {grown} KiB"
    original = result.values["original_metadata"]
    assert original["nsymbt"] == 2**31 - 1
    assert original["extended_header.Application"] == "EPU"


def test_a_negative_extended_header_size(collection_tests, tmp_path):
    tree = collection_tests.materialise("epu_falcon", tmp_path)
    patched(tree / EPU, NSYMBT, np.int32(-5).tobytes())
    original = extracted(collection_tests, tree, EPU).values["original_metadata"]
    assert (original["nx"], original["nsymbt"]) == (4096, -5)
    assert not any(k.startswith("extended_header.") for k in original)
