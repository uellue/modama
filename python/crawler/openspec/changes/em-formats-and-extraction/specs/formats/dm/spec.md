# Spec Delta

## Purpose

Gatan Digital Micrograph images (DM3 and DM4), the largest population of single-file electron microscopy data at ER-C, recognised by content and described by the acquisition values in their tags.

## ADDED Requirements

### Requirement: DM3 and DM4 files are recognised by content
A file whose header is that of a Digital Micrograph file of version 3 or 4 SHALL be a single-file dataset of the matching DM type, whatever its name; a file named `.dm3` or `.dm4` without that header SHALL NOT get the DM type.

#### Scenario: A DM4 file from an instrument
- **WHEN** a representative DM4 file is crawled
- **THEN** it is one dataset of the DM4 type

#### Scenario: A misnamed file
- **WHEN** a text file is named `image.dm4`
- **THEN** it does not get the DM4 type

### Requirement: DM metadata is extracted from the tags
For a DM3 or DM4 dataset, the extractor SHALL keep as values every tag of RosettaSciIO's `original_metadata` but the skip list, flat under its dotted path (`original_metadata`, decision 230), then the reader's mapped metadata and axes (`mapped_metadata`, `axes`). The description SHALL start with the summary line; the subjects SHALL carry the reader's microscope, acquisition mode and signal type, then the imaging mode and the camera model (decision 235).

#### Scenario: Empty tags and infinities
- **WHEN** a tag is empty, or a number is infinite (`Exposure Live Time` `inf`)
- **THEN** the empty tag stays as `[]` (decision 161), the infinity is stored as Python writes it, `inf`, as JSON holds none

#### Scenario: Stored with the dataset, not in the record
- **WHEN** a DM image is crawled (`cl_image_dm4`)
- **THEN** its values are stored with its dataset, and its record's description holds the summary line only, not the tags (`Acquisition.Monarc Spectrometer.Grating` is in the values, `Monarc` not in the description). The storage cuts the values as every extraction: at most 1,000 entries in all, for all tags together (the most in RosettaSciIO's 110 DM test files: 403, none of them cut)

#### Scenario: No unit the reader does not give
- **WHEN** a DM file's tags give the voltage as `Microscope Info.Formatted Voltage` `300kV` and as `Microscope Info.Voltage` `300000.0`
- **THEN** the description shows `300kV` as the tag gives it, and no value converted to another unit, neither `300000.0` nor RosettaSciIO's `beam_energy` `300.0` (README, "Values and units")

#### Scenario: A representative DM4 image
- **WHEN** a representative DM4 file with known tags is crawled (`cl_image_dm4`)
- **THEN** its record's description starts with `IMAGING, SCANNING, SEM, 3kV, 2.5kx, STEM Camera Length 1.0, DigiScan, y 2, x 2, scale 18.325349807739258 µm, 5/14/2021, 11:41:07 AM; `, its subjects are the format's name, `Zeiss SEM COM`, `SEM`, `CL` and `IMAGING`, its values carry 120 tags (the image's 101 but the Session Info form, its image data's calibrations, dimensions, type, its name and identifier) and RosettaSciIO's mapped metadata in a section of its own

#### Scenario: The data image, not the thumbnail
- **WHEN** a DM file's `ImageList` holds the thumbnail first (named by `Thumbnails`) and the data image second
- **THEN** the values carry the data image's tags, the image RosettaSciIO's reader takes (the first in `ImageList` that `Thumbnails` does not name), under `ImageList.TagGroup0`, as RosettaSciIO's `original_metadata` holds it

#### Scenario: The tags, not the image data
- **WHEN** a DM file's metadata is extracted
- **THEN** the extractor reads its tags and skips the image data, in reads no larger than NFS's read size, so that a file on NFS costs about its tags and not a buffer of up to 1 MiB per seek

#### Scenario: An RGBA image
- **WHEN** a DM4 file holds an RGBA image, which RosettaSciIO does not load lazily
- **THEN** its tags are extracted as for any other image

### Requirement: What is left out
The values of a DM image and of a K2IS tag file, and a workspace's description, SHALL keep every tag but one skip list, defined once (`dm.skipped`; decisions 129, 235): GMS's user-interface settings by path pattern (`dm.SETTINGS`) or the image viewer's class, and values not suitable for text (`values.textual`: lists over 16 items, strings over 1,000 characters or with control characters, bytes, an unread array). A tag never seen before SHALL be kept.

#### Scenario: User-interface settings are left out of the values
- **WHEN** a DM image's `ImageTags` hold the image viewer's group (`Acquisition.Parameters.Objects.TagGroup1` of class `cm_stdviewerimagedisplayer`, with `Window Relative Position` and `Zoom`) next to processing objects (`Objects.TagGroup0` of class `cm_imgproc_finalcombine`, `TagGroup2` of class `cm_imgproc_histogram`), and the Session Info form (`Session Info.Items`)
- **THEN** the values carry the processing objects' tags and `Session Info.Specimen`, and no tag of the viewer's group or of `Session Info.Items`

#### Scenario: The older Session Info form
- **WHEN** a DM image holds the form under `Microscope Info.Items`, with `Microscope Info.Specimen` `FeGe lamella`, as older GMS writes it
- **THEN** no tag of the form is in the values, and the summary line ends with `FeGe lamella`

#### Scenario: What GMS keeps outside the image's tags
- **WHEN** a DM file holds, at the root of its tags, the document's, page's and window's settings and bookkeeping (`ApplicationBounds`, `DocumentObjectList` with its `ImageDisplayInfo`, `HasWindowPosition`, `Image Behavior`, `ImageSourceList`, `InImageMode`, `LayoutType`, `MinVersionList`, `NextDocumentObjectID`, `Page Behavior`, `PageSetup`, `SentinelList`, `Thumbnails`, `WindowPosition`), and the image data not read (`ImageData.Data`)
- **THEN** none of them is in the values; the image's name, its data's calibrations and dimensions are (`ImageList.TagGroup0.ImageData.Calibrations.Dimension.TagGroup0.Units` `µm`)

#### Scenario: Large arrays are left out
- **WHEN** a DM image holds a CL detector's `Saturation fraction` of 67 values (RosettaSciIO's `2D__test-MonarcCL_spectrum-SI.dm4`; 16,384 and 28,776 in others) and the camera's `Active Size (pixels)` of 2
- **THEN** the values hold the active size and not the saturation fraction, neither in `original_metadata` nor where RosettaSciIO maps it (`mapped_metadata`). The limit of 16 lies between the longest list of values about the data seen, 4 items, and the shortest blob or array, 60 (`PageSetup.Win32`, a Windows structure as bytes)

#### Scenario: A tag never seen before
- **WHEN** a DM image holds a tag group of a vendor nobody has seen, `Foo Vendor.New Setting` `7`
- **THEN** the values hold `Foo Vendor.New Setting` `7`

### Requirement: The summary line of a DM file's tags
For a DM image (its `ImageTags`, or a stack builder's `source.Tags at creation`, as RosettaSciIO's mapping reads them) and a K2IS tag file (its tags), the extractor SHALL build the summary line from a chosen list of tags (`dm.HEADLINE`), the only positive list, by nature: their values where present and not empty, in the list's order, as the file holds them, a value repeated only once (Imaging and Operation Mode both `Lorentz`). Choosing the tags is the only editorial step (decision 230).

#### Scenario: The chosen tags
- **WHEN** a summary line is built
- **THEN** it holds the values of, in this order: `Microscope Info.Imaging Mode`, `Operation Mode`, `Illumination Mode`, `Formatted Voltage` (else `Voltage`), `Formatted Indicated Mag` (else `Indicated Magnification`), `STEM Camera Length`; `Acquisition.Device.Source Model`; `DataBar.Device Name`; `DataBar.Exposure Time (s)`; `Acquisition.Parameters.Parameter Set Name`; `SI Dimensions.Size X` and `Size Y` (at the top of the tags, as a K2IS tag file holds them); a DM image's size as RosettaSciIO gives its axes (each axis's name and size, then `scale`, the scale and its unit); `DataBar.Acquisition Date` and `Acquisition Time`; `Session Info.Specimen` and `Operator` (else under `Microscope Info`)

#### Scenario: Text as it is, numbers after their names
- **WHEN** a summary line holds a text and a number
- **THEN** the text stands as the file holds it, no word of ours, no conversion, no re-casing (`300kV`, `Lorentz`); the number follows its tag's name, as the number alone says nothing (`Exposure Time (s) 2.0`), and is left out when it is 0, which GMS writes where it has no value (`STEM Camera Length 0.0`; the tag stays in the values)

#### Scenario: The summary line of an image from a camera
- **WHEN** a DM4 image holds the tags of `2018-7-17 15_29_0000.dm4` (staging, a K2 summit on an FEI Tecnai, as ncempy lists them): `Microscope Info.Imaging Mode` and `Operation Mode` `Lorentz`, `Illumination Mode` `TEM NANOPROBE`, `Formatted Voltage` `300kV`, `Formatted Indicated Mag` `11.5kx`, `Acquisition.Device.Source Model` `K2 summit`, `DataBar.Device Name` `K2-0001`, `DataBar.Exposure Time (s)` `2.0`, `Acquisition.Parameters.Parameter Set Name` `Search`, `DataBar.Acquisition Date` `7/17/2018` and `Acquisition Time` `3:29:20 PM`, 3838 × 3710 pixels of 0.45048588514328003 nm
- **THEN** its description starts with `Lorentz, TEM NANOPROBE, 300kV, 11.5kx, K2 summit, K2-0001, Exposure Time (s) 2.0, Search, y 3838, x 3710, scale 0.45048588514328003 nm, 7/17/2018, 3:29:20 PM; ` and its subjects add `Lorentz` and `K2 summit`

#### Scenario: No Formatted tags
- **WHEN** a DM image has no `Formatted Voltage` and no `Formatted Indicated Mag`, but `Voltage` `200000.0` and `Indicated Magnification` `320.0` (RosettaSciIO's `2D__test_diffraction_pattern.dm3`)
- **THEN** the summary line holds `Voltage 200000.0, Indicated Magnification 320.0` in their place

#### Scenario: A stack builder's image
- **WHEN** a DM image keeps its tags in `source.Tags at creation` (RosettaSciIO's `test_stackbuilder_imagestack.dm3`)
- **THEN** the summary line is built from them

#### Scenario: A tag that is missing or empty
- **WHEN** a file has no `Acquisition.Device.Source Model`, no `DataBar.Exposure Time (s)` and an empty `Session Info.Operator` (`stem_image_dm3`)
- **THEN** the summary line has no camera model, no exposure and no operator, and nothing in their place: `DIFFRACTION, SCANNING, STEM NANOPROBE, 200kV, 225kx, STEM Camera Length 135.0, DigiScan, y 68, x 68, scale 0.24853801727294922 nm, 8/8/2016, 4:26:37 PM`

#### Scenario: Empty specimen and operator are left out of the summary line
- **WHEN** a DM image's `Session Info.Specimen` and `Session Info.Operator` are empty
- **THEN** the description names neither, and the values keep both as `[]`

#### Scenario: Filled specimen and operator are in the summary line
- **WHEN** a DM image's `Session Info.Specimen` is `FeGe lamella` and its `Session Info.Operator` is `A. Person`
- **THEN** the summary line ends with `FeGe lamella, A. Person`
