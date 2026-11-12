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
For a DM3 or DM4 dataset, the extractor SHALL keep as values every tag of the data image's `ImageTags` but the user-interface settings, each under its path of tag names with RosettaSciIO's value (its `original_metadata`; `[]` for an empty tag, decision 161; `inf` for an infinity, which JSON cannot hold), and the image's axes. The record's description SHALL start with the summary line of these tags; the subjects SHALL carry RosettaSciIO's microscope, acquisition mode and signal type, then the imaging mode and the camera model. The values are stored with the dataset, not in the record.

#### Scenario: No unit the reader does not give
- **WHEN** a DM file's tags give the voltage as `Microscope Info.Formatted Voltage` `300kV` and as `Microscope Info.Voltage` `300000.0`
- **THEN** the description shows `300kV` as the tag gives it, and no value converted to another unit (README, "Values and units")

#### Scenario: A representative DM4 image
- **WHEN** a representative DM4 file with known tags is crawled (`cl_image_dm4`)
- **THEN** its record's description starts with `IMAGING, SCANNING, SEM, 3kV, 2.5kx, 18.325349807739258 µm/pixel, 2×2, 2021-05-14 11:41; `, its subjects are the format's name, `Zeiss SEM COM`, `SEM`, `CL` and `IMAGING`, and its values carry its 101 image tags, without the 18 of the Session Info form

#### Scenario: The data image, not the thumbnail
- **WHEN** a DM file's `ImageList` holds the thumbnail first (named by `Thumbnails`) and the data image second
- **THEN** the values carry the data image's tags, the image RosettaSciIO's reader takes (the first in `ImageList` that `Thumbnails` does not name)

#### Scenario: The tags, not the image data
- **WHEN** a DM file's metadata is extracted
- **THEN** the extractor reads its tags and skips the image data, in reads no larger than NFS's read size, so that a file on NFS costs about its tags and not a buffer of up to 1 MiB per seek

#### Scenario: An RGBA image
- **WHEN** a DM4 file holds an RGBA image, which RosettaSciIO does not load lazily
- **THEN** its tags are extracted as for any other image

### Requirement: User-interface settings are left out
The values of a DM image and of a K2IS tag file SHALL leave out Gatan Microscopy Suite's user-interface settings (decision 129: "everything except things like GMS GUI settings (e.g. window size and position)"), by an explicit list (design D4 of change `dm-containers-and-k2is`): a tag group whose `Class Name` is `cm_stdviewerimagedisplayer` (the image viewer), and the group `Session Info.Items` (the definition of GMS's Session Info form). Everything else stays.

#### Scenario: User-interface settings are left out of the values
- **WHEN** a DM image's `ImageTags` hold the image viewer's group (`Acquisition.Parameters.Objects.TagGroup1` of class `cm_stdviewerimagedisplayer`, with `Window Relative Position` and `Zoom`) next to processing objects (`Objects.TagGroup0` of class `cm_imgproc_finalcombine`, `TagGroup2` of class `cm_imgproc_histogram`), and the Session Info form (`Session Info.Items`)
- **THEN** the values carry the processing objects' tags and `Session Info.Specimen`, and no tag of the viewer's group or of `Session Info.Items`

#### Scenario: What GMS keeps outside the image's tags
- **WHEN** a DM file holds, outside the data image's `ImageTags`, the document's, page's and window's settings (`DocumentObjectList` with its `ImageDisplayInfo`, `Image Behavior`, `Page Behavior`, `PageSetup`, `WindowPosition`), the thumbnail and the image data's own tags (`ImageData`)
- **THEN** none of them is in the values; the pixel size and dimensions of `ImageData` are in the axes

### Requirement: The summary line of a DM file's tags
For a DM image (its `ImageTags`) and a K2IS tag file (its tags), the extractor SHALL build the summary line by one rule, from the tags listed in the scenario "The order of the summary line", each where present and not empty, in that order, the values as the tags give them (README, "Values and units").

#### Scenario: The order of the summary line
- **WHEN** a summary line is built
- **THEN** it holds, each where present:
  1. the imaging mode (`Microscope Info.Imaging Mode`), then the operation mode (`Microscope Info.Operation Mode`) where it differs;
  2. the illumination mode (`Microscope Info.Illumination Mode`);
  3. the voltage (`Microscope Info.Formatted Voltage`);
  4. the magnification (`Microscope Info.Formatted Indicated Mag`);
  5. the camera length, where the illumination mode names STEM (as RosettaSciIO decides the STEM mode): `STEM Camera Length` and the value of `Microscope Info.STEM Camera Length`, no unit (the tag names none);
  6. the camera model (`Acquisition.Device.Source Model`);
  7. the exposure: the value of `DataBar.Exposure Time (s)`, then `s exposure`;
  8. the acquisition's parameter set (`Acquisition.Parameters.Parameter Set Name`: `Search`, `View`, `Record`): `parameter set` and the name;
  9. the size: the scan (`scan of X×Y positions`, from `SI Dimensions.Size X` and `Size Y` at the top of the tags, as a K2IS tag file holds them), then a DM image's pixel size and dimensions;
  10. the date and time of `DataBar.Acquisition Date` and `Acquisition Time`, as RosettaSciIO's reader converts them, to the minute;
  11. the specimen (`specimen` and `Session Info.Specimen`) and the operator (`operator` and `Session Info.Operator`).

#### Scenario: The summary line of an image from a camera
- **WHEN** a DM4 image holds the tags of `2018-7-17 15_29_0000.dm4` (staging, a K2 summit on an FEI Tecnai, as ncempy lists them): `Microscope Info.Imaging Mode` and `Operation Mode` `Lorentz`, `Illumination Mode` `TEM NANOPROBE`, `Formatted Voltage` `300kV`, `Formatted Indicated Mag` `11.5kx`, `Acquisition.Device.Source Model` `K2 summit`, `DataBar.Exposure Time (s)` `2.0`, `Acquisition.Parameters.Parameter Set Name` `Search`, `DataBar.Acquisition Date` `7/17/2018` and `Acquisition Time` `3:29:20 PM`, with a pixel size of 0.45048588514328003 nm and 3710 × 3838 pixels
- **THEN** its description starts with `Lorentz, TEM NANOPROBE, 300kV, 11.5kx, K2 summit, 2.0 s exposure, parameter set Search, 0.45048588514328003 nm/pixel, 3710×3838, 2018-07-17 15:29; ` and its subjects add `Lorentz` and `K2 summit`

#### Scenario: A tag that is missing or empty
- **WHEN** a file has no `Acquisition.Device.Source Model`, no `DataBar.Exposure Time (s)` and an empty `Session Info.Operator` (`stem_image_dm3`)
- **THEN** the summary line has no camera model, no exposure and no operator, and nothing in their place

#### Scenario: Empty specimen and operator are left out of the summary line
- **WHEN** a DM image's `Session Info.Specimen` and `Session Info.Operator` are empty
- **THEN** the description names neither, and the values keep both as `[]`

#### Scenario: Filled specimen and operator are in the summary line
- **WHEN** a DM image's `Session Info.Specimen` is `FeGe lamella` and its `Session Info.Operator` is `A. Person`
- **THEN** the summary line ends with `specimen FeGe lamella, operator A. Person`
