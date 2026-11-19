# Lab actions: every VM-side step, two ways, measured

One entrypoint: `scripts/lab.sh <lab> <step> [arg]` on the VM.
- **SSH:** `ssh -i ~/.ssh/mags_jl ubuntu@<vm> 'bash mags-mlops-prod-demo/scripts/lab.sh <lab> <step> [arg]'`
- **gh:** `scripts/remote.sh <lab> <step> [arg]` (= `gh workflow run lab.yml -f lab=… -f step=… -f arg=…` + `gh run watch`)

Latency = wall-clock from `gh workflow run` to run completion, measured with `scripts/remote.sh` on L4 (`sync=true` unless noted). "Step" = time inside `lab.sh` (from the job summary). **Live** = fine to trigger on stage (≲ 60 s); **backstage** = start it before the segment.

| Lab · step | What it does | gh latency | step time | Use |
|---|---|---|---|---|
| _(filled in during Phase B)_ | | | | |
