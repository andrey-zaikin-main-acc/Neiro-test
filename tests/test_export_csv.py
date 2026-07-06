import app.db as db
import app.services.repository as repo


def test_export_runs_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(repo, "get_connection", db.get_connection)
    db.init_db()
    repo.create_run({"kit":"kit1","stage_model":"mineru","file_name":"a.pdf","file_count":1,"page_count":2,"image_count":0,"table_count":0,"visual_input":0,"wall_clock_seconds":0.1,"result":"ok","critical_errors":0})
    csv_path = repo.export_runs_csv(tmp_path / "out.csv")
    text = csv_path.read_text(encoding="utf-8")
    assert "kit1" in text
    assert "stage_model" in text
