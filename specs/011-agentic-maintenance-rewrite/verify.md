# Verification Prompt: Agentic Maintenance Rewrite (Spec 011)

Read `specs/011-agentic-maintenance-rewrite/plan.md` for context on what was implemented.

Your job is to verify the full implementation is correct, fix any remaining issues, and run everything end-to-end. Work through each section in order.

---

## Phase 0: Fix Known Broken Tests

The implementation renamed agent methods (`run` → `sync`, `run_sync` → `chat`) but missed updating 5 test files. Fix these FIRST before running anything:

### `tests/test_agent_memory_write_flow.py`
- Lines 133, 167, 168: Change `agent.run(trace_path)` → `agent.sync(trace_path)`

### `tests/test_agent_memory_write_integration.py`
- Line 101: Change `agent.run(trace_path)` → `agent.sync(trace_path)`

### `tests/test_agent_memory_write_modes_e2e.py`
- Line 122: Change `agent.run(trace_path)` → `agent.sync(trace_path)`

### `tests/test_cli.py`
- Line 97 (inside `_FakeAgent`): Rename method `run_sync` → `chat`

### `tests/test_context_layers_e2e.py`
- Line 27 (inside `_FakeAgent`): Rename method `run_sync` → `chat`

After fixing, run `scripts/run_tests.sh unit` and confirm all tests pass before proceeding.

---

## Phase 1: Structural Verification

Check that every file from the plan exists and has correct structure. For each check, print PASS or FAIL with details.

### 1.1 Prompts package exists
```bash
ls -la acreta/runtime/prompts/
```
Expected: `__init__.py`, `system.py`, `sync.py`, `maintain.py`, `chat.py`

### 1.2 Dead files removed
```bash
test ! -f acreta/memory/maintenance.py && echo "PASS: maintenance.py deleted" || echo "FAIL: maintenance.py still exists"
```

### 1.3 No old method names in source code
```bash
# These should return ZERO matches in acreta/ source (not tests/)
rg "def run_sync\b" acreta/
rg "def run\(" acreta/runtime/agent.py
rg "_build_system_prompt" acreta/runtime/agent.py
rg "_build_memory_write_prompt" acreta/runtime/agent.py
rg "_build_chat_prompt" acreta/app/cli.py
rg "_looks_like_auth_error" acreta/app/cli.py
rg "maintain_default_steps" acreta/app/daemon.py
rg "resolve_maintain_steps" acreta/app/daemon.py
rg "_run_maintain_step" acreta/app/daemon.py
rg -- "--steps" acreta/app/cli.py
```
Each command should return nothing. Any match is a FAIL.

### 1.4 No old method names in test code
After Phase 0 fixes, verify:
```bash
rg "agent\.run\(" tests/
rg "\.run_sync\(" tests/
```
Should return ZERO matches. Any match is a FAIL.

### 1.5 New methods exist
```bash
rg "def chat\(" acreta/runtime/agent.py
rg "def sync\(" acreta/runtime/agent.py
rg "def maintain\(" acreta/runtime/agent.py
```
Each should return exactly one match.

### 1.6 Imports are wired correctly
```bash
# agent.py imports from prompts package
rg "from acreta.runtime.prompts" acreta/runtime/agent.py

# cli.py imports from prompts.chat
rg "from acreta.runtime.prompts.chat" acreta/app/cli.py

# daemon.py calls agent.sync() and agent.maintain()
rg "\.sync\(" acreta/app/daemon.py
rg "\.maintain\(" acreta/app/daemon.py
```

---

## Phase 2: Self-Test Verification

Run every self-test and confirm they pass:

```bash
python -m acreta.runtime.prompts.system
python -m acreta.runtime.prompts.sync
python -m acreta.runtime.prompts.maintain
python -m acreta.runtime.prompts.chat
python -m acreta.runtime.agent
python -m acreta.app.daemon
```

Each should exit 0 with no errors. If any fails, fix it and re-run.

---

## Phase 3: Unit Tests

```bash
scripts/run_tests.sh unit
```

ALL tests must pass. If any fail, investigate and fix. Common issues to watch for:
- `AttributeError: 'AcretaAgent' object has no attribute 'run'` → missed rename
- `TypeError: run_maintain_once() got an unexpected keyword argument 'steps_raw'` → caller not updated
- Import errors from deleted modules or moved functions

---

## Phase 4: Content Quality Checks

### 4.1 Every file has top-level docstring
```bash
for f in acreta/runtime/prompts/__init__.py acreta/runtime/prompts/system.py acreta/runtime/prompts/sync.py acreta/runtime/prompts/maintain.py acreta/runtime/prompts/chat.py; do
  head -3 "$f" | grep -q '"""' && echo "PASS: $f has docstring" || echo "FAIL: $f missing docstring"
done
```

### 4.2 Every function has docstring
```bash
# Look for def lines NOT followed by a docstring (within 2 lines)
for f in acreta/runtime/prompts/system.py acreta/runtime/prompts/sync.py acreta/runtime/prompts/maintain.py acreta/runtime/prompts/chat.py; do
  echo "--- $f ---"
  python3 -c "
import ast, sys
with open('$f') as fh:
    tree = ast.parse(fh.read())
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        doc = ast.get_docstring(node)
        status = 'PASS' if doc else 'FAIL'
        print(f'  {status}: {node.name}() line {node.lineno}')
"
done
```

### 4.3 Triple-quoted strings (no concatenated prompt strings)
```bash
# Prompt files should NOT have patterns like: "line\n" + "line\n" or ("line\n" "line\n")
# Check for string concat patterns in prompt files
for f in acreta/runtime/prompts/system.py acreta/runtime/prompts/sync.py acreta/runtime/prompts/maintain.py acreta/runtime/prompts/chat.py; do
  count=$(rg -c '^\s+\".*\\n\"$' "$f" 2>/dev/null || echo 0)
  if [ "$count" = "0" ]; then
    echo "PASS: $f uses triple-quoted strings"
  else
    echo "FAIL: $f has $count concatenated string lines"
  fi
done
```

### 4.4 Maintain prompt content quality
Read `acreta/runtime/prompts/maintain.py` and verify the prompt includes ALL of these concepts (search for keywords):
```bash
for keyword in "scan" "duplicate" "merge" "archive" "consolidate" "report" "memory_root" "run_folder" "TodoWrite" "explore" "soft-delete\|archived\|mv " "frontmatter" "confidence" "decisions" "learnings" "summaries"; do
  if rg -qi "$keyword" acreta/runtime/prompts/maintain.py; then
    echo "PASS: maintain prompt mentions '$keyword'"
  else
    echo "FAIL: maintain prompt MISSING '$keyword'"
  fi
done
```

### 4.5 Maintain prompt does NOT touch summaries
```bash
# Prompt should explicitly say NOT to touch summaries
rg -i "not.*summar|do not.*summar|never.*summar|skip.*summar" acreta/runtime/prompts/maintain.py && echo "PASS: summaries exclusion stated" || echo "FAIL: missing summaries exclusion"
```

### 4.6 Maintain uses soft-delete (not hard delete)
```bash
rg -i "mv\|move\|archived" acreta/runtime/prompts/maintain.py && echo "PASS: soft-delete pattern present" || echo "FAIL: missing soft-delete pattern"
rg -i "do not delete\|never delete\|no hard.delete\|soft.delete" acreta/runtime/prompts/maintain.py && echo "PASS: no-delete rule present" || echo "FAIL: missing no-delete rule"
```

---

## Phase 5: Integration Smoke Test

### 5.1 Agent construction
```bash
python3 -c "
from acreta.runtime.agent import AcretaAgent
agent = AcretaAgent(skills=['acreta'])
assert hasattr(agent, 'chat'), 'missing chat method'
assert hasattr(agent, 'sync'), 'missing sync method'
assert hasattr(agent, 'maintain'), 'missing maintain method'
assert not hasattr(agent, 'run_sync'), 'old run_sync still exists'
assert 'AcretaAgent' in agent.system_prompt
print('PASS: Agent construction and method check')
"
```

### 5.2 Prompt builders return valid content
```bash
python3 -c "
from pathlib import Path
from acreta.runtime.prompts import build_system_prompt, build_sync_prompt, build_maintain_prompt, build_chat_prompt
from acreta.runtime.prompts.maintain import build_maintain_artifact_paths
from tempfile import TemporaryDirectory

# System prompt
sp = build_system_prompt(['acreta'])
assert 'AcretaAgent' in sp
assert 'Skills:' in sp
print('PASS: system prompt')

# Chat prompt
cp = build_chat_prompt('what is X?', [], [])
assert 'what is X?' in cp
print('PASS: chat prompt')

# Sync prompt
with TemporaryDirectory() as tmp:
    root = Path(tmp)
    trace = root / 'trace.jsonl'
    trace.write_text('{\"role\":\"user\",\"content\":\"hi\"}\n')
    run_folder = root / 'workspace' / 'sync-test'
    run_folder.mkdir(parents=True)
    from acreta.runtime.agent import _build_artifact_paths
    arts = _build_artifact_paths(run_folder)
    meta = {'run_id': 'sync-test', 'trace_path': str(trace), 'repo_name': 'test'}
    syncp = build_sync_prompt(trace_file=trace, memory_root=root / 'memory', run_folder=run_folder, artifact_paths=arts, metadata=meta)
    assert 'trace_path' in syncp
    assert 'memory_root' in syncp
    print('PASS: sync prompt')

    # Maintain prompt
    mrun = root / 'workspace' / 'maintain-test'
    mrun.mkdir(parents=True)
    marts = build_maintain_artifact_paths(mrun)
    mp = build_maintain_prompt(memory_root=root / 'memory', run_folder=mrun, artifact_paths=marts)
    assert 'memory_root' in mp
    assert 'maintain_actions' in mp
    assert 'archive' in mp.lower()
    assert 'merge' in mp.lower()
    print('PASS: maintain prompt')
print('ALL PROMPT CHECKS PASSED')
"
```

### 5.3 CLI parser accepts new maintain flags
```bash
python3 -c "
from acreta.app.cli import build_parser
parser = build_parser()
# maintain with only --force and --dry-run should work
args = parser.parse_args(['maintain', '--dry-run'])
assert args.dry_run is True
assert not hasattr(args, 'steps'), 'steps flag should be removed'
print('PASS: maintain CLI parser')
"
```

### 5.4 Daemon function signature
```bash
python3 -c "
import inspect
from acreta.app.daemon import run_maintain_once
sig = inspect.signature(run_maintain_once)
params = list(sig.parameters.keys())
assert 'force' in params, f'missing force param, got {params}'
assert 'dry_run' in params, f'missing dry_run param, got {params}'
assert 'steps_raw' not in params, f'steps_raw should be removed, got {params}'
assert 'parse_csv' not in params, f'parse_csv should be removed, got {params}'
assert 'window' not in params, f'window should be removed, got {params}'
print(f'PASS: run_maintain_once signature: {params}')
"
```

---

## Phase 6: No Dead Code / No Orphan References

```bash
# No references to deleted maintenance.py
rg "acreta.memory.maintenance\|from acreta.memory import maintenance\|memory.maintenance" acreta/ tests/

# No references to old step functions
rg "maintain_default_steps\|resolve_maintain_steps\|_run_maintain_step" acreta/ tests/

# No references to old build_extract_report from daemon maintain path
# (dashboard.py is allowed to use it)
rg "build_extract_report" acreta/app/daemon.py

# No old prompt builder references
rg "_build_system_prompt\|_build_memory_write_prompt\|_build_chat_prompt\|_looks_like_auth_error" acreta/ tests/
```

All commands should return ZERO matches. Any match means dead references remain.

---

## Phase 7: Final Full Test Run

```bash
scripts/run_tests.sh unit
```

Print the full output. Every test must pass.

---

## Phase 8: End-to-End Maintenance Test (Real LLM Calls)

This phase calls `agent.maintain()` for real against a temporary memory_root with sample memories. It costs API calls and takes a few minutes. Run it after all other phases pass.

### 8.1 Set up test memory_root

Create a temporary directory with sample memory files that have intentional duplicates and low-quality entries for the agent to act on.

```bash
python3 << 'PYEOF'
import json
import shutil
from pathlib import Path
from tempfile import mkdtemp

tmp = Path(mkdtemp(prefix="acreta-maintain-e2e-"))
memory_root = tmp / "memory"
workspace_root = tmp / "workspace"

# Create folder structure
for folder in ("decisions", "learnings", "summaries", "archived/decisions", "archived/learnings"):
    (memory_root / folder).mkdir(parents=True)
workspace_root.mkdir(parents=True)

# --- DECISIONS ---

# Two near-duplicate decisions (should be merged)
(memory_root / "decisions" / "20260220-use-postgres-for-storage.md").write_text("""\
---
id: use-postgres-for-storage
title: Use PostgreSQL for Storage
created: 2026-02-20T10:00:00Z
updated: 2026-02-20T10:00:00Z
source: sync-20260220-100000-aaa111
confidence: 0.8
tags: [database, storage]
---
We decided to use PostgreSQL as the primary storage backend for the application.
It provides ACID compliance and good performance for our workload.
""")

(memory_root / "decisions" / "20260220-postgresql-as-primary-database.md").write_text("""\
---
id: postgresql-as-primary-database
title: PostgreSQL as Primary Database
created: 2026-02-20T14:00:00Z
updated: 2026-02-20T14:00:00Z
source: sync-20260220-140000-bbb222
confidence: 0.85
tags: [database, backend]
---
Decision to adopt PostgreSQL as the primary database. It supports our relational
data model well and has strong ecosystem support. Chosen over MySQL and SQLite
for production use due to better concurrency handling.
""")

# A good unique decision (should be kept as-is)
(memory_root / "decisions" / "20260221-api-versioning-via-url-prefix.md").write_text("""\
---
id: api-versioning-via-url-prefix
title: API Versioning via URL Prefix
created: 2026-02-21T09:00:00Z
updated: 2026-02-21T09:00:00Z
source: sync-20260221-090000-ccc333
confidence: 0.9
tags: [api, versioning]
---
Use URL path prefix for API versioning (e.g., /v1/users, /v2/users).
This is simpler than header-based versioning and more visible to consumers.
""")

# --- LEARNINGS ---

# A trivial low-value learning (should be archived)
(memory_root / "learnings" / "20260220-ran-pip-install.md").write_text("""\
---
id: ran-pip-install
title: Ran pip install
created: 2026-02-20T08:00:00Z
updated: 2026-02-20T08:00:00Z
source: sync-20260220-080000-ddd444
kind: procedure
confidence: 0.2
tags: [setup]
---
Ran pip install to install dependencies.
""")

# Two overlapping learnings (should be merged)
(memory_root / "learnings" / "20260220-docker-layer-caching.md").write_text("""\
---
id: docker-layer-caching
title: Docker Layer Caching
created: 2026-02-20T11:00:00Z
updated: 2026-02-20T11:00:00Z
source: sync-20260220-110000-eee555
kind: insight
confidence: 0.8
tags: [docker, performance]
---
Docker builds are faster when you copy requirements.txt first and install
dependencies before copying the rest of the source code. This way the
dependency layer is cached and only rebuilt when requirements change.
""")

(memory_root / "learnings" / "20260221-optimize-dockerfile-with-layer-order.md").write_text("""\
---
id: optimize-dockerfile-with-layer-order
title: Optimize Dockerfile with Layer Order
created: 2026-02-21T08:00:00Z
updated: 2026-02-21T08:00:00Z
source: sync-20260221-080000-fff666
kind: insight
confidence: 0.75
tags: [docker, optimization, build]
---
Dockerfile layer ordering matters for build cache. Put rarely-changing layers
(like dependency installation) before frequently-changing layers (like source
code copy). Specifically, COPY requirements.txt and RUN pip install before
COPY . to maximize cache hits.
""")

# A good unique learning (should be kept)
(memory_root / "learnings" / "20260221-pytest-tmp-path-fixture.md").write_text("""\
---
id: pytest-tmp-path-fixture
title: pytest tmp_path Fixture
created: 2026-02-21T10:00:00Z
updated: 2026-02-21T10:00:00Z
source: sync-20260221-100000-ggg777
kind: insight
confidence: 0.85
tags: [testing, pytest]
---
Use pytest's built-in tmp_path fixture for temporary directories in tests.
It auto-cleans and provides unique paths per test. Better than manual
tempfile.mkdtemp which requires explicit cleanup.
""")

# Write paths for the test harness
config = {
    "memory_root": str(memory_root),
    "workspace_root": str(workspace_root),
    "tmp_dir": str(tmp),
}
config_path = tmp / "e2e_config.json"
config_path.write_text(json.dumps(config, indent=2))
print(f"E2E config: {config_path}")
print(f"Memory root: {memory_root}")
print(f"  decisions: {len(list((memory_root / 'decisions').glob('*.md')))} files")
print(f"  learnings: {len(list((memory_root / 'learnings').glob('*.md')))} files")
print(f"Workspace: {workspace_root}")
PYEOF
```

Save the printed `e2e_config.json` path for the next step.

### 8.2 Run agent.maintain() for real

```bash
python3 << 'PYEOF'
import json
import sys
from pathlib import Path

# Read config from Phase 8.1 — replace this path with the actual output
import glob
configs = sorted(glob.glob("/tmp/acreta-maintain-e2e-*/e2e_config.json"))
if not configs:
    print("FAIL: No e2e config found. Run Phase 8.1 first.")
    sys.exit(1)
config = json.loads(Path(configs[-1]).read_text())

memory_root = config["memory_root"]
workspace_root = config["workspace_root"]

print(f"Running maintain against: {memory_root}")
print("This will make real LLM API calls...")

from acreta.runtime.agent import AcretaAgent

agent = AcretaAgent(
    skills=["acreta"],
    default_cwd=str(Path.cwd()),
    timeout_seconds=300,
)

result = agent.maintain(
    memory_root=memory_root,
    workspace_root=workspace_root,
)

print("\n=== MAINTAIN RESULT ===")
print(json.dumps(result, indent=2))

# Save result for validation
result_path = Path(config["tmp_dir"]) / "maintain_result.json"
result_path.write_text(json.dumps(result, indent=2))
print(f"\nResult saved to: {result_path}")
PYEOF
```

### 8.3 Validate results

```bash
python3 << 'PYEOF'
import json
import sys
from pathlib import Path
import glob

# Load result
configs = sorted(glob.glob("/tmp/acreta-maintain-e2e-*/e2e_config.json"))
config = json.loads(Path(configs[-1]).read_text())
result_path = Path(config["tmp_dir"]) / "maintain_result.json"
if not result_path.exists():
    print("FAIL: No maintain result found. Run Phase 8.2 first.")
    sys.exit(1)

result = json.loads(result_path.read_text())
memory_root = Path(config["memory_root"])
errors = []

# --- Check 1: Result structure ---
for key in ("memory_root", "workspace_root", "run_folder", "artifacts", "counts"):
    if key not in result:
        errors.append(f"FAIL: Missing key '{key}' in result")
print(f"{'PASS' if not errors else 'FAIL'}: Result structure")

# --- Check 2: maintain_actions.json exists ---
artifacts = result.get("artifacts", {})
actions_path = Path(artifacts.get("maintain_actions", ""))
if actions_path.exists():
    print(f"PASS: maintain_actions.json exists at {actions_path}")
    actions = json.loads(actions_path.read_text())
    print(f"  Actions: {json.dumps(actions.get('counts', {}))}")
else:
    errors.append(f"FAIL: maintain_actions.json missing at {actions_path}")
    print(f"FAIL: maintain_actions.json missing")

# --- Check 3: agent.log exists ---
log_path = Path(artifacts.get("agent_log", ""))
if log_path.exists() and log_path.stat().st_size > 0:
    print(f"PASS: agent.log exists ({log_path.stat().st_size} bytes)")
else:
    errors.append("FAIL: agent.log missing or empty")
    print("FAIL: agent.log missing or empty")

# --- Check 4: Counts are present and sane ---
counts = result.get("counts", {})
total_actions = sum(counts.values())
print(f"Counts: {counts}")
if total_actions == 0:
    errors.append("WARN: Zero actions taken — agent may not have done anything")
    print("WARN: Zero actions — agent may have been too conservative")
else:
    print(f"PASS: {total_actions} total actions taken")

# --- Check 5: Were near-duplicates handled? ---
# Check if postgres decisions were merged (one should be in archived/)
archived_decisions = list((memory_root / "archived" / "decisions").glob("*.md"))
archived_learnings = list((memory_root / "archived" / "learnings").glob("*.md"))
remaining_decisions = list((memory_root / "decisions").glob("*.md"))
remaining_learnings = list((memory_root / "learnings").glob("*.md"))

print(f"\nMemory state after maintain:")
print(f"  decisions remaining: {len(remaining_decisions)}")
print(f"  learnings remaining: {len(remaining_learnings)}")
print(f"  archived decisions: {len(archived_decisions)}")
print(f"  archived learnings: {len(archived_learnings)}")

# We started with 3 decisions, 4 learnings
# Expected: at least 1 archived (the trivial "ran pip install" or a duplicate)
if archived_decisions or archived_learnings:
    print("PASS: At least one memory was archived")
    for f in archived_decisions + archived_learnings:
        print(f"  archived: {f.name}")
else:
    errors.append("WARN: Nothing was archived — agent may not have identified low-value or duplicate memories")
    print("WARN: Nothing was archived")

# --- Check 6: No files written outside allowed roots ---
run_folder = Path(result.get("run_folder", ""))
if run_folder.exists():
    all_files = list(run_folder.rglob("*"))
    print(f"PASS: Run folder exists with {len(all_files)} files")
else:
    errors.append("FAIL: Run folder does not exist")
    print("FAIL: Run folder missing")

# --- Check 7: Summaries untouched ---
summaries = list((memory_root / "summaries").rglob("*.md"))
if len(summaries) == 0:
    print("PASS: Summaries folder empty (untouched, as expected)")
else:
    errors.append(f"FAIL: Agent wrote to summaries/ ({len(summaries)} files)")
    print(f"FAIL: Agent wrote to summaries/")

# --- Check 8: All remaining memory files have valid frontmatter ---
import frontmatter as fm
broken = []
for md in remaining_decisions + remaining_learnings:
    try:
        post = fm.load(str(md))
        if not post.metadata or not post.metadata.get("id"):
            broken.append(f"{md.name}: missing id in frontmatter")
    except Exception as exc:
        broken.append(f"{md.name}: {exc}")
if broken:
    for b in broken:
        errors.append(f"FAIL: Broken frontmatter: {b}")
    print(f"FAIL: {len(broken)} files with broken frontmatter")
else:
    print(f"PASS: All {len(remaining_decisions) + len(remaining_learnings)} remaining memories have valid frontmatter")

# --- Summary ---
print("\n" + "=" * 50)
if errors:
    print(f"E2E RESULT: {len(errors)} issues found")
    for e in errors:
        print(f"  - {e}")
else:
    print("E2E RESULT: ALL CHECKS PASSED")
PYEOF
```

### 8.4 Print final memory diff

Show what the agent actually did — which files were merged, archived, or modified:

```bash
python3 << 'PYEOF'
import glob, json
from pathlib import Path

configs = sorted(glob.glob("/tmp/acreta-maintain-e2e-*/e2e_config.json"))
config = json.loads(Path(configs[-1]).read_text())
memory_root = Path(config["memory_root"])

print("=== REMAINING DECISIONS ===")
for f in sorted((memory_root / "decisions").glob("*.md")):
    print(f"  {f.name}")

print("\n=== REMAINING LEARNINGS ===")
for f in sorted((memory_root / "learnings").glob("*.md")):
    print(f"  {f.name}")

print("\n=== ARCHIVED DECISIONS ===")
for f in sorted((memory_root / "archived" / "decisions").glob("*.md")):
    print(f"  {f.name}")

print("\n=== ARCHIVED LEARNINGS ===")
for f in sorted((memory_root / "archived" / "learnings").glob("*.md")):
    print(f"  {f.name}")

# Show the maintain_actions report
result = json.loads((Path(config["tmp_dir"]) / "maintain_result.json").read_text())
actions_path = Path(result["artifacts"]["maintain_actions"])
if actions_path.exists():
    report = json.loads(actions_path.read_text())
    print("\n=== MAINTAIN ACTIONS REPORT ===")
    print(json.dumps(report, indent=2))
PYEOF
```

---

## Summary Template

After completing all phases, print a summary table:

```
| Phase | Check                        | Status |
|-------|------------------------------|--------|
| 0     | Fix broken tests             | ?      |
| 1.1   | Prompts package exists       | ?      |
| 1.2   | maintenance.py deleted       | ?      |
| 1.3   | No old names in source       | ?      |
| 1.4   | No old names in tests        | ?      |
| 1.5   | New methods exist            | ?      |
| 1.6   | Imports wired correctly      | ?      |
| 2     | Self-tests pass              | ?      |
| 3     | Unit tests pass              | ?      |
| 4.1   | File docstrings              | ?      |
| 4.2   | Function docstrings          | ?      |
| 4.3   | Triple-quoted strings        | ?      |
| 4.4   | Maintain prompt content      | ?      |
| 4.5   | Summaries exclusion          | ?      |
| 4.6   | Soft-delete pattern          | ?      |
| 5.1   | Agent construction           | ?      |
| 5.2   | Prompt builders              | ?      |
| 5.3   | CLI parser                   | ?      |
| 5.4   | Daemon signature             | ?      |
| 6     | No dead code / orphans       | ?      |
| 7     | Final full test run          | ?      |
| 8.1   | E2E: test memories created   | ?      |
| 8.2   | E2E: agent.maintain() ran    | ?      |
| 8.3   | E2E: results validated       | ?      |
| 8.4   | E2E: memory diff printed     | ?      |
```

Replace `?` with PASS or FAIL. For any FAIL, explain what's wrong and fix it.
