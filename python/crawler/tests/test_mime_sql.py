from pathlib import Path

import pytest
import xdg
from modama_crawler import database, mime_sql
from psycopg.rows import dict_row
from xdg import Mime


@pytest.fixture
def pg_unit_test(conn):
    conn.row_factory = dict_row
    return conn


def test_glob_to_like_simple():
    assert mime_sql._glob_to_like("*.png") == "%.png"
    assert mime_sql._glob_to_like("?ame.txt") == "_ame.txt"
    assert mime_sql._glob_to_like("README") == "README"
    assert mime_sql._glob_to_like("file_?.md") == "file\\__.md"


def test_build_sql_where_clause():
    filters = [
        mime_sql.SQLPathFilter(
            mime=Mime.MIMEtype("text", "plain"),
            weight=50,
            pattern="*.txt",
            case_sensitive=False,
            sql="(LOWER(path) LIKE %s ESCAPE '\\')",
            params=("%/%.txt",),
        )
    ]
    sql, params = mime_sql.build_sql_where_clause(filters)
    assert "LOWER(path) LIKE %s" in sql
    assert params == ("%/%.txt",)


def test_collect_sql_path_filters():
    xdg.Mime.update_cache()
    filters = mime_sql.collect_sql_path_filters()
    assert filters
    assert any(f.pattern.startswith("*.") for f in filters)


def test_sniff_paths_with_magic(tmp_path: Path):
    blob = tmp_path / "test.png"
    blob.write_bytes(b"\x89PNG\r\n\x1a\n")

    result = mime_sql.sniff_paths_with_magic([str(blob)])
    assert str(blob) in result
    assert result[str(blob)] is not None


def test_build_mime_filter_map():
    filters = mime_sql.collect_sql_path_filters()
    assert filters
    mapping = mime_sql.build_mime_filter_map()
    assert isinstance(mapping, dict)
    # At least one mime from the collected filters should be present in the map
    collected_mimes = {f.mime for f in filters}
    assert any(m in mapping for m in collected_mimes)


def test_resolve_ambiguous_with_get_type2(pg_unit_test, tmp_path: Path):
    conn = pg_unit_test
    database.ensure_dataset_tables(conn)

    # Create a real PNG file so get_type2 can inspect contents
    blob = tmp_path / "amb.png"
    blob.write_bytes(b"\x89PNG\r\n\x1a\n")

    # Insert into files, datasets, and two candidate mimes
    cur = conn.cursor()
    cur.execute("INSERT INTO files (path) VALUES (%s)", (str(blob),))
    cur.execute("SELECT path_id FROM files WHERE path = %s", (str(blob),))
    path_id = cur.fetchone()["path_id"]
    cur.execute("INSERT INTO datasets (path_id) VALUES (%s)", (path_id,))
    cur.execute("SELECT dataset_id FROM datasets WHERE path_id = %s", (path_id,))
    dataset_id = cur.fetchone()["dataset_id"]
    cur.execute(
        "INSERT INTO mimes (dataset_id, mime) VALUES (%s, %s)",
        (dataset_id, "application/octet-stream"),
    )
    cur.execute(
        "INSERT INTO mimes (dataset_id, mime) VALUES (%s, %s)",
        (dataset_id, "image/png"),
    )
    conn.commit()

    summary = mime_sql._resolve_ambiguous_with_get_type2(conn)
    assert summary["checked"] == 1
    assert summary["resolved"] == 1

    rows = list(
        conn.execute(
            "SELECT mime FROM mimes WHERE dataset_id = %s", (dataset_id,)
        ).fetchall()
    )
    assert len(rows) == 1
    assert rows[0]["mime"] == "image/png"


def test_apply_mime_prefilter_with_resolution(pg_unit_test, tmp_path: Path):
    conn = pg_unit_test
    database.ensure_dataset_tables(conn)

    # Create test files
    png_file = tmp_path / "test.png"
    png_file.write_bytes(b"\x89PNG\r\n\x1a\n")

    txt_file = tmp_path / "test.txt"
    txt_file.write_bytes(b"Hello, World!")

    # Insert files into the files table
    cur = conn.cursor()
    cur.execute("INSERT INTO files (path) VALUES (%s)", (str(png_file),))
    cur.execute("INSERT INTO files (path) VALUES (%s)", (str(txt_file),))
    conn.commit()

    with database.crawling(conn):
        cur.execute("INSERT INTO crawl (path) VALUES (%s)", (str(png_file),))
        cur.execute("INSERT INTO crawl (path) VALUES (%s)", (str(txt_file),))

        # Build filters_map for testing
        png_filter = mime_sql._build_path_filter(
            "*.png", False, Mime.MIMEtype("image", "png"), 50
        )
        txt_filter = mime_sql._build_path_filter(
            "*.txt", False, Mime.MIMEtype("text", "plain"), 50
        )
        filters_map = {
            Mime.MIMEtype("image", "png"): [png_filter],
            Mime.MIMEtype("text", "plain"): [txt_filter],
        }

        # Run the complete workflow
        summary = mime_sql.apply_mime_prefilter_with_resolution(
            conn, filters_map=filters_map
        )

    # Verify datasets were created
    assert "datasets_created" in summary
    assert summary["datasets_created"] == 2

    res = conn.execute(
        "SELECT * FROM datasets",
    ).fetchall()
    print("datasets", res)
    assert res

    res = conn.execute(
        "SELECT * FROM files",
    ).fetchall()
    print("files", res)
    assert res

    res = conn.execute(
        "SELECT * FROM files_in_datasets",
    ).fetchall()
    print("files_in_datasets", res)

    res = conn.execute(
        "SELECT * FROM mimes",
    ).fetchall()
    print("mimes", res)
    assert res
    # Verify MIME types were resolved correctly
    png_mime_rows = list(
        conn.execute(
            "SELECT m.mime FROM mimes m JOIN datasets d ON m.dataset_id = d.dataset_id "
            "JOIN files f ON d.path_id = f.path_id WHERE f.path = %s",
            (str(png_file),),
        ).fetchall()
    )
    assert len(png_mime_rows) == 1
    assert png_mime_rows[0]["mime"] == "image/png"

    txt_mime_rows = list(
        conn.execute(
            "SELECT m.mime FROM mimes m JOIN datasets d ON m.dataset_id = d.dataset_id "
            "JOIN files f ON d.path_id = f.path_id WHERE f.path = %s",
            (str(txt_file),),
        ).fetchall()
    )
    assert len(txt_mime_rows) == 1
    assert txt_mime_rows[0]["mime"] == "text/plain"

    # Verify temporary table was cleaned up
    cur.execute("SELECT tablename FROM pg_tables WHERE tablename = 'mimes'")
    assert cur.fetchone() is not None  # Main mimes table should exist
    cur.execute(
        "SELECT tablename FROM pg_tables WHERE tablename = 'mimes_temp' AND schemaname = 'pg_temp'"
    )
    assert cur.fetchone() is None  # Temp mimes table should not exist
