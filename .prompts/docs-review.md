Review documentation for accuracy, completeness, and consistency. Focus on things that require judgment—automated checks handle the rest.

## What's Already Automated

Don't waste time on these—CI and pre-commit hooks handle them:

- **README help output**: `markdown-code-runner` regenerates `agent-cli --help` blocks
- **Options tables**: `docs_gen` module auto-generates options from CLI introspection
- **Linting/formatting**: Handled by pre-commit

The `docs_gen` module (`agent_cli/docs_gen.py`) provides:
- `all_options_for_docs(cmd)`: Complete options tables grouped by panel
- `env_vars_table()`: Environment variables documentation
- `provider_matrix()`: Provider comparison table
- `config_example(cmd)`: Example TOML configuration
- `commands_table()`: Commands overview table

Run `uv run python docs/run_markdown_code_runner.py` to regenerate all auto-generated content.

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

Options tables are now auto-generated, so focus on what's NOT automated:

**Check for missing command docs:**

```bash
# Compare commands in CLI vs docs that exist
agent-cli --help
ls docs/commands/*.md
```

Every command should have a corresponding `docs/commands/<command>.md` file. When adding a new command doc, also update:
- `docs/commands/index.md` - add to the commands table
- `zensical.toml` - add to the `nav` sidebar under Commands

**What still needs manual review:**

| Check | What to Look For |
|-------|------------------|
| Description accuracy | Does the prose description match actual behavior? |
| Example commands | Would these actually work? Are they useful? |
| Workflow explanations | Is the step-by-step flow still accurate? |
| Use cases | Are suggested use cases realistic? |
| Cross-links | Do links to related commands work? |

**Verify auto-generation is working:**

```bash
# Run update script and check for changes
uv run python docs/run_markdown_code_runner.py
git diff docs/
```

If the script produces changes, either commit them or investigate why docs drifted.

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

### 5. High-Risk Areas (AI-Generated Content)

These are particularly prone to errors when docs are AI-generated or AI-maintained:

| Area | How to Verify | Notes |
|------|---------------|-------|
| **Tool/function names** | Check `agent_cli/_tools.py` | Tool names in prose/examples may drift |
| **File paths** | Grep for `PID_DIR`, `CONFIG_DIR`, etc. | Paths in prose may be wrong |
| **Dependencies** | Compare against `pyproject.toml` | Listed packages that don't exist |
| **Provider names** | Check `agent_cli/services/` | Providers listed that aren't implemented |

**Now auto-generated (lower risk):**
- Model defaults → captured in options tables via `docs_gen`
- Environment variables → use `env_vars_table()` for accuracy
- Option defaults/types → auto-generated from CLI introspection

```bash
# Verify tool names
grep -E "def.*_tool|Tool\(" agent_cli/_tools.py

# Verify file paths
grep -rE "(PID_DIR|CONFIG_DIR|CACHE_DIR)" agent_cli/

# Verify dependencies
cat pyproject.toml | grep -A 50 "dependencies"

# Verify providers match implementations
ls agent_cli/services/
```

### 6. Check Examples

For examples in any doc:
- Would the commands actually work?
- Are model names current (not deprecated)?
- Do examples use current syntax and options?

### 7. Cross-Reference Consistency

The same info appears in multiple places. Check for conflicts:
- README.md vs docs/index.md
- Prose/examples in docs vs actual CLI behavior
- docs/configuration.md vs agent_cli/example-config.toml
- Provider/port info across architecture docs

Note: Options tables are auto-generated, so conflicts there indicate the update script wasn't run.

### 8. Cross-Links for Navigation

When commands are mentioned in prose or examples, they should link to their documentation pages. This improves discoverability and user navigation.

**Key pages to check for missing cross-links:**

| Page | Should Link To |
|------|----------------|
| `configuration.md` | `commands/config.md`, command-specific docs |
| `getting-started.md` | Setup commands, test commands used in examples |
| `system-integration.md` | `commands/install-hotkeys.md`, hotkey commands |
| `commands/index.md` | Individual command pages |
| Architecture docs | Related command pages |

**Pattern to look for:**

```bash
# Find command mentions that might need links
grep -rE "agent-cli (config|transcribe|speak|chat|autocorrect)" docs/*.md | grep -v "commands/"

# Find backtick command references without links
grep -E '`(transcribe|autocorrect|speak|config|memory)`' docs/*.md | grep -v '\[.*\]\('
```

**Good cross-link patterns:**
- After code blocks: `See: [\`command\`](commands/command.md)`
- In prose: `Use the [\`config\`](commands/config.md) command to...`
- In tables: Link command names in the Command column

**Don't over-link:** Code blocks themselves don't need links (they're not clickable). Add links in surrounding prose or after the block.

### 9. Self-Check This Prompt

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

- **File**: docs/commands/chat.md:25
- **Problem**: Example uses `--model gpt-4` but the default model is now `gpt-4o-mini`
- **Fix**: Update the example to use the current default or a valid model name
- **Verify**: `agent-cli chat --help` shows current default
```
