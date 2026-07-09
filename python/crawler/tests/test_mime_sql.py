import sqlite3
from pathlib import Path

import xdg
from xdg import Mime

from modama_crawler import mime_sql


def test_glob_to_like_simple():
    assert mime_sql._glob_to_like('*.png') == '%.png'
    assert mime_sql._glob_to_like('?ame.txt') == '_ame.txt'
    assert mime_sql._glob_to_like('README') == 'README'
    assert mime_sql._glob_to_like('file_?.md') == 'file\\__.md'


def test_build_sql_where_clause():
    filters = [
        mime_sql.SQLPathFilter(
            mime=Mime.MIMEtype('text', 'plain'),
            weight=50,
            pattern='*.txt',
            case_sensitive=False,
            sql="(LOWER(path) LIKE ? ESCAPE '\\')",
            params=('%/%.txt', '%.txt'),
            is_simple=True,
        )
    ]
    sql, params = mime_sql.build_sql_where_clause(filters)
    assert 'LOWER(path) LIKE ?' in sql
    assert params == ('%/%.txt', '%.txt')


def test_collect_sql_path_filters():
    xdg.Mime.update_cache()
    filters = mime_sql.collect_sql_path_filters()
    assert filters
    assert any(f.pattern.startswith('*.') for f in filters)


def test_query_matching_paths_and_summarize_candidates():
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE files (path TEXT, mime TEXT, weight INTEGER)')
    conn.executemany(
        'INSERT INTO files (path, mime, weight) VALUES (?, ?, ?)',
        [
            ('a/b/foo.txt', 'text/plain', 50),
            ('c/d/bar.png', 'image/png', 50),
            ('README', 'text/x-readme', 10),
        ],
    )

    filters = [
        mime_sql._build_path_filter('*.txt', False, Mime.MIMEtype('text', 'plain'), 50, 'path'),
        mime_sql._build_path_filter('*.png', False, Mime.MIMEtype('image', 'png'), 50, 'path'),
    ]
    rows = mime_sql.query_matching_paths(conn, 'files', 'path', filters=filters)
    assert rows

    summary = mime_sql.summarize_candidates(rows)
    assert len(summary) == 2
    assert any(entry.path == 'a/b/foo.txt' and entry.resolved is not None for entry in summary)
    assert any(entry.path == 'c/d/bar.png' and entry.resolved is not None for entry in summary)


def test_sniff_paths_with_magic(tmp_path: Path):
    blob = tmp_path / 'test.png'
    blob.write_bytes(b'\x89PNG\r\n\x1a\n')

    result = mime_sql.sniff_paths_with_magic([str(blob)])
    assert str(blob) in result
    assert result[str(blob)] is not None


def test_build_mime_filter_map():
    filters = mime_sql.collect_sql_path_filters('path')
    assert filters
    mapping = mime_sql.build_mime_filter_map('path')
    assert isinstance(mapping, dict)
    # At least one mime from the collected filters should be present in the map
    collected_mimes = {f.mime for f in filters}
    assert any(m in mapping for m in collected_mimes)


def test_ensure_and_apply_prefilter():
    conn = sqlite3.connect(':memory:')
    # Use a different name for the source table to avoid colliding with the
    # prefilter's own 'files' table created by ensure_dataset_tables.
    conn.execute('CREATE TABLE repo_files (path TEXT)')
    paths = ['/x/img/photo.png', '/x/doc/report.txt', '/README']
    conn.executemany('INSERT INTO repo_files (path) VALUES (?)', [(p,) for p in paths])

    # Build a small filters_map for predictable behavior
    png_filter = mime_sql._build_path_filter('*.png', False, Mime.MIMEtype('image', 'png'), 50, 'path')
    txt_filter = mime_sql._build_path_filter('*.txt', False, Mime.MIMEtype('text', 'plain'), 50, 'path')
    filters_map = {
        Mime.MIMEtype('image', 'png'): [png_filter],
        Mime.MIMEtype('text', 'plain'): [txt_filter],
    }

    mime_sql.ensure_dataset_tables(conn)
    mime_sql.apply_mime_prefilter(conn, 'repo_files', path_column='path', filters_map=filters_map)

    # Verify datasets populated (only matched paths are inserted)
    rows = list(conn.execute('SELECT path FROM files JOIN datasets USING (path_id)').fetchall())
    assert len(rows) == 2

    # Verify mime mappings for known types exist
    mime_rows = list(conn.execute('SELECT mime FROM mimes').fetchall())
    mime_values = {r[0] for r in mime_rows}
    assert any('image/png' in m for m in mime_values)
    assert any('text/plain' in m for m in mime_values)


def test_resolve_ambiguous_with_get_type2(tmp_path: Path):
    conn = sqlite3.connect(':memory:')
    mime_sql.ensure_dataset_tables(conn)

    # Create a real PNG file so get_type2 can inspect contents
    blob = tmp_path / 'amb.png'
    blob.write_bytes(b'\x89PNG\r\n\x1a\n')

    # Insert into files, datasets, and two candidate mimes
    cur = conn.cursor()
    cur.execute('INSERT INTO files (path) VALUES (?)', (str(blob),))
    cur.execute('SELECT path_id FROM files WHERE path = ?', (str(blob),))
    path_id = cur.fetchone()[0]
    cur.execute('INSERT INTO datasets (path_id) VALUES (?)', (path_id,))
    cur.execute('SELECT dataset_id FROM datasets WHERE path_id = ?', (path_id,))
    dataset_id = cur.fetchone()[0]
    cur.execute('INSERT INTO mimes (dataset_id, mime) VALUES (?, ?)', (dataset_id, 'application/octet-stream'))
    cur.execute('INSERT INTO mimes (dataset_id, mime) VALUES (?, ?)', (dataset_id, 'image/png'))
    conn.commit()

    summary = mime_sql.resolve_ambiguous_with_get_type2(conn)
    assert summary['checked'] == 1
    assert summary['resolved'] == 1

    rows = list(conn.execute('SELECT mime FROM mimes WHERE dataset_id = ?', (dataset_id,)).fetchall())
    assert len(rows) == 1
    assert rows[0][0] == 'image/png'
