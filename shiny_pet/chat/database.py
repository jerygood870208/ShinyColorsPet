"""Bounded SQLite chat history and relationship memory."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _utc_timestamp(value: str) -> str:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class Message:
    id: int
    character: str
    role: str
    content: str
    created_at: str
    source: str = "chat"
    trigger_event_type: str = ""
    scheduled_for: str = ""
    voice_cache_key: str = ""


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


@dataclass(frozen=True, slots=True)
class ScheduleState:
    character_id: str
    proactive_enabled: bool = False
    proactive_tier: str = "normal"
    timezone: str = "system"
    quiet_hours_start: str = "23:00"
    quiet_hours_end: str = "08:00"
    daily_proactive_cap: int = 3
    last_interaction_at: str = ""
    last_checked_at: str = ""
    last_producer_birthday_year: int = 0
    idol_birthday_ack_year: int = 0


@dataclass(frozen=True, slots=True)
class LoreHit:
    kind: str
    title: str
    content: str
    importance: int


@dataclass(frozen=True, slots=True)
class LoreRecord:
    id: int
    character: str
    title: str
    content: str
    tags: tuple[str, ...]
    importance: int
    updated_at: str
    last_used_at: str = ""


@dataclass(frozen=True, slots=True)
class CharacterRelationRecord:
    id: int
    character: str
    other_character: str
    relation_label: str
    description: str
    importance: int
    updated_at: str


class ChatDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()
        self.fts5_trigram_available = False
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
                CREATE TABLE IF NOT EXISTS application_metadata (
                    key TEXT PRIMARY KEY, value TEXT NOT NULL
                );
            """)
            message_columns = {str(row[1]) for row in db.execute("PRAGMA table_info(messages)")}
            if "source" not in message_columns:
                db.execute("ALTER TABLE messages ADD COLUMN source TEXT NOT NULL DEFAULT 'chat'")
            if "trigger_event_type" not in message_columns:
                db.execute("ALTER TABLE messages ADD COLUMN trigger_event_type TEXT")
            if "scheduled_for" not in message_columns:
                db.execute("ALTER TABLE messages ADD COLUMN scheduled_for TEXT")
            if "voice_cache_key" not in message_columns:
                db.execute("ALTER TABLE messages ADD COLUMN voice_cache_key TEXT")
            db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS messages_voice_cache_key "
                "ON messages(voice_cache_key) "
                "WHERE voice_cache_key IS NOT NULL AND voice_cache_key != ''"
            )
            # Canonical storage is UTC. Older scheduler rows retained the offset supplied by
            # the model/application, so normalize them in-place without changing the instant.
            db.execute(
                "UPDATE messages SET scheduled_for="
                "strftime('%Y-%m-%dT%H:%M:%S+00:00',scheduled_for) "
                "WHERE scheduled_for IS NOT NULL AND julianday(scheduled_for) IS NOT NULL"
            )
            columns = {str(row[1]) for row in db.execute("PRAGMA table_info(memories)")}
            if "updated_at" not in columns:
                db.execute("ALTER TABLE memories ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")
            db.execute("UPDATE memories SET updated_at=created_at WHERE updated_at='' ")

            db.executescript("""
                CREATE TABLE IF NOT EXISTS character_schedule_state (
                    character_id TEXT PRIMARY KEY,
                    proactive_enabled INTEGER NOT NULL DEFAULT 0,
                    proactive_tier TEXT NOT NULL DEFAULT 'normal',
                    timezone TEXT NOT NULL DEFAULT 'system',
                    quiet_hours_start TEXT NOT NULL DEFAULT '23:00',
                    quiet_hours_end TEXT NOT NULL DEFAULT '08:00',
                    daily_proactive_cap INTEGER NOT NULL DEFAULT 3,
                    last_interaction_at TEXT,
                    last_checked_at TEXT,
                    last_producer_birthday_year INTEGER,
                    idol_birthday_ack_year INTEGER,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS character_schedule_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    character_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    event_key TEXT NOT NULL,
                    scheduled_for TEXT NOT NULL,
                    fired_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 1,
                    next_attempt_at TEXT,
                    message_id INTEGER,
                    detail TEXT,
                    UNIQUE(character_id, event_type, event_key)
                );
                CREATE INDEX IF NOT EXISTS schedule_log_character_type
                    ON character_schedule_log(character_id, event_type, scheduled_for DESC);
                CREATE TABLE IF NOT EXISTS character_lore (
                    id INTEGER PRIMARY KEY,
                    character TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    importance INTEGER NOT NULL DEFAULT 5,
                    source TEXT NOT NULL DEFAULT 'manual',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_used_at TEXT,
                    UNIQUE(character, title)
                );
                CREATE TABLE IF NOT EXISTS character_relations (
                    id INTEGER PRIMARY KEY,
                    character TEXT NOT NULL,
                    other_character TEXT NOT NULL,
                    relation_label TEXT NOT NULL,
                    description TEXT NOT NULL,
                    importance INTEGER NOT NULL DEFAULT 5,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(character, other_character, relation_label)
                );
            """)
            self.fts5_trigram_available = self._install_lore_fts(db)

    @staticmethod
    def _install_lore_fts(db: sqlite3.Connection) -> bool:
        try:
            db.execute(
                "CREATE VIRTUAL TABLE temp.__shiny_fts_probe USING fts5(value, tokenize='trigram')"
            )
            db.execute("INSERT INTO temp.__shiny_fts_probe(value) VALUES('生日快樂')")
            probe = db.execute(
                "SELECT rowid FROM temp.__shiny_fts_probe WHERE value MATCH '生日快'"
            ).fetchone()
            if probe is None:
                raise sqlite3.OperationalError("FTS5 trigram query probe failed")
            db.execute("DROP TABLE temp.__shiny_fts_probe")
            existing_columns = {
                str(row[1]) for row in db.execute("PRAGMA table_info(character_lore_fts)")
            }
            if existing_columns and "tags_json" not in existing_columns:
                db.executescript("""
                    DROP TRIGGER IF EXISTS character_lore_ai;
                    DROP TRIGGER IF EXISTS character_lore_ad;
                    DROP TRIGGER IF EXISTS character_lore_au;
                    DROP TABLE character_lore_fts;
                """)
            db.executescript("""
                CREATE VIRTUAL TABLE IF NOT EXISTS character_lore_fts USING fts5(
                    content, title, tags_json, content='character_lore', content_rowid='id',
                    tokenize='trigram'
                );
                DROP TRIGGER IF EXISTS character_lore_ai;
                DROP TRIGGER IF EXISTS character_lore_ad;
                DROP TRIGGER IF EXISTS character_lore_au;
                CREATE TRIGGER IF NOT EXISTS character_lore_ai AFTER INSERT ON character_lore BEGIN
                    INSERT INTO character_lore_fts(rowid,content,title,tags_json)
                    VALUES(new.id,new.content,new.title,new.tags_json);
                END;
                CREATE TRIGGER IF NOT EXISTS character_lore_ad AFTER DELETE ON character_lore BEGIN
                    INSERT INTO character_lore_fts(character_lore_fts,rowid,content,title,tags_json)
                    VALUES('delete',old.id,old.content,old.title,old.tags_json);
                END;
                CREATE TRIGGER IF NOT EXISTS character_lore_au AFTER UPDATE ON character_lore BEGIN
                    INSERT INTO character_lore_fts(character_lore_fts,rowid,content,title,tags_json)
                    VALUES('delete',old.id,old.content,old.title,old.tags_json);
                    INSERT INTO character_lore_fts(rowid,content,title,tags_json)
                    VALUES(new.id,new.content,new.title,new.tags_json);
                END;
                INSERT INTO character_lore_fts(character_lore_fts) VALUES('rebuild');
            """)
            return True
        except sqlite3.Error:
            return False

    def add_message(
        self,
        character: str,
        role: str,
        content: str,
        *,
        source: str = "chat",
        trigger_event_type: str = "",
        scheduled_for: str = "",
    ) -> Message:
        content = str(content).strip()
        if role not in {"user", "assistant", "system"} or not content:
            raise ValueError("message requires a valid role and non-empty content")
        if source not in {"chat", "scheduler"}:
            raise ValueError("unknown message source")
        timestamp = _now()
        scheduled_timestamp = _utc_timestamp(scheduled_for) if scheduled_for else ""
        with self._lock, closing(self._connect()) as db, db:
            cursor = db.execute(
                "INSERT INTO messages(character,role,content,created_at,source,"
                "trigger_event_type,scheduled_for) VALUES(?,?,?,?,?,?,?)",
                (
                    character,
                    role,
                    content,
                    timestamp,
                    source,
                    trigger_event_type or None,
                    scheduled_timestamp or None,
                ),
            )
            identifier = int(cursor.lastrowid or 0)
        return Message(
            identifier,
            character,
            role,
            content,
            timestamp,
            source,
            trigger_event_type,
            scheduled_timestamp,
        )

    @staticmethod
    def _message(row: tuple[object, ...]) -> Message:
        return Message(
            int(str(row[0])),
            str(row[1]),
            str(row[2]),
            str(row[3]),
            str(row[4]),
            str(row[5] or "chat"),
            str(row[6] or ""),
            str(row[7] or ""),
            str(row[8] or ""),
        )

    def history(self, character: str, limit: int = 24) -> list[Message]:
        limit = int(limit)
        with self._lock, closing(self._connect()) as db, db:
            if limit <= 0:
                rows = db.execute(
                    "SELECT id,character,role,content,created_at,source,trigger_event_type,"
                    "scheduled_for,voice_cache_key FROM messages WHERE character=? "
                    "ORDER BY julianday(COALESCE(scheduled_for,created_at)),id",
                    (character,),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM (SELECT id,character,role,content,created_at,source,"
                    "trigger_event_type,scheduled_for,voice_cache_key FROM messages "
                    "WHERE character=? "
                    "ORDER BY julianday(COALESCE(scheduled_for,created_at)) DESC,id DESC LIMIT ?) "
                    "ORDER BY julianday(COALESCE(scheduled_for,created_at)),id",
                    (character, limit),
                ).fetchall()
        return [self._message(row) for row in rows]

    def search_messages(self, character: str, query: str = "", limit: int = 500) -> list[Message]:
        value = f"%{query.strip()}%"
        with self._lock, closing(self._connect()) as db, db:
            rows = db.execute(
                "SELECT id,character,role,content,created_at,source,trigger_event_type,"
                "scheduled_for,voice_cache_key FROM messages "
                "WHERE character=? AND content LIKE ? "
                "ORDER BY julianday(COALESCE(scheduled_for,created_at)) DESC,id DESC LIMIT ?",
                (character, value, max(1, min(2000, limit))),
            ).fetchall()
        return [self._message(row) for row in rows]

    def set_message_voice_cache_key(self, message_id: int, cache_key: str) -> bool:
        """Persist the generated voice file associated with one assistant message."""
        key = Path(str(cache_key)).name
        if not key or key != str(cache_key):
            raise ValueError("voice cache key must be a plain filename")
        with self._lock, closing(self._connect()) as db, db:
            cursor = db.execute(
                "UPDATE messages SET voice_cache_key=? "
                "WHERE id=? AND role='assistant'",
                (key, int(message_id)),
            )
            return cursor.rowcount == 1

    def backfill_voice_cache_keys(
        self,
        entries: list[tuple[str, float]],
        max_delay_seconds: float = 60.0,
        *,
        migration_key: str = "",
    ) -> int:
        """Match legacy audio to the nearest preceding unlinked assistant message."""
        maximum_delay = max(0.0, float(max_delay_seconds))
        with self._lock, closing(self._connect()) as db, db:
            if migration_key and db.execute(
                "SELECT 1 FROM application_metadata WHERE key=?", (migration_key,)
            ).fetchone():
                return 0
            used_keys = {
                str(row[0])
                for row in db.execute(
                    "SELECT voice_cache_key FROM messages "
                    "WHERE voice_cache_key IS NOT NULL AND voice_cache_key != ''"
                )
            }
            messages: list[tuple[int, float]] = []
            for identifier, created_at in db.execute(
                "SELECT id,created_at FROM messages "
                "WHERE role='assistant' AND COALESCE(voice_cache_key,'')=''"
            ):
                try:
                    timestamp = datetime.fromisoformat(str(created_at)).timestamp()
                except ValueError:
                    continue
                messages.append((int(identifier), timestamp))

            matched_ids: set[int] = set()
            matched = 0
            for cache_key, audio_timestamp in sorted(entries, key=lambda item: item[1]):
                key = Path(str(cache_key)).name
                if not key or key != str(cache_key) or key in used_keys:
                    continue
                candidates = [
                    (identifier, message_timestamp)
                    for identifier, message_timestamp in messages
                    if identifier not in matched_ids
                    and 0.0 <= float(audio_timestamp) - message_timestamp <= maximum_delay
                ]
                if not candidates:
                    continue
                identifier, _timestamp = max(candidates, key=lambda item: item[1])
                db.execute(
                    "UPDATE messages SET voice_cache_key=? WHERE id=?",
                    (key, identifier),
                )
                used_keys.add(key)
                matched_ids.add(identifier)
                matched += 1
            if migration_key:
                db.execute(
                    "INSERT INTO application_metadata(key,value) VALUES(?,?)",
                    (migration_key, _now()),
                )
            return matched

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
            row = db.execute(
                "SELECT character,user_key,affection,mood,summary FROM relationships "
                "WHERE character=? AND user_key=?",
                (character, user_key),
            ).fetchone()
        return Relationship(*row) if row else Relationship(character, user_key)

    def update_relationship(self, relationship: Relationship) -> None:
        affection = max(0, min(100, int(relationship.affection)))
        with self._lock, closing(self._connect()) as db, db:
            db.execute(
                "INSERT INTO relationships"
                "(character,user_key,affection,mood,summary,updated_at) "
                "VALUES(?,?,?,?,?,?) ON CONFLICT(character,user_key) DO UPDATE SET "
                "affection=excluded.affection,mood=excluded.mood,summary=excluded.summary,"
                "updated_at=excluded.updated_at",
                (
                    relationship.character,
                    relationship.user_key,
                    affection,
                    relationship.mood,
                    relationship.summary[:2000],
                    _now(),
                ),
            )

    def remember(
        self, character: str, user_key: str, content: str, tags: tuple[str, ...] = ()
    ) -> bool:
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
            db.execute(
                "INSERT INTO memories"
                "(character,user_key,content,tags_json,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?)",
                (
                    character,
                    user_key,
                    value[:2000],
                    json.dumps(list(tags), ensure_ascii=False),
                    timestamp,
                    timestamp,
                ),
            )
        return True

    def memories(self, character: str, user_key: str, limit: int = 12) -> list[str]:
        with self._lock, closing(self._connect()) as db, db:
            rows = db.execute(
                "SELECT content FROM memories WHERE character=? AND user_key=? "
                "ORDER BY id DESC LIMIT ?",
                (character, user_key, max(1, min(50, limit))),
            ).fetchall()
        return [str(row[0]) for row in reversed(rows)]

    def memory_records(
        self, character: str, user_key: str, query: str = "", limit: int = 500
    ) -> list[Memory]:
        with self._lock, closing(self._connect()) as db, db:
            rows = db.execute(
                "SELECT id,character,user_key,content,tags_json,created_at,updated_at "
                "FROM memories WHERE character=? AND user_key=? AND content LIKE ? "
                "ORDER BY id DESC LIMIT ?",
                (character, user_key, f"%{query.strip()}%", max(1, min(2000, limit))),
            ).fetchall()
        return [
            Memory(
                int(row[0]),
                str(row[1]),
                str(row[2]),
                str(row[3]),
                tuple(json.loads(str(row[4]))),
                str(row[5]),
                str(row[6]),
            )
            for row in rows
        ]

    def update_memory(self, identifier: int, content: str) -> bool:
        value = " ".join(content.split()).strip()
        if not value:
            return False
        with self._lock, closing(self._connect()) as db, db:
            cursor = db.execute(
                "UPDATE memories SET content=?,updated_at=? WHERE id=?",
                (value[:2000], _now(), int(identifier)),
            )
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
        self.update_relationship(
            Relationship(character, user_key, current.affection, current.mood, summary)
        )
        return summary

    def ensure_schedule_state(self, character: str) -> ScheduleState:
        if not character.strip():
            raise ValueError("character is required")
        timestamp = _now()
        with self._lock, closing(self._connect()) as db, db:
            db.execute(
                "INSERT OR IGNORE INTO character_schedule_state(character_id,updated_at) "
                "VALUES(?,?)",
                (character, timestamp),
            )
            row = db.execute(
                "SELECT character_id,proactive_enabled,proactive_tier,timezone,"
                "quiet_hours_start,quiet_hours_end,daily_proactive_cap,last_interaction_at,"
                "last_checked_at,last_producer_birthday_year,idol_birthday_ack_year "
                "FROM character_schedule_state WHERE character_id=?",
                (character,),
            ).fetchone()
        assert row is not None
        return ScheduleState(
            str(row[0]),
            bool(row[1]),
            str(row[2]),
            str(row[3]),
            str(row[4] or ""),
            str(row[5] or ""),
            int(row[6]),
            str(row[7] or ""),
            str(row[8] or ""),
            int(row[9] or 0),
            int(row[10] or 0),
        )

    def schedule_states(self, *, enabled_only: bool = False) -> list[ScheduleState]:
        suffix = " WHERE proactive_enabled=1" if enabled_only else ""
        with self._lock, closing(self._connect()) as db:
            rows = db.execute(
                "SELECT character_id FROM character_schedule_state"
                + suffix
                + " ORDER BY character_id"
            ).fetchall()
        return [self.ensure_schedule_state(str(row[0])) for row in rows]

    def update_schedule_preferences(
        self, character: str, *, enabled: bool, tier: str, quiet_start: str, quiet_end: str
    ) -> ScheduleState:
        caps = {"quiet": 1, "normal": 3, "clingy": 6}
        if tier not in caps:
            raise ValueError("unknown proactive tier")
        for value in (quiet_start, quiet_end):
            if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value) is None:
                raise ValueError("quiet hours must use HH:MM")
        self.ensure_schedule_state(character)
        with self._lock, closing(self._connect()) as db, db:
            db.execute(
                "UPDATE character_schedule_state SET proactive_enabled=?,proactive_tier=?,"
                "timezone='system',quiet_hours_start=?,quiet_hours_end=?,"
                "daily_proactive_cap=?,updated_at=? WHERE character_id=?",
                (int(enabled), tier, quiet_start, quiet_end, caps[tier], _now(), character),
            )
        return self.ensure_schedule_state(character)

    def record_user_interaction(self, character: str, created_at: str) -> None:
        self.ensure_schedule_state(character)
        with self._lock, closing(self._connect()) as db, db:
            db.execute(
                "UPDATE character_schedule_state SET last_interaction_at=?,updated_at=? "
                "WHERE character_id=?",
                (created_at, _now(), character),
            )

    def set_schedule_year(self, character: str, field: str, year: int) -> None:
        if field not in {"last_producer_birthday_year", "idol_birthday_ack_year"}:
            raise ValueError("unknown schedule year field")
        self.ensure_schedule_state(character)
        with self._lock, closing(self._connect()) as db, db:
            db.execute(
                f"UPDATE character_schedule_state SET {field}=?,updated_at=? WHERE character_id=?",
                (int(year), _now(), character),
            )

    def update_last_checked(self, character: str, checked_at: str) -> None:
        self.ensure_schedule_state(character)
        with self._lock, closing(self._connect()) as db, db:
            db.execute(
                "UPDATE character_schedule_state SET last_checked_at=?,updated_at=? "
                "WHERE character_id=?",
                (checked_at, _now(), character),
            )

    def claim_schedule_event(
        self, character: str, event_type: str, event_key: str, scheduled_for: str, now: str
    ) -> int:
        """Atomically claim a new, retryable, or stale queued event."""
        stale_before = (datetime.fromisoformat(now) - timedelta(minutes=10)).isoformat(
            timespec="seconds"
        )
        with self._lock, closing(self._connect()) as db, db:
            cursor = db.execute(
                "INSERT OR IGNORE INTO character_schedule_log"
                "(character_id,event_type,event_key,scheduled_for,fired_at,status) "
                "VALUES(?,?,?,?,?,'queued')",
                (character, event_type, event_key, scheduled_for, now),
            )
            if cursor.rowcount:
                return int(cursor.lastrowid or 0)
            row = db.execute(
                "SELECT id,status,attempt_count,next_attempt_at,fired_at "
                "FROM character_schedule_log WHERE character_id=? AND event_type=? "
                "AND event_key=?",
                (character, event_type, event_key),
            ).fetchone()
            if row is None or int(row[2]) >= 3:
                return 0
            retryable = (str(row[1]) == "error" and str(row[3] or "") <= now) or (
                str(row[1]) == "queued" and str(row[4]) <= stale_before
            )
            if not retryable:
                return 0
            db.execute(
                "UPDATE character_schedule_log SET status='queued',attempt_count=attempt_count+1,"
                "fired_at=?,next_attempt_at=NULL,detail=NULL WHERE id=?",
                (now, int(row[0])),
            )
            return int(row[0])

    def complete_schedule_event(
        self, log_id: int, character: str, content: str, event_type: str, scheduled_for: str
    ) -> Message:
        value = str(content).strip()
        if not value:
            raise ValueError("scheduled message cannot be empty")
        created_at = _now()
        scheduled_timestamp = _utc_timestamp(scheduled_for)
        with self._lock, closing(self._connect()) as db, db:
            cursor = db.execute(
                "INSERT INTO messages(character,role,content,created_at,source,"
                "trigger_event_type,scheduled_for) VALUES(?,'assistant',?,?,?,?,?)",
                (character, value, created_at, "scheduler", event_type, scheduled_timestamp),
            )
            message_id = int(cursor.lastrowid or 0)
            updated = db.execute(
                "UPDATE character_schedule_log SET status='sent',message_id=?,detail=NULL "
                "WHERE id=? AND status='queued'",
                (message_id, int(log_id)),
            )
            if updated.rowcount != 1:
                raise RuntimeError("scheduled event claim is no longer active")
        return Message(
            message_id,
            character,
            "assistant",
            value,
            created_at,
            "scheduler",
            event_type,
            scheduled_timestamp,
        )

    def fail_schedule_event(self, log_id: int, detail: str) -> None:
        with self._lock, closing(self._connect()) as db, db:
            row = db.execute(
                "SELECT attempt_count FROM character_schedule_log WHERE id=?", (int(log_id),)
            ).fetchone()
            if row is None:
                return
            attempts = int(row[0])
            delay = 5 if attempts == 1 else 30
            next_at = ""
            if attempts < 3:
                next_at = (datetime.now(timezone.utc) + timedelta(minutes=delay)).isoformat(
                    timespec="seconds"
                )
            db.execute(
                "UPDATE character_schedule_log SET status='error',next_attempt_at=?,detail=? "
                "WHERE id=?",
                (next_at or None, str(detail)[:2000], int(log_id)),
            )

    def record_skipped_event(
        self, character: str, event_type: str, event_key: str, scheduled_for: str, detail: str
    ) -> None:
        now = _now()
        with self._lock, closing(self._connect()) as db, db:
            db.execute(
                "INSERT OR IGNORE INTO character_schedule_log"
                "(character_id,event_type,event_key,scheduled_for,fired_at,status,detail) "
                "VALUES(?,?,?,?,?,'skipped',?)",
                (character, event_type, event_key, scheduled_for, now, detail[:2000]),
            )

    def latest_sent_event(self, character: str, event_type: str) -> str:
        with self._lock, closing(self._connect()) as db:
            row = db.execute(
                "SELECT scheduled_for FROM character_schedule_log WHERE character_id=? "
                "AND event_type=? AND status='sent' ORDER BY scheduled_for DESC LIMIT 1",
                (character, event_type),
            ).fetchone()
        return str(row[0]) if row else ""

    def latest_checkin_anchor(self, character: str) -> str:
        with self._lock, closing(self._connect()) as db:
            row = db.execute(
                "SELECT scheduled_for FROM character_schedule_log WHERE character_id=? "
                "AND event_type='checkin' AND (status='sent' OR "
                "(status='error' AND attempt_count>=3)) "
                "ORDER BY scheduled_for DESC LIMIT 1",
                (character,),
            ).fetchone()
        return str(row[0]) if row else ""

    def sent_event_count(self, character: str, event_type: str, start: str, end: str) -> int:
        with self._lock, closing(self._connect()) as db:
            row = db.execute(
                "SELECT COUNT(*) FROM character_schedule_log WHERE character_id=? "
                "AND event_type=? AND status='sent' AND scheduled_for>=? AND scheduled_for<?",
                (character, event_type, start, end),
            ).fetchone()
        return int(row[0] or 0)

    def user_messages_between(self, character: str, start: str, end: str) -> list[str]:
        with self._lock, closing(self._connect()) as db:
            rows = db.execute(
                "SELECT content FROM messages WHERE character=? AND role='user' "
                "AND created_at>=? AND created_at<? ORDER BY created_at,id",
                (character, start, end),
            ).fetchall()
        return [str(row[0]) for row in rows]

    def import_lore(
        self, character: str, lore: list[dict[str, object]], relations: list[dict[str, object]]
    ) -> tuple[int, int]:
        if not character.strip():
            raise ValueError("character is required")

        def text_field(item: dict[str, object], key: str, limit: int) -> str:
            value = " ".join(str(item.get(key, "")).split()).strip()
            if not value or len(value) > limit:
                raise ValueError(f"{key} must contain 1-{limit} characters")
            return value

        checked_lore: list[tuple[str, str, str, int]] = []
        for item in lore:
            title = text_field(item, "title", 200)
            content = text_field(item, "content", 1500)
            tags = item.get("tags", [])
            importance = item.get("importance", 5)
            if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
                raise ValueError("tags must be an array of text")
            if type(importance) is not int or not 1 <= importance <= 10:
                raise ValueError("importance must be 1-10")
            checked_lore.append((title, content, json.dumps(tags, ensure_ascii=False), importance))
        checked_relations: list[tuple[str, str, str, int]] = []
        for item in relations:
            other = text_field(item, "other_character", 200)
            label = text_field(item, "relation_label", 200)
            description = text_field(item, "description", 1500)
            importance = item.get("importance", 5)
            if type(importance) is not int or not 1 <= importance <= 10:
                raise ValueError("importance must be 1-10")
            checked_relations.append((other, label, description, importance))
        timestamp = _now()
        with self._lock, closing(self._connect()) as db, db:
            for title, content, tags_json, importance in checked_lore:
                db.execute(
                    "INSERT INTO character_lore(character,title,content,tags_json,importance,"
                    "source,enabled,created_at,updated_at) VALUES(?,?,?,?,?,'imported',1,?,?) "
                    "ON CONFLICT(character,title) DO UPDATE SET content=excluded.content,"
                    "tags_json=excluded.tags_json,importance=excluded.importance,"
                    "source='imported',enabled=1,updated_at=excluded.updated_at",
                    (character, title, content, tags_json, importance, timestamp, timestamp),
                )
            for other, label, description, importance in checked_relations:
                db.execute(
                    "INSERT INTO character_relations(character,other_character,relation_label,"
                    "description,importance,enabled,created_at,updated_at) "
                    "VALUES(?,?,?,?,?,1,?,?) ON CONFLICT(character,other_character,relation_label) "
                    "DO UPDATE SET description=excluded.description,importance=excluded.importance,"
                    "enabled=1,updated_at=excluded.updated_at",
                    (character, other, label, description, importance, timestamp, timestamp),
                )
        return len(checked_lore), len(checked_relations)

    def lore_records(self, character: str) -> list[LoreRecord]:
        """Return all editable lore for one character."""
        with self._lock, closing(self._connect()) as db:
            rows = db.execute(
                "SELECT id,character,title,content,tags_json,importance,updated_at,last_used_at "
                "FROM character_lore WHERE character=? AND enabled=1 "
                "ORDER BY importance DESC,title COLLATE NOCASE,id",
                (character,),
            ).fetchall()
        records: list[LoreRecord] = []
        for row in rows:
            try:
                raw_tags = json.loads(str(row[4]))
            except json.JSONDecodeError:
                raw_tags = []
            tags = tuple(str(tag) for tag in raw_tags) if isinstance(raw_tags, list) else ()
            records.append(
                LoreRecord(
                    int(str(row[0])),
                    str(row[1]),
                    str(row[2]),
                    str(row[3]),
                    tags,
                    int(str(row[5])),
                    str(row[6]),
                    str(row[7] or ""),
                )
            )
        return records

    def character_relation_records(self, character: str) -> list[CharacterRelationRecord]:
        """Return all editable inter-character relationships for one character."""
        with self._lock, closing(self._connect()) as db:
            rows = db.execute(
                "SELECT id,character,other_character,relation_label,description,importance,"
                "updated_at FROM character_relations WHERE character=? AND enabled=1 "
                "ORDER BY importance DESC,other_character COLLATE NOCASE,relation_label,id",
                (character,),
            ).fetchall()
        return [
            CharacterRelationRecord(
                int(str(row[0])),
                str(row[1]),
                str(row[2]),
                str(row[3]),
                str(row[4]),
                int(str(row[5])),
                str(row[6]),
            )
            for row in rows
        ]

    def save_lore_record(
        self,
        character: str,
        title: str,
        content: str,
        tags: list[str],
        importance: int,
        record_id: int = 0,
    ) -> int:
        """Create or update one lore record, preserving the character boundary."""
        value_title = " ".join(str(title).split()).strip()
        value_content = " ".join(str(content).split()).strip()
        value_tags = [" ".join(str(tag).split()).strip() for tag in tags]
        if not character.strip():
            raise ValueError("character is required")
        if not 1 <= len(value_title) <= 200:
            raise ValueError("title must contain 1-200 characters")
        if not 1 <= len(value_content) <= 1500:
            raise ValueError("content must contain 1-1500 characters")
        if any(not tag for tag in value_tags):
            raise ValueError("tags must not contain empty text")
        if type(importance) is not int or not 1 <= importance <= 10:
            raise ValueError("importance must be 1-10")
        timestamp = _now()
        try:
            with self._lock, closing(self._connect()) as db, db:
                if record_id:
                    cursor = db.execute(
                        "UPDATE character_lore SET title=?,content=?,tags_json=?,importance=?,"
                        "source='manual',updated_at=? WHERE id=? AND character=?",
                        (
                            value_title,
                            value_content,
                            json.dumps(value_tags, ensure_ascii=False),
                            importance,
                            timestamp,
                            int(record_id),
                            character,
                        ),
                    )
                    if cursor.rowcount != 1:
                        raise ValueError("找不到要更新的角色知識")
                    return int(record_id)
                cursor = db.execute(
                    "INSERT INTO character_lore(character,title,content,tags_json,importance,"
                    "source,enabled,created_at,updated_at) VALUES(?,?,?,?,?,'manual',1,?,?) "
                    "ON CONFLICT(character,title) DO UPDATE SET content=excluded.content,"
                    "tags_json=excluded.tags_json,importance=excluded.importance,source='manual',"
                    "enabled=1,updated_at=excluded.updated_at",
                    (
                        character,
                        value_title,
                        value_content,
                        json.dumps(value_tags, ensure_ascii=False),
                        importance,
                        timestamp,
                        timestamp,
                    ),
                )
                if cursor.lastrowid:
                    return int(cursor.lastrowid)
                row = db.execute(
                    "SELECT id FROM character_lore WHERE character=? AND title=?",
                    (character, value_title),
                ).fetchone()
                return int(str(row[0])) if row else 0
        except sqlite3.IntegrityError as exc:
            raise ValueError("同一角色已經有相同標題的知識") from exc

    def save_character_relation_record(
        self,
        character: str,
        other_character: str,
        relation_label: str,
        description: str,
        importance: int,
        record_id: int = 0,
    ) -> int:
        other = " ".join(str(other_character).split()).strip()
        label = " ".join(str(relation_label).split()).strip()
        detail = " ".join(str(description).split()).strip()
        if not character.strip():
            raise ValueError("character is required")
        if not 1 <= len(other) <= 200:
            raise ValueError("other_character must contain 1-200 characters")
        if not 1 <= len(label) <= 200:
            raise ValueError("relation_label must contain 1-200 characters")
        if not 1 <= len(detail) <= 1500:
            raise ValueError("description must contain 1-1500 characters")
        if type(importance) is not int or not 1 <= importance <= 10:
            raise ValueError("importance must be 1-10")
        timestamp = _now()
        try:
            with self._lock, closing(self._connect()) as db, db:
                if record_id:
                    cursor = db.execute(
                        "UPDATE character_relations SET other_character=?,relation_label=?,"
                        "description=?,importance=?,updated_at=? WHERE id=? AND character=?",
                        (other, label, detail, importance, timestamp, int(record_id), character),
                    )
                    if cursor.rowcount != 1:
                        raise ValueError("找不到要更新的人物關係")
                    return int(record_id)
                cursor = db.execute(
                    "INSERT INTO character_relations(character,other_character,relation_label,"
                    "description,importance,enabled,created_at,updated_at) "
                    "VALUES(?,?,?,?,?,1,?,?) ON CONFLICT(character,other_character,relation_label) "
                    "DO UPDATE SET description=excluded.description,importance=excluded.importance,"
                    "enabled=1,updated_at=excluded.updated_at",
                    (character, other, label, detail, importance, timestamp, timestamp),
                )
                if cursor.lastrowid:
                    return int(cursor.lastrowid)
                row = db.execute(
                    "SELECT id FROM character_relations WHERE character=? AND other_character=? "
                    "AND relation_label=?",
                    (character, other, label),
                ).fetchone()
                return int(str(row[0])) if row else 0
        except sqlite3.IntegrityError as exc:
            raise ValueError("同一角色已經有相同的人物與關係標籤") from exc

    def delete_lore_record(self, character: str, record_id: int) -> bool:
        with self._lock, closing(self._connect()) as db, db:
            cursor = db.execute(
                "DELETE FROM character_lore WHERE id=? AND character=?",
                (int(record_id), character),
            )
        return cursor.rowcount == 1

    def delete_character_relation_record(self, character: str, record_id: int) -> bool:
        with self._lock, closing(self._connect()) as db, db:
            cursor = db.execute(
                "DELETE FROM character_relations WHERE id=? AND character=?",
                (int(record_id), character),
            )
        return cursor.rowcount == 1

    def search_character_lore(self, character: str, query: str, limit: int = 5) -> list[LoreHit]:
        value = " ".join(str(query).split()).strip()
        if not value:
            return []
        maximum = max(1, min(20, int(limit)))
        cjk_runs = re.findall(r"[\u3400-\u9fff\u3040-\u30ff]{2,}", value)
        terms = [
            word
            for word in re.findall(r"[\w-]{2,}", value, re.UNICODE)
            if not any("\u3400" <= char <= "\u9fff" for char in word)
        ]
        for run in cjk_runs:
            terms.extend(run[index : index + 2] for index in range(len(run) - 1))
        terms = list(dict.fromkeys(terms))[:16] or [value]
        with self._lock, closing(self._connect()) as db, db:
            relation_rows = db.execute(
                "SELECT id,other_character,relation_label,description,importance "
                "FROM character_relations WHERE character=? AND enabled=1",
                (character,),
            ).fetchall()
            relation_hits = [
                row for row in relation_rows if str(row[1]).casefold() in value.casefold()
            ]
            lore_rows: list[tuple[object, ...]] = []
            fts_terms = [term for term in terms if len(term) >= 3]
            if self.fts5_trigram_available and fts_terms:
                safe_query = " OR ".join('"' + term.replace('"', '""') + '"' for term in fts_terms)
                try:
                    lore_rows = db.execute(
                        "SELECT l.id,l.title,l.content,l.importance,bm25(character_lore_fts) "
                        "FROM character_lore_fts JOIN character_lore l "
                        "ON l.id=character_lore_fts.rowid "
                        "WHERE character_lore_fts MATCH ? AND l.character=? AND l.enabled=1 "
                        "ORDER BY bm25(character_lore_fts),l.importance DESC LIMIT ?",
                        (safe_query, character, maximum * 3),
                    ).fetchall()
                except sqlite3.Error:
                    lore_rows = []
            if not lore_rows:

                def like_query(operator: str) -> list[tuple[object, ...]]:
                    where = f" {operator} ".join(
                        "(title LIKE ? OR content LIKE ? OR tags_json LIKE ?)" for _ in terms
                    )
                    params: list[object] = [character]
                    for token in terms:
                        wildcard = f"%{token}%"
                        params.extend((wildcard, wildcard, wildcard))
                    params.append(maximum * 3)
                    return db.execute(
                        "SELECT id,title,content,importance,0 FROM character_lore "
                        "WHERE character=? AND enabled=1 AND "
                        + where
                        + " ORDER BY importance DESC,id DESC LIMIT ?",
                        params,
                    ).fetchall()

                lore_rows = like_query("AND") or like_query("OR")
            selected: list[tuple[str, int, LoreHit]] = []
            for row in relation_hits:
                selected.append(
                    (
                        "r",
                        int(str(row[0])),
                        LoreHit(
                            "relation", f"與「{row[1]}」：{row[2]}", str(row[3]), int(str(row[4]))
                        ),
                    )
                )
            for row in lore_rows:
                selected.append(
                    (
                        "l",
                        int(str(row[0])),
                        LoreHit("lore", str(row[1]), str(row[2]), int(str(row[3]))),
                    )
                )
            selected = selected[:maximum]
            timestamp = _now()
            lore_ids = [identifier for kind, identifier, _hit in selected if kind == "l"]
            if lore_ids:
                placeholders = ",".join("?" for _ in lore_ids)
                db.execute(
                    f"UPDATE character_lore SET last_used_at=? WHERE id IN ({placeholders})",
                    (timestamp, *lore_ids),
                )
        return [hit for _kind, _identifier, hit in selected]

    def statistics(self, character: str, user_key: str, days: int = 0) -> dict[str, int | str]:
        cutoff = (
            (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
            if days > 0
            else ""
        )
        time_filter = " AND created_at>=?" if cutoff else ""
        params: tuple[str, ...] = (character, cutoff) if cutoff else (character,)
        with self._lock, closing(self._connect()) as db, db:
            total, user_count, assistant_count, days = db.execute(
                "SELECT COUNT(*),SUM(role='user'),SUM(role='assistant'),"
                "COUNT(DISTINCT substr(created_at,1,10)) FROM messages WHERE character=?"
                + time_filter,
                params,
            ).fetchone()
            memories = db.execute(
                "SELECT COUNT(*) FROM memories WHERE character=? AND user_key=?",
                (character, user_key),
            ).fetchone()[0]
            latest = db.execute(
                "SELECT MAX(created_at) FROM messages WHERE character=?" + time_filter, params
            ).fetchone()[0]
        return {
            "messages": int(total or 0),
            "user_messages": int(user_count or 0),
            "assistant_messages": int(assistant_count or 0),
            "active_days": int(days or 0),
            "memories": int(memories or 0),
            "latest": str(latest or ""),
        }

    def clear(self, category: str) -> int:
        tables = {
            "messages": ("messages",),
            "memory": ("memories", "relationships"),
            "all": (
                "messages",
                "memories",
                "relationships",
                "character_schedule_log",
                "character_schedule_state",
                "character_lore",
                "character_relations",
            ),
        }.get(category)
        if tables is None:
            raise ValueError("unknown data category")
        deleted = 0
        with self._lock, closing(self._connect()) as db, db:
            for table in tables:
                cursor = db.execute(f"DELETE FROM {table}")
                deleted += max(0, cursor.rowcount)
        return deleted
