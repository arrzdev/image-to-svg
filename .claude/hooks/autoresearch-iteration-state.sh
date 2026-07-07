#!/usr/bin/env bash
# Project-level autoresearch hook — surfaces / snapshots MID-ITERATION worktree
# state so a /clear'd, resumed, or compacted session picks up an in-flight
# worktree-parallel iteration (including "orchestrator was mid-merge across
# worktrees") instead of restarting it.
#
# Layers ON TOP of the plugin's own SessionStart/PreCompact hooks (which handle
# objective + run history). The plugin is left unmodified; this file lives in
# the repo so the behavior is project-scoped and travels with the repo.
#
# Registered in .claude/settings.json for BOTH SessionStart (startup|resume|
# compact|clear) and PreCompact. Dispatches on hook_event_name.
#
# State file: research/autoresearch.iteration.json (see autoresearch.md "Worktree-
# parallel iterations"). phase == "idle" (or file absent) => nothing in flight,
# stay silent.
set -uo pipefail

input=$(cat)
cwd=$(printf '%s' "$input" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("cwd",""))' 2>/dev/null)
event=$(printf '%s' "$input" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("hook_event_name",""))' 2>/dev/null)
[ -n "$cwd" ] && cd "$cwd" 2>/dev/null || true

# Only speak for a real, non-paused autoresearch session.
[ -f "research/autoresearch.md" ] || exit 0
[ -f ".autoresearch-off" ] && exit 0

STATE="research/autoresearch.iteration.json"

# Is there an active (non-idle) iteration to resume?
active=$(python3 - "$STATE" <<'PY' 2>/dev/null
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print(""); sys.exit()
print("yes" if d.get("phase", "idle") not in ("", "idle") else "")
PY
)

if [ "$event" = "PreCompact" ]; then
  # Durable snapshot before context is lost (mirrors the plugin's jsonl backup).
  if [ -f "$STATE" ] && [ -n "$active" ]; then
    mkdir -p research
    cp "$STATE" "research/autoresearch.iteration.json.precompact.bak"
    echo "[autoresearch] mid-iteration worktree state snapshotted before compaction."
  fi
  exit 0
fi

# SessionStart: inject the in-flight state as context so the resumed
# orchestrator continues the worktree/merge sequence.
[ -n "$active" ] || exit 0

echo "## ⚠ Autoresearch MID-ITERATION — resume the worktree-parallel cycle, do NOT restart it"
python3 - "$STATE" <<'PY' 2>/dev/null
import json, sys
d = json.load(open(sys.argv[1]))
na = d.get("next_action")
print(f"- **NEXT ACTION: {na}**" if na else
      "- WARNING next_action MISSING from iteration.json - schema violation; "
      "derive the step from the fields below, then fix the writer.")
print(f"- phase: **{d.get('phase')}** | iteration {d.get('iteration')} | "
      f"focus {d.get('focus')} | best {d.get('best_sha')}")
for c in d.get("candidates", []):
    print(f"- candidate `{c.get('id')}` [{c.get('domain')}] wt={c.get('worktree')} "
          f"effort={c.get('effort','?')} "
          f"| sub-agent said: {c.get('subagent_verdict','?')} "
          f"| ORCHESTRATOR verdict: {c.get('orchestrator_verdict','PENDING — re-verify yourself')}")
ig = d.get("integration") or {}
if ig.get("order"):          # a real multi-winner merge is in progress
    print(f"- integration (MID-MERGE): applying {ig.get('order')} in "
          f"wt={ig.get('worktree')}; applied={ig.get('applied')} "
          f"step={ig.get('step')} last_verified_ok={ig.get('last_verified_ok')}")
elif ig.get("single_winner"):
    print(f"- integration: single winner {ig.get('single_winner')} — "
          f"no combination; broaden it to all 8 targets, then ship.")
print("- Protocol: research/autoresearch.md → 'Worktree-parallel iterations'. Any "
      "candidate whose ORCHESTRATOR verdict is PENDING must be re-rendered and "
      "eye-judged by YOU (sub-agent self-report is a claim, not a result). If "
      "phase=integrating, continue the merge sequence from the recorded step, "
      "re-verifying after each apply.")
PY
echo "- On-disk worktrees still present (verify against this list):"
git worktree list 2>/dev/null | sed 's/^/    /'
echo ""
exit 0
