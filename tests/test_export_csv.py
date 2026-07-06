import app.db as db
import app.services.repository as repo


def test_export_runs_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(repo, "get_connection", db.get_connection)
    db.init_db()
    repo.create_run({"kit":"kit1","stage_model":"mineru","file_name":"a.pdf","file_count":1,"page_count":2,"image_count":0,"table_count":None,"visual_input":"не использовался","wall_clock_seconds":0.1,"result":"ok","critical_errors":0})
    csv_path = repo.export_runs_csv(tmp_path / "out.csv")
    text = csv_path.read_text(encoding="utf-8")
    assert "kit1" in text
    assert "stage_model" in text


def test_export_runs_csv_contains_all_test_run_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test_fields.sqlite3")
    monkeypatch.setattr(repo, "get_connection", db.get_connection)
    db.init_db()
    repo.create_run({"kit":"kit1","stage_model":"mineru","file_name":"a.pdf","file_count":1,"page_count":2,"visual_input":"не использовался","wall_clock_seconds":0.1,"result":"ok","critical_errors":0,"input_summary":"вход","short_result":"результат","critical_issues":"нет","suitability":"пригодно"})
    csv_path = repo.export_runs_csv(tmp_path / "out_fields.csv")
    header = csv_path.read_text(encoding="utf-8").splitlines()[0].split(",")
    for field in repo.FIELDS:
        assert field in header
    for field in ["input_summary", "short_result", "critical_issues", "suitability"]:
        assert field in header
