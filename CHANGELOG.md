# Changelog

## [0.1.3] - 2026-10-29

### Added
- `unc` module: `DRIVE_MAP` (the office `net use` list: E, I, L, M, O, Q,
  R, S, T, U, V, W, X, Y), `to_unc(path)` and `from_unc(path, like)`.

### Changed
- `destination_folder`, `ensure_customer_tree` and `rename_customer_folder`
  translate a mapped-drive `root` (`X:\POST RECEIVED`) to its UNC share
  before touching the file system, so filing works on a runner whose
  service account has no drive letters mapped. `destination_folder` now
  returns that UNC path; use `unc.from_unc(folder, root)` to get the
  drive-letter form back.

## [0.1.2] - 2026-10-09

### Changed
- A customer folder, its table row and (through x-drive stage 1) its
  workbook row carry the **exact** Sugar account name. A folder whose name
  differs from Sugar's in any way, case included (`Abbeycroft Leisure` vs
  `ABBEYCROFT LEISURE`) or by Ltd/Limited, &/and or a stray NBSP, is renamed
  to Sugar's spelling before filing. `name_key()` is now only for matching a
  name to an account, never for deciding a rename.
- `pick_row` prefers the row named exactly as Sugar's name.

### Added
- `rename_folder` (case-only renames go through a temporary name, since
  Windows treats them as one folder; a half-done one is put back),
  `same_folder`, `disk_name`.

## [0.1.1] - 2026-10-09

### Changed
- Reads `XDRIVE_CUSTOMER_MASTER.deleted` (automation-x-drive-post-report
  migration 004 renamed `folder_missing` to `deleted`). Needs that migration:
  against the old column the lookup fails and the file is filed by name.
- A filing for an account whose only rows are deleted reuses a deleted row
  already under Sugar's name instead of inserting a duplicate; any other
  deleted row is ignored (e.g. `Abodus`, merged into `ABODUS LIMITED`).

## [0.1.0] - 2026-10-09

### Added
- `customer_folders`: `name_key`, `safe_folder_name`, `resolve_customer_folder`,
  `rename_customer_folder`, `pick_row`, `repoint_shortcuts`, against
  `Titan_INSE.dbo.XDRIVE_CUSTOMER_MASTER` / `_AUDIT`.
- `routing`: `INSPIRED_PROCESS_CLIENTS`, `is_inspired_client`, `normalise_utility`,
  `TreeSpec`, `ensure_customer_tree`, `destination_folder`. Moved from
  lib-odc-core's `file_allocation`.
