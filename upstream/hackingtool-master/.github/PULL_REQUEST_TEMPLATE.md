<!--
  TITLE FORMAT
  ─────────────────────────────────────────────────────────────────
  Adding a new tool  →  [New Tool] ToolName — Category
  Bug fix            →  [Fix] Short description of what was fixed
  Improvement        →  [Improve] Short description
  ─────────────────────────────────────────────────────────────────
  PRs without a properly formatted title may be closed without review.
-->

## Type of Change
- [ ] New tool addition
- [ ] Bug fix
- [ ] Improvement / refactor
- [ ] Documentation update

---

## For New Tool Additions — Required Fields

| Field | Value |
|---|---|
| **Tool name** | |
| **GitHub URL** | |
| **Category** | |
| **Supported OS** | Linux / macOS / Both |
| **Install method** | pip / go install / apt / git clone |

**Why should it be added?**
<!-- What gap does this fill? Min 2 sentences. -->

**Is the tool actively maintained?**
<!-- Link to last release / commit -->

---

## Checklist

- [ ] Title follows the format above
- [ ] New tool class added to the correct `tools/*.py` file
- [ ] `TITLE`, `DESCRIPTION`, `INSTALL_COMMANDS`, `RUN_COMMANDS`, `PROJECT_URL` all set
- [ ] `SUPPORTED_OS` set correctly (`["linux"]` / `["linux", "macos"]`)
- [ ] Tool added to the `TOOLS` list in the collection class at the bottom of the file
- [ ] No new dependencies added to `requirements.txt` without discussion
- [ ] Tested locally — install and run commands work
