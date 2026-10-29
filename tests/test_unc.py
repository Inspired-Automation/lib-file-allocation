from datetime import date
from pathlib import Path

import pytest

from file_allocation_core import unc
from file_allocation_core.routing import TreeSpec, destination_folder
from file_allocation_core.unc import from_unc, to_unc

CC = r"\\inspiredenergysolutions.local\DFS\Public\!CC"


@pytest.mark.parametrize("given, expected", [
    (r"X:\POST RECEIVED", CC + r"\POST RECEIVED"),
    ("x:/POST RECEIVED/2026-10", CC + r"\POST RECEIVED\2026-10"),
    ("X:", CC),
    ("X:\\", CC),
    (r"I:\BPI\ODC", r"\\inspiredenergysolutions.local\DFS\Public\!IES\BPI\ODC"),
    (r"R:\Bills", r"\\IES-BU-FS-V01\Burgess Hill\InprovaEnergy\Bills"),
    (r"V:\a", r"\\ies-dc-07\FEML\Public\a"),
    (Path(r"O:\ODC_Clients"), r"\\inspiredenergysolutions.local\DFS\BromleyShares\STC\ODC_Clients"),
])
def test_mapped_drive_becomes_unc(given, expected):
    assert to_unc(given) == expected


@pytest.mark.parametrize("given", [
    r"C:\Users\bot\Downloads\a.pdf",   # unmapped drive
    CC + r"\POST RECEIVED",            # already UNC
    "X:relative",                      # drive-relative, left alone
    "relative\\path",
    "",
])
def test_other_paths_unchanged(given):
    assert to_unc(given) == given


def test_none_is_empty():
    assert to_unc(None) == ""


def test_every_mapped_drive_is_a_unc_share():
    assert set(unc.DRIVE_MAP) == set("EILMOQRSTUVWXY")
    assert all(share.startswith("\\\\") and not share.endswith("\\") for share in unc.DRIVE_MAP.values())


def test_from_unc_restores_the_drive_letter():
    filed = to_unc(r"X:\POST RECEIVED") + r"\Acme\INVOICE\NEW\a.pdf"
    assert from_unc(filed, r"X:\POST RECEIVED") == r"X:\POST RECEIVED\Acme\INVOICE\NEW\a.pdf"


@pytest.mark.parametrize("path, like", [
    (CC + r"\POST RECEIVED\a.pdf", r"C:\POST RECEIVED"),     # like not mapped
    (r"\\other\share\a.pdf", r"X:\POST RECEIVED"),            # not under like
    (CC + r"\POST RECEIVED 2\a.pdf", r"X:\POST RECEIVED"),    # prefix, not a parent
])
def test_from_unc_leaves_unrelated_paths(path, like):
    assert from_unc(path, like) == path


def test_destination_folder_files_a_mapped_root_through_its_share(tmp_path, monkeypatch):
    monkeypatch.setitem(unc.DRIVE_MAP, "X", str(tmp_path))
    folder = destination_folder(
        root=r"X:\POST RECEIVED", client_name="Crown Gas", doc_type="INVOICE", utility="Elec",
        tree=TreeSpec(doc_types=("INVOICE",), statuses=("NEW",)), source="odc",
        customer_name="Acme", today=date(2026, 10, 29),
    )
    assert folder == tmp_path / "POST RECEIVED" / "2026-10"
    assert folder.is_dir()
