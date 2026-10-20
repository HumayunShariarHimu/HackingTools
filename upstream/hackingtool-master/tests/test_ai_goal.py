import json
import subprocess

from hackingtool import ai_goal, skill


def test_validate_keeps_wellformed_and_sets_installed(monkeypatch):
    monkeypatch.setattr(ai_goal.shutil, "which",
                        lambda b: "/usr/bin/subfinder" if b == "subfinder" else None)
    raw = {"target": "limendo.com", "steps": [
        {"tool": "subfinder", "argv": ["subfinder", "-d", "limendo.com"], "why": "discover"},
        {"tool": "amass", "argv": ["amass", "enum", "-d", "limendo.com"], "why": "more"},
    ]}
    plan = ai_goal._validate(raw)
    assert plan.target == "limendo.com"
    assert [s.tool for s in plan.steps] == ["subfinder", "amass"]
    assert plan.steps[0].installed is True      # on PATH
    assert plan.steps[1].installed is False     # not on PATH → will skip at run


def test_validate_drops_malformed_steps(monkeypatch):
    monkeypatch.setattr(ai_goal.shutil, "which", lambda b: None)
    raw = {"target": "x", "steps": [
        {"tool": "ok", "argv": ["ok", "-a"], "why": ""},          # keep
        {"tool": "bad", "argv": "not-a-list", "why": ""},          # drop: argv not a list
        {"tool": "empty", "argv": [], "why": ""},                  # drop: empty argv
        {"tool": "mixed", "argv": ["mixed", 5], "why": ""},        # drop: non-str element
        {"why": "no argv at all"},                                 # drop: missing argv
    ]}
    plan = ai_goal._validate(raw)
    assert [s.tool for s in plan.steps] == ["ok"]


def test_validate_tolerates_junk():
    assert ai_goal._validate({}).steps == []
    assert ai_goal._validate({"steps": "nope"}).steps == []


def test_plan_parses_model_json(monkeypatch):
    monkeypatch.setattr(ai_goal.shutil, "which", lambda b: "/x")
    reply = ('sure, here is the plan:\n'
             '{"target":"limendo.com","steps":['
             '{"tool":"subfinder","argv":["subfinder","-d","limendo.com","-silent"],"why":"discover"}'
             ']} -- run safely')
    monkeypatch.setattr(ai_goal.ai_recommend, "ask", lambda prompt: reply)
    plan = ai_goal.plan("find subdomains of limendo.com", [])
    assert plan is not None
    assert plan.target == "limendo.com"
    assert plan.steps[0].argv == ["subfinder", "-d", "limendo.com", "-silent"]


def test_plan_prompt_carries_charter_and_objective(monkeypatch):
    captured = {}

    def fake_ask(prompt):
        captured["p"] = prompt

    monkeypatch.setattr(ai_goal.ai_recommend, "ask", fake_ask)
    ai_goal.plan("enumerate SMB on 10.0.0.5", [{"title": "Nmap", "example": "nmap -sV x"}])
    p = captured["p"]
    assert skill.charter()[:30] in p          # safety charter prepended
    assert "enumerate SMB on 10.0.0.5" in p    # objective present
    assert "Nmap" in p                         # toolbox surfaced


def test_methodology_loads():
    s = ai_goal.skill.methodology()
    assert isinstance(s, str) and s
    assert "Passive before active" in s


def test_plan_prompt_includes_methodology(monkeypatch):
    captured = {}

    def fake_ask(prompt):
        captured["p"] = prompt

    monkeypatch.setattr(ai_goal.ai_recommend, "ask", fake_ask)
    ai_goal.plan("enumerate subdomains", [])
    p = captured["p"]
    assert "OPERATOR PLAYBOOK" in p
    assert "subfinder" in p


def test_validate_captures_install_hint(monkeypatch):
    monkeypatch.setattr(ai_goal.shutil, "which", lambda b: None)
    plan = ai_goal._validate({"target": "x", "steps": [
        {"tool": "subfinder", "argv": ["subfinder", "-d", "x"], "why": "enum",
         "install": "go install github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest"}]})
    assert plan.steps[0].install_hint.startswith("go install")
    assert plan.steps[0].installed is False


def test_print_plan_shows_install_for_uninstalled(capsys):
    p = ai_goal.Plan("x", [ai_goal.Step("subfinder", ["subfinder", "-d", "x"], "enum",
                                        installed=False, install_hint="pipx install foo")])
    ai_goal._print_plan(p)
    out = capsys.readouterr().out
    assert "install" in out and "pipx install foo" in out


def test_toolbox_str_groups_by_category():
    box = [{"title": "nmap", "category": "Recon", "example": "nmap -sV x"},
           {"title": "ffuf", "category": "Web", "example": ""}]
    s = ai_goal._toolbox_str(box)
    assert "[Recon]" in s and "[Web]" in s and "nmap" in s


def test_plan_none_when_no_model(monkeypatch):
    monkeypatch.setattr(ai_goal.ai_recommend, "ask", lambda prompt: None)
    assert ai_goal.plan("anything", []) is None


def test_plan_empty_on_junk_reply(monkeypatch):
    monkeypatch.setattr(ai_goal.ai_recommend, "ask", lambda prompt: "no json here at all")
    plan = ai_goal.plan("anything", [])
    assert plan is not None and plan.steps == []


def test_run_step_uses_list_form_argv(monkeypatch, tmp_path):
    seen = {}

    def fake_run(argv, **kw):
        seen["argv"] = argv
        seen["shell"] = kw.get("shell", False)
        seen["cwd"] = kw.get("cwd")
        return subprocess.CompletedProcess(argv, 0, stdout="www.x.com\n", stderr="")

    monkeypatch.setattr(ai_goal.subprocess, "run", fake_run)
    step = ai_goal.Step("subfinder", ["subfinder", "-d", "x.com"], "why", installed=True)
    ai_goal._run_step(step, 1, 1, tmp_path)
    assert seen["argv"] == ["subfinder", "-d", "x.com"]   # a LIST, never a string
    assert seen["shell"] is False
    assert seen["cwd"] == str(tmp_path)
    assert (tmp_path / "step-1-subfinder.txt").read_text() == "www.x.com\n"


def test_run_step_survives_oserror(monkeypatch, tmp_path):
    def boom(argv, **kw):
        # real ENOENT carries markup-looking brackets: "[Errno 2] No such file..."
        raise OSError("[Errno 2] No such file or directory: 'ghost'")
    monkeypatch.setattr(ai_goal.subprocess, "run", boom)
    step = ai_goal.Step("ghost", ["ghost"], "why", installed=True)
    ai_goal._run_step(step, 1, 1, tmp_path)   # must not raise (incl. no MarkupError)


def test_run_step_survives_markup_in_output(monkeypatch, tmp_path):
    def fake_run(argv, **kw):
        return subprocess.CompletedProcess(argv, 0, stdout="found [/api/v1] endpoint\n", stderr="")
    monkeypatch.setattr(ai_goal.subprocess, "run", fake_run)
    step = ai_goal.Step("x", ["x"], "why", installed=True)
    ai_goal._run_step(step, 1, 1, tmp_path)   # must not raise MarkupError
    assert (tmp_path / "step-1-x.txt").read_text() == "found [/api/v1] endpoint\n"


def test_run_skips_uninstalled_and_runs_installed(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(ai_goal, "_toolbox", lambda: [])
    monkeypatch.setattr(ai_goal, "_workspace", lambda: tmp_path)
    monkeypatch.setattr(ai_goal, "plan", lambda obj, box: ai_goal.Plan("x.com", [
        ai_goal.Step("subfinder", ["subfinder", "-d", "x.com"], "d", installed=True),
        ai_goal.Step("amass", ["amass", "enum"], "d", installed=False),
    ]))
    # auto-answer: authorize target 'y', then step-1 'y'
    answers = iter(["y", "y"])
    monkeypatch.setattr(ai_goal.prompt, "simple", lambda *a, **k: next(answers))
    monkeypatch.setattr(ai_goal, "_run_step",
                        lambda step, n, total, ws: calls.append(step.tool))
    ai_goal.run("find subdomains of x.com")
    assert calls == ["subfinder"]     # amass (not installed) skipped, never run


def test_run_aborts_when_target_not_authorized(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(ai_goal, "_toolbox", lambda: [])
    monkeypatch.setattr(ai_goal, "plan", lambda obj, box: ai_goal.Plan("x.com", [
        ai_goal.Step("subfinder", ["subfinder"], "d", installed=True)]))
    monkeypatch.setattr(ai_goal.prompt, "simple", lambda *a, **k: "n")   # not authorized
    monkeypatch.setattr(ai_goal, "_run_step",
                        lambda *a, **k: calls.append("ran"))
    ai_goal.run("x")
    assert calls == []                # nothing executed


def test_run_falls_back_to_recommend_when_no_model(monkeypatch):
    hit = {}
    monkeypatch.setattr(ai_goal, "_toolbox", lambda: [])
    monkeypatch.setattr(ai_goal, "plan", lambda obj, box: None)   # no model
    import hackingtool.cli as cli
    monkeypatch.setattr(cli, "recommend_tools", lambda intent: hit.setdefault("intent", intent))
    ai_goal.run("crack a hash")
    assert hit["intent"] == "crack a hash"


def test_print_plan_survives_markup_in_argv():
    p = ai_goal.Plan("x.com", [ai_goal.Step("t", ["t", "[/api]"], "why [/b]", installed=True)])
    ai_goal._print_plan(p)   # must not raise MarkupError


def test_run_survives_markup_in_plan(monkeypatch, tmp_path):
    """Plan with bracket chars in argv and target should not raise MarkupError when prompting."""
    ran = []
    monkeypatch.setattr(ai_goal, "_toolbox", lambda: [])
    monkeypatch.setattr(ai_goal, "_workspace", lambda: tmp_path)
    monkeypatch.setattr(ai_goal, "plan", lambda o, b: ai_goal.Plan(
        "[/evil].com", [ai_goal.Step("t", ["t", "[/api]"], "why [/b]", installed=True)]))
    monkeypatch.setattr(ai_goal, "_run_step", lambda *a, **k: ran.append(1))
    answers = iter(["y", "s"])   # authorize, then skip the step
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    ai_goal.run("do a thing")    # must not raise MarkupError
    assert ran == []             # step was skipped


def test_run_edit_with_unbalanced_quotes(monkeypatch, tmp_path):
    """Edit path with unbalanced quotes should not crash; step not run."""
    ran = []
    monkeypatch.setattr(ai_goal, "_toolbox", lambda: [])
    monkeypatch.setattr(ai_goal, "_workspace", lambda: tmp_path)
    monkeypatch.setattr(ai_goal, "plan", lambda o, b: ai_goal.Plan("x.com", [
        ai_goal.Step("t", ["t", "x"], "why", installed=True)]))
    monkeypatch.setattr(ai_goal, "_run_step", lambda *a, **k: ran.append(1))
    # answers: auth 'y', then edit 'e', then bad command
    answers = iter(["y", "e", 'foo "bar'])   # unbalanced quote
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    ai_goal.run("do a thing")    # must not raise ValueError
    assert ran == []             # step not run due to parse error


def test_run_edit_with_empty_input(monkeypatch, tmp_path):
    """Edit path with empty input should skip step."""
    ran = []
    monkeypatch.setattr(ai_goal, "_toolbox", lambda: [])
    monkeypatch.setattr(ai_goal, "_workspace", lambda: tmp_path)
    monkeypatch.setattr(ai_goal, "plan", lambda o, b: ai_goal.Plan("x.com", [
        ai_goal.Step("t", ["t", "x"], "why", installed=True)]))
    monkeypatch.setattr(ai_goal, "_run_step", lambda *a, **k: ran.append(1))
    # answers: auth 'y', then edit 'e', then empty string
    answers = iter(["y", "e", ""])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    ai_goal.run("do a thing")    # must not crash
    assert ran == []             # step not run due to empty edit


def test_run_edit_audits_the_edited_command(monkeypatch, tmp_path):
    """run.log must record the actually-run (edited) argv, not just the proposal."""
    monkeypatch.setattr(ai_goal, "_toolbox", lambda: [])
    monkeypatch.setattr(ai_goal, "_workspace", lambda: tmp_path)
    monkeypatch.setattr(ai_goal, "plan", lambda o, b: ai_goal.Plan("x.com", [
        ai_goal.Step("echo", ["echo", "proposed"], "why", installed=True)]))
    monkeypatch.setattr(ai_goal.subprocess, "run",
                        lambda argv, **kw: subprocess.CompletedProcess(argv, 0, stdout="", stderr=""))
    # auth 'y', then edit 'e', then the replacement command
    answers = iter(["y", "e", "echo edited-cmd"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    ai_goal.run("do a thing")
    log = (tmp_path / "run.log").read_text()
    assert "edited: echo edited-cmd" in log


def test_dispatch_routes_goal(monkeypatch):
    from hackingtool import prompt
    seen = {}
    monkeypatch.setattr(ai_goal, "run", lambda obj, ctx=None: seen.setdefault("obj", obj))
    sig = prompt.dispatch("/goal find subdomains of x.com", prompt.PromptCtx("home"))
    assert sig is prompt.CONTINUE
    assert seen["obj"] == "find subdomains of x.com"


def test_goal_is_a_listed_command():
    from hackingtool import repl
    assert "/goal" in repl._COMMANDS


def test_run_writes_audit_trail(monkeypatch, tmp_path):
    monkeypatch.setattr(ai_goal, "_toolbox", lambda: [])
    monkeypatch.setattr(ai_goal, "_workspace", lambda: tmp_path)
    monkeypatch.setattr(ai_goal, "plan", lambda obj, box: ai_goal.Plan("x.com", [
        ai_goal.Step("echo", ["echo", "hi"], "d", installed=True)]))
    monkeypatch.setattr(ai_goal.subprocess, "run",
                        lambda argv, **kw: subprocess.CompletedProcess(argv, 0, stdout="hi\n", stderr=""))
    answers = iter(["y", "y"])
    monkeypatch.setattr(ai_goal.prompt, "simple", lambda *a, **k: next(answers))
    ai_goal.run("find subdomains of x.com")

    plan_json = json.loads((tmp_path / "plan.json").read_text())
    assert plan_json["target"] == "x.com"
    assert isinstance(plan_json["steps"], list)

    log = (tmp_path / "run.log").read_text()
    assert "authorized target=" in log
    assert "exit 0" in log


def test_run_q_aborts_before_first_step(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(ai_goal, "_toolbox", lambda: [])
    monkeypatch.setattr(ai_goal, "_workspace", lambda: tmp_path)
    monkeypatch.setattr(ai_goal, "plan", lambda obj, box: ai_goal.Plan("x.com", [
        ai_goal.Step("a", ["a"], "d", installed=True),
        ai_goal.Step("b", ["b"], "d", installed=True),
    ]))
    answers = iter(["y", "q"])
    monkeypatch.setattr(ai_goal.prompt, "simple", lambda *a, **k: next(answers))
    monkeypatch.setattr(ai_goal, "_run_step",
                        lambda step, n, total, ws: calls.append(step.tool))
    ai_goal.run("do a thing")
    assert calls == []     # q aborts before step 1 ever runs


def test_run_calls_model_exactly_once(monkeypatch, tmp_path):
    counter = {"n": 0}

    def fake_ask(prompt):
        counter["n"] += 1
        return ('{"target":"x.com","steps":['
                '{"tool":"a","argv":["a"],"why":""}]}')

    monkeypatch.setattr(ai_goal, "_toolbox", lambda: [])
    monkeypatch.setattr(ai_goal, "_workspace", lambda: tmp_path)
    monkeypatch.setattr(ai_goal.shutil, "which", lambda b: "/usr/bin/a")
    monkeypatch.setattr(ai_goal.ai_recommend, "ask", fake_ask)
    monkeypatch.setattr(ai_goal, "_run_step", lambda *a, **k: None)
    answers = iter(["y", "s"])
    monkeypatch.setattr(ai_goal.prompt, "simple", lambda *a, **k: next(answers))
    ai_goal.run("obj")
    assert counter["n"] == 1
