# Spec Delta

## ADDED Requirements

### Requirement: EMPAD metadata is extracted from the header
For an EMPAD dataset, the extractor SHALL keep as values, first (`original_metadata`, decision 230), every element and attribute of the XML header as found (requirement "Every element and attribute is kept"); second (`mapped_metadata`), what it computes: the frame count of a series or the scan size (in RosettaSciIO 0.15.0's order: `scan_parameters.series_count`, then `pix_x` and `pix_y`, then the raw file's name `scan_x<n>_y<n>.raw`), the frame size (128×128, the detector's, not in the header), the exposure time as a number and the acquisition time. The description SHALL start with the summary line: the series count, the scan size and the exposure time, then the timestamp's `isoformat`, as the header writes them after the element's or attribute's name, a value computed after its name in `mapped_metadata`; the exposure time with `(unit unknown)`, as no source gives its unit (README, "Values and units"); no other word or unit of ours, no conversion (decision 230).

#### Scenario: A representative EMPAD acquisition
- **WHEN** a representative EMPAD header with its raw file is crawled (`scan_v1_2_2`)
- **THEN** its record's description starts with `scan 32×64, exposure_time 1 (unit unknown), 2026-03-25T16:47:52.586728; `
- **AND** its values carry the header's 80 entries in `original_metadata` and `scan` [32, 64], `frame` [128, 128], `exposure_time` 1.0 and `acquired` `2026-03-25T16:47:52.586728` in `mapped_metadata`

#### Scenario: A series
- **WHEN** an EMPAD header has `scan_parameters.series_count` `4` and `exposure_time` `1.0` (`pair`)
- **THEN** its record's description starts with `series_count 4, exposure_time 1.0 (unit unknown), 2022-05-02T17:28:39.775119; `

### Requirement: Every element and attribute is kept
The extractor SHALL keep every attribute and every element's text of the header in `original_metadata`, flat, under its path below the root element, as text as the file writes it (spaces included), and SHALL NOT keep a list of wanted elements (@weber, 2026-11-12: "we don't keep a positive list, but a negative 'skip these' list"). The path joins element names with dots; as in XPath, an attribute is `@name` and an element with siblings of its name is numbered from 1 (`scan_parameters[2].scan_size`). An element without children and attributes keeps its text, an empty one as empty text (decision 161). The skip list: the whitespace around child elements, and the empty text of an element whose attributes or children carry its content (`<raw_file filename="scan_x32_y64.raw"/>` gives `raw_file.@filename` and no `raw_file`; `<camserver_parameters>` gives its children only).

#### Scenario: Elements and attributes as found
- **WHEN** the header of `scan_v1_2_2` is extracted
- **THEN** `original_metadata` has `@name` `EMPAD_v1.2.2_x32_y64_size0.6`, `timestamp.@isoformat` `2026-03-25T16:47:52.586728`, `software_version` `1.2.2  (2021-08-20)`, `reconstructions.@Sentinel` `Test  ` and `background_image.@absolute_filename` ` /home/empad/backgrounds/img_exp_1_frm_0_cnt_1000_0002`, spaces as written
- **AND** the two `scan_parameters` as `scan_parameters[1].@mode` `search` and `scan_parameters[2].scan_size` `0.6`, the seven reconstructions as `reconstructions.reconstruction[1]` to `[7]`
- **AND** no entry `raw_file` or `camserver_parameters` of its own

#### Scenario: An entry nobody has seen before
- **WHEN** a header has the made-up element `<made_up_group made_up_attribute="a"><made_up_value>42 zz</made_up_value><made_up_empty/></made_up_group>`
- **THEN** `original_metadata` has `made_up_group.@made_up_attribute` `a`, `made_up_group.made_up_value` `42 zz` and `made_up_group.made_up_empty` as empty text, next to the header's other entries
