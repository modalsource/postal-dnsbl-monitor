"""PostgreSQL database service for IP address management."""

import logging
from contextlib import contextmanager
from typing import Generator, Optional

import psycopg2
import psycopg2.extras
from psycopg2.extensions import ISOLATION_LEVEL_READ_COMMITTED

from src.models.ip_record import IPRecord


logger = logging.getLogger(__name__)


@contextmanager
def get_db_connection(
    dsn: str,
) -> Generator[psycopg2.extensions.connection, None, None]:
    """Context manager for PostgreSQL connection with READ COMMITTED isolation.

    Args:
        dsn: PostgreSQL connection string.

    Yields:
        psycopg2.extensions.connection: Database connection.

    Raises:
        psycopg2.Error: On connection or transaction failures.
    """
    conn = psycopg2.connect(dsn)
    conn.set_isolation_level(ISOLATION_LEVEL_READ_COMMITTED)
    try:
        yield conn
        conn.commit()  # Commit on successful context exit
    except Exception:
        conn.rollback()  # Rollback on any exception
        raise
    finally:
        conn.close()


class DatabaseService:
    """Service for PostgreSQL operations on postal.ip_addresses table."""

    def __init__(self, dsn: str):
        """Initialize database service.

        Args:
            dsn: PostgreSQL connection string.
        """
        self.dsn = dsn

    def get_all_ips(self) -> list[IPRecord]:
        """Fetch all IP records from postal.ip_addresses.

        Returns:
            list[IPRecord]: List of IP records.

        Raises:
            psycopg2.Error: On database errors.
        """
        with get_db_connection(self.dsn) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, ip, priority, "oldPriority" as old_priority,
                           "blockingLists" as blocking_lists, "lastEvent" as last_event
                    FROM postal.ip_addresses
                    ORDER BY id
                """
                )
                rows = cur.fetchall()
                return [
                    IPRecord(
                        id=row["id"],
                        ip=row["ip"],
                        priority=row["priority"],
                        old_priority=row["old_priority"],
                        blocking_lists=row["blocking_lists"] or "",
                        last_event=row["last_event"],
                    )
                    for row in rows
                ]

    def update_ip_listed(
        self, ip_id: int, current_priority: int, zones: list[str], listed_priority: int
    ) -> bool:
        """Idempotent update for clean → listed transition (FR-015).

        Sets oldPriority exactly once (preserves existing value).
        Only updates if blockingLists differs (idempotency).

        Args:
            ip_id: Database ID of IP record.
            current_priority: Current priority value (for setting oldPriority).
            zones: List of DNSBL zones where IP is listed.
            listed_priority: Priority value to set for listed IPs.

        Returns:
            bool: True if update occurred, False if no-op (already in this state).

        Raises:
            psycopg2.Error: On database errors.
        """
        sorted_zones = ",".join(sorted(zones))
        last_event = f"new block from list(s) {sorted_zones}"

        with get_db_connection(self.dsn) as conn:
            with conn.cursor() as cur:
                # Only update if blockingLists differs (idempotency check)
                cur.execute(
                    """
                    UPDATE postal.ip_addresses
                    SET priority = %s,
                        "oldPriority" = CASE
                            WHEN "oldPriority" IS NULL THEN %s
                            ELSE "oldPriority"  -- Preserve existing oldPriority (FR-014)
                        END,
                        "blockingLists" = %s,
                        "lastEvent" = %s
                    WHERE id = %s
                      AND "blockingLists" != %s  -- Only update if changed
                """,
                    (
                        listed_priority,
                        current_priority,
                        sorted_zones,
                        last_event,
                        ip_id,
                        sorted_zones,
                    ),
                )
                return cur.rowcount > 0  # True if row was updated

    def update_ip_clean(
        self, ip_id: int, old_priority: Optional[int], clean_fallback: int
    ) -> bool:
        """Idempotent update for listed → clean transition (FR-015).

        Restores priority from oldPriority, clears oldPriority and blockingLists.

        Args:
            ip_id: Database ID of IP record.
            old_priority: Backed-up priority to restore (or None if missing).
            clean_fallback: Fallback priority if old_priority is None.

        Returns:
            bool: True if update occurred, False if no-op.

        Raises:
            psycopg2.Error: On database errors.
        """
        restore_priority = old_priority if old_priority is not None else clean_fallback

        with get_db_connection(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE postal.ip_addresses
                    SET priority = %s,
                        "oldPriority" = NULL,
                        "blockingLists" = '',
                        "lastEvent" = 'block removed'
                    WHERE id = %s
                      AND "blockingLists" != ''  -- Only update if currently listed
                """,
                    (restore_priority, ip_id),
                )
                return cur.rowcount > 0

    def update_ip_zone_change(self, ip_id: int, zones: list[str]) -> bool:
        """Idempotent update for listed → listed (zone change) transition (FR-015).

        Updates blockingLists while preserving priority and oldPriority.

        Args:
            ip_id: Database ID of IP record.
            zones: New list of DNSBL zones where IP is listed.

        Returns:
            bool: True if update occurred, False if no-op.

        Raises:
            psycopg2.Error: On database errors.
        """
        sorted_zones = ",".join(sorted(zones))
        last_event = f"blocking list change: {sorted_zones}"

        with get_db_connection(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE postal.ip_addresses
                    SET "blockingLists" = %s,
                        "lastEvent" = %s
                    WHERE id = %s
                      AND "blockingLists" != %s  -- Only update if changed
                """,
                    (sorted_zones, last_event, ip_id, sorted_zones),
                )
                return cur.rowcount > 0
