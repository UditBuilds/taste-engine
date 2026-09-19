"""connect()'s pragmas and schema-version gating (briefs/portability_defects.md C2)."""
from __future__ import annotations

import taste_engine.db as dbmod


class TestConnectPragmas:
    def test_sets_wal_and_busy_timeout(self, tmp_path):
        conn = dbmod.connect(tmp_path / "t.db")
        try:
            assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
            assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        finally:
            conn.close()


class TestSchemaVersionGating:
    def test_first_connect_applies_schema_and_stamps_version(self, tmp_path):
        conn = dbmod.connect(tmp_path / "t.db")
        try:
            assert conn.execute("PRAGMA user_version").fetchone()[0] == dbmod.SCHEMA_VERSION
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            assert "plays" in tables and "written_tracks" in tables
        finally:
            conn.close()

    def test_second_connect_does_not_rerun_the_script(self, tmp_path, monkeypatch):
        """A DB already at SCHEMA_VERSION must skip executescript entirely -
        proven by corrupting SCHEMA so any real call would raise, not by
        counting calls (sqlite3.Connection.executescript can't be patched,
        it's a C-level method on an immutable type)."""
        path = tmp_path / "t.db"
        dbmod.connect(path).close()

        monkeypatch.setattr(dbmod, "SCHEMA", "THIS IS NOT VALID SQL ;;; (((")
        conn = dbmod.connect(path)  # must not raise
        try:
            assert conn.execute("PRAGMA user_version").fetchone()[0] == dbmod.SCHEMA_VERSION
        finally:
            conn.close()

    def test_version_bump_reapplies_and_preserves_existing_tables(self, tmp_path, monkeypatch):
        """Simulates a future SCHEMA addition: bumping SCHEMA_VERSION must
        re-run the (idempotent) script rather than leaving an older database
        permanently missing whatever a code change added."""
        path = tmp_path / "t.db"
        dbmod.connect(path).close()

        monkeypatch.setattr(dbmod, "SCHEMA_VERSION", dbmod.SCHEMA_VERSION + 1)
        monkeypatch.setattr(
            dbmod, "SCHEMA", dbmod.SCHEMA + "\nCREATE TABLE IF NOT EXISTS t_new (id INTEGER);"
        )
        conn = dbmod.connect(path)
        try:
            assert conn.execute("PRAGMA user_version").fetchone()[0] == dbmod.SCHEMA_VERSION
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            assert "t_new" in tables
            assert "plays" in tables  # pre-existing tables untouched
        finally:
            conn.close()
