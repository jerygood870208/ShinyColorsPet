"""Bounded SQLite chat history and relationship memory."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class Message:
    id: int
    character: str
    role: str
    content: str
    created_at: str


@dataclass(frozen=True, slots=True)
class Relationship:
    character: str
    user_key: str
    affection: int = 50
    mood: str = "calm"
    summary: str = ""


@dataclass(frozen=True, slots=True)
class Memory:
    id: int
    character: str
    user_key: str
    content: str
    tags: tuple[str, ...]
    created_at: str
    updated_at: str


class ChatDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _initialize(self) -> None:
        with self._lock, closing(self._connect()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY, character TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user','assistant','system')),
                    content TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS messages_character_id
                    ON messages(character, id DESC);
                CREATE TABLE IF NOT EXISTS relationships (
                    character TEXT NOT NULL, user_key TEXT NOT NULL,
                    affection INTEGER NOT NULL DEFAULT 50 CHECK(affection BETWEEN 0 AND 100),
                    mood TEXT NOT NULL DEFAULT 'calm', summary TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL, PRIMARY KEY(character, user_key)
                );
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY, character TEXT NOT NULL, user_key TEXT NOT NULL,
                    content TEXT NOT NULL, tags_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT ''
                );
            """)
            columns = {str(row[1]) for row in db.execute("PRAGMA table_info(memories)")}
            if "updated_at" not in columns:
                db.execute("ALTER TABLE memories ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")
            db.execute("UPDATE memories SET updated_at=created_at WHERE updated_at='' ")

    def add_message(self, character: str, role: str, content: str) -> Message:
        content = str(content).strip()
        if role not in {"user", "assistant", "system"} or not content:
            raise ValueError("message requires a valid role and non-empty content")
        timestamp = _now()
        with self._lock, closing(self._connect()) as db, db:
            cursor = db.execute("INSERT INTO messages(character,role,content,created_at) "
                "VALUES(?,?,?,?)", (character, role, content, timestamp))
            identifier = int(cursor.lastrowid or 0)
        return Message(identifier, character, role, content, timestamp)

    def history(self, character: str, limit: int = 24) -> list[Message]:
        limit = int(limit)
        with self._lock, closing(self._connect()) as db, db:
            if limit <= 0:
                rows = db.execute(
                    "SELECT id,character,role,content,created_at FROM "
                    "messages WHERE character=? ORDER BY id DESC", (character,),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT id,character,role,content,created_at FROM "
                    "messages WHERE character=? ORDER BY id DESC LIMIT ?",
                    (character, limit),
                ).fetchall()
        return [Message(*row) for row in reversed(rows)]

    def search_messages(self, character: str, query: str = "", limit: int = 500) -> list[Message]:
        value = f"%{query.strip()}%"
        with self._lock, closing(self._connect()) as db, db:
            rows = db.execute(
                "SELECT id,character,role,content,created_at FROM messages "
                "WHERE character=? AND content LIKE ? ORDER BY id DESC LIMIT ?",
                (character, value, max(1, min(2000, limit))),
            ).fetchall()
        return [Message(*row) for row in rows]

    def delete_messages(self, identifiers: list[int]) -> int:
        ids = sorted({int(value) for value in identifiers if int(value) > 0})
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        with self._lock, closing(self._connect()) as db, db:
            cursor = db.execute(f"DELETE FROM messages WHERE id IN ({placeholders})", ids)
            return max(0, cursor.rowcount)

    def relationship(self, character: str, user_key: str = "default") -> Relationship:
        with self._lock, closing(self._connect()) as db, db:
            row = db.execute("SELECT character,user_key,affection,mood,summary FROM relationships "
                "WHERE character=? AND user_key=?", (character, user_key)).fetchone()
        return Relationship(*row) if row else Relationship(character, user_key)

    def update_relationship(self, relationship: Relationship) -> None:
        affection = max(0, min(100, int(relationship.affection)))
        with self._lock, closing(self._connect()) as db, db:
            db.execute(
                "INSERT INTO relationships"
                "(character,user_key,affection,mood,summary,updated_at) "
                "VALUES(?,?,?,?,?,?) ON CONFLICT(character,user_key) DO UPDATE SET "
                "affection=excluded.affection,mood=excluded.mood,summary=excluded.summary,"
                "updated_at=excluded.updated_at", (relationship.character, relationship.user_key,
                affection, relationship.mood, relationship.summary[:2000], _now()))

    def remember(self, character: str, user_key: str, content: str,
                 tags: tuple[str, ...] = ()) -> bool:
        value = " ".join(content.split()).strip()
        if not value:
            return False
        with self._lock, closing(self._connect()) as db, db:
            rows = db.execute(
                "SELECT content FROM memories WHERE character=? AND user_key=?",
                (character, user_key),
            ).fetchall()
            normalized = value.casefold()
            if any(" ".join(str(row[0]).split()).casefold() == normalized for row in rows):
                return False
            timestamp = _now()
            db.execute("INSERT INTO memories"
                "(character,user_key,content,tags_json,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?)", (character, user_key, value[:2000],
                json.dumps(list(tags), ensure_ascii=False), timestamp, timestamp))
        return True

    def memories(self, character: str, user_key: str, limit: int = 12) -> list[str]:
        with self._lock, closing(self._connect()) as db, db:
            rows = db.execute(
                "SELECT content FROM memories WHERE character=? AND user_key=? "
                "ORDER BY id DESC LIMIT ?",
                (character, user_key, max(1, min(50, limit))),
            ).fetchall()
        return [str(row[0]) for row in reversed(rows)]

    def memory_records(self, character: str, user_key: str, query: str = "",
                       limit: int = 500) -> list[Memory]:
        with self._lock, closing(self._connect()) as db, db:
            rows = db.execute(
                "SELECT id,character,user_key,content,tags_json,created_at,updated_at "
                "FROM memories WHERE character=? AND user_key=? AND content LIKE ? "
                "ORDER BY id DESC LIMIT ?",
                (character, user_key, f"%{query.strip()}%", max(1, min(2000, limit))),
            ).fetchall()
        return [Memory(int(row[0]), str(row[1]), str(row[2]), str(row[3]),
                       tuple(json.loads(str(row[4]))), str(row[5]), str(row[6])) for row in rows]

    def update_memory(self, identifier: int, content: str) -> bool:
        value = " ".join(content.split()).strip()
        if not value:
            return False
        with self._lock, closing(self._connect()) as db, db:
            cursor = db.execute("UPDATE memories SET content=?,updated_at=? WHERE id=?",
                                (value[:2000], _now(), int(identifier)))
            return cursor.rowcount > 0

    def delete_memories(self, identifiers: list[int]) -> int:
        ids = sorted({int(value) for value in identifiers if int(value) > 0})
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        with self._lock, closing(self._connect()) as db, db:
            cursor = db.execute(f"DELETE FROM memories WHERE id IN ({placeholders})", ids)
            return max(0, cursor.rowcount)

    def refresh_relationship_summary(self, character: str, user_key: str) -> str:
        records = self.memory_records(character, user_key, limit=12)
        summary = "；".join(item.content for item in reversed(records))[:2000]
        current = self.relationship(character, user_key)
        self.update_relationship(Relationship(character, user_key, current.affection,
                                               current.mood, summary))
        return summary

    def statistics(self, character: str, user_key: str, days: int = 0) -> dict[str, int | str]:
        cutoff = ((datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
                  if days > 0 else "")
        time_filter = " AND created_at>=?" if cutoff else ""
        params: tuple[str, ...] = (character, cutoff) if cutoff else (character,)
        with self._lock, closing(self._connect()) as db, db:
            total, user_count, assistant_count, days = db.execute(
                "SELECT COUNT(*),SUM(role='user'),SUM(role='assistant'),"
                "COUNT(DISTINCT substr(created_at,1,10)) FROM messages WHERE character=?" +
                time_filter, params,
            ).fetchone()
            memories = db.execute(
                "SELECT COUNT(*) FROM memories WHERE character=? AND user_key=?",
                (character, user_key),
            ).fetchone()[0]
            latest = db.execute("SELECT MAX(created_at) FROM messages WHERE character=?" +
                                time_filter, params).fetchone()[0]
        return {"messages": int(total or 0), "user_messages": int(user_count or 0),
                "assistant_messages": int(assistant_count or 0), "active_days": int(days or 0),
                "memories": int(memories or 0), "latest": str(latest or "")}

    def clear(self, category: str) -> int:
        tables = {
            "messages": ("messages",),
            "memory": ("memories", "relationships"),
            "all": ("messages", "memories", "relationships"),
        }.get(category)
        if tables is None:
            raise ValueError("unknown data category")
        deleted = 0
        with self._lock, closing(self._connect()) as db, db:
            for table in tables:
                cursor = db.execute(f"DELETE FROM {table}")
                deleted += max(0, cursor.rowcount)
        return deleted
