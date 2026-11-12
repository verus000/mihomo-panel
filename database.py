"""SQLite storage with short read transactions and serialized writes."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3

JSON_COLUMNS = {'tags', 'last_probe'}
BOOLEAN_COLUMNS = {'enabled', 'manual_country', 'available', 'remote'}


def record(cursor, values):
    row = dict(zip((column[0] for column in cursor.description), values))
    for key in JSON_COLUMNS & row.keys():
        if row[key] is not None:
            row[key] = json.loads(row[key])
    for key in BOOLEAN_COLUMNS & row.keys():
        row[key] = bool(row[key])
    return row


class Database:
    def __init__(self, path):
        self.path = Path(path)

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=90, isolation_level=None)
        try:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA synchronous=FULL')
            db.row_factory = record
            return db
        except BaseException:
            db.close()
            raise

    def initialize(self):
        self.path.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
        # Create privately even when invoked outside systemd's UMask.
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        db = self._connect()
        try:
            if db.execute('PRAGMA user_version').fetchone()['user_version'] > 1:
                raise ValueError('数据库版本高于当前程序，拒绝降级')
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript(Path(__file__).with_name('schema.sql').read_text())
        finally:
            db.close()

    @contextmanager
    def connection(self, *, write=False):
        db = self._connect()
        try:
            # Taking the writer lock before reading avoids stale snapshot upgrades.
            db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            if not write:
                db.execute('PRAGMA query_only=ON')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()
