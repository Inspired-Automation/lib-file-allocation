"""An in-memory stand-in for the two customer master tables, understanding
exactly the statements customer_folders issues."""

import copy

import pyodbc
import pytest

from file_allocation_core import customer_folders as cf


class FakeCursor:
    def __init__(self, db):
        self.db = db
        self._result = []

    def execute(self, sql, params=()):
        db = self.db
        if db.fail_on and db.fail_on in sql:
            raise pyodbc.OperationalError("08S01", "Communication link failure")
        if sql == cf.SELECT_ROWS_FOR_ID:
            (sugar_id,) = params
            self._result = [
                (r["id"], r["customer"], r["deleted"])
                for r in sorted(db.rows, key=lambda r: (r["deleted"], r["id"]))
                if r["customer_id"] == sugar_id
            ]
        elif sql == cf.SELECT_ROW_HOLDING_NAME:
            name, row_id = params
            self._result = [
                (r["id"],) for r in db.rows
                if r["customer"].lower() == name.lower() and r["id"] != row_id
            ]
        elif sql == cf.UPDATE_CUSTOMER_KEY:
            name, row_id = params
            for r in db.rows:
                if r["id"] == row_id:
                    r["customer"] = name
            self._result = []
        elif sql == cf.INSERT_MINIMAL_ROW:
            name, sugar_id = params
            if any(r["customer"].lower() == name.lower() for r in db.rows):
                raise pyodbc.IntegrityError("23000", "Cannot insert duplicate key row")
            db.rows.append({
                "id": max((r["id"] for r in db.rows), default=0) + 1,
                "customer": name, "customer_id": sugar_id, "deleted": 0,
            })
            self._result = []
        elif sql == cf.INSERT_AUDIT_ROW:
            db.audit.append(params)
            self._result = []
        else:
            raise AssertionError(f"unexpected SQL: {sql}")

    def fetchall(self):
        return list(self._result)

    def fetchone(self):
        return self._result[0] if self._result else None


class FakeDB:
    def __init__(self, rows=None):
        self.rows = [
            {"deleted": 0, **row} for row in (rows or [])
        ]
        self.audit = []
        self.fail_on = None
        self.committed = 0
        self._snapshot = None
        self.closed = 0

    # connection interface
    def cursor(self):
        if self._snapshot is None:
            self._snapshot = (copy.deepcopy(self.rows), list(self.audit))
        return FakeCursor(self)

    def commit(self):
        self.committed += 1
        self._snapshot = None

    def rollback(self):
        if self._snapshot is not None:
            self.rows, self.audit = copy.deepcopy(self._snapshot[0]), list(self._snapshot[1])
        self._snapshot = None

    def close(self):
        self.closed += 1


@pytest.fixture
def fake_db(monkeypatch):
    """Factory: fake_db(rows) installs a FakeDB as every _connect() result."""
    def make(rows=None):
        db = FakeDB(rows)
        monkeypatch.setattr(cf, "_connect", lambda dsn: db)
        return db
    return make


@pytest.fixture
def no_shortcuts(monkeypatch):
    """Record shortcut writes instead of calling WScript.Shell."""
    written = []

    class Shell:
        def CreateShortCut(self, path):  # noqa: N802 - COM spelling
            class Link:
                def save(inner):
                    written.append((path, inner.Targetpath))
            return Link()

    monkeypatch.setattr(cf, "_shell", lambda: Shell())
    import file_allocation_core.routing as routing
    monkeypatch.setattr(routing, "_shell", lambda: Shell())
    return written
