"""MySQL database service for IP address management."""

import logging
from contextlib import contextmanager
from typing import Generator, Optional
from urllib.parse import urlparse

import mysql.connector
from mysql.connector import Error as MySQLError

from src.models.ip_record import IPRecord


logger = logging.getLogger(__name__)


@contextmanager
def get_db_connection(
    dsn: str,
) -> Generator[mysql.connector.connection.MySQLConnection, None, None]:
    """Context manager for MySQL connection with READ COMMITTED isolation.

    Args:
        dsn: MySQL connection string (mysql://user:password@host:port/database).

    Yields:
        mysql.connector.connection.MySQLConnection: Database connection.

    Raises:
        mysql.connector.Error: On connection or transaction failures.
    """
    # Parse DSN to extract connection parameters
    parsed = urlparse(dsn)
    conn = mysql.connector.connect(
        host=parsed.hostname,
        port=parsed.port or 3306,
        user=parsed.username,
        password=parsed.password,
        database=parsed.path.lstrip("/"),
        autocommit=False,
    )
    try:
        # Set transaction isolation level to READ COMMITTED
        cursor = conn.cursor()
        cursor.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
        cursor.close()

        yield conn
        conn.commit()  # Commit on successful context exit
    except Exception:
        conn.rollback()  # Rollback on any exception
        raise
    finally:
        conn.close()


class DatabaseService:
    """Service for MySQL operations on postal.ip_addresses table."""

    def __init__(self, dsn: str):
        """Initialize database service.

        Args:
            dsn: MySQL connection string.
        """
        self.dsn = dsn

    def get_all_ips(self) -> list[IPRecord]:
        """Fetch all IP records from postal.ip_addresses.

        Returns:
            list[IPRecord]: List of IP records.

        Raises:
            mysql.connector.Error: On database errors.
        """
        with get_db_connection(self.dsn) as conn:
            with conn.cursor(dictionary=True) as cur:
                cur.execute(
                    """
                    SELECT id, ipv4 as ip, priority, oldPriority as old_priority,
                           blockingLists as blocking_lists, lastEvent as last_event
                    FROM postal.ip_addresses
                    WHERE ipv4 IS NOT NULL
                    ORDER BY id
                """
                )
                rows = cur.fetchall()
                return [
                    IPRecord(
                        id=row["id"],
                        ip=row["ip"],
                        priority=row["priority"] or 100,
                        old_priority=row["old_priority"],
                        blocking_lists=row["blocking_lists"] or "",
                        last_event=row["last_event"],
                    )
                    for row in rows
                ]

    def update_ip_listed(
        self,
        ip_id: int,
        ip_address: str,
        current_priority: int,
        zones: list[str],
        listed_priority: int,
    ) -> bool:
        """Idempotent update for clean -> listed transition (FR-015).

        Sets oldPriority exactly once (preserves existing value).
        Only updates if blockingLists differs (idempotency).

        Args:
            ip_id: Database ID of IP record.
            ip_address: IP address (for logging).
            current_priority: Current priority value (for setting oldPriority).
            zones: List of DNSBL zones where IP is listed.
            listed_priority: Priority value to set for listed IPs.

        Returns:
            bool: True if update occurred, False if no-op (already in this state).

        Raises:
            mysql.connector.Error: On database errors.
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
                        oldPriority = CASE
                            WHEN oldPriority IS NULL THEN %s
                            ELSE oldPriority
                        END,
                        blockingLists = %s,
                        lastEvent = %s
                    WHERE id = %s
                      AND blockingLists != %s
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
                updated = cur.rowcount > 0

                if updated:
                    logger.info(
                        f"Database update: IP {ip_address} CLEAN -> LISTED (priority {current_priority} -> {listed_priority}, {len(zones)} zones)"
                    )

                return updated

    def update_ip_clean(
        self,
        ip_id: int,
        ip_address: str,
        old_priority: Optional[int],
        clean_fallback: int,
    ) -> bool:
        """Idempotent update for listed -> clean transition (FR-015).

        Restores priority from oldPriority, clears oldPriority and blockingLists.

        Args:
            ip_id: Database ID of IP record.
            ip_address: IP address (for logging).
            old_priority: Backed-up priority to restore (or None if missing).
            clean_fallback: Fallback priority if old_priority is None.

        Returns:
            bool: True if update occurred, False if no-op.

        Raises:
            mysql.connector.Error: On database errors.
        """
        restore_priority = old_priority if old_priority is not None else clean_fallback

        with get_db_connection(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE postal.ip_addresses
                    SET priority = %s,
                        oldPriority = NULL,
                        blockingLists = '',
                        lastEvent = 'block removed'
                    WHERE id = %s
                      AND blockingLists != ''
                """,
                    (restore_priority, ip_id),
                )
                updated = cur.rowcount > 0

                if updated:
                    fallback_note = " (using fallback)" if old_priority is None else ""
                    logger.info(
                        f"Database update: IP {ip_address} LISTED -> CLEAN (priority restored to {restore_priority}{fallback_note})"
                    )

                return updated

    def update_ip_zone_change(
        self, ip_id: int, ip_address: str, zones: list[str]
    ) -> bool:
        """Idempotent update for listed -> listed (zone change) transition (FR-015).

        Updates blockingLists while preserving priority and oldPriority.

        Args:
            ip_id: Database ID of IP record.
            ip_address: IP address (for logging).
            zones: New list of DNSBL zones where IP is listed.

        Returns:
            bool: True if update occurred, False if no-op.

        Raises:
            mysql.connector.Error: On database errors.
        """
        sorted_zones = ",".join(sorted(zones))
        last_event = f"blocking list change: {sorted_zones}"

        with get_db_connection(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE postal.ip_addresses
                    SET blockingLists = %s,
                        lastEvent = %s
                    WHERE id = %s
                      AND blockingLists != %s
                """,
                    (sorted_zones, last_event, ip_id, sorted_zones),
                )
                updated = cur.rowcount > 0

                if updated:
                    logger.info(
                        f"Database update: IP {ip_address} LISTED -> LISTED (zone change, now {len(zones)} zones)"
                    )

                return updated
