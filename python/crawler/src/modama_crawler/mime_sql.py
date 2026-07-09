from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

from xdg import Mime

SQL_ESCAPE_RE = re.compile(r'([%_\\])')


@dataclass(frozen=True)
class SQLPathFilter:
    mime: Mime.MIMEtype
    weight: int
    pattern: str
    case_sensitive: bool
    sql: str
    params: Tuple[str, ...]
    is_simple: bool


@dataclass(frozen=True)
class CandidateMatch:
    path: str
    candidates: Sequence[Tuple[Mime.MIMEtype, int]]
    resolved: Optional[Mime.MIMEtype]
    needs_content: bool


def _escape_like(text: str) -> str:
    return SQL_ESCAPE_RE.sub(r'\\\1', text)


def _glob_to_like(pattern: str) -> Optional[str]:
    if '[' in pattern or ']' in pattern:
        return None

    result = []
    for ch in pattern:
        if ch == '*':
            result.append('%')
        elif ch == '?':
            result.append('_')
        elif ch in ('%', '_', '\\'):
            result.append('\\')
            result.append(ch)
        else:
            result.append(ch)
    return ''.join(result)


def _sql_filter_for_basename(pattern: str, case_sensitive: bool, path_column: str = 'path') -> Optional[Tuple[str, Tuple[str, ...]]]:
    """Return a (sql, params) tuple for a basename-anchored LIKE filter or None.

    This helper only constructs the SQL expression and parameter tuple; callers
    build higher-level `SQLPathFilter` objects as needed.
    """
    like_pattern = _glob_to_like(pattern)
    if like_pattern is None:
        return None

    if case_sensitive:
        path_expr = path_column
        like_expr = like_pattern
    else:
        path_expr = f'LOWER({path_column})'
        like_expr = like_pattern.lower()

    params = (f'%/{like_expr}',)
    escape_clause = " ESCAPE '\\'"
    sql = f'({path_expr} LIKE ?{escape_clause})'

    return sql, params


def _build_path_filter(pattern: str, case_sensitive: bool, mime: Mime.MIMEtype, weight: int, path_column: str = 'path') -> Optional[SQLPathFilter]:
    result = _sql_filter_for_basename(pattern, case_sensitive, path_column=path_column)
    if result is None:
        return None
    sql, params = result

    return SQLPathFilter(
        mime=mime,
        weight=weight,
        pattern=pattern,
        case_sensitive=case_sensitive,
        sql=sql,
        params=params,
        is_simple=True,
    )


def collect_sql_path_filters(path_column: str = 'path') -> List[SQLPathFilter]:
    Mime.update_cache()
    result: List[SQLPathFilter] = []

    for mtype, rule_set in Mime.globs.allglobs.items():
        for weight, pattern, flags in sorted(rule_set, key=lambda item: item[0], reverse=True):
            case_sensitive = 'cs' in flags
            filter_ = _build_path_filter(pattern, case_sensitive, mtype, weight, path_column=path_column)
            if filter_ is not None:
                result.append(filter_)
    return result


def build_sql_where_clause(filters: Iterable[SQLPathFilter]) -> Tuple[str, Tuple[str, ...]]:
    pieces: List[str] = []
    params: List[str] = []
    for filter_ in filters:
        pieces.append(filter_.sql)
        params.extend(filter_.params)
    if not pieces:
        return '1 = 0', ()
    return ' OR '.join(pieces), tuple(params)


def query_matching_paths(
    conn: sqlite3.Connection,
    table_name: str,
    path_column: str = 'path',
    filters: Optional[Sequence[SQLPathFilter]] = None,
) -> List[Tuple[str, str, int]]:
    if filters is None:
        filters = collect_sql_path_filters(path_column=path_column)

    where_clause, params = build_sql_where_clause(filters)
    sql = f'SELECT {path_column}, mime, weight FROM {table_name} WHERE {where_clause}'
    cursor = conn.execute(sql, params)
    return cursor.fetchall()


def resolve_name_matches(path: str) -> Sequence[Tuple[Mime.MIMEtype, int]]:
    Mime.update_cache()
    return list(Mime.globs.all_matches(path))


def summarize_candidates(rows: Sequence[Tuple[str, str, int]]) -> Sequence[CandidateMatch]:
    groups: dict[str, List[Tuple[Mime.MIMEtype, int]]] = {}
    for path, mime_name, weight in rows:
        # mime_name is stored as a string representation for compatibility
        mime = Mime.MIMEtype(*mime_name.split('/', 1)) if '/' in mime_name else Mime.MIMEtype(mime_name, '')
        groups.setdefault(path, []).append((mime, weight))

    results: List[CandidateMatch] = []
    for path, entries in groups.items():
        entries.sort(key=lambda item: item[1], reverse=True)
        if not entries:
            results.append(CandidateMatch(path, [], None, True))
            continue

        top_weight = entries[0][1]
        top_entries = [entry for entry in entries if entry[1] == top_weight]
        if len(top_entries) == 1:
            results.append(CandidateMatch(path, entries, top_entries[0][0], False))
        else:
            results.append(CandidateMatch(path, entries, None, True))
    return results


def sniff_paths_with_magic(paths: Iterable[str], possible: Optional[Sequence[Mime.MIMEtype]] = None, follow: bool = True) -> dict[str, Optional[Mime.MIMEtype]]:
    Mime.update_cache()
    result: dict[str, Optional[Mime.MIMEtype]] = {}

    for path in paths:
        try:
            mime_type = Mime.magic.match(path, possible=possible)
        except IOError:
            mime_type = None
        result[path] = mime_type
    return result


def build_mime_filter_map(path_column: str = 'path') -> dict[Mime.MIMEtype, List[SQLPathFilter]]:
    """Build a mapping of MIME -> list[SQLPathFilter] including only SQL-convertible filters.

    Each list is sorted by descending weight.
    """
    filters = collect_sql_path_filters(path_column=path_column)
    mapping: dict[Mime.MIMEtype, List[SQLPathFilter]] = {}
    for f in filters:
        if not f.is_simple:
            continue
        mapping.setdefault(f.mime, []).append(f)

    for lst in mapping.values():
        lst.sort(key=lambda x: x.weight, reverse=True)
    return mapping


def ensure_dataset_tables(conn: sqlite3.Connection, dataset_table: str = 'datasets', mime_table: str = 'dataset_mimes') -> None:
    """Create minimal `datasets` and `dataset_mimes` tables if they do not exist."""
    cur = conn.cursor()
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {dataset_table} (
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE
        )
        """
    )
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {mime_table} (
            dataset_id INTEGER,
            mime TEXT,
            weight INTEGER,
            PRIMARY KEY(dataset_id, mime)
        )
        """
    )
    conn.commit()


def apply_mime_prefilter(
    conn: sqlite3.Connection,
    source_table: str,
    path_column: str = 'path',
    dataset_table: str = 'datasets',
    mime_table: str = 'dataset_mimes',
    filters_map: Optional[dict[Mime.MIMEtype, List[SQLPathFilter]]] = None,
) -> dict[str, int]:
    """Apply SQL-based mime filters to `source_table` and populate dataset tables.

    Returns a summary mapping mime-string -> matched count.
    """
    if filters_map is None:
        filters_map = build_mime_filter_map(path_column=path_column)

    ensure_dataset_tables(conn, dataset_table=dataset_table, mime_table=mime_table)
    cur = conn.cursor()
    summary: dict[str, int] = {}

    for mime, filters in filters_map.items():
        if not filters:
            continue

        where_clause, params = build_sql_where_clause(filters)
        sql = f"SELECT {path_column} FROM {source_table} WHERE {where_clause}"
        rows = [r[0] for r in conn.execute(sql, params).fetchall()]
        if not rows:
            summary[str(mime)] = 0
            continue

        top_weight = max(f.weight for f in filters)
        mime_str = str(mime)
        count = 0

        for path in rows:
            cur.execute(f'INSERT OR IGNORE INTO {dataset_table} (path) VALUES (?)', (path,))
            cur.execute(f'SELECT id FROM {dataset_table} WHERE path = ?', (path,))
            row = cur.fetchone()
            if row is None:
                # fallback: use lastrowid if available
                dataset_id = cur.lastrowid
            else:
                dataset_id = row[0]

            cur.execute(
                f'INSERT OR REPLACE INTO {mime_table} (dataset_id, mime, weight) VALUES (?, ?, ?)',
                (dataset_id, mime_str, top_weight),
            )
            count += 1

        summary[mime_str] = count

    conn.commit()
    return summary


def resolve_ambiguous_with_get_type2(
    conn: sqlite3.Connection,
    dataset_table: str = 'datasets',
    mime_table: str = 'dataset_mimes',
) -> dict[str, int]:
    """Resolve ambiguous dataset MIME mappings using xdg.Mime.get_type2.

    For datasets that have more than one mime candidate in `mime_table`, call
    `Mime.get_type2(path)` and delete any entries that don't match the result.
    Returns a summary dict with counts: {'checked': n, 'resolved': m}.
    """
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT d.id, d.path
        FROM {dataset_table} d
        JOIN {mime_table} m ON d.id = m.dataset_id
        GROUP BY d.id
        HAVING COUNT(m.mime) > 1
        """
    )
    ambiguous = cur.fetchall()
    checked = 0
    resolved = 0

    for dataset_id, path in ambiguous:
        checked += 1
        try:
            mt = Mime.get_type2(path)
        except Exception:
            mt = None
        if mt is None:
            continue
        mt_str = str(mt)
        # Delete any candidate rows that don't match the resolved mime
        cur.execute(f"DELETE FROM {mime_table} WHERE dataset_id = ? AND mime != ?", (dataset_id, mt_str))
        # Ensure resolved mapping exists
        cur.execute(f"SELECT 1 FROM {mime_table} WHERE dataset_id = ? AND mime = ?", (dataset_id, mt_str))
        if cur.fetchone() is None:
            cur.execute(f"INSERT INTO {mime_table} (dataset_id, mime, weight) VALUES (?, ?, ?)", (dataset_id, mt_str, 0))
        resolved += 1

    conn.commit()
    return {"checked": checked, "resolved": resolved}
