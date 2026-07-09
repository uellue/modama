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


def _sql_filter_for_basename(pattern: str, case_sensitive: bool, path_column: str = 'path') -> Optional[SQLPathFilter]:
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

    return SQLPathFilter(
        mime=Mime.MIMEtype('', ''),
        weight=0,
        pattern=pattern,
        case_sensitive=case_sensitive,
        sql=sql,
        params=params,
        is_simple=True,
    )


def _build_path_filter(pattern: str, case_sensitive: bool, mime: Mime.MIMEtype, weight: int, path_column: str = 'path') -> Optional[SQLPathFilter]:
    filter_ = _sql_filter_for_basename(pattern, case_sensitive, path_column=path_column)
    if filter_ is None:
        return None

    return SQLPathFilter(
        mime=mime,
        weight=weight,
        pattern=pattern,
        case_sensitive=case_sensitive,
        sql=filter_.sql,
        params=filter_.params,
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
