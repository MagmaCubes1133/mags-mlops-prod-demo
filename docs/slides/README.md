# Slides — From model weights to production endpoints

**Deck:** [`From-Model-Weights-to-Production-Endpoints_Saumya-Saraswat.pptx`](From-Model-Weights-to-Production-Endpoints_Saumya-Saraswat.pptx), 55 slides (54 shown + hidden BK-01).
**Speaker:** Saumya Saraswat. ISTE STTP @ K. J. Somaiya, Thu 3 Dec 2026, 2:00–5:15 PM IST.
Presenters: see [`../demo-day.md`](../demo-day.md) for the run sheet.

## Diagrams → slides

| Diagram | Slide |
|---|---|
| [d13](diagrams/d13_artifact_lineage.png) artifact lineage | S3-04 |
| [d01](diagrams/d01_gantt_naive_vs_continuous.png) naive vs continuous (Gantt) | S3-06 |
| [d02](diagrams/d02_roofline_l4.png) L4 roofline | S3-07 |
| [d03](diagrams/d03_static_vs_continuous_batching.png) static vs continuous batching | S3-09 |
| [d14](diagrams/d14_chunked_prefill.png) chunked prefill | S3-09a |
| [d15](diagrams/d15_batch_isolation.png) why requests don't mix | S3-09b |
| [d04](diagrams/d04_contiguous_vs_paged_kv.png) contiguous vs paged KV | S3-10 |
| [d05](diagrams/d05_driver_container_layers.png) driver / container layers | S3-11 |
| [d06](diagrams/d06_edge_architecture.png) edge architecture | S3-17 |
| [d07](diagrams/d07_history_resend_prefix_cache.png) history resend + prefix cache | S3-20a |
| [d08](diagrams/d08_storage_tiers_scale_ladder.png) storage tiers / scale ladder | S3-20b |
| [d09](diagrams/d09_vram_budget_bar.png) VRAM budget bar | S4-02 |
| [d10](diagrams/d10_kv_capacity_l4.png) KV capacity on L4 | S4-04 |
| [d11](diagrams/d11_multilora_serving.png) multi-LoRA serving | S4-12 |
| [d12](diagrams/d12_alias_repoint_rollback.png) alias repoint / rollback | S4-13 |

## Provenance

Numbers trace to [`docs/benchmarks.md`](../benchmarks.md) (`docs/slide-numbers.md` at `5016f02`) and [`results/*.csv`](../../results/).
Not measured: S3-20b's CPU/NVMe/remote rows (labelled estimates on the slide) and d14's step widths (labelled illustrative).
