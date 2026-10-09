from datetime import date

import pytest

from file_allocation_core import routing
from file_allocation_core.routing import TreeSpec, destination_folder

ODC_TREE = TreeSpec(
    doc_types=("LETTER", "INVOICE"), statuses=("ARCHIVE", "HOLDING", "NEW"),
    utilities=("ELEC", "GAS"),
)
EBILL_TREE = TreeSpec(doc_types=("INVOICE", "EBILL"), statuses=("ARCHIVE", "HOLDING", "NEW"))
POST_TREE = TreeSpec(
    doc_types=("INVOICE",), statuses=("NEW", "ARCHIVE", "HOLDING"),
    utilities=("ELEC",), shortcuts=True,
)


@pytest.mark.parametrize("client, expected", [
    ("Inspired PLC", True), (" inspired plc ", True), ("IGNITE", True),
    ("Crown Gas", False), ("", False), (None, False),
])
def test_is_inspired_client(client, expected):
    assert routing.is_inspired_client(client) is expected


@pytest.mark.parametrize("raw, normalised", [
    ("Electricity", "Elec"), ("GAS", "Gas"), ("Water", "Water"), (None, ""),
])
def test_normalise_utility(raw, normalised):
    assert routing.normalise_utility(raw) == normalised


def test_other_client_goes_to_flat_month_folder(tmp_path):
    folder = destination_folder(
        root=tmp_path, client_name="Crown Gas", doc_type="INVOICE", utility="Elec",
        tree=ODC_TREE, source="odc", customer_name="Acme", today=date(2026, 10, 9),
    )
    assert folder == tmp_path / "2026-10"
    assert folder.is_dir()
    assert not (tmp_path / "Acme").exists()


def test_inspired_without_id_builds_tree_by_name(tmp_path):
    folder = destination_folder(
        root=tmp_path, client_name="Ignite", doc_type="INVOICE", utility="Elec",
        tree=ODC_TREE, source="odc", customer_name="Primark",
    )
    assert folder == tmp_path / "Primark" / "INVOICE" / "NEW" / "Elec"
    assert (tmp_path / "Primark" / "LETTER" / "HOLDING").is_dir()
    assert (tmp_path / "Primark" / "INVOICE" / "NEW" / "GAS").is_dir()
    assert not (tmp_path / "Primark" / "sugar_id.txt").exists()


def test_inspired_with_id_uses_customer_master(tmp_path, monkeypatch):
    calls = []

    def fake_resolve(root, sugar_id, sugar_name, source, *, dsn):
        calls.append((sugar_id, sugar_name, source, dsn))
        return "Stored Folder"
    monkeypatch.setattr(routing, "resolve_customer_folder", fake_resolve)

    folder = destination_folder(
        root=tmp_path, client_name="Inspired PLC", doc_type="EBILL", utility="",
        tree=EBILL_TREE, source="ebill", sugar_id="ID1", sugar_name="Sugar Name",
        customer_name="PDF Name", dsn="Jupiter",
    )
    assert calls == [("ID1", "Sugar Name", "ebill", "Jupiter")]
    assert folder == tmp_path / "Stored Folder" / "EBILL" / "NEW"
    assert (tmp_path / "Stored Folder" / "INVOICE" / "ARCHIVE").is_dir()


def test_inspired_with_id_but_no_dsn_files_by_sugar_name(tmp_path):
    folder = destination_folder(
        root=tmp_path, client_name="Inspired PLC", doc_type="INVOICE", utility="Elec",
        tree=ODC_TREE, source="odc", sugar_id="ID1", sugar_name="A/B Ltd",
    )
    assert folder == tmp_path / "AB Ltd" / "INVOICE" / "NEW" / "Elec"


def test_blank_customer_raises_instead_of_filing_in_root(tmp_path):
    with pytest.raises(ValueError):
        destination_folder(
            root=tmp_path, client_name="Inspired PLC", doc_type="INVOICE", utility="Elec",
            tree=ODC_TREE, source="odc", customer_name="",
        )


def test_existing_destination_does_not_rebuild_tree(tmp_path):
    (tmp_path / "Acme" / "INVOICE" / "NEW" / "Elec").mkdir(parents=True)
    destination_folder(
        root=tmp_path, client_name="Inspired PLC", doc_type="INVOICE", utility="Elec",
        tree=ODC_TREE, source="odc", customer_name="Acme",
    )
    assert not (tmp_path / "Acme" / "LETTER").exists()


def test_post_tree_creates_shortcuts(tmp_path, no_shortcuts):
    routing.ensure_customer_tree(tmp_path / "Acme", POST_TREE)
    root = tmp_path / "Acme" / "INVOICE"
    assert sorted(no_shortcuts) == sorted([
        (str(root / "NEW" / "ELEC" / "ARCHIVE.lnk"), str(root / "ARCHIVE")),
        (str(root / "NEW" / "ELEC" / "HOLDING.lnk"), str(root / "HOLDING")),
    ])
