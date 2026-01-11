# Audit Prompt: Verify Evidence for External Library Assumptions

Use this prompt to have an AI agent verify that all assumptions in the `dev` module are backed by hard evidence.

---

## Prompt

You are auditing the `dev` module in this PR. Your task is to verify that every assumption about external tools (terminals, editors, AI agents) is backed by hard evidence.

### Scope

- `agent_cli/dev/` - all adapters for terminals, editors, and coding agents
- `tests/dev/test_verification.py` - verification tests with evidence docstrings

### For each adapter class, verify

1. **Environment variable detection** (e.g., `detect_env_vars`, `detect_term_program`)
   - Is there a test that documents the official source?
   - Does the evidence include: URL, quote/code snippet, verification method?
   - Is the source primary (official docs, man pages, source code) not secondary (blog posts, Stack Overflow)?

2. **Command-line flags** (e.g., `--cwd`, `--name`, `--tab-title`)
   - Was this verified via `--help` output or man pages?
   - Is the exact flag syntax documented?

3. **Install commands** (npm packages, pip packages)
   - Is the package name verified against npmjs.com or pypi.org?
   - Are there any deprecated package names being used?

### Evidence quality criteria

- ✅ Official docs with URL and quote
- ✅ Man page with exact quote
- ✅ Source code with file path and code snippet
- ✅ CLI `--help` output with exact flags shown
- ⚠️ Community knowledge (acceptable if marked as such)
- ❌ "Assumed" or "should work" without verification
- ❌ Secondary sources without primary verification

### Output format

For each adapter, report:

```
[Adapter Name]
- Detection: [env var] → [PASS/FAIL] - [source URL or reason]
- Commands: [flags] → [PASS/FAIL] - [verification method]
- Install: [package] → [PASS/FAIL] - [registry URL]
```

Flag any items marked ⚠️ (undocumented) or ❌ (unverified).

### Files to check

```
agent_cli/dev/terminals/*.py
agent_cli/dev/editors/*.py
agent_cli/dev/coding_agents/*.py
tests/dev/test_verification.py
```
