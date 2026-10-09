# Changelog

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
