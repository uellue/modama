"""EMPAD extraction (spec formats/empad, "EMPAD metadata is extracted from the header", "Every element and attribute is kept")."""

from modama_crawler.walk import walk

from modama_formats_em.testing import described


def test_a_representative_empad_acquisition(collection_tests, tmp_path):
    (scan,) = described(collection_tests, "scan_v1_2_2", tmp_path)
    assert scan.description.startswith(
        "scan_resolution_x 32, scan_resolution_y 64, exposure_time 1 (unit unknown), "
        "2026-03-25T16:47:52.586728; "
    )
    assert scan.subjects == ["EMPAD", "4D-STEM"]
    # Only the header is read, not the raw file of 136 MB
    assert scan.bytes_read < 64 * 1024
    values = scan.dataset.extraction.extracted.values
    assert list(values) == ["original_metadata", "mapped_metadata"]
    assert len(values["original_metadata"]) == 80
    assert values["mapped_metadata"] == {
        "scan": [32, 64],
        "frame": [128, 128],
        "exposure_time": 1.0,
        "acquired": "2026-03-25T16:47:52.586728",
    }


def test_a_series(collection_tests, tmp_path):
    (series,) = described(collection_tests, "pair", tmp_path)
    assert series.description.startswith(
        "series_count 4, exposure_time 1.0 (unit unknown), 2022-05-02T17:28:39.775119; "
    )
    assert series.subjects == ["EMPAD"]


def test_every_element_and_attribute_as_found(collection_tests, tmp_path):
    (scan,) = described(collection_tests, "scan_v1_2_2", tmp_path)
    original = scan.dataset.extraction.extracted.values["original_metadata"]
    assert original["@name"] == "EMPAD_v1.2.2_x32_y64_size0.6"
    assert original["timestamp.@isoformat"] == "2026-03-25T16:47:52.586728"
    assert original["software_version"] == "1.2.2  (2021-08-20)"
    assert original["reconstructions.@Sentinel"] == "Test  "
    assert original["background_image.@absolute_filename"] == (
        " /home/empad/backgrounds/img_exp_1_frm_0_cnt_1000_0002"
    )
    # Siblings of one name are numbered from 1, as in XPath
    assert original["scan_parameters[1].@mode"] == "search"
    assert original["scan_parameters[2].scan_size"] == "0.6"
    assert original["reconstructions.reconstruction[7].@absolute_filename"].endswith(
        "scan_roi3_cw_annulus_x64_y64_ri20_ro50.tif"
    )
    # An element without siblings of its name has no number
    assert original["iom_measurements.full_scan_field_of_view.x"] == (
        "1.272412341559544e-06"
    )
    assert not any("iom_measurements[" in key for key in original)
    # The skip list: an element whose attributes or children carry its content
    # has no entry of its own
    assert "raw_file" not in original and original["raw_file.@filename"]
    assert "camserver_parameters" not in original


def edited(ct, fixture: str, workdir, old: bytes, new: bytes):
    """The extraction of a fixture's header with old replaced by new, once."""
    tree = ct.materialise(fixture, workdir)
    (xml,) = tree.glob("*.xml")
    xml.write_bytes(xml.read_bytes().replace(old, new, 1))
    (d,) = walk(tree, ct.collection.formats).datasets
    (empad,) = ct.collection.formats
    return empad.extract(d, str(tree))


def test_an_entry_nobody_has_seen_before(collection_tests, tmp_path):
    made_up = (
        b'<made_up_group made_up_attribute="a"><made_up_value>42 zz</made_up_value>'
        b"<made_up_empty/></made_up_group></root>"
    )
    extracted = edited(collection_tests, "scan_v1_2_2", tmp_path, b"</root>", made_up)
    original = extracted.values["original_metadata"]
    assert original["made_up_group.@made_up_attribute"] == "a"
    assert original["made_up_group.made_up_value"] == "42 zz"
    # Empty, and kept as empty text (decision 161)
    assert original["made_up_group.made_up_empty"] == ""
    assert len(original) == 83


def test_text_of_the_root_and_after_an_element(collection_tests, tmp_path):
    extracted = edited(
        collection_tests,
        "pair",
        tmp_path,
        b'<root name="SCA2_rings">',
        b'<root name="SCA2_rings">made-up root text',
    )
    assert extracted.values["original_metadata"]["#text"] == "made-up root text"
    made_up = b"<made_up>1</made_up> made-up tail </root>"
    tail = edited(collection_tests, "pair", tmp_path / "b", b"</root>", made_up)
    assert tail.values["original_metadata"]["made_up#tail"] == " made-up tail "


def test_pretty_printing_is_not_content(collection_tests, tmp_path):
    made_up = (
        b"<made_up_flag>\n        false\n      </made_up_flag>"
        b"<made_up_pair>\n  1   2\n</made_up_pair>"
        b"<made_up_spaces> a </made_up_spaces>"
        b"<made_up_tail>3</made_up_tail>\n  made-up tail\n</root>"
    )
    extracted = edited(collection_tests, "pair", tmp_path, b"</root>", made_up)
    original = extracted.values["original_metadata"]
    assert original["made_up_flag"] == "false"
    assert original["made_up_pair"] == "1   2"
    assert original["made_up_spaces"] == " a "
    assert original["made_up_tail#tail"] == "made-up tail"


def test_a_path_met_twice_keeps_both(collection_tests, tmp_path, caplog):
    # A tag name with a dot gives the path of an element and its child
    made_up = b"<a><b>1</b></a><a.b>2</a.b></root>"
    extracted = edited(collection_tests, "pair", tmp_path, b"</root>", made_up)
    original = extracted.values["original_metadata"]
    assert (original["a.b"], original["a.b#2"]) == ("1", "2")
    (warning,) = caplog.records
    assert "a.b twice" in warning.getMessage()


def test_a_value_not_suitable_for_text_is_left_out(collection_tests, tmp_path):
    made_up = b"<made_up_long>" + b"x" * 1001 + b"</made_up_long></root>"
    extracted = edited(collection_tests, "pair", tmp_path, b"</root>", made_up)
    original = extracted.values["original_metadata"]
    assert "made_up_long" not in original
    assert len(original) == 19


def test_a_timestamp_in_another_form(collection_tests, tmp_path, caplog):
    extracted = edited(
        collection_tests,
        "pair",
        tmp_path,
        b'isoformat="2022-05-02T17:28:39.775119"',
        b'isoformat="May 2, 2022"',
    )
    assert extracted.summary[-1] == "May 2, 2022"
    assert "acquired" not in extracted.values["mapped_metadata"]
    (warning,) = caplog.records
    assert "'May 2, 2022'" in warning.getMessage()


def test_empty_text_is_not_a_mapped_value(collection_tests, tmp_path):
    extracted = edited(
        collection_tests,
        "pair",
        tmp_path,
        b"<exposure_time>1.0</exposure_time>",
        b"<exposure_time></exposure_time>",
    )
    assert "exposure_time" not in extracted.values["mapped_metadata"]
    assert extracted.values["original_metadata"]["exposure_time"] == ""
    assert not any(s.startswith("exposure_time") for s in extracted.summary)
