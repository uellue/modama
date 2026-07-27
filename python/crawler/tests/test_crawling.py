"""Tests for crawling functionality.

Tests the initial repository population workflow using simple file types
(txt, png) similar to test_mime_sql.py patterns.
"""

from pathlib import Path

from xdg import Mime

from modama_crawler import database, crawling


def test_crawl_repository(pg_unit_test, tmp_path: Path):
    """Test that crawl_repository populates the temporary crawl table."""
    conn = pg_unit_test

    # Create test files and directories
    png_file = tmp_path / "test.png"
    png_file.write_bytes(b"\x89PNG\r\n\x1a\n")

    txt_file = tmp_path / "test.txt"
    txt_file.write_bytes(b"Hello, World!")

    subdir = tmp_path / "subdir"
    subdir.mkdir()
    subdir_file = subdir / "nested.txt"
    subdir_file.write_bytes(b"Nested content")

    # Ensure database tables exist
    database.ensure_dataset_tables(conn)

    # Crawl the temporary directory
    cur = conn.cursor()
    count = crawling.crawl_repository(conn, root_path=tmp_path)

    # Verify count (tmp_path itself + subdir + 2 files)
    assert count == 4

    # Verify crawl table was populated
    cur.execute("SELECT COUNT(*) FROM crawl")
    crawl_count = cur.fetchone()["count"]
    assert crawl_count == 4

    # Verify paths are in crawl table
    cur.execute("SELECT path FROM crawl ORDER BY path")
    crawl_paths = [row["path"] for row in cur.fetchall()]

    assert str(png_file) in crawl_paths
    assert str(txt_file) in crawl_paths
    assert str(subdir_file) in crawl_paths


def test_populate_files_from_crawl(pg_unit_test, tmp_path: Path):
    """Test that populate_files_from_crawl transfers data correctly."""
    conn = pg_unit_test

    # Create test files
    png_file = tmp_path / "test.png"
    png_file.write_bytes(b"\x89PNG\r\n\x1a\n")

    txt_file = tmp_path / "test.txt"
    txt_file.write_bytes(b"Hello, World!")

    # Ensure database tables exist
    database.ensure_dataset_tables(conn)

    # Crawl and populate
    crawling.crawl_repository(conn, root_path=tmp_path)
    files_inserted, _ = crawling.populate_files_from_crawl(conn)

    # Verify files were inserted
    assert files_inserted == 2

    # Verify files table was populated
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM files")
    files_count = cur.fetchone()["count"]
    assert files_count == 2

    # Verify crawl table was dropped
    cur.execute("SELECT tablename FROM pg_tables WHERE tablename = 'crawl'")
    assert cur.fetchone() is None


def test_crawl_and_populate(pg_unit_test, tmp_path: Path):
    """Test complete crawling and population workflow."""
    conn = pg_unit_test

    # Create test files
    png_file = tmp_path / "test.png"
    png_file.write_bytes(b"\x89PNG\r\n\x1a\n")

    txt_file = tmp_path / "test.txt"
    txt_file.write_bytes(b"Hello, World!")

    # Ensure database tables exist
    database.ensure_dataset_tables(conn)

    # Build filters for testing
    from modama_crawler import mime_sql

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

    # Run complete workflow
    summary = crawling.crawl_and_populate(
        conn, root_path=tmp_path, filters_map=filters_map
    )

    # Verify summary
    assert summary["crawled"] == 2  # 2 files
    assert summary["files_inserted"] == 2
    assert summary["datasets_created"] == 2

    # Verify all tables were populated
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM files")
    assert cur.fetchone()["count"] == 2

    cur.execute("SELECT COUNT(*) FROM datasets")
    assert cur.fetchone()["count"] == 2

    cur.execute("SELECT COUNT(*) FROM mimes")
    assert cur.fetchone()["count"] == 2

    # Verify MIME types were resolved correctly
    cur.execute(
        "SELECT m.mime FROM mimes m JOIN datasets d ON m.dataset_id = d.dataset_id "
        "JOIN files f ON d.path_id = f.path_id WHERE f.path = %s",
        (str(png_file),),
    )
    png_mime = cur.fetchone()["mime"]
    assert png_mime == "image/png"

    cur.execute(
        "SELECT m.mime FROM mimes m JOIN datasets d ON m.dataset_id = d.dataset_id "
        "JOIN files f ON d.path_id = f.path_id WHERE f.path = %s",
        (str(txt_file),),
    )
    txt_mime = cur.fetchone()["mime"]
    assert txt_mime == "text/plain"
