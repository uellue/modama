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
