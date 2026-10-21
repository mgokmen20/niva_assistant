"""Add profile columns to an existing users table.

``create_all`` does not alter tables that already exist. New installs get
the columns from the model. This sync covers a database created earlier.
"""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

_PROFILE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("phone_number", "VARCHAR(32)"),
    ("thermal_preference", "VARCHAR(32) NOT NULL DEFAULT 'balanced'"),
    ("environment_routine", "VARCHAR(32) NOT NULL DEFAULT 'mostly_indoor'"),
    ("baseline_offset", "FLOAT NOT NULL DEFAULT 0"),
    ("preferred_language", "VARCHAR(8) NOT NULL DEFAULT 'en'"),
)


def ensure_user_profile_columns(connection: Connection) -> None:
    """Add missing profile columns. Column names are fixed, not user input."""
    _add_missing_columns(connection, _PROFILE_COLUMNS)


def ensure_recommendation_history_columns(connection: Connection) -> None:
    """Add the temperature band on recommendation logs created before it existed."""
    inspector = inspect(connection)
    if "recommendation_logs" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("recommendation_logs")}
    if "temperature_band" not in existing:
        connection.execute(
            text("ALTER TABLE recommendation_logs ADD COLUMN temperature_band VARCHAR(16) NOT NULL DEFAULT ''")
        )
    if "gender" not in existing:
        connection.execute(
            text(
                "ALTER TABLE recommendation_logs ADD COLUMN gender VARCHAR(16) NOT NULL DEFAULT 'unspecified'"
            )
        )


def ensure_wardrobe_item_columns(connection: Connection) -> None:
    """Add availability on wardrobe rows created before the laundry toggle."""
    inspector = inspect(connection)
    if "wardrobe_items" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("wardrobe_items")}
    if "is_active" not in existing:
        active_default = "1" if connection.dialect.name == "sqlite" else "TRUE"
        connection.execute(
            text(f"ALTER TABLE wardrobe_items ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT {active_default}")
        )
    if "image_url" not in existing:
        connection.execute(text("ALTER TABLE wardrobe_items ADD COLUMN image_url VARCHAR(500)"))


def ensure_user_account_columns(connection: Connection) -> None:
    """Add role-management columns on a database created before RBAC."""
    active_default = "1" if connection.dialect.name == "sqlite" else "TRUE"
    columns = (
        ("is_active", f"BOOLEAN NOT NULL DEFAULT {active_default}"),
        ("last_login_at", "TIMESTAMP"),
        ("last_login_ip", "VARCHAR(64)"),
    )
    _add_missing_columns(connection, columns)


def _add_missing_columns(connection: Connection, columns: tuple[tuple[str, str], ...]) -> None:
    """Add each missing column. Names and types are constants, not request data."""
    inspector = inspect(connection)
    if "users" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("users")}
    for name, column_type in columns:
        if name in existing:
            continue
        connection.execute(text(f"ALTER TABLE users ADD COLUMN {name} {column_type}"))
