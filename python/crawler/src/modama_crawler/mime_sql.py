from __future__ import annotations

import re
import psycopg
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

from xdg import Mime


SQL_ESCAPE_RE = re.compile(r"([%_\\])")


@dataclass(frozen=True)
class SQLPathFilter:
    mime: Mime.MIMEtype
    weight: int
    pattern: str
    case_sensitive: bool
    sql: str
    params: Tuple[str, ...]


@dataclass(frozen=True)
class CandidateMatch:
    path: str
    candidates: Sequence[Tuple[Mime.MIMEtype, int]]
    resolved: Optional[Mime.MIMEtype]
    needs_content: bool


def _escape_like(text: str) -> str:
    return SQL_ESCAPE_RE.sub(r"\\\1", text)


def _glob_to_like(pattern: str) -> Optional[str]:
    if "[" in pattern or "]" in pattern:
        return None

    result = []
    for ch in pattern:
        if ch == "*":
            result.append("%")
        elif ch == "?":
            result.append("_")
        elif ch in ("%", "_", "\\"):
            result.append("\\")
            result.append(ch)
        else:
            result.append(ch)
    return "".join(result)


def _sql_filter_for_basename(
    pattern: str, case_sensitive: bool
) -> Optional[Tuple[str, Tuple[str, ...]]]:
    """Return a (sql, params) tuple for a basename-anchored LIKE filter or None.

    This helper only constructs the SQL expression and parameter tuple; callers
    build higher-level `SQLPathFilter` objects as needed.
    """
    like_pattern = _glob_to_like(pattern)
    if like_pattern is None:
        return None

    if case_sensitive:
        path_expr = "path"
        like_expr = like_pattern
    else:
        path_expr = "LOWER(path)"
        like_expr = like_pattern.lower()

    params = (f"%/{like_expr}",)
    escape_clause = " ESCAPE '\\'"
    sql = f"({path_expr} LIKE %s{escape_clause})"

    return sql, params


def _build_path_filter(
    pattern: str, case_sensitive: bool, mime: Mime.MIMEtype, weight: int
) -> Optional[SQLPathFilter]:
    result = _sql_filter_for_basename(pattern, case_sensitive)
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
    )


def collect_sql_path_filters() -> List[SQLPathFilter]:
    Mime.update_cache()
    result: List[SQLPathFilter] = []

    for mtype, rule_set in Mime.globs.allglobs.items():
        for weight, pattern, flags in sorted(
            rule_set, key=lambda item: item[0], reverse=True
        ):
            case_sensitive = "cs" in flags
            filter_ = _build_path_filter(pattern, case_sensitive, mtype, weight)
            if filter_ is not None:
                result.append(filter_)
    return result


def build_sql_where_clause(
    filters: Iterable[SQLPathFilter],
) -> Tuple[str, Tuple[str, ...]]:
    pieces: List[str] = []
    params: List[str] = []
    for filter_ in filters:
        pieces.append(filter_.sql)
        params.extend(filter_.params)
    if not pieces:
        return "1 = 0", ()
    return " OR ".join(pieces), tuple(params)


def resolve_name_matches(path: str) -> Sequence[Tuple[Mime.MIMEtype, int]]:
    Mime.update_cache()
    return list(Mime.globs.all_matches(path))


def summarize_candidates(
    rows: Sequence[Tuple[str, str, int]],
) -> Sequence[CandidateMatch]:
    groups: dict[str, List[Tuple[Mime.MIMEtype, int]]] = {}
    for path, mime_name, weight in rows:
        # mime_name is stored as a string representation for compatibility
        mime = (
            Mime.MIMEtype(*mime_name.split("/", 1))
            if "/" in mime_name
            else Mime.MIMEtype(mime_name, "")
        )
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


def sniff_paths_with_magic(
    paths: Iterable[str],
    possible: Optional[Sequence[Mime.MIMEtype]] = None,
    follow: bool = True,
) -> dict[str, Optional[Mime.MIMEtype]]:
    Mime.update_cache()
    result: dict[str, Optional[Mime.MIMEtype]] = {}

    for path in paths:
        try:
            mime_type = Mime.magic.match(path, possible=possible)
        except IOError:
            mime_type = None
        result[path] = mime_type
    return result


def build_mime_filter_map() -> dict[Mime.MIMEtype, List[SQLPathFilter]]:
    """Build a mapping of MIME -> list[SQLPathFilter] including only SQL-convertible filters.

    Each list is sorted by descending weight.
    """
    filters = collect_sql_path_filters()
    mapping: dict[Mime.MIMEtype, List[SQLPathFilter]] = {}
    for f in filters:
        mapping.setdefault(f.mime, []).append(f)

    for lst in mapping.values():
        lst.sort(key=lambda x: x.weight, reverse=True)
    return mapping


def _apply_mime_prefilter(
    conn: psycopg.Connection,
    mimes_table: str = "mimes",
    filters_map: Optional[dict[Mime.MIMEtype, List[SQLPathFilter]]] = None,
) -> dict[str, int]:
    """Apply SQL-based mime filters to files table and populate dataset tables.

    Args:
        conn: PostgreSQL database connection
        mimes_table: Name of the mimes table to use (default: "mimes")
        filters_map: Optional mapping of MIME types to filters

    Returns a summary mapping mime-string -> matched count.
    """
    if filters_map is None:
        filters_map = build_mime_filter_map()

    cur = conn.cursor()
    summary: dict[str, int] = {}

    for mime, filters in filters_map.items():
        print(mime)
        if not filters:
            continue

        where_clause, params = build_sql_where_clause(filters)
        mime_str = str(mime)

        # Create datasets for all matching paths (one dataset per file)
        cur.execute(
            f"""
            INSERT INTO datasets (path_id) 
            SELECT path_id FROM files WHERE ({where_clause}) 
            AND path_id not in (SELECT path_id FROM files_in_datasets) 
            AND path_id not in (SELECT path_id FROM datasets)
            ON CONFLICT (path_id) DO NOTHING
            """,
            params,
        )

        # Assign MIME type to all newly created datasets in one go
        cur.execute(
            f"""
            INSERT INTO {mimes_table} (dataset_id, mime) 
            SELECT d.dataset_id, %s 
            FROM datasets d 
            JOIN files f USING (path_id) 
            WHERE ({where_clause}) 
            ON CONFLICT (dataset_id, mime) DO NOTHING
            """,
            (mime_str, *params),
        )

        summary[mime_str] = cur.rowcount
        conn.commit()
    return summary


def _resolve_ambiguous_with_get_type2(
    conn: psycopg.Connection,
    mimes_table: str = "mimes",
) -> dict[str, int]:
    """Resolve ambiguous dataset MIME mappings using xdg.Mime.get_type2.

    For datasets that have more than one mime candidate in mimes table, call
    `Mime.get_type2(path)` and delete any entries that don't match the result.

    Args:
        conn: PostgreSQL database connection
        mimes_table: Name of the mimes table to use (default: "mimes")

    Returns a summary dict with counts: {'checked': n, 'resolved': m}.
    """
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT d.dataset_id, f.path
        FROM datasets d
        JOIN {mimes_table} m ON d.dataset_id = m.dataset_id
        JOIN files f ON d.path_id = f.path_id
        GROUP BY d.dataset_id, f.path
        HAVING COUNT(m.mime) > 1
        """
    )
    ambiguous = cur.fetchall()
    checked = 0
    resolved = 0

    for row in ambiguous:
        dataset_id = row["dataset_id"]
        path = row["path"]
        print(path)
        checked += 1
        try:
            mt = Mime.get_type2(path)
        except Exception:
            mt = None
        if mt is None:
            continue
        mt_str = str(mt)
        # Delete any candidate rows that don't match the resolved mime
        cur.execute(
            f"DELETE FROM {mimes_table} WHERE dataset_id = %s AND mime != %s",
            (dataset_id, mt_str),
        )
        # Ensure resolved mapping exists
        cur.execute(
            f"SELECT 1 FROM {mimes_table} WHERE dataset_id = %s AND mime = %s",
            (dataset_id, mt_str),
        )
        if cur.fetchone() is None:
            cur.execute(
                f"INSERT INTO {mimes_table} (dataset_id, mime) VALUES (%s, %s)",
                (dataset_id, mt_str),
            )
        resolved += 1

    conn.commit()
    return {"checked": checked, "resolved": resolved}


def apply_mime_prefilter_with_resolution(
    conn: psycopg.Connection,
    filters_map: Optional[dict[Mime.MIMEtype, List[SQLPathFilter]]] = None,
) -> dict[str, int]:
    """Apply MIME prefilter and resolve ambiguities in a single pass.

    This function performs the complete workflow:
    1. Creates a temporary mimes table in the temp database
    2. Applies MIME filters to match files
    3. Resolves ambiguous MIME types using get_type2
    4. Integrates the refined results into the actual mimes table
    5. Drops the temporary mimes table

    Args:
        conn: PostgreSQL database connection
        filters_map: Optional mapping of MIME types to filters

    Returns:
        Summary dict with datasets_created count
    """
    cur = conn.cursor()

    # Step 1: Create temporary mimes table
    cur.execute(
        """
        CREATE TEMP TABLE mimes_temp (
            dataset_id INTEGER,
            mime TEXT,
            UNIQUE(dataset_id, mime)
        )
        """
    )

    try:
        # Step 2: Apply prefilter using temporary mimes table
        _apply_mime_prefilter(
            conn,
            mimes_table="mimes_temp",
            filters_map=filters_map,
        )

        # Step 3: Resolve ambiguities in temporary mimes table
        _resolve_ambiguous_with_get_type2(
            conn,
            mimes_table="mimes_temp",
        )

        # Step 4: Integrate results into actual mimes table
        cur.execute(
            """
            INSERT INTO mimes (dataset_id, mime)
            SELECT dataset_id, mime FROM mimes_temp
            ON CONFLICT (dataset_id, mime) DO NOTHING
            """
        )

        conn.commit()

        # Return summary (count of datasets created)
        cur.execute("SELECT COUNT(DISTINCT path_id) AS cnt FROM datasets")
        dataset_count = cur.fetchone()["cnt"]

        return {"datasets_created": dataset_count}

    finally:
        # Step 5: Drop temporary mimes table
        cur.execute("DROP TABLE IF EXISTS mimes_temp")
        conn.commit()
