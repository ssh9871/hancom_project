"""Atomic file commits and recoverable, persistent command history."""

from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import json
import os
import sqlite3
import tempfile
import time

from .package import MAX_PACKAGE, HwpxError, Package


def digest(data):
    return sha256(data).hexdigest()


def read_file(path):
    with Path(path).open("rb") as f:
        data = f.read(MAX_PACKAGE + 1)
    if len(data) > MAX_PACKAGE:
        raise HwpxError("Package size limit exceeded")
    return data


def history_path(path):
    return path.parent / ".hwpx-history" / (digest(os.fsencode(str(path))) + ".sqlite3")


@contextmanager
def locked(path):
    lock = path.with_name(path.name + ".hwpx-lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise HwpxError(f"Writer lock exists: {lock}. If a crashed writer left it, verify no writer is running before removing it.") from exc
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps({"pid": os.getpid(), "time": time.time()}))
        yield
    finally:
        lock.unlink(missing_ok=True)


def connect(path):
    dbpath = history_path(path)
    dbpath.parent.mkdir(exist_ok=True)
    db = sqlite3.connect(dbpath)
    db.execute("PRAGMA synchronous=FULL")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS revisions (
            id INTEGER PRIMARY KEY, data BLOB NOT NULL, hash TEXT NOT NULL, command TEXT NOT NULL, time REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS pending (oldhash TEXT, newhash TEXT NOT NULL, revision INTEGER NOT NULL, staged INTEGER NOT NULL);
    """)
    pending = db.execute("SELECT oldhash,newhash,revision,staged FROM pending").fetchone()
    if pending:
        current = digest(read_file(path)) if path.exists() else None
        old, new, rev, staged = pending
        if current == new:
            if staged:
                previous = db.execute("SELECT value FROM state WHERE key='cursor'").fetchone()
                db.execute("DELETE FROM revisions WHERE id>? AND id!=?",(int(previous[0]) if previous else 0,rev))
            db.execute("INSERT OR REPLACE INTO state VALUES ('cursor',?)", (str(rev),))
        elif current != old:
            db.close()
            raise HwpxError("Interrupted transaction conflicts with external file; history requires manual recovery")
        else:
            cursor = db.execute("SELECT value FROM state WHERE key='cursor'").fetchone()
            # A new revision was staged before the rename; do not expose it as redo.
            if staged and (cursor is None or rev > int(cursor[0])):
                db.execute("DELETE FROM revisions WHERE id=?", (rev,))
        db.execute("DELETE FROM pending")
        db.commit()
    return db


def validate_data(data, password=None):
    from .crypto import decrypt
    return Package(decrypt(data,password)).validate()


def atomic_write(path, data, expected, password=None):
    current = read_file(path) if path.exists() else None
    if (digest(current) if current is not None else None) != expected:
        raise HwpxError("File changed since it was read; save cancelled")
    fd, temp = tempfile.mkstemp(prefix=".hwpx-", suffix=".tmp", dir=path.parent)
    temp = Path(temp)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        validate_data(read_file(temp),password)
        current = read_file(path) if path.exists() else None
        if (digest(current) if current is not None else None) != expected:
            raise HwpxError("External modification detected before commit")
        if expected is None and os.name == "nt":
            # On Windows rename fails if the destination exists, without requiring hard links.
            os.rename(temp, path)
        elif expected is None:
            # POSIX rename would overwrite a destination created after the version check.
            os.link(temp, path)
        else:
            os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def save(path, data, expected=None, command="edit", password=None):
    path = Path(path).absolute()
    if path.suffix.lower() != ".hwpx":
        raise HwpxError("Output must use the .hwpx extension")
    validate_data(data,password)
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked(path):
        before = read_file(path) if path.exists() else None
        oldhash = digest(before) if before is not None else None
        if oldhash != expected:
            raise HwpxError("Output already exists or changed; use explicit --in-place for the input file")
        if before == data:
            return {"output": str(path), "version": digest(data), "changed": False}
        db = connect(path)
        try:
            cursor_row = db.execute("SELECT value FROM state WHERE key='cursor'").fetchone()
            if cursor_row:
                cursor = int(cursor_row[0])
                recorded = db.execute("SELECT hash FROM revisions WHERE id=?", (cursor,)).fetchone()
                if recorded is None or recorded[0] != oldhash:
                    raise HwpxError("History and file differ; use a new output path to start a new history")
            else:
                cursor = 0
                if before is not None:
                    db.execute("INSERT INTO revisions VALUES (0,?,?,?,?)", (before, oldhash, "initial", time.time()))
                    db.execute("INSERT INTO state VALUES ('cursor','0')")
            if before is not None:
                backup = path.with_name(path.name + ".bak")
                try:
                    with backup.open("xb") as f:
                        f.write(before)
                        f.flush()
                        os.fsync(f.fileno())
                except FileExistsError:
                    pass
            rev = db.execute("SELECT COALESCE(MAX(id),0)+1 FROM revisions").fetchone()[0]
            db.execute("INSERT INTO revisions VALUES (?,?,?,?,?)", (rev, data, digest(data), command, time.time()))
            db.execute("INSERT INTO pending VALUES (?,?,?,1)", (oldhash, digest(data), rev))
            db.commit()
            atomic_write(path, data, oldhash,password)
            db.execute("DELETE FROM revisions WHERE id>? AND id!=?",(cursor,rev))
            db.execute("INSERT OR REPLACE INTO state VALUES ('cursor',?)", (str(rev),))
            db.execute("DELETE FROM pending")
            db.commit()
        finally:
            db.close()
    return {"output": str(path), "version": digest(data), "changed": True}


def history(path, op="list", revision=None, password=None):
    path = Path(path).absolute()
    with locked(path):
        if not history_path(path).exists():
            raise HwpxError("No history for this file")
        db = connect(path)
        try:
            cursor = int(db.execute("SELECT value FROM state WHERE key='cursor'").fetchone()[0])
            rows = db.execute("SELECT id,hash,command,time,length(data) FROM revisions ORDER BY id").fetchall()
            if op == "list":
                return {"cursor": cursor, "bytes": sum(r[4] for r in rows), "revisions": [
                    dict(zip(("id", "version", "command", "time", "bytes"), r)) for r in rows]}
            current = digest(read_file(path))
            recorded = db.execute("SELECT hash FROM revisions WHERE id=?", (cursor,)).fetchone()[0]
            if current != recorded:
                raise HwpxError("External change detected; history operation cancelled")
            if op == "prune":
                require_revision = int(revision) if revision is not None else cursor
                if require_revision > cursor:
                    raise HwpxError("Cannot prune the current revision")
                db.execute("DELETE FROM revisions WHERE id<?", (require_revision,))
                db.commit()
                db.execute("VACUUM")
                return {"pruned_before": require_revision}
            if op == "undo":
                row = db.execute("SELECT id,data,hash FROM revisions WHERE id<? ORDER BY id DESC LIMIT 1", (cursor,)).fetchone()
            elif op == "redo":
                row = db.execute("SELECT id,data,hash FROM revisions WHERE id>? ORDER BY id LIMIT 1", (cursor,)).fetchone()
            elif op == "restore":
                row = db.execute("SELECT id,data,hash FROM revisions WHERE id=?", (revision,)).fetchone()
            else:
                raise HwpxError("Unknown history operation")
            if row is None:
                raise HwpxError("No revision available")
            rev, data, newhash = row
            db.execute("INSERT INTO pending VALUES (?,?,?,0)", (current, newhash, rev))
            db.commit()
            atomic_write(path, data, current,password)
            db.execute("UPDATE state SET value=? WHERE key='cursor'", (str(rev),))
            db.execute("DELETE FROM pending")
            db.commit()
            return {"output": str(path), "revision": rev, "version": newhash}
        finally:
            db.close()
