#!/usr/bin/env bash
# Laptop: run one lab step through GitHub Actions (the <lab>.yml button; engine lab.yml), stream its
# output, and report dispatch→done wall-clock time. Step names match the Actions dropdowns.
# Usage: scripts/remote.sh <lab> <step> [arg]     e.g. lab4 switch awq · lab2 client-smoke · common logs vllm
#        SYNC=false skips the VM git sync (faster). LABEL=… (lab4) / DURATION=… (lab5) for client steps.
# Needs: gh (authenticated). VM steps over SSH instead: bash scripts/lab.sh <lab> <step> [arg] on the VM.
set -euo pipefail
[ $# -ge 2 ] || { echo "usage: scripts/remote.sh <lab> <step> [arg]"; exit 2; }
R=${REPO:-MagmaCubes1133/mags-mlops-prod-demo}
W="$1.yml"
t0=$(date +%s)
since=$(date -u -d "@$((t0 - 5))" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u +%Y-%m-%dT%H:%M:%SZ)

extra=()
[ "$1" = lab4 ] && extra=(-f label="${LABEL:-run}")
[ "$1" = lab5 ] && extra=(-f duration="${DURATION:-180}")
gh workflow run "$W" --repo "$R" --ref "${REF:-main}" \
  -f step="$2${3:+ $3}" -f sync="${SYNC:-true}" "${extra[@]}" >/dev/null
id=""
for _ in $(seq 1 30); do
  id=$(gh run list --repo "$R" --workflow "$W" --event workflow_dispatch --limit 5 --json databaseId,createdAt \
    --jq "[.[] | select(.createdAt >= \"$since\")] | last | .databaseId // empty")
  [ -n "$id" ] && break
  sleep 2
done
[ -n "$id" ] || { echo "could not find the dispatched run"; exit 1; }

rc=0
gh run watch "$id" --repo "$R" --exit-status --interval 3 >/dev/null 2>&1 || rc=$?
# print the step output between the engine's ">>> " and "<<< exit" markers (log lines: job<TAB>step<TAB>timestamp text)
gh run view "$id" --repo "$R" --log 2>/dev/null | cut -f3- | sed -E 's/^[^ ]+ //; s/\[[0-9;]*m//g'   | awk '/^>>> / {on = 1; next} /^<<< exit/ {on = 0} on' || true
echo "remote $* → $([ $rc = 0 ] && echo OK || echo "FAILED ($rc)") · dispatch→done $(( $(date +%s) - t0 ))s · run $id"
exit "$rc"
