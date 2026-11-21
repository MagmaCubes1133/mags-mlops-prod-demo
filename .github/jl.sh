# Sourced by .github/workflows/demo-gpu.yml. Public repo: mask ids/IPs BEFORE anything can print them
# (`jl exec` itself prints "Executing on <machine_id>").

# vm_find: sets VM_ID, VM_GPU, VM_STATUS (empty when no VM). Prefers $MACHINE_ID if it still exists,
# otherwise looks the VM up by name ($VM_NAME). Also exports them to $GITHUB_ENV for later steps.
vm_find() {
  local row
  row=$(jl list --json | jq -c --arg n "$VM_NAME" --arg id "${MACHINE_ID:-}" '
    ([.[] | select($id != "" and (.machine_id | tostring) == $id)] + [.[] | select(.name == $n)]) | first // empty')
  VM_ID=$(jq -r '.machine_id // empty' <<<"$row")
  VM_GPU=$(jq -r '.gpu_type // empty' <<<"$row")
  VM_STATUS=$(jq -r '.status // empty' <<<"$row")
  if [ -n "$VM_ID" ]; then
    echo "::add-mask::$VM_ID"
    jq -r '[.public_ip, .private_ip, (.ssh_command // "" | split("@")[1] // empty)] | .[] | select(. != null and . != "")' <<<"$row" \
      | while read -r v; do echo "::add-mask::$v"; done
  fi
  { echo "VM_ID=$VM_ID"; echo "VM_GPU=$VM_GPU"; echo "VM_STATUS=$VM_STATUS"; } >>"${GITHUB_ENV:-/dev/null}"
  echo "VM: ${VM_ID:+found} ${VM_ID:-none} gpu=${VM_GPU:-?} status=${VM_STATUS:-?}"
}

# vm_exec '<shell>': run on the VM (exit code propagates). Never pass secrets on the command line.
vm_exec() { jl exec "$VM_ID" -- bash -lc "$1"; }

# vm_sync: VM checkout := exactly $GITHUB_SHA (detached; works from any branch or detached HEAD).
# Any failure (fetch, checkout over local edits, HEAD mismatch) exits non-zero -> the step goes red.
vm_sync() {
  vm_exec "set -euo pipefail
    [ -d $REPO_DIR/.git ] || git clone -q https://github.com/$GITHUB_REPOSITORY $REPO_DIR
    cd $REPO_DIR
    git fetch -q origin $GITHUB_SHA
    git checkout -q --detach $GITHUB_SHA
    [ \"\$(git rev-parse HEAD)\" = $GITHUB_SHA ] || { echo 'sync: HEAD is not $GITHUB_SHA'; exit 1; }
    echo \"synced: \$(git log --oneline -1)\""
}

# vm_wait_ssh: up to 5 min for sshd after create/resume
vm_wait_ssh() {
  for _ in $(seq 1 30); do vm_exec true >/dev/null 2>&1 && return 0; sleep 10; done
  echo "SSH not ready after 300s"; return 1
}
