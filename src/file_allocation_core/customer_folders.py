"""POST RECEIVED customer folders, keyed on Sugar account id.

Titan_INSE.dbo.XDRIVE_CUSTOMER_MASTER is the one record of which POST
RECEIVED folder belongs to which Sugar account. It is owned by
automation-x-drive-post-report (migrations/002), which mirrors the customer
master workbook into it daily; every process that files into POST RECEIVED
reads it through this module before creating a folder, so a Sugar account
never gets a second folder.

The rule, for a filing that knows the customer's Sugar id:

    * id in the table, folder name matches Sugar's current name -> that folder
    * id in the table, name differs   -> rename the folder, update the
                                         table's key, audit it, then file
    * id not in the table             -> new folder under Sugar's name, and a
                                         new table row ("Row added")

Names are compared with name_key(), which ignores case, whitespace
(including NBSP) and the known variations Ltd/Limited and &/and, so none of
those ever trigger a rename.

sugar_id.txt is retired: nothing in this module reads or writes it.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import pyodbc

logger = logging.getLogger(__name__)

# Fully qualified so every caller can use its existing DSN (in practice
# DSN=Jupiter) whatever that DSN's default database is.
MASTER_TABLE = "Titan_INSE.dbo.XDRIVE_CUSTOMER_MASTER"
AUDIT_TABLE = "Titan_INSE.dbo.XDRIVE_CUSTOMER_MASTER_AUDIT"

# Audit field_touched values written by this module. "Customer" is the
# workbook's header for column A, so renames read the same whichever process
# made them; changed_by says which.
FIELD_CUSTOMER = "Customer"
ROW_ADDED = "Row added"

# ---------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------

# Known name variations, applied in order to an already lowercased,
# whitespace-collapsed name. Ltd and Limited are the same company, as are &
# and "and". Add a variation here, nowhere else.
NAME_VARIATIONS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bltd\b\.?"), "limited"),
    (re.compile(r"&"), " and "),
]

_WHITESPACE = re.compile(r"\s+")
_ILLEGAL_FOLDER_CHARS = '<>:"\\|?*'


def _collapse(text: str) -> str:
    # \s covers NBSP (U+00A0) in Python 3, so a pasted non-breaking space
    # collapses like any other.
    return _WHITESPACE.sub(" ", text).strip()


def name_key(name) -> str:
    """Comparison key for a customer name: lowercase, whitespace collapsed,
    Ltd/Limited and &/and folded, trailing dots dropped. Two names with the
    same key are the same customer for every purpose in this module."""
    if name is None:
        return ""
    key = _collapse(str(name).lower())
    for pattern, replacement in NAME_VARIATIONS:
        key = _collapse(pattern.sub(replacement, key))
    return key.rstrip(". ")


def safe_folder_name(name) -> str:
    """The folder name for a Sugar account name: trimmed (NBSP included),
    "/" removed, other characters Windows can't hold in a name replaced with
    "-", trailing dots and spaces dropped (Windows drops them silently)."""
    if name is None:
        return ""
    text = _collapse(str(name)).replace("/", "")
    for char in _ILLEGAL_FOLDER_CHARS:
        text = text.replace(char, "-")
    return _collapse(text).rstrip(". ")


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

SELECT_ROWS_FOR_ID = f"""
SELECT id, customer
FROM {MASTER_TABLE}
WHERE customer_id = ? AND folder_missing = 0
ORDER BY id
"""

# Exact match under the column's (case-insensitive) collation: the same test
# the unique index on customer applies.
SELECT_ROW_HOLDING_NAME = f"""
SELECT id FROM {MASTER_TABLE} WHERE customer = ? AND id <> ?
"""

UPDATE_CUSTOMER_KEY = f"""
UPDATE {MASTER_TABLE}
SET customer = ?, last_synced_utc = SYSUTCDATETIME()
WHERE id = ?
"""

INSERT_MINIMAL_ROW = f"""
INSERT INTO {MASTER_TABLE} (customer, customer_id) VALUES (?, ?)
"""

INSERT_AUDIT_ROW = f"""
INSERT INTO {AUDIT_TABLE} (customer, field_touched, old_value, new_value, changed_by)
VALUES (?, ?, ?, ?, ?)
"""


@dataclass(frozen=True)
class CustomerRow:
    id: int
    customer: str


def _rows_for_id(cursor, sugar_id: str) -> list[CustomerRow]:
    cursor.execute(SELECT_ROWS_FOR_ID, (sugar_id.strip().lower(),))
    return [CustomerRow(int(row[0]), row[1]) for row in cursor.fetchall()]


def pick_row(rows: list[CustomerRow], target: str) -> CustomerRow:
    """The row to file into when several share one Sugar id: the one whose
    name already matches Sugar's (by name_key), else the oldest."""
    wanted = name_key(target)
    for row in rows:
        if name_key(row.customer) == wanted:
            return row
    return rows[0]


# ---------------------------------------------------------------------------
# Shortcuts
# ---------------------------------------------------------------------------

SHORTCUT_TARGETS = ("ARCHIVE", "HOLDING")


def _shell():
    """WScript.Shell, or None when pywin32 isn't installed. Imported lazily so
    a bot that never needs shortcuts doesn't need pywin32."""
    try:
        import win32com.client  # noqa: PLC0415
    except ImportError:
        logger.warning("CUSTOMER_FOLDERS - pywin32 not installed, shortcuts skipped")
        return None
    return win32com.client.Dispatch("WScript.Shell")


def write_shortcut(link_path: Path, target: Path, shell=None) -> bool:
    """Create or re-point one .lnk. Returns True on success."""
    shell = shell or _shell()
    if shell is None:
        return False
    try:
        shortcut = shell.CreateShortCut(str(link_path))
        shortcut.Targetpath = str(target)
        shortcut.save()
        return True
    except Exception:  # pywintypes.com_error isn't importable without pywin32
        logger.exception("CUSTOMER_FOLDERS - failed writing shortcut %s -> %s", link_path, target)
        return False


def repoint_shortcuts(customer_root: Path) -> int:
    """Re-point every <DocType>\\NEW\\<Utility>\\ARCHIVE.lnk / HOLDING.lnk
    under customer_root at <customer_root>\\<DocType>\\ARCHIVE|HOLDING.

    Shortcuts hold absolute paths, so they still point at the old folder name
    after a rename. Returns the number re-pointed.
    """
    customer_root = Path(customer_root)
    links = [
        link
        for name in SHORTCUT_TARGETS
        for link in customer_root.glob(f"*/NEW/*/{name}.lnk")
    ]
    if not links:
        return 0
    shell = _shell()
    if shell is None:
        return 0
    repointed = 0
    for link in links:
        doc_type_root = link.parent.parent.parent
        if write_shortcut(link, doc_type_root / link.stem.upper(), shell):
            repointed += 1
    return repointed


# ---------------------------------------------------------------------------
# Rename and resolve
# ---------------------------------------------------------------------------

def rename_customer_folder(conn, root, row: CustomerRow, target: str, source: str) -> str:
    """Bring row's folder in line with Sugar's current name and return the
    folder name to file into.

    | old folder | target folder | result                                     |
    |------------|---------------|--------------------------------------------|
    | exists     | missing       | folder renamed, key updated, audited       |
    | missing    | exists        | key updated, audited (already renamed)     |
    | missing    | missing       | key updated, audited (caller creates it)   |
    | exists     | exists        | collision: nothing changed, old returned   |

    Nothing is changed either when another table row already holds the
    target name (the unique index on customer would reject it), or when the
    rename itself fails (a file open in the folder): the old name is
    returned and the next filing or stage 1's daily run tries again.

    The folder is renamed before the table is written. If the table write
    fails the folder keeps its new name and stage 1's rename pass repairs
    the table (old folder missing, target present).
    """
    root = Path(root)
    old_path = root / row.customer
    new_path = root / target
    old_exists = old_path.is_dir()
    new_exists = new_path.is_dir()

    if old_exists and new_exists:
        logger.warning(
            "CUSTOMER_FOLDERS - '%s' should be renamed to '%s' but both folders exist; "
            "left for a human to merge", row.customer, target,
        )
        return row.customer

    cursor = conn.cursor()
    cursor.execute(SELECT_ROW_HOLDING_NAME, (target, row.id))
    if cursor.fetchone() is not None:
        logger.warning(
            "CUSTOMER_FOLDERS - '%s' should be renamed to '%s' but another master row "
            "already holds that name; left unchanged", row.customer, target,
        )
        return row.customer

    if old_exists:
        try:
            old_path.rename(new_path)
        except OSError:
            logger.exception(
                "CUSTOMER_FOLDERS - could not rename '%s' to '%s' (a file may be open); "
                "filing into the old folder", old_path, new_path,
            )
            return row.customer
        logger.info("CUSTOMER_FOLDERS - renamed folder '%s' -> '%s'", row.customer, target)
        repoint_shortcuts(new_path)

    try:
        cursor.execute(UPDATE_CUSTOMER_KEY, (target, row.id))
        cursor.execute(INSERT_AUDIT_ROW, (target, FIELD_CUSTOMER, row.customer, target, source))
        conn.commit()
    except pyodbc.Error:
        conn.rollback()
        logger.exception(
            "CUSTOMER_FOLDERS - folder is '%s' but the master table still says '%s'; "
            "stage 1 will repair it", target, row.customer,
        )
    return target


def _connect(dsn: str):
    return pyodbc.connect(f"DSN={dsn}", autocommit=False)


def resolve_customer_folder(
    root,
    sugar_id: str,
    sugar_name: str,
    source: str,
    *,
    dsn: str,
) -> str:
    """Return the POST RECEIVED folder name to file a document for this Sugar
    account into, renaming the folder first if Sugar's name has changed.

    Opens its own connection (trusted, via dsn) so its commits never touch
    the caller's transaction. Never raises for a database problem: it logs a
    warning and falls back to safe_folder_name(sugar_name), today's
    behaviour, because a missing lookup must never stop a file being filed.
    """
    target = safe_folder_name(sugar_name)
    if not sugar_id or not target:
        return target
    sugar_id = sugar_id.strip().lower()

    try:
        conn = _connect(dsn)
    except pyodbc.Error:
        logger.warning(
            "CUSTOMER_FOLDERS - customer master unavailable (DSN=%s), using '%s'",
            dsn, target, exc_info=True,
        )
        return target

    try:
        cursor = conn.cursor()
        rows = _rows_for_id(cursor, sugar_id)
        if not rows:
            try:
                cursor.execute(INSERT_MINIMAL_ROW, (target, sugar_id))
                cursor.execute(INSERT_AUDIT_ROW, (target, ROW_ADDED, None, target, source))
                conn.commit()
                logger.info(
                    "CUSTOMER_FOLDERS - new customer master row '%s' (%s)", target, sugar_id
                )
            except pyodbc.IntegrityError:
                # Another account already holds this folder name, or another
                # process inserted it a moment ago. File by name, as today.
                conn.rollback()
                logger.warning(
                    "CUSTOMER_FOLDERS - '%s' already in the customer master under a "
                    "different id; filing by name", target,
                )
            return target

        row = pick_row(rows, target)
        if name_key(row.customer) == name_key(target):
            return row.customer
        return rename_customer_folder(conn, root, row, target, source)
    except pyodbc.Error:
        try:
            conn.rollback()
        except pyodbc.Error:
            pass
        logger.warning(
            "CUSTOMER_FOLDERS - customer master lookup failed for %s, using '%s'",
            sugar_id, target, exc_info=True,
        )
        return target
    finally:
        conn.close()
