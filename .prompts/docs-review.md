Review documentation for accuracy, completeness, and consistency. Focus on things that require judgment—automated checks handle the rest.

## What's Already Automated

Don't waste time on these—CI and pre-commit hooks handle them:

- **README help output**: `markdown-code-runner` regenerates `agent-cli --help` blocks
- **Linting/formatting**: Handled by pre-commit

## What This Review Is For

Focus on things that require judgment:

1. **Accuracy**: Does the documentation match what the code actually does?
2. **Completeness**: Are there undocumented features, options, or behaviors?
3. **Clarity**: Would a new user understand this? Are examples realistic?
4. **Consistency**: Do different docs contradict each other?
5. **Freshness**: Has the code changed in ways the docs don't reflect?

## Review Process

### 1. Check Recent Changes

```bash
# What changed recently that might need doc updates?
git log --oneline -20 | grep -iE "feat|fix|add|remove|change|option"

# What code files changed?
git diff --name-only HEAD~20 | grep "\.py$"
```

Look for new features, changed defaults, renamed options, or removed functionality.

### 2. Verify Command Documentation

Each command in `docs/commands/` has manually maintained options tables. These can drift.

For each command's options table, compare against `agent-cli <command> --help`:
- Are all options listed?
- Are short flags correct?
- Are defaults accurate?
- Are descriptions accurate?

```bash
# List all commands
agent-cli --help

# Check specific command options
agent-cli transcribe --help
agent-cli chat --help
# etc.
```

### 3. Verify docs/configuration.md

Compare against the actual defaults in `agent_cli/opts.py` and config models:

```bash
# Find option defaults
grep -E "typer\.Option|default" agent_cli/opts.py

# Find config models
grep -r "class.*BaseModel" agent_cli/ --include="*.py" -A 10
```

Check:
- All config keys documented
- Types and defaults match code
- Config file locations are accurate
- Example TOML would actually work

### 4. Verify docs/architecture/

```bash
# What source files actually exist?
git ls-files "agent_cli/**/*.py"

# Check service implementations
ls agent_cli/services/
ls agent_cli/agents/
```

Check:
- Provider tables match actual implementations
- Port defaults match `agent_cli/opts.py`
- Dependencies match `pyproject.toml`
- File paths and locations are accurate

### 5. Check Examples

For examples in any doc:
- Would the commands actually work?
- Are model names current (not deprecated)?
- Do examples use current syntax and options?

### 6. Cross-Reference Consistency

The same info appears in multiple places. Check for conflicts:
- README.md vs docs/index.md
- docs/commands/*.md vs actual CLI help
- docs/configuration.md vs agent_cli/example-config.toml
- Provider/port info across architecture docs

### 7. Self-Check This Prompt

This prompt can become outdated too. If you notice:
- New automated checks that should be listed above
- New doc files that need review guidelines
- Patterns that caused issues

Include prompt updates in your fixes.

## Output Format

Categorize findings:

1. **Critical**: Wrong info that would break user workflows
2. **Inaccuracy**: Technical errors (wrong defaults, paths, types)
3. **Missing**: Undocumented features or options
4. **Outdated**: Was true, no longer is
5. **Inconsistency**: Docs contradict each other
6. **Minor**: Typos, unclear wording

For each issue, provide a ready-to-apply fix:

```
### Issue: [Brief description]

- **File**: docs/commands/chat.md:45
- **Problem**: `--history-dir` default shown as `~/.chat-history` but actual default is `~/.config/agent-cli/history`
- **Fix**: Update the default value in the options table
- **Verify**: `agent-cli chat --help`
```
