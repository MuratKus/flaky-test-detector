"""SQLite-based history store.

Tracks test outcomes across CI runs to detect flakiness patterns.
Each ingest creates a new run record, and individual test results
are stored with their fingerprints for trend analysis.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from flakydetector.models import RunSummary, TestOutcome

DEFAULT_DB = Path(".flaky-detector.db")


class Store:

    def __init__(self, db_path: Path = DEFAULT_DB):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._migrate()

    def _migrate(self) -> None:
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                ingested_at TEXT NOT NULL,
                total INTEGER DEFAULT 0,
                passed INTEGER DEFAULT 0,
                failed INTEGER DEFAULT 0,
                errored INTEGER DEFAULT 0,
                skipped INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL REFERENCES runs(run_id),
                test_name TEXT NOT NULL,
                classname TEXT DEFAULT '',
                outcome TEXT NOT NULL,
                duration_sec REAL DEFAULT 0.0,
                error_message TEXT DEFAULT '',
                stacktrace TEXT DEFAULT '',
                fingerprint TEXT DEFAULT '',
                suite TEXT DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_results_test_name
                ON results(test_name);
            CREATE INDEX IF NOT EXISTS idx_results_fingerprint
                ON results(fingerprint);
            CREATE INDEX IF NOT EXISTS idx_results_run_id
                ON results(run_id);
        """)

    def ingest(self, summary: RunSummary) -> int:
        """Store a run and its results. Returns number of results stored."""
        now = datetime.now(timezone.utc).isoformat()

        self.conn.execute(
            """INSERT OR REPLACE INTO runs
               (run_id, source, ingested_at, total, passed, failed, errored, skipped)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                summary.run_id, summary.source, now,
                summary.total, summary.passed, summary.failed,
                summary.errored, summary.skipped,
            ),
        )

        for r in summary.results:
            self.conn.execute(
                """INSERT INTO results
                   (run_id, test_name, classname, outcome, duration_sec,
                    error_message, stacktrace, fingerprint, suite)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    summary.run_id, r.fqn, r.classname, r.outcome.value,
                    r.duration_sec, r.error_message or "", r.stacktrace or "",
                    r.fingerprint or "", r.suite,
                ),
            )

        self.conn.commit()
        return len(summary.results)

    def get_test_history(self, test_name: str, limit: int = 50) -> list[dict]:
        """Get recent outcomes for a specific test."""
        rows = self.conn.execute(
            """SELECT r.run_id, r.outcome, r.fingerprint, r.error_message,
                      runs.ingested_at
               FROM results r
               JOIN runs ON r.run_id = runs.run_id
               WHERE r.test_name = ?
               ORDER BY runs.ingested_at DESC
               LIMIT ?""",
            (test_name, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_all_test_names(self) -> list[str]:
        """Get all distinct test names in the store."""
        rows = self.conn.execute(
            "SELECT DISTINCT test_name FROM results"
        ).fetchall()
        return [row["test_name"] for row in rows]

    def get_failure_fingerprint_counts(self) -> list[dict]:
        """Group failures by fingerprint to find common root causes."""
        rows = self.conn.execute(
            """SELECT fingerprint, COUNT(*) as count,
                      GROUP_CONCAT(DISTINCT test_name) as tests,
                      MAX(error_message) as sample_error
               FROM results
               WHERE outcome IN ('failed', 'error')
                 AND fingerprint != ''
               GROUP BY fingerprint
               ORDER BY count DESC
               LIMIT 50""",
        ).fetchall()
        return [dict(row) for row in rows]

    def get_run_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) as n FROM runs").fetchone()
        return row["n"]

    def close(self) -> None:
        self.conn.close()
