# CLAUDE.md

## Purpose
Shared POST RECEIVED filing rules, package `file_allocation_core`. A library,
not a Control Room bot: no entry point of its own. Consumers:

| Consumer | How |
|---|---|
| ODC supplier bots | through `lib-odc-core`'s `file_allocation.allocate()`, which depends on this package |
| `automation-post-allocation` | direct, scanned post |
| `automation-emailed-invoice-ebills-allocation` | direct, emailed invoices and ebills |
| `automation-x-drive-post-report` | direct, stage 1's daily customer master sync (owns the table) |

## Tech Stack
- Python 3.14
- `pyodbc`, trusted connections, parameterised queries
- `pywin32`, optional and imported lazily, for `.lnk` shortcuts only
- Built and distributed as a wheel via GitHub Releases, same as `lib-core` and `lib-odc-core`

## Databases
- `Titan_INSE.dbo.XDRIVE_CUSTOMER_MASTER` and `..._AUDIT`, always by
  three-part name, so a caller can use any DSN that reaches Titan_INSE (in
  practice `DSN=Jupiter`). **Owned by `automation-x-drive-post-report`**,
  which holds the DDL (`migrations/002`) and mirrors its customer master
  workbook into the table daily. This package only reads by
  `customer_id`, inserts a minimal row for a new Sugar id, renames the
  `customer` key, and writes audit rows with `changed_by` set to the
  caller's `source`. Rows with `deleted = 1` (folder removed, e.g. merged into
  another folder of the same account, `merged_into` says which) are never
  filed into or renamed; one already under Sugar's name is reused rather than
  duplicated when it is the account's only row.
- `resolve_customer_folder` opens its **own** connection per call, so its
  commits never touch the caller's transaction.

## Key Business Logic
- **One folder per Sugar account.** See README's rule table. The table is
  the bible; `sugar_id.txt` is retired and must never be written again.
- **`name_key()` is the one name comparison.** Lowercase, whitespace
  (including NBSP) collapsed, `NAME_VARIATIONS` folded (Ltd/Ltd./Limited,
  &/and), trailing dots dropped. There is deliberately **no wildcard or
  fuzzy matching**: the business confirmed Ltd/Limited and &/and are the
  only known variations (2026-10-09). Add a new one to `NAME_VARIATIONS`
  only.
- **`safe_folder_name()`** turns a Sugar name into a folder name: `/`
  removed (matches the ebill bot's legacy rule), other illegal characters
  replaced with `-`, trailing dots/spaces dropped.
- **Renames never guess.** A collision (old and new folder both exist), a
  target name already held by another table row, or a failed rename (file
  open) leaves everything as it is and files into the old folder.
- **The folder is renamed before the table is written.** If the table
  write fails, x-drive stage 1's rename pass repairs it on its next run
  (old folder gone, target present).
- **Never block filing.** Any database error is logged and the caller gets
  `safe_folder_name(sugar_name)`, the pre-table behaviour.
- **Client routing.** `INSPIRED_PROCESS_CLIENTS` (`inspired plc`,
  `ignite`) is the only copy of this list. Those clients file per customer;
  every other client files to the flat `{root}\{YYYY-MM}` folder.
  `destination_folder` raises rather than filing an Inspired-process
  document loose in root when there is no customer name.

## Known Gotchas
- The import package is `file_allocation_core`, not `file_allocation`: the
  ebill bot has its own `src/file_allocation.py` that would shadow it.
- Shortcuts hold absolute paths; every rename re-points them
  (`repoint_shortcuts`). Without pywin32 they're skipped with a warning and
  x-drive stage 1, which has pywin32, re-points them.

## Change Log
- 2026-10-09: 0.1.0. Created from `lib-odc-core`'s `file_allocation`
  routing and the x-drive customer master rename rules, so every POST
  RECEIVED filer shares one implementation.
- 2026-10-09: 0.1.1. Reads `deleted` (was `folder_missing`, renamed by
  x-drive migration 004); deleted rows are skipped, or reused when they are
  the account's only row under Sugar's name.
