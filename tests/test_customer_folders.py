from pathlib import Path
import pyodbc
import pytest

from file_allocation_core import customer_folders as cf

ID = "beb9dff0-a1c2-11e7-b049-02e80462a44f"


# --- names -----------------------------------------------------------------

@pytest.mark.parametrize("a, b", [
    ("ABC Ltd", "abc limited"),
    ("ABC Ltd.", "ABC LIMITED"),
    ("M&S", "M and S"),
    ("M & S Ltd", "m and s limited"),
    ("Bristol NHS Foundation Trust ", "BRISTOL NHS FOUNDATION TRUST"),
    ("  Acme   Group ", "acme group"),
])
def test_name_key_folds_known_variations(a, b):
    assert cf.name_key(a) == cf.name_key(b)


@pytest.mark.parametrize("a, b", [
    ("ABC Ltd", "ABC Holdings Ltd"),
    ("Altdorf", "Alimitedorf"),          # "ltd" only as a whole word
    ("Acme", "Acme Group"),
])
def test_name_key_keeps_real_differences(a, b):
    assert cf.name_key(a) != cf.name_key(b)


def test_name_key_blank():
    assert cf.name_key(None) == ""
    assert cf.name_key("   ") == ""


@pytest.mark.parametrize("raw, folder", [
    ("A/B Ltd", "AB Ltd"),
    ('Who: "Me"?', "Who- -Me--"),
    ("Trailing Co. ", "Trailing Co"),
    ("Name ", "Name"),
    ("Back\\slash", "Back-slash"),
])
def test_safe_folder_name(raw, folder):
    assert cf.safe_folder_name(raw) == folder


def test_pick_row_prefers_matching_name_else_oldest():
    rows = [cf.CustomerRow(1, "Old Name"), cf.CustomerRow(5, "NEW NAME LIMITED")]
    assert cf.pick_row(rows, "New Name Ltd").id == 5
    assert cf.pick_row(rows, "Something Else").id == 1


# --- resolve_customer_folder ---------------------------------------------------

def test_new_id_inserts_row_and_audit(fake_db, tmp_path):
    db = fake_db()
    folder = cf.resolve_customer_folder(tmp_path, ID.upper(), "Acme Ltd", "ebill", dsn="Jupiter")
    assert folder == "Acme Ltd"
    assert db.rows == [{"id": 1, "customer": "Acme Ltd", "customer_id": ID, "deleted": 0}]
    assert db.audit == [("Acme Ltd", cf.ROW_ADDED, None, "Acme Ltd", "ebill")]
    assert db.committed == 1 and db.closed == 1


def test_exact_sugar_name_returns_stored_folder_unchanged(fake_db, tmp_path):
    db = fake_db([{"id": 1, "customer": "ACME LIMITED", "customer_id": ID}])
    (tmp_path / "ACME LIMITED").mkdir()
    assert cf.resolve_customer_folder(tmp_path, ID, "ACME LIMITED", "odc", dsn="J") == "ACME LIMITED"
    assert db.audit == []


def test_ltd_variation_is_renamed_to_exact_sugar_name(fake_db, tmp_path, no_shortcuts):
    """A document for 'acme ltd' files into the Sugar-named folder."""
    db = fake_db([{"id": 1, "customer": "acme ltd", "customer_id": ID}])
    (tmp_path / "acme ltd").mkdir()
    assert cf.resolve_customer_folder(tmp_path, ID, "ACME LIMITED", "odc", dsn="J") == "ACME LIMITED"
    assert cf.disk_name(tmp_path, "acme limited") == "ACME LIMITED"
    assert not (tmp_path / "acme ltd").exists()
    assert db.rows[0]["customer"] == "ACME LIMITED"


def test_case_only_difference_renames_folder_in_place(fake_db, tmp_path, no_shortcuts):
    db = fake_db([{"id": 1, "customer": "Abbeycroft Leisure", "customer_id": ID}])
    (tmp_path / "Abbeycroft Leisure" / "INVOICE").mkdir(parents=True)
    (tmp_path / "Abbeycroft Leisure" / "INVOICE" / "bill.pdf").write_text("pdf")
    assert cf.resolve_customer_folder(tmp_path, ID, "ABBEYCROFT LEISURE", "odc", dsn="J") == "ABBEYCROFT LEISURE"
    assert cf.disk_name(tmp_path, "abbeycroft leisure") == "ABBEYCROFT LEISURE"
    assert (tmp_path / "ABBEYCROFT LEISURE" / "INVOICE" / "bill.pdf").read_text() == "pdf"
    assert [p.name for p in tmp_path.iterdir()] == ["ABBEYCROFT LEISURE"]
    assert db.rows[0]["customer"] == "ABBEYCROFT LEISURE"
    assert db.audit == [("ABBEYCROFT LEISURE", "Customer", "Abbeycroft Leisure", "ABBEYCROFT LEISURE", "odc")]


def test_case_only_with_folder_already_right_updates_table_only(fake_db, tmp_path):
    db = fake_db([{"id": 1, "customer": "Abbeycroft Leisure", "customer_id": ID}])
    (tmp_path / "ABBEYCROFT LEISURE").mkdir()
    assert cf.resolve_customer_folder(tmp_path, ID, "ABBEYCROFT LEISURE", "odc", dsn="J") == "ABBEYCROFT LEISURE"
    assert cf.disk_name(tmp_path, "abbeycroft leisure") == "ABBEYCROFT LEISURE"
    assert db.rows[0]["customer"] == "ABBEYCROFT LEISURE" and len(db.audit) == 1


def test_case_only_rename_failure_keeps_old_folder(fake_db, tmp_path, monkeypatch):
    db = fake_db([{"id": 1, "customer": "Abbeycroft Leisure", "customer_id": ID}])
    (tmp_path / "Abbeycroft Leisure").mkdir()
    real_rename = cf.Path.rename

    def fail_second(self, target):
        if ".renaming-" in self.name and Path(target).name == "ABBEYCROFT LEISURE":
            raise PermissionError(32, "in use")
        return real_rename(self, target)
    monkeypatch.setattr(cf.Path, "rename", fail_second)
    assert cf.resolve_customer_folder(tmp_path, ID, "ABBEYCROFT LEISURE", "odc", dsn="J") == "Abbeycroft Leisure"
    assert [p.name for p in tmp_path.iterdir()] == ["Abbeycroft Leisure"]
    assert db.audit == []


def test_mismatch_renames_folder_updates_key_and_audits(fake_db, tmp_path, no_shortcuts):
    db = fake_db([{"id": 1, "customer": "University Hospitals Bristol", "customer_id": ID}])
    old = tmp_path / "University Hospitals Bristol"
    (old / "INVOICE" / "NEW" / "ELEC").mkdir(parents=True)
    (old / "INVOICE" / "NEW" / "ELEC" / "ARCHIVE.lnk").write_text("x")
    (old / "INVOICE" / "NEW" / "ELEC" / "bill.pdf").write_text("pdf")

    folder = cf.resolve_customer_folder(
        tmp_path, ID, "BRISTOL NHS FOUNDATION TRUST ", "post-allocation", dsn="J"
    )

    new = tmp_path / "BRISTOL NHS FOUNDATION TRUST"
    assert folder == "BRISTOL NHS FOUNDATION TRUST"
    assert not old.exists()
    assert (new / "INVOICE" / "NEW" / "ELEC" / "bill.pdf").read_text() == "pdf"
    assert db.rows[0]["customer"] == "BRISTOL NHS FOUNDATION TRUST"
    assert db.audit == [(
        "BRISTOL NHS FOUNDATION TRUST", "Customer",
        "University Hospitals Bristol", "BRISTOL NHS FOUNDATION TRUST", "post-allocation",
    )]
    assert no_shortcuts == [(
        str(new / "INVOICE" / "NEW" / "ELEC" / "ARCHIVE.lnk"), str(new / "INVOICE" / "ARCHIVE"),
    )]


def test_already_renamed_folder_only_updates_table(fake_db, tmp_path):
    db = fake_db([{"id": 1, "customer": "Old Co", "customer_id": ID}])
    (tmp_path / "New Co").mkdir()
    assert cf.resolve_customer_folder(tmp_path, ID, "New Co", "odc", dsn="J") == "New Co"
    assert db.rows[0]["customer"] == "New Co"
    assert len(db.audit) == 1


def test_neither_folder_exists_rekeys_for_caller_to_create(fake_db, tmp_path):
    db = fake_db([{"id": 1, "customer": "Old Co", "customer_id": ID}])
    assert cf.resolve_customer_folder(tmp_path, ID, "New Co", "odc", dsn="J") == "New Co"
    assert db.rows[0]["customer"] == "New Co"


def test_collision_touches_nothing(fake_db, tmp_path):
    db = fake_db([{"id": 1, "customer": "Old Co", "customer_id": ID}])
    (tmp_path / "Old Co").mkdir()
    (tmp_path / "New Co").mkdir()
    assert cf.resolve_customer_folder(tmp_path, ID, "New Co", "odc", dsn="J") == "Old Co"
    assert db.rows[0]["customer"] == "Old Co"
    assert db.audit == []
    assert (tmp_path / "Old Co").is_dir() and (tmp_path / "New Co").is_dir()


def test_target_name_held_by_another_row_touches_nothing(fake_db, tmp_path):
    db = fake_db([
        {"id": 1, "customer": "Old Co", "customer_id": ID},
        {"id": 2, "customer": "New Co", "customer_id": "other-id"},
    ])
    (tmp_path / "Old Co").mkdir()
    assert cf.resolve_customer_folder(tmp_path, ID, "New Co", "odc", dsn="J") == "Old Co"
    assert (tmp_path / "Old Co").is_dir()
    assert db.audit == []


def test_failed_rename_files_into_old_folder(fake_db, tmp_path, monkeypatch):
    db = fake_db([{"id": 1, "customer": "Old Co", "customer_id": ID}])
    (tmp_path / "Old Co").mkdir()

    def locked(self, target):
        raise PermissionError(32, "The process cannot access the file")
    monkeypatch.setattr(cf.Path, "rename", locked)

    assert cf.resolve_customer_folder(tmp_path, ID, "New Co", "odc", dsn="J") == "Old Co"
    assert db.rows[0]["customer"] == "Old Co"
    assert db.audit == []


def test_several_rows_for_one_id_uses_matching_row(fake_db, tmp_path):
    db = fake_db([
        {"id": 1, "customer": "Bristol Old", "customer_id": ID},
        {"id": 2, "customer": "Bristol NHS", "customer_id": ID},
    ])
    (tmp_path / "Bristol Old").mkdir()
    (tmp_path / "Bristol NHS").mkdir()
    assert cf.resolve_customer_folder(tmp_path, ID, "Bristol NHS", "odc", dsn="J") == "Bristol NHS"
    assert db.audit == []


def test_deleted_rows_are_not_filed_into(fake_db, tmp_path):
    db = fake_db([{"id": 1, "customer": "Gone Co", "customer_id": ID, "deleted": 1}])
    assert cf.resolve_customer_folder(tmp_path, ID, "Fresh Co", "odc", dsn="J") == "Fresh Co"
    assert [r["customer"] for r in db.rows] == ["Gone Co", "Fresh Co"]


def test_insert_collision_with_other_account_files_by_name(fake_db, tmp_path):
    db = fake_db([{"id": 1, "customer": "Acme Ltd", "customer_id": "other-id"}])
    assert cf.resolve_customer_folder(tmp_path, ID, "Acme Ltd", "odc", dsn="J") == "Acme Ltd"
    assert len(db.rows) == 1
    assert db.audit == []


def test_db_unavailable_falls_back_to_sugar_name(monkeypatch, tmp_path):
    def down(dsn):
        raise pyodbc.OperationalError("08001", "SQL Server does not exist")
    monkeypatch.setattr(cf, "_connect", down)
    assert cf.resolve_customer_folder(tmp_path, ID, "A/B Ltd", "odc", dsn="J") == "AB Ltd"


def test_query_failure_falls_back_to_sugar_name(fake_db, tmp_path):
    db = fake_db([{"id": 1, "customer": "Old Co", "customer_id": ID}])
    db.fail_on = "SELECT id, customer"
    assert cf.resolve_customer_folder(tmp_path, ID, "New Co", "odc", dsn="J") == "New Co"
    assert db.closed == 1


def test_audit_write_failure_keeps_renamed_folder(fake_db, tmp_path, no_shortcuts):
    db = fake_db([{"id": 1, "customer": "Old Co", "customer_id": ID}])
    (tmp_path / "Old Co").mkdir()
    db.fail_on = "INSERT INTO Titan_INSE.dbo.XDRIVE_CUSTOMER_MASTER_AUDIT"
    assert cf.resolve_customer_folder(tmp_path, ID, "New Co", "odc", dsn="J") == "New Co"
    assert (tmp_path / "New Co").is_dir()
    assert db.rows[0]["customer"] == "Old Co"   # rolled back; stage 1 repairs it


def test_blank_id_or_name_skips_lookup(fake_db, tmp_path):
    db = fake_db()
    assert cf.resolve_customer_folder(tmp_path, "", "Acme", "odc", dsn="J") == "Acme"
    assert cf.resolve_customer_folder(tmp_path, ID, "", "odc", dsn="J") == ""
    assert db.rows == [] and db.closed == 0


def test_repoint_shortcuts_without_pywin32(monkeypatch, tmp_path):
    link = tmp_path / "INVOICE" / "NEW" / "ELEC" / "HOLDING.lnk"
    link.parent.mkdir(parents=True)
    link.write_text("x")
    monkeypatch.setattr(cf, "_shell", lambda: None)
    assert cf.repoint_shortcuts(tmp_path) == 0


def test_merged_row_ignored_in_favour_of_live_row(fake_db, tmp_path):
    """Abodus was merged into ABODUS LIMITED: the deleted row is never chosen
    or renamed, even though it is older."""
    db = fake_db([
        {"id": 1908, "customer": "Abodus", "customer_id": ID, "deleted": 1},
        {"id": 1913, "customer": "ABODUS LIMITED", "customer_id": ID},
    ])
    (tmp_path / "ABODUS LIMITED").mkdir()
    assert cf.resolve_customer_folder(tmp_path, ID, "ABODUS LIMITED", "odc", dsn="J") == "ABODUS LIMITED"
    assert db.audit == [] and len(db.rows) == 2


def test_only_deleted_row_under_sugar_name_is_reused_not_duplicated(fake_db, tmp_path):
    db = fake_db([{"id": 7, "customer": "Back Again Ltd", "customer_id": ID, "deleted": 1}])
    assert cf.resolve_customer_folder(tmp_path, ID, "BACK AGAIN LIMITED", "ebill", dsn="J") == "Back Again Ltd"
    assert len(db.rows) == 1 and db.audit == []


def test_pick_row_prefers_exact_name():
    rows = [cf.CustomerRow(1, "acme limited"), cf.CustomerRow(2, "ACME LIMITED")]
    assert cf.pick_row(rows, "ACME LIMITED").id == 2
