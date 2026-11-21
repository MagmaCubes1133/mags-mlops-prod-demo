# Sourced by lab.yml (engine). Prints the step header into the live log and writes the run-page summary:
# status, the repo scripts the step ran (linked at this commit), how to run it yourself, highlights,
# markdown tables the scripts printed, and the full raw log. Never prints secrets or IPs (callers redact).
# Needs: LAB, STEP_IN; GITHUB_* from Actions.

step_scripts() { # repo files for $LAB + first word of $STEP_IN, from .github/lab-steps.tsv
  awk -F'\t' -v l="$LAB" -v s="${STEP_IN%% *}" '$1 == l && $2 == s {print $3}' .github/lab-steps.tsv
}

# report_header <where> <command>: first lines of the live log
report_header() {
  echo ">>> $LAB $STEP_IN"   # remote.sh prints what is between >>> and <<<
  echo "scripts : $(step_scripts)"
  echo "where   : $1"
  echo "command : $2"
  echo "yourself: scripts/remote.sh $LAB $STEP_IN   (laptop, via Actions)"
  echo "----------------------------------------------------------------"
}

# report_summary <rc> <seconds> <out-file> <where> <command>
report_summary() {
  local rc=$1 secs=$2 out=$3 where=$4 cmd=$5 f n links="" icon
  for f in $(step_scripts); do
    links+="[\`$f\`](${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/blob/${GITHUB_SHA}/$f) "
  done
  if [ "$rc" = 0 ]; then icon="✅ passed"; else icon="❌ failed (exit $rc)"; fi
  n=$(wc -l < "$out")
  {
    echo "## $LAB · \`$STEP_IN\` — $icon in ${secs}s"
    echo
    echo "| | |"
    echo "|---|---|"
    echo "| **Scripts** | $links|"
    echo "| **Where** | $where |"
    echo "| **Command** | \`$cmd\` |"
    echo "| **Run it yourself** | \`scripts/remote.sh $LAB $STEP_IN\` · or this lab's button in Actions |"
    echo
    echo "### Highlights"
    grep -E 'PASS|FAIL|SKIP|HEALTHY|VERIFIED|WRONG PROFILE|RESULT|TOTAL|non-2xx|stream complete|CUT OFF|hit|GiB|KV cache|[Mm]aximum concurrency|backend|kernel|drain|active profile|/health|ERROR|SMOKE|peak|preempt|sql-prod ->|-> /adapters|caddy:|valid|reload' "$out" \
      | grep -v '^|' | head -30 | sed -e 's/`/'"'"'/g' -e 's/^/- `/' -e 's/$/`/' || true
    grep -q '^|.*|$' "$out" && { echo; echo "### Tables"; echo; grep '^|.*|$' "$out"; }
    echo
    echo "### Output ($n lines$( [ "$n" -gt 800 ] && echo "; last 800 shown, full log in the run's log-… artifact"))"
    echo
    echo '```text'
    # shellcheck disable=SC2016  # literal backticks
    tail -n 800 "$out" | sed 's/```/` ` `/g'
    echo '```'
  } >> "$GITHUB_STEP_SUMMARY"
  echo "ART_NAME=$(printf '%s' "$LAB-$STEP_IN" | tr -c 'A-Za-z0-9._-' '-')-$(date +%s%N | cut -c1-13)" >> "$GITHUB_ENV"
}
