> **СТАТУС: SUPERSEDED / RESOLVED (v1.2 Phase 7).** Гипотеза про media-driver оказалась неверной; черновик подавать НЕ нужно.
>
> **Резолюция (закрыто, v1.2 Phase 7):** реальная первопричина - отсутствие синхронизации выхода MFX VPP перед подачей в энкодер при VA-памяти внутри самого qsvencc (а не iHD/ядро, как предполагалось ранее). Фикс - rigaya/QSVEnc `45003f1` (issue #308; параллельный патч #316 соавторен пользователем). Принята сборка r4634 через зеркало Release `deps-qsvencc-r4634` (проверка sha256). Замок регрессии - `tests/integration/test_concurrency_immunity.py::test_qsvencc_immune_at_production_jobs`; рантайм-гейт - `enpipe.shared.qsvencc_version` (r4634). Подробности: [`scene-chunk-frame-mismatch.md`](./scene-chunk-frame-mismatch.md), раздел «ФАЗА 7».

# Upstream bug report — draft (CORRECTED after CI build + hardware test)

Status: the original draft proposed a one-line P010 `rt_format` fix. **We built and tested it — it is INERT** (see "Update" below). This draft is reframed accordingly. The corruption is a **cross-process 10-bit reference-surface aliasing** issue whose likely home is intel/media-driver (iHD), with a possible contributing factor in QSVEnc's surface-pool structure. File thoughtfully; lead with the media-driver angle.

## Update / what we verified (do not skip)
- Built qsvencc 8.22 + the P010 `rt_format` patch (`format = VA_RT_FORMAT_YUV420_10` in `AllocImpl` and `ReallocImpl`) via CI. Binary confirmed patched (`r4386`).
- 3-way concurrency test on Arc A380: **stock 5/15 corrupt (control valid); patched 22/45 corrupt — no change**, identical signature (offset 299, ~15.7 dB foreign content), full HW speed.
- Root cause of the patch's failure: `vaCreateSurfaces` is called with an explicit `VASurfaceAttribPixelFormat = VA_FOURCC_P010` attribute (`qsv_allocator_va.cpp` ~L309-312). iHD honors that attribute and creates correct P010 surfaces regardless of the rt_format argument — so the rt_format value is inert. It is still technically wrong (a cosmetic latent defect worth cleaning up) but it is **not** the corruption fix.

---

**Title (media-driver):** Cross-process frame corruption: concurrent 10-bit AV1 encodes with B-frame reorder on Arc alias reference surfaces between independent processes (iHD 25.2.3 / DG2)

### Environment
- Intel Arc A380 (Alchemist/DG2), iHD 25.2.3, libmfx-gen (vpl-gpu-rt) 25.1.4, libvpl 2.14.0, libva 2.22.0, kernel 6.19, oneVPL runtime.

### Symptom
Multiple **independent processes** encoding H.264→AV1 concurrently on one Arc GPU: ~35–65% of runs produce **one frame whose pixel content comes from a different concurrent process** (a whole different scene). Frame count stays correct → silent. In isolation, 100% clean and bit-identical.

Trigger requires **all three simultaneously** (breaking any one → 0%):
1. hardware VA decode into VA video-memory surfaces,
2. 10-bit P010 surfaces (`--output-depth 10` / encode profile main-10),
3. B-frame reorder (`GopRefDist > 1`, B-pyramid).

The corrupt frame is **deterministic** — always the same reordered-reference position within the chunk — and carries foreign cross-process content, pointing at **aliasing of the P010 reference surface across process/VA boundaries** rather than an encode-parameter fault.

### Key evidence isolating the layer
- **ffmpeg `av1_qsv`** (same oneVPL/iHD runtime, same GPU) with the **verified-identical combo** (HW `h264_qsv` decode + 10-bit P010 via `vpp_qsv=format=p010le` + `GopRefDist:6 BRefType:pyramid`) is **35/35 clean** under the same 3-way/5-way concurrency. So the driver *can* do this correctly — the trigger depends on the client's surface-pool management.
- **QSVEnc** (Rigaya) with the same combo corrupts ~35–65%. Difference vs ffmpeg: QSVEnc uses a single producer-owned VA pool OR-combined `FROM_DECODE|FROM_VPPIN|FROM_ENCODE`, sized from summed `QueryIOSurf` counts, growing with `GopRefDist`; ffmpeg uses per-component `AVHWFramesContext` pools with distinct `AllocId`s and explicit handoff. (Files: `QSVPipeline/qsv_pipeline.cpp:1708-1822,1773`; `qsv_allocator_va.cpp`.)
- The rt_format patch (above) is inert, confirming the fault is not the surface *format request* but the **cross-process isolation of the 10-bit reference surface memory** (BO/GEM handle reuse under concurrent submission).

### Ask
- **intel/media-driver:** is there a known cross-process isolation issue for P010 (10-bit) video surfaces used as encode references under concurrent multi-process submission on DG2? Any surface memory-type/tiling/BO-handle scoping that can collide across independent VADisplays/processes?
- **rigaya/QSVEnc (secondary):** would giving the P010 VPP-output/reference pool a dedicated `AllocId`/pool (closer to ffmpeg's per-component contexts) avoid triggering the driver issue? (Hypothesis; not yet tested.)

### Repro sketch
Run 3 independent `qsvencc --avhw --va -c av1 --output-depth 10 --gop-ref-dist 6 --b-pyramid ...` processes on distinct segments of one H.264 source, concurrently, on one Arc device; decode each output and per-frame-PSNR against an isolated-encode reference; ~1 frame/chunk shows foreign content at a reorder-reference offset in ~1/3+ of runs.

---

## enpipe-side disposition (this project)
Per user decision 2026-07-22: document + upstream, no enpipe code change. Working workarounds (each sacrifices one wanted property): `--avsw` (SW decode, ~2.5× slower decode; keeps 10-bit+B-frames+DV/HDR), `--output-depth 8` (loses 10-bit/HDR), `--gop-ref-dist 1` (loses B-frame efficiency, +29% size), or migrate the encoder to ffmpeg `av1_qsv` (clean + full speed, but DV-RPU/HDR10+ passthrough must be validated). Full analysis: debug session `scene-chunk-frame-mismatch.md`, memory `qsv-concurrent-encode-corruption`. Fork branch `Tualua/QSVEnc@p010-fix` holds the (inert) rt_format patch — safe to delete.
