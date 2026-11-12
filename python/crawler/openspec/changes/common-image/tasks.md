# Tasks

## 1. The part

- [x] 1.1 `image/` in `modama-formats-common`: the formats `common/tiff`, `png`, `jpeg`, `bmp`, `gif`, `webp`, `svg` on the core's types, in `PARTS`; dependencies pinned in `pyproject.toml` (tifffile 2026.11.8, Pillow 13.0.0, defusedxml 0.7.1, current releases on PyPI on 2026-11-12, Python 3.14 wheels: Pillow `cp314`, the others pure Python). Verify: spec "Image files are datasets of their format" as `test_an_sem_image_from_an_fei_instrument`, `test_an_image_of_each_other_kind`, `test_an_eps_file`, `test_a_text_file_named_like_an_image`; `test_registered_as_common`.
- [x] 1.2 Fixtures with licence and source in `fixtures.toml` and `LICENSE.fixtures`: RosettaSciIO's FEI, Zeiss and ImageJ TIFFs, Pillow's `flower.jpg`, Matplotlib's `multi_font_astext.svg`, the rest from `generate.py`. Verify: `test_manifest`, `test_coverage`, `test_fixture[*]` with the recorded results in `expected/` reviewed.

## 2. Extraction

- [x] 2.1 TIFF through tifffile (`tiff.py`). Verify: the scenarios of "TIFF metadata is every tag of the first page" and "What a TIFF's values leave out" as `test_the_fei_metadata_of_an_sem_image`, `test_the_zeiss_metadata_of_an_sem_image`, `test_an_image_saved_by_imagej`, `test_a_tag_nobody_has_seen_before`, `test_layout_settings_and_arrays_are_left_out`, `test_a_large_tag_value_is_not_read`.
- [x] 2.2 PNG, JPEG, BMP, GIF, WEBP through Pillow (`pil.py`). Verify: `test_the_exif_of_a_camera_jpeg`, `test_the_text_chunks_of_a_png_file`, `test_an_exif_tag_nobody_has_seen_before`, `test_the_comment_of_a_gif_file`, `test_binary_exif_fields_are_left_out`.
- [x] 2.3 SVG through defusedxml (`svg.py`). Verify: `test_an_svg_file_written_by_matplotlib`, `test_an_svg_files_title_description_and_an_attribute_nobody_has_seen`.
- [x] 2.4 Summary lines. Verify: `test_the_summary_line_of_an_fei_sem_image`, `_of_a_zeiss_sem_image`, `_of_a_camera_jpeg`.
- [x] 2.5 Bounded reads, time zone. Verify: `test_a_large_image_file[tiff, bigtiff, png, jpeg, bmp, gif]` (one 64 KiB buffer each, `pytest -s` prints the bytes), `test_a_large_svg_file`, `test_a_large_webp_file`, `test_dates_in_another_time_zone`; the suite also under `TZ=Europe/Berlin`.

## 3. Documentation and checks

- [x] 3.1 README table rows; BACKLOG: Pillow's `getexif` under "Sync with upstream", what is left under the deferred items. Verify: by reading.
- [x] 3.2 Checks as CI runs them: `uvx ruff format --check --diff` and `uvx ruff check` from the repository root (only the known errors in `prototypes/*.ipynb`); `pytest src` in `python/modama-formats-common`; the crawler suite.
- [x] 3.3 Independent review (main, 2026-11-12), findings applied (proposal, "From the review", 12 to 16). Verify: `test_an_svg_file_with_one_large_element`, `test_a_broken_small_svg_file`, `test_what_an_svg_files_values_leave_out`, `test_a_header_of_more_than_pillows_pixel_limit`, `test_an_oversize_compressed_text_chunk`, `test_imagejs_info_line_by_line`, `test_imagejs_info_with_lines_of_another_form`, `test_exif_fields_of_type_undefined_as_text`, `test_the_text_chunks_of_a_png_file` (dpi in `mapped_metadata`), `test_the_fei_metadata_of_an_sem_image` (`first_page_shape`); recorded results re-recorded and reviewed.
- [ ] 3.4 Real files: `modama-chain browse` on staging's images (@weber), the summary lines and values of FEI/Thermo, Zeiss, ImageJ and DM-exported TIFFs, the EPU fractions' read sizes.
