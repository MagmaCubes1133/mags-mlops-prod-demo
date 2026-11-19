#!/usr/bin/env bash
# Laptop: run one VM-side lab step through GitHub Actions (.github/workflows/lab.yml), stream its
# output, and report dispatch→done wall-clock time.
# Usage: scripts/remote.sh <lab> <step> [arg]        SYNC=false skips the VM git sync (faster)
# Needs: gh (authenticated). Same steps over SSH: bash scripts/lab.sh <lab> <step> [arg] on the VM.
set -euo pipefail
[ $# -ge 2 ] || { echo "usage: scripts/remote.sh <lab> <step> [arg]"; exit 2; }
R=${REPO:-MagmaCubes1133/mags-mlops-prod-demo}
t0=$(date +%s)
since=$(date -u -d "@$((t0 - 5))" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u +%Y-%m-%dT%H:%M:%SZ)

gh workflow run lab.yml --repo "$R" --ref "${REF:-main}" \
  -f lab="$1" -f step="$2" -f arg="${3:-}" -f sync="${SYNC:-true}" >/dev/null
id=""
for _ in $(seq 1 30); do
  id=$(gh run list --repo "$R" --workflow lab.yml --event workflow_dispatch --limit 5 --json databaseId,createdAt \
    --jq "[.[] | select(.createdAt >= \"$since\")] | last | .databaseId // empty")
  [ -n "$id" ] && break
  sleep 2
done
[ -n "$id" ] || { echo "could not find the dispatched run"; exit 1; }

rc=0
gh run watch "$id" --repo "$R" --exit-status --interval 3 >/dev/null 2>&1 || rc=$?
# print the "Run step" output (log lines are: job<TAB>step<TAB>timestamp text)
gh run view "$id" --repo "$R" --log 2>/dev/null | awk -F'\t' '$2 == "Run step" {sub(/^[^ ]+ /, "", $3); print $3}' \
  | grep -vE '^(source |set \+e|t=|cmd=|vm_exec|rc=|\{|echo|\}|dir=|\[\[|exit|##\[group\]|##\[endgroup\]|shell: |  [A-Z_]+: )' || true
echo "remote $* → $([ $rc = 0 ] && echo OK || echo "FAILED ($rc)") · dispatch→done $(( $(date +%s) - t0 ))s · run $id"
exit "$rc"
