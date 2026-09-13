import sqlite3

import pytest

from taste_engine import config


@pytest.fixture(scope="session")
def db():
    """Read-only connection to the parsed database.

    Skips rather than fails when the database has not been built: the Takeout
    export is gitignored, so a fresh clone cannot run the dataset assertions.
    """
    if not config.DB_PATH.exists():
        pytest.skip(
            "data/taste.db not built - run `python -m taste_engine.parse_takeout` first"
        )
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def takeout_present():
    if not config.WATCH_HISTORY_HTML.exists():
        pytest.skip("Takeout export not present under data/raw/")
    return True
