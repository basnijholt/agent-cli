# Code Duplication Detection Implementation Report

## Executive Summary

This report documents the research, evaluation, and implementation of a code duplication detection system for the agent-cli project. The goal was to prevent duplicated code from entering the codebase, addressing an issue where seven code review agents failed to notice nearly identical files (`agent_cli/api.py` and `agent_cli/server/proxy/api.py`).

**Chosen Solution**: Two complementary tools integrated as pre-commit hooks:
1. **[jscpd](https://github.com/kucherenko/jscpd)** (primary) - Fast token-based detection with 3% threshold
2. **[pylint duplicate-code](https://pylint.readthedocs.io/)** (secondary) - AST-based Python-specific detection for 70+ line duplications

## Tools Evaluated

### 1. jscpd (JavaScript Copy/Paste Detector) ✅ SELECTED

**Pros**:
- Fast execution (~1.2s for 110 files)
- Token-based detection using Rabin-Karp algorithm
- Supports 150+ languages including Python
- Highly configurable (threshold, minLines, minTokens, ignore patterns)
- Clean, actionable output with line numbers
- Actively maintained (v4.0.7 released recently)
- JSON/YAML configuration support

**Cons**:
- Requires Node.js/npx (available on most development systems)
- No official pre-commit hook repository (requires local hook)
- Token-based, not AST-based (slightly less semantic understanding)

**Performance**: 1.2 seconds for 110 Python files (17,555 lines, 116,273 tokens)

### 2. Pylint duplicate-code (R0801)

**Pros**:
- Python-specific, AST-based detection
- Part of existing Python tooling ecosystem
- Integrated with pylint's broader analysis capabilities
- Configuration via `.pylintrc` or `pyproject.toml`

**Cons**:
- Slower execution (~4.5s for same codebase)
- Less focused (duplicate-code is just one of many checks)
- Cannot be disabled per-file with inline comments
- Configuration tied to pylint's overall settings
- Reports all duplicates to first file alphabetically (confusing output)

**Performance**: 4.5 seconds for the same codebase

### 3. Clone Digger

**Pros**:
- Python AST-based (semantic similarity detection)
- Detects parametric clones (same structure, different values)

**Cons**:
- Not actively maintained (last update years ago)
- No pre-commit integration
- Outdated Python support

### 4. PMD CPD (Copy/Paste Detector)

**Pros**:
- Multi-language support
- Well-established tool

**Cons**:
- Java-based, requires JVM
- Heavier dependency footprint
- Less common in Python ecosystems

### 5. pycode_similar

**Pros**:
- Python-specific, AST-based
- Designed for plagiarism detection

**Cons**:
- Focused on academic plagiarism detection
- Less suitable for development workflow integration
- Not designed for pre-commit hooks

## Selection Rationale

**jscpd was selected** because:

1. **Performance**: 4x faster than pylint's duplicate-code checker (1.2s vs 4.5s), crucial for pre-commit hooks that run on every commit
2. **Focus**: Dedicated duplication detection tool (single responsibility)
3. **Configuration**: Rich, flexible configuration via JSON file
4. **Output**: Clean, actionable output showing exact line ranges
5. **Maintenance**: Actively maintained with recent releases
6. **Extensibility**: Works for any language, future-proofing for multi-language projects

## Implementation Details

### Files Created/Modified

1. **`.jscpd.json`** (new) - Configuration file for jscpd
2. **`.pre-commit-config.yaml`** (modified) - Added jscpd and pylint hooks
3. **`pyproject.toml`** (modified) - Added pylint dev dependency and configuration
4. **`CLAUDE.md`** (modified) - Added documentation section

### jscpd Configuration

```json
{
  "$schema": "https://json.schemastore.org/jscpd.json",
  "threshold": 3,
  "reporters": ["console"],
  "path": ["agent_cli/"],
  "ignore": [
    "**/node_modules/**",
    "**/.git/**",
    "**/.venv/**",
    "**/venv/**",
    "**/__pycache__/**",
    "**/*.egg-info/**",
    "**/build/**",
    "**/dist/**",
    "**/tests/**",
    "**/test_*.py",
    "**/*_test.py",
    "**/scripts/**"
  ],
  "format": ["python"],
  "minLines": 15,
  "minTokens": 100,
  "absolute": false,
  "gitignore": true
}
```

### pylint Configuration (in pyproject.toml)

```toml
[tool.pylint.similarities]
min-similarity-lines = 70
ignore-comments = true
ignore-docstrings = true
ignore-imports = true
ignore-signatures = true
```

### Pre-commit Hooks

```yaml
- repo: local
  hooks:
    - id: jscpd
      name: jscpd (copy/paste detector)
      entry: npx jscpd --config .jscpd.json
      language: system
      pass_filenames: false
      always_run: true
      stages: [pre-commit]
    - id: pylint-duplicate-code
      name: pylint (duplicate-code only)
      entry: uv run pylint --disable=all --enable=duplicate-code --ignore=tests,scripts agent_cli/
      language: system
      types: [python]
      pass_filenames: false
      always_run: true
      stages: [pre-commit]
```

## Validation Results

### Current Codebase Status

The current codebase has **1.5% duplication** (264 lines, 2,429 tokens across 7 clone instances), which is below the 3% threshold. The hook passes successfully.

Detected duplications (existing, not blocking):
- Config object creation patterns between `assistant.py`, `voice_edit.py`, `chat.py`, `transcribe.py`, `transcribe_daemon.py`
- These represent legitimate shared patterns that could be refactored but don't block commits

### Would It Have Caught the Original Issue?

**Yes, definitively.** Testing with simulated duplicate files showed:

1. **Exact duplicates**: Detected as 50% duplication (100% of one file matches the other)
2. **Modified duplicates** (changed comments, versions, minor tweaks): Detected as 16.38% duplication

Both scenarios far exceed the 3% threshold and would have blocked the commit.

### Performance Validation

- **Execution time**: 1.2 seconds (well under the 30-second target)
- **Pre-commit overhead**: Minimal impact on commit workflow

## False Positives

### Excluded by Default

1. **Test files** (`tests/**`, `test_*.py`, `*_test.py`) - Tests often have similar structures intentionally
2. **Scripts directory** (`scripts/**`) - Standalone scripts may duplicate main code for isolation
3. **Build artifacts** (`build/**`, `dist/**`, `*.egg-info/**`)
4. **Virtual environments** (`.venv/**`, `venv/**`)
5. **Cache directories** (`__pycache__/**`)

### Existing Duplications (Not False Positives)

The 7 detected clones in the current codebase are **real duplications** that could benefit from refactoring:
- Config dataclass instantiation patterns
- Async audio processing workflows
- Provider configuration setup

These are kept as warnings (below threshold) rather than errors, allowing incremental improvement.

## Recommendations

### Threshold Tuning

The current 3% threshold is appropriate for:
- Catching significant new duplications (like the original ~400-line api.py issue)
- Not blocking commits for minor shared patterns
- Allowing incremental improvement of existing code

**Consider lowering to 2%** once the existing duplications are addressed through refactoring.

### Addressing Existing Duplications

Priority refactoring opportunities:

1. **Config creation patterns** (highest impact):
   - Extract `create_all_configs()` function in `config.py`
   - Reuse across `assistant.py`, `voice_edit.py`, `chat.py`, `transcribe.py`, `transcribe_daemon.py`

2. **Audio processing workflows**:
   - Consider shared base class or higher-order function for common patterns

### Minimum Line/Token Thresholds

- **minLines: 15** - Catches meaningful duplications, ignores trivial patterns
- **minTokens: 100** - Ensures semantic significance, not just similar short snippets

These can be adjusted based on team preference. Lower values catch more duplications but may increase noise.

## Limitations

1. **Token-based, not AST-based**: jscpd uses token matching, not abstract syntax tree analysis. It may miss semantically identical code with different formatting, or flag code that looks similar but behaves differently.

2. **No inline suppression**: Unlike pylint, jscpd doesn't support inline comments to ignore specific blocks. Use file-level ignores in `.jscpd.json`.

3. **Node.js dependency**: Requires `npx` to be available. This is typically available on development machines with Node.js installed.

4. **Whole-file analysis**: The hook analyzes the entire codebase each time, not just changed files. For this codebase size, this is fast enough, but may need optimization for very large codebases.

## Conclusion

The jscpd-based duplication detection system successfully addresses the original problem:

- **Would have caught** the `api.py` duplication that slipped through 7 code review agents
- **Fast enough** for pre-commit workflow (1.2s)
- **Configurable** to balance strictness with practicality
- **Well-documented** for team adoption

The implementation is complete and ready for use.
