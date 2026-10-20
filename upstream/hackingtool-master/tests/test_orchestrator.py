import json
import subprocess
import hackingtool.engagement as engagement
import hackingtool.orchestrator as orchestrator

def _root(tmp_path, monkeypatch):
    monkeypatch.setattr(engagement, "ENGAGEMENTS_ROOT", tmp_path)

def test_load_pipeline_reads_yaml():
    p = orchestrator.load_pipeline("recon")
    assert p["name"] == "recon"
    assert [s["tool"] for s in p["steps"]] == ["subfinder", "httpx", "nuclei"]

def test_run_pipeline_wires_stdin_and_normalizes(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    e = engagement.create("acme", targets=["example.com"])

    # every tool "installed"
    monkeypatch.setattr(orchestrator.shutil, "which", lambda t: "/usr/bin/" + t)

    calls = {}
    def fake_run(cmd, input=None, capture_output=None, text=None, timeout=None, **kwargs):
        tool = cmd[0]
        calls[tool] = input  # capture what each step received on stdin
        out = {
            "subfinder": "a.example.com\n",
            "httpx": json.dumps({"url": "https://a.example.com", "status_code": 200}) + "\n",
            "nuclei": json.dumps({"template-id": "x", "info": {"name": "X", "severity": "low"},
                                  "matched-at": "https://a.example.com"}) + "\n",
        }[tool]
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")
    monkeypatch.setattr(orchestrator.subprocess, "run", fake_run)

    result = orchestrator.run_pipeline(e, "recon")

    assert calls["subfinder"] == "example.com"          # targets -> stdin
    assert calls["httpx"] == "a.example.com"            # subfinder forward -> stdin
    assert calls["nuclei"] == "https://a.example.com"   # httpx bare url -> stdin
    kinds = sorted(f.kind for f in result)
    assert kinds == ["service", "subdomain", "vulnerability"]
    assert e.findings_file.exists()
    assert (e.raw_dir / "subfinder.txt").exists()

def test_run_pipeline_skips_missing_tool(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    e = engagement.create("acme", targets=["example.com"])
    monkeypatch.setattr(orchestrator.shutil, "which", lambda t: None)  # nothing installed
    result = orchestrator.run_pipeline(e, "recon")
    assert result == []
    assert "not installed" in e.log_file.read_text()

def test_scope_out_host_not_forwarded(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    e = engagement.create("acme", targets=["example.com"],
                          scope_in=["*.example.com"], scope_out=["admin.example.com"])
    monkeypatch.setattr(orchestrator.shutil, "which", lambda t: "/usr/bin/" + t)
    captured = {}
    def fake_run(cmd, input=None, capture_output=None, text=None, timeout=None, **kwargs):
        tool = cmd[0]
        captured[tool] = input
        out = {
            "subfinder": "admin.example.com\ngood.example.com\n",
            "httpx": json.dumps({"url": "https://good.example.com", "status_code": 200}) + "\n",
            "nuclei": "",
        }[tool]
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")
    monkeypatch.setattr(orchestrator.subprocess, "run", fake_run)
    orchestrator.run_pipeline(e, "recon")
    # subfinder discovered admin (excluded) + good; only good should be piped to httpx
    assert "admin.example.com" not in captured["httpx"]
    assert "good.example.com" in captured["httpx"]
    assert "scope-out" in e.log_file.read_text()
