"""Usage: python -m modama_crawler {crawl,serve,records}. See cli.py."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
