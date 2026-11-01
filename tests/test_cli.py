import respx
from typer.testing import CliRunner

from conftest import fixture_text
from tracker.cli import app

runner = CliRunner()


def env(tmp_path, monkeypatch, sources_yaml):
    f = tmp_path / "sources.yaml"
    f.write_text(sources_yaml)
    monkeypatch.setenv("SOURCES_FILE", str(f))
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("SNAPSHOT_DIR", str(tmp_path / "snaps"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("HOST_MIN_INTERVAL", "0")
    monkeypatch.chdir(tmp_path)  # no stray .env
    return f


YAML = "sources:\n  - {id: fci, name: FCI, url: 'https://fci.example/n', tier: 1}\n" \
       "  - {id: disabled-one, name: Disabled, url: 'https://off.example/', enabled: false}\n"


def test_list_and_add_source(tmp_path, monkeypatch):
    f = env(tmp_path, monkeypatch, YAML)
    out = runner.invoke(app, ["list-sources"]).output
    assert "fci" in out and "[off]" in out
    r = runner.invoke(app, ["add-source", "https://new.example", "--name", "New Kerala", "--state", "Kerala"])
    assert r.exit_code == 0 and "new-kerala" in f.read_text()
    assert runner.invoke(app, ["add-source", "https://new.example", "--name", "New Kerala"]).exit_code == 1


@respx.mock
def test_run_end_to_end_baseline_then_alert(tmp_path, monkeypatch):
    env(tmp_path, monkeypatch, YAML)
    html = fixture_text("fci_notices.html")
    route = respx.get("https://fci.example/n").respond(200, html=html)
    r1 = runner.invoke(app, ["run", "--tier", "1"])
    assert r1.exit_code == 0 and "(baseline)" in r1.output and "0 new alerts" in r1.output
    route.respond(200, html=html.replace("</ul>", "<li><a href='/z.pdf'>E-Auction of Rice at Goa</a></li></ul>"))
    r2 = runner.invoke(app, ["run", "--tier", "1"])
    assert "1 new alerts" in r2.output and "RICE AUCTION" in r2.output
    assert "OK" in runner.invoke(app, ["health"]).output


@respx.mock
def test_run_fail_on_error_exit_code(tmp_path, monkeypatch):
    env(tmp_path, monkeypatch, YAML)
    respx.get("https://fci.example/n").respond(404)
    assert runner.invoke(app, ["run", "--tier", "1"]).exit_code == 0
    assert runner.invoke(app, ["run", "--tier", "1", "--fail-on-error"]).exit_code == 1


def test_run_with_no_matching_sources(tmp_path, monkeypatch):
    env(tmp_path, monkeypatch, YAML)
    assert runner.invoke(app, ["run", "--tier", "3"]).exit_code == 1


@respx.mock
def test_test_source_shows_hits_without_state(tmp_path, monkeypatch):
    env(tmp_path, monkeypatch, YAML)
    respx.get("https://fci.example/n").respond(200, html=fixture_text("fci_notices.html"))
    out = runner.invoke(app, ["test-source", "https://fci.example/n"]).output
    assert "MATCH:rice" in out and "1 matching items" in out
    assert not (tmp_path / "t.db").exists()


def test_test_notify_and_digest_use_console(tmp_path, monkeypatch):
    env(tmp_path, monkeypatch, YAML)
    assert "Test message" in runner.invoke(app, ["test-notify"]).output
    assert "Digest sent" in runner.invoke(app, ["digest"]).output
