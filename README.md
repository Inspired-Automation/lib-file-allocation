# lib-file-allocation

Shared POST RECEIVED filing rules (`file_allocation_core`). Every process that
files documents into `\\inspiredenergysolutions.local\DFS\Public\!CC\POST RECEIVED`
uses it to decide where a document goes and which customer folder it belongs
to. One customer folder per Sugar account is the goal.

## Install

```
file-allocation-core @ https://github.com/Inspired-Automation/lib-file-allocation/releases/download/v0.1.0/file_allocation_core-0.1.0-py3-none-any.whl
```

Add `pywin32` (or the `[shortcuts]` extra) if the bot builds trees with
`ARCHIVE.lnk` / `HOLDING.lnk` shortcuts. Without it shortcuts are skipped with
a warning.

## The rule

Every filing knows the customer's Sugar id. Before creating a folder, look
the id up in `Titan_INSE.dbo.XDRIVE_CUSTOMER_MASTER` (owned by
`automation-x-drive-post-report`):

| Table says | Action |
|---|---|
| id found, folder name matches Sugar's current name | file into that folder |
| id found, name differs | rename the folder, update the table, write an audit row, then file |
| id not found | create the folder under Sugar's name, insert the table row ("Row added"), then file |

Names are compared with `name_key()`: case, whitespace (including NBSP), and the
known variations **Ltd/Limited** and **&/and** are ignored, and never trigger a
rename. If both the old and the new folder exist, nothing is renamed: the
document goes into the folder the table holds, and the daily x-drive sync
reports the pair for a human to merge.

`sugar_id.txt` is retired: nothing writes it any more.

## Usage

```python
from file_allocation_core.routing import TreeSpec, destination_folder

TREE = TreeSpec(
    doc_types=("LETTER", "INVOICE", "LEGAL", "DEBT", "PAYREM"),
    statuses=("NEW", "ARCHIVE", "HOLDING"),
    utilities=("ELEC", "WATER", "GAS", "OTHER"),
    shortcuts=True,
)

folder = destination_folder(
    root=r"\\inspiredenergysolutions.local\DFS\Public\!CC\POST RECEIVED",
    client_name="Inspired PLC",       # Inspired PLC / Ignite: per-customer; anyone else: flat YYYY-MM
    doc_type="INVOICE",
    utility="ELEC",
    tree=TREE,
    source="post-allocation",         # written to the audit table's changed_by
    sugar_id=sugar_id,
    sugar_name=sugar_account_name,
    dsn="Jupiter",                    # any trusted DSN that can reach Titan_INSE
)
```

`destination_folder` returns the folder, creating the customer tree the first
time it's missing. A database problem never stops filing: it logs a warning
and files under `safe_folder_name(sugar_name)`.

Lower level: `customer_folders.resolve_customer_folder`, `name_key`,
`safe_folder_name`, `rename_customer_folder`, `repoint_shortcuts`;
`routing.is_inspired_client`, `normalise_utility`, `ensure_customer_tree`.

## Database access

The run-as account needs SELECT, INSERT and UPDATE on
`Titan_INSE.dbo.XDRIVE_CUSTOMER_MASTER` and INSERT on
`Titan_INSE.dbo.XDRIVE_CUSTOMER_MASTER_AUDIT`. Schema:
`automation-x-drive-post-report/migrations/002_rebuild_customer_master_as_xlsx_mirror.sql`.

## Development

```
pip install -e ".[dev]"
pytest
```

See `RELEASING.md` to cut a release.
