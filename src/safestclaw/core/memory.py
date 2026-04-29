"""
SafestClaw Memory - Persistent storage for conversations and data.

SQLite-based with async support. No cloud required.
Uses prepared statements with named parameters for SQL injection safety.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)


class PreparedStatements:
    """
    Pre-defined SQL statements with named parameters.

    Using named parameters (:param) instead of positional (?) provides:
    - Protection against SQL injection via parameter binding
    - Better readability and maintainability
    - Reduced risk of parameter ordering errors
    - Explicit statement caching by SQLite
    """

    # Messages
    INSERT_MESSAGE = """
        INSERT INTO messages (user_id, channel, text, intent, params, metadata)
        VALUES (:user_id, :channel, :text, :intent, :params, :metadata)
    """

    SELECT_MESSAGES_BASE = """
        SELECT id, user_id, channel, text, intent, params, metadata, created_at
        FROM messages WHERE user_id = :user_id
    """

    SELECT_MESSAGES_WITH_CHANNEL = """
        SELECT id, user_id, channel, text, intent, params, metadata, created_at
        FROM messages WHERE user_id = :user_id AND channel = :channel
        ORDER BY created_at DESC LIMIT :limit
    """

    SELECT_MESSAGES_NO_CHANNEL = """
        SELECT id, user_id, channel, text, intent, params, metadata, created_at
        FROM messages WHERE user_id = :user_id
        ORDER BY created_at DESC LIMIT :limit
    """

    # Preferences
    SELECT_PREFERENCES = """
        SELECT data FROM preferences WHERE user_id = :user_id
    """

    UPSERT_PREFERENCES = """
        INSERT OR REPLACE INTO preferences (user_id, data, updated_at)
        VALUES (:user_id, :data, CURRENT_TIMESTAMP)
    """

    # Reminders
    INSERT_REMINDER = """
        INSERT INTO reminders (user_id, channel, task, trigger_at, repeat)
        VALUES (:user_id, :channel, :task, :trigger_at, :repeat)
    """

    SELECT_PENDING_REMINDERS = """
        SELECT id, user_id, channel, task, trigger_at, repeat, completed, created_at
        FROM reminders
        WHERE completed = 0 AND trigger_at <= :before
        ORDER BY trigger_at
    """

    UPDATE_REMINDER_COMPLETED = """
        UPDATE reminders SET completed = 1 WHERE id = :reminder_id
    """

    # Webhooks
    UPSERT_WEBHOOK = """
        INSERT OR REPLACE INTO webhooks (name, secret, action, params)
        VALUES (:name, :secret, :action, :params)
    """

    SELECT_WEBHOOK = """
        SELECT id, name, secret, action, params, enabled, created_at
        FROM webhooks WHERE name = :name AND enabled = 1
    """

    SELECT_ALL_WEBHOOKS = """
        SELECT id, name, secret, action, params, enabled, created_at
        FROM webhooks
    """

    # Crawl cache
    UPSERT_CRAWL_CACHE = """
        INSERT OR REPLACE INTO crawl_cache (url, content, links, summary, fetched_at, expires_at)
        VALUES (:url, :content, :links, :summary, CURRENT_TIMESTAMP, :expires_at)
    """

    SELECT_CRAWL_CACHE = """
        SELECT url, content, links, summary, fetched_at, expires_at
        FROM crawl_cache
        WHERE url = :url AND expires_at > CURRENT_TIMESTAMP
    """

    # Key-value store
    UPSERT_KEYVALUE = """
        INSERT OR REPLACE INTO keyvalue (key, value, expires_at, updated_at)
        VALUES (:key, :value, :expires_at, CURRENT_TIMESTAMP)
    """

    SELECT_KEYVALUE = """
        SELECT value FROM keyvalue
        WHERE key = :key AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
    """

    # User-learned patterns
    UPSERT_PATTERN = """
        INSERT INTO user_patterns (user_id, phrase, intent, params, use_count, updated_at)
        VALUES (:user_id, :phrase, :intent, :params, 1, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id, phrase) DO UPDATE SET
            intent = :intent,
            params = :params,
            use_count = use_count + 1,
            updated_at = CURRENT_TIMESTAMP
    """

    SELECT_USER_PATTERNS = """
        SELECT phrase, intent, params, use_count
        FROM user_patterns
        WHERE user_id = :user_id
        ORDER BY use_count DESC
    """

    SELECT_PATTERN_MATCH = """
        SELECT intent, params, use_count
        FROM user_patterns
        WHERE user_id = :user_id AND phrase = :phrase
    """


class Memory:
    """
    Persistent memory storage using SQLite.

    Stores:
    - Conversation history
    - User preferences
    - Scheduled tasks
    - Webhook configurations
    - Crawl cache
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._connection: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Initialize database and create tables."""
        self._connection = await aiosqlite.connect(
            self.db_path,
            timeout=30.0,  # Wait up to 30 seconds for locks
        )
        # Enable WAL mode for better concurrency (allows reads during writes)
        await self._connection.execute("PRAGMA journal_mode=WAL")
        # Use row_factory for named column access (safer than positional indexing)
        self._connection.row_factory = aiosqlite.Row
        await self._create_tables()
        logger.info(f"Memory initialized at {self.db_path}")

    async def _create_tables(self) -> None:
        """Create database tables if they don't exist."""
        assert self._connection is not None

        await self._connection.executescript("""
            -- Conversation history
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                channel TEXT NOT NULL,
                text TEXT NOT NULL,
                intent TEXT,
                params TEXT,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_messages_user ON messages(user_id);
            CREATE INDEX IF NOT EXISTS idx_messages_channel ON messages(channel);
            CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at);

            -- User preferences and settings
            CREATE TABLE IF NOT EXISTS preferences (
                user_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Scheduled reminders and tasks
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                channel TEXT NOT NULL,
                task TEXT NOT NULL,
                trigger_at TIMESTAMP NOT NULL,
                repeat TEXT,
                completed INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_reminders_trigger ON reminders(trigger_at);
            CREATE INDEX IF NOT EXISTS idx_reminders_user ON reminders(user_id);

            -- Webhook configurations
            CREATE TABLE IF NOT EXISTS webhooks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                secret TEXT,
                action TEXT NOT NULL,
                params TEXT,
                enabled INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Crawl cache
            CREATE TABLE IF NOT EXISTS crawl_cache (
                url TEXT PRIMARY KEY,
                content TEXT,
                links TEXT,
                summary TEXT,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_crawl_expires ON crawl_cache(expires_at);

            -- Key-value store for arbitrary data
            CREATE TABLE IF NOT EXISTS keyvalue (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                expires_at TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- User-learned patterns for natural language understanding
            CREATE TABLE IF NOT EXISTS user_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                phrase TEXT NOT NULL,
                intent TEXT NOT NULL,
                params TEXT,
                use_count INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, phrase)
            );
            CREATE INDEX IF NOT EXISTS idx_patterns_user ON user_patterns(user_id);
            CREATE INDEX IF NOT EXISTS idx_patterns_phrase ON user_patterns(phrase);
        """)
        await self._connection.commit()

    async def close(self) -> None:
        """Close database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None
            logger.info("Memory connection closed")

    # Message storage
    async def store_message(
        self,
        user_id: str,
        channel: str,
        text: str,
        parsed: Any,
        metadata: dict | None = None,
    ) -> int:
        """Store a message in history using prepared statement."""
        assert self._connection is not None

        cursor = await self._connection.execute(
            PreparedStatements.INSERT_MESSAGE,
            {
                "user_id": user_id,
                "channel": channel,
                "text": text,
                "intent": parsed.intent if parsed else None,
                "params": json.dumps(parsed.params) if parsed else None,
                "metadata": json.dumps(metadata) if metadata else None,
            },
        )
        await self._connection.commit()
        return cursor.lastrowid or 0

    async def get_history(
        self,
        user_id: str,
        limit: int = 50,
        channel: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve conversation history using prepared statement."""
        assert self._connection is not None

        # Use pre-defined prepared statements to avoid dynamic query construction
        if channel:
            query = PreparedStatements.SELECT_MESSAGES_WITH_CHANNEL
            params = {"user_id": user_id, "channel": channel, "limit": limit}
        else:
            query = PreparedStatements.SELECT_MESSAGES_NO_CHANNEL
            params = {"user_id": user_id, "limit": limit}

        cursor = await self._connection.execute(query, params)
        rows = await cursor.fetchall()

        # Use named column access via row_factory for safer data retrieval
        return [
            {
                "id": row["id"],
                "user_id": row["user_id"],
                "channel": row["channel"],
                "text": row["text"],
                "intent": row["intent"],
                "params": json.loads(row["params"]) if row["params"] else None,
                "metadata": json.loads(row["metadata"]) if row["metadata"] else None,
                "created_at": row["created_at"],
            }
            for row in reversed(rows)
        ]

    # Preferences
    async def set_preference(self, user_id: str, key: str, value: Any) -> None:
        """Set a user preference using prepared statement."""
        assert self._connection is not None

        # Get existing preferences using prepared statement
        cursor = await self._connection.execute(
            PreparedStatements.SELECT_PREFERENCES, {"user_id": user_id}
        )
        row = await cursor.fetchone()

        if row:
            prefs = json.loads(row["data"])
        else:
            prefs = {}

        prefs[key] = value

        await self._connection.execute(
            PreparedStatements.UPSERT_PREFERENCES,
            {"user_id": user_id, "data": json.dumps(prefs)},
        )
        await self._connection.commit()

    async def get_preference(self, user_id: str, key: str, default: Any = None) -> Any:
        """Get a user preference using prepared statement."""
        assert self._connection is not None

        cursor = await self._connection.execute(
            PreparedStatements.SELECT_PREFERENCES, {"user_id": user_id}
        )
        row = await cursor.fetchone()

        if row:
            prefs = json.loads(row["data"])
            return prefs.get(key, default)

        return default

    # Reminders
    async def add_reminder(
        self,
        user_id: str,
        channel: str,
        task: str,
        trigger_at: datetime,
        repeat: str | None = None,
    ) -> int:
        """Add a reminder using prepared statement."""
        assert self._connection is not None

        cursor = await self._connection.execute(
            PreparedStatements.INSERT_REMINDER,
            {
                "user_id": user_id,
                "channel": channel,
                "task": task,
                "trigger_at": trigger_at.isoformat(),
                "repeat": repeat,
            },
        )
        await self._connection.commit()
        return cursor.lastrowid or 0

    async def get_pending_reminders(self, before: datetime | None = None) -> list[dict]:
        """Get reminders that are due using prepared statement."""
        assert self._connection is not None

        before = before or datetime.now()

        cursor = await self._connection.execute(
            PreparedStatements.SELECT_PENDING_REMINDERS,
            {"before": before.isoformat()},
        )
        rows = await cursor.fetchall()

        return [
            {
                "id": row["id"],
                "user_id": row["user_id"],
                "channel": row["channel"],
                "task": row["task"],
                "trigger_at": datetime.fromisoformat(row["trigger_at"]),
                "repeat": row["repeat"],
                "completed": bool(row["completed"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    async def complete_reminder(self, reminder_id: int) -> None:
        """Mark a reminder as completed using prepared statement."""
        assert self._connection is not None

        await self._connection.execute(
            PreparedStatements.UPDATE_REMINDER_COMPLETED,
            {"reminder_id": reminder_id},
        )
        await self._connection.commit()

    # Webhooks
    async def add_webhook(
        self,
        name: str,
        action: str,
        params: dict | None = None,
        secret: str | None = None,
    ) -> None:
        """Register a webhook using prepared statement."""
        assert self._connection is not None

        await self._connection.execute(
            PreparedStatements.UPSERT_WEBHOOK,
            {
                "name": name,
                "secret": secret,
                "action": action,
                "params": json.dumps(params) if params else None,
            },
        )
        await self._connection.commit()

    async def get_webhook(self, name: str) -> dict | None:
        """Get a webhook by name using prepared statement."""
        assert self._connection is not None

        cursor = await self._connection.execute(
            PreparedStatements.SELECT_WEBHOOK, {"name": name}
        )
        row = await cursor.fetchone()

        if row:
            return {
                "id": row["id"],
                "name": row["name"],
                "secret": row["secret"],
                "action": row["action"],
                "params": json.loads(row["params"]) if row["params"] else None,
                "enabled": bool(row["enabled"]),
                "created_at": row["created_at"],
            }

        return None

    async def list_webhooks(self) -> list[dict]:
        """List all webhooks using prepared statement."""
        assert self._connection is not None

        cursor = await self._connection.execute(PreparedStatements.SELECT_ALL_WEBHOOKS)
        rows = await cursor.fetchall()

        return [
            {
                "id": row["id"],
                "name": row["name"],
                "secret": row["secret"],
                "action": row["action"],
                "params": json.loads(row["params"]) if row["params"] else None,
                "enabled": bool(row["enabled"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    # Crawl cache
    async def cache_crawl(
        self,
        url: str,
        content: str,
        links: list[str],
        summary: str | None = None,
        ttl_hours: int = 24,
    ) -> None:
        """Cache crawl results using prepared statement."""
        assert self._connection is not None

        expires_at = datetime.now() + timedelta(hours=ttl_hours)

        await self._connection.execute(
            PreparedStatements.UPSERT_CRAWL_CACHE,
            {
                "url": url,
                "content": content,
                "links": json.dumps(links),
                "summary": summary,
                "expires_at": expires_at.isoformat(),
            },
        )
        await self._connection.commit()

    async def get_cached_crawl(self, url: str) -> dict | None:
        """Get cached crawl result if not expired using prepared statement."""
        assert self._connection is not None

        cursor = await self._connection.execute(
            PreparedStatements.SELECT_CRAWL_CACHE, {"url": url}
        )
        row = await cursor.fetchone()

        if row:
            return {
                "url": row["url"],
                "content": row["content"],
                "links": json.loads(row["links"]) if row["links"] else [],
                "summary": row["summary"],
                "fetched_at": row["fetched_at"],
                "expires_at": row["expires_at"],
            }

        return None

    # Key-value store
    async def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        """Set a key-value pair using prepared statement."""
        assert self._connection is not None

        expires_at = None
        if ttl_seconds:
            expires_at = (datetime.now() + timedelta(seconds=ttl_seconds)).isoformat()

        await self._connection.execute(
            PreparedStatements.UPSERT_KEYVALUE,
            {"key": key, "value": json.dumps(value), "expires_at": expires_at},
        )
        await self._connection.commit()

    async def get(self, key: str, default: Any = None) -> Any:
        """Get a value by key using prepared statement."""
        assert self._connection is not None

        cursor = await self._connection.execute(
            PreparedStatements.SELECT_KEYVALUE, {"key": key}
        )
        row = await cursor.fetchone()

        if row:
            return json.loads(row["value"])

        return default

    # User-learned patterns
    async def learn_pattern(
        self,
        user_id: str,
        phrase: str,
        intent: str,
        params: dict | None = None,
    ) -> None:
        """
        Learn a user's phrase-to-intent mapping.

        When a user corrects a misunderstood command, store the mapping
        so future similar phrases can be matched correctly.
        """
        assert self._connection is not None

        await self._connection.execute(
            PreparedStatements.UPSERT_PATTERN,
            {
                "user_id": user_id,
                "phrase": phrase.lower().strip(),
                "intent": intent,
                "params": json.dumps(params) if params else None,
            },
        )
        await self._connection.commit()
        logger.debug(f"Learned pattern: '{phrase}' -> {intent}")

    async def get_user_patterns(self, user_id: str) -> list[dict]:
        """Get all learned patterns for a user, ordered by usage frequency."""
        assert self._connection is not None

        cursor = await self._connection.execute(
            PreparedStatements.SELECT_USER_PATTERNS, {"user_id": user_id}
        )
        rows = await cursor.fetchall()

        return [
            {
                "phrase": row["phrase"],
                "intent": row["intent"],
                "params": json.loads(row["params"]) if row["params"] else None,
                "use_count": row["use_count"],
            }
            for row in rows
        ]

    async def match_learned_pattern(
        self, user_id: str, phrase: str
    ) -> dict | None:
        """Check if we have an exact learned pattern match for this phrase."""
        assert self._connection is not None

        cursor = await self._connection.execute(
            PreparedStatements.SELECT_PATTERN_MATCH,
            {"user_id": user_id, "phrase": phrase.lower().strip()},
        )
        row = await cursor.fetchone()

        if row:
            return {
                "intent": row["intent"],
                "params": json.loads(row["params"]) if row["params"] else None,
                "use_count": row["use_count"],
            }

        return None
