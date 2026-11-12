"""EMPAD extraction (spec formats/empad, "EMPAD metadata is extracted from the header", "Every element and attribute is kept")."""

from modama_crawler.walk import walk

from modama_formats_em.testing import described


def test_a_representative_empad_acquisition(collection_tests, tmp_path):
    (scan,) = described(collection_tests, "scan_v1_2_2", tmp_path)
    assert scan.description.startswith(
        "scan 32×64, exposure_time 1 (unit unknown), 2026-03-25T16:47:52.586728; "
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
    assert original["iom_measurements.full_scan_field_of_view.x"] == (
        "1.272412341559544e-06"
    )
    # The skip list: an element whose attributes or children carry its content
    # has no entry of its own
    assert "raw_file" not in original and original["raw_file.@filename"]
    assert "camserver_parameters" not in original


def test_an_entry_nobody_has_seen_before(collection_tests, tmp_path):
    tree = collection_tests.materialise("scan_v1_2_2", tmp_path)
    (xml,) = tree.glob("*.xml")
    made_up = (
        b'<made_up_group made_up_attribute="a"><made_up_value>42 zz</made_up_value>'
        b"<made_up_empty/></made_up_group></root>"
    )
    xml.write_bytes(xml.read_bytes().replace(b"</root>", made_up))
    (d,) = walk(tree, collection_tests.collection.formats).datasets
    (empad,) = collection_tests.collection.formats
    original = empad.extract(d, str(tree)).values["original_metadata"]
    assert original["made_up_group.@made_up_attribute"] == "a"
    assert original["made_up_group.made_up_value"] == "42 zz"
    # Empty, and kept as empty text (decision 161)
    assert original["made_up_group.made_up_empty"] == ""
    assert len(original) == 83
