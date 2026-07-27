"""Crawling module for initial repository population.

This module provides high-level orchestration functions for crawling the
filesystem repository and populating the database with initial file entries.
"""

from pathlib import Path
from typing import Optional

import psycopg

from modama_crawler.database import crawl_repository, populate_files_from_crawl
from modama_crawler.mime_sql import apply_mime_prefilter_with_resolution


def crawl_and_populate(
    conn: psycopg.Connection,
    root_path: Optional[Path] = None,
    filters_map: Optional[dict] = None,
) -> dict:
    """Perform complete crawling and database population workflow.

    This function orchestrates the complete initial population workflow:
    1. Crawl the filesystem and populate temporary crawl table
    2. Transfer entries from crawl table to files table
    3. Run MIME prefilter with resolution to create datasets and mimes entries

    Args:
        conn: PostgreSQL database connection
        root_path: Root directory to crawl (defaults to MODAMA_DATA_ROOT)
        filters_map: Optional mapping of MIME types to filters for apply_mime_prefilter_with_resolution

    Returns:
        dict: Summary with counts:
            - 'crawled': number of entries crawled
            - 'files_inserted': number of files inserted into files table
            - 'datasets_created': number of datasets created by MIME prefilter

    Note:
        This is designed for initial population only. For incremental updates,
        see TODO comments in populate_files_from_crawl() for future enhancements.
    """
    # Step 1: Crawl the repository
    crawled_count = crawl_repository(conn, root_path=root_path)

    # Step 2: Transfer to permanent files table
    files_inserted, _ = populate_files_from_crawl(conn)

    # Step 3: Apply MIME prefilter to create datasets and mimes
    mime_summary = apply_mime_prefilter_with_resolution(conn, filters_map=filters_map)
    datasets_created = mime_summary.get("datasets_created", 0)

    return {
        "crawled": crawled_count,
        "files_inserted": files_inserted,
        "datasets_created": datasets_created,
    }
