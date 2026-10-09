"""Where a document is filed: client routing, destination folder, folder tree.

The single place that decides whether a client takes the Inspired process
(one folder per customer under POST RECEIVED, chosen through
customer_folders.resolve_customer_folder) or the flat monthly folder every
other client uses. File naming, staging, copying and each bot's own
logging stay in the bots: their conventions differ.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .customer_folders import (
    SHORTCUT_TARGETS,
    _shell,
    resolve_customer_folder,
    safe_folder_name,
    write_shortcut,
)

logger = logging.getLogger(__name__)

#: Clients that take the Inspired process: per-customer folders rather than
#: the flat monthly folder. Ignite follows Inspired PLC exactly. The one copy
#: of this list; lib-odc-core's duplicate_check imports it.
INSPIRED_PROCESS_CLIENTS = frozenset({"inspired plc", "ignite"})


def is_inspired_client(client_name) -> bool:
    return (client_name or "").strip().lower() in INSPIRED_PROCESS_CLIENTS


def normalise_utility(utility) -> str:
    """ODC's utility folder naming: anything containing "elec" is Elec,
    "gas" is Gas, everything else passes through unchanged."""
    lowered = (utility or "").lower()
    if "elec" in lowered:
        return "Elec"
    if "gas" in lowered:
        return "Gas"
    return utility or ""


@dataclass(frozen=True)
class TreeSpec:
    """The folders a new customer folder gets.

    Every doc type gets every status; the NEW status gets one subfolder per
    utility (none when utilities is empty). With shortcuts, each
    NEW\\<utility> also gets ARCHIVE.lnk and HOLDING.lnk pointing at its
    doc type's ARCHIVE and HOLDING folders.
    """
    doc_types: tuple[str, ...]
    statuses: tuple[str, ...]
    utilities: tuple[str, ...] = field(default=())
    shortcuts: bool = False


def ensure_customer_tree(customer_root: Path, tree: TreeSpec) -> None:
    """Create any missing folders (and shortcuts) of tree under customer_root.
    Idempotent. Never writes sugar_id.txt."""
    customer_root = Path(customer_root)
    for doc_type in tree.doc_types:
        for status in tree.statuses:
            status_root = customer_root / doc_type / status
            if status == "NEW" and tree.utilities:
                for utility in tree.utilities:
                    (status_root / utility).mkdir(parents=True, exist_ok=True)
            else:
                status_root.mkdir(parents=True, exist_ok=True)

    if not (tree.shortcuts and tree.utilities):
        return
    missing = [
        (customer_root / doc_type / "NEW" / utility / f"{name}.lnk", customer_root / doc_type / name)
        for doc_type in tree.doc_types
        for utility in tree.utilities
        for name in SHORTCUT_TARGETS
        if not (customer_root / doc_type / "NEW" / utility / f"{name}.lnk").exists()
    ]
    if missing:
        shell = _shell()
        if shell is not None:
            for link, target in missing:
                write_shortcut(link, target, shell)


def destination_folder(
    *,
    root,
    client_name: str,
    doc_type: str,
    utility: str,
    tree: TreeSpec,
    source: str,
    sugar_id: str | None = None,
    sugar_name: str | None = None,
    customer_name: str | None = None,
    dsn: str | None = None,
    today: date | None = None,
) -> Path:
    """Return (and create) the folder a document is filed into.

    Inspired-process clients: {root}\\{customer folder}\\{doc_type}\\NEW\\{utility}
    (no utility level when utility is blank). The customer folder comes from
    the customer master when there is a Sugar id and a dsn, renaming the
    folder first if Sugar's name has changed; otherwise it is
    safe_folder_name(sugar_name or customer_name). The customer tree is built
    the first time the destination is missing.

    Every other client: {root}\\{YYYY-MM}, the current month.

    Raises ValueError when an Inspired-process filing has no usable customer
    name, rather than filing loose in root.
    """
    root = Path(root)
    if not is_inspired_client(client_name):
        folder = root / (today or date.today()).strftime("%Y-%m")
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    name = sugar_name or customer_name or ""
    if sugar_id and dsn:
        customer = resolve_customer_folder(root, sugar_id, name, source, dsn=dsn)
    else:
        if sugar_id and not dsn:
            logger.debug(
                "ROUTING - no customer master DSN configured, filing %s by name", sugar_id
            )
        customer = safe_folder_name(name)
    if not customer:
        raise ValueError(f"No customer folder name for client {client_name!r} (sugar id {sugar_id!r})")

    destination = root / customer / doc_type / "NEW"
    if utility:
        destination = destination / utility
    if not destination.is_dir():
        logger.info("ROUTING - %s missing, building the customer folder tree", destination)
        ensure_customer_tree(root / customer, tree)
        destination.mkdir(parents=True, exist_ok=True)
    return destination
