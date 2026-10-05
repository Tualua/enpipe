# Phase 7: Adopt Fixed qsvencc + Concurrency Regression Lock - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-02
**Phase:** 07-adopt-fixed-qsvencc-concurrency-regression-lock
**Areas discussed:** qsvencc build in images, version gate (QSV-02), regression test (COR-02), upstream VA-API backend

---

## qsvencc build in images

| Option | Description | Selected |
|--------|-------------|----------|
| Source build, pinned SHA | builder stage, git clone + checkout | |
| Upstream CI artifact .deb | prebuilt from upstream Actions | |
| Manual host build | user-built .deb | |

**User's choice:** Other — "use the builds linked in https://github.com/rigaya/QSVEnc/issues/308#issuecomment-5941969693". Verified: run 36932190976, head 45003f1, deb sha256 aa10f196…743d, `8.31 (r4634)`, artifact expires 2026-10-15.

| Pin | Selected |
|-----|----------|
| Exactly 45003f1 | ✓ |
| Floating master HEAD | |

| Images | Selected |
|--------|----------|
| Both devcontainer + runtime/GHCR | ✓ |
| devcontainer only | |

| Release switch | Selected |
|----------------|----------|
| Manual, separate quick task | ✓ |
| Auto fallback in Dockerfile | |

| Artifact expiry handling | Selected |
|--------------------------|----------|
| Mirror to GitHub Release of our repo + sha256 pin | ✓ |
| nightly.link + source-build fallback | |
| nightly.link only | |
| Commit .deb to repo | |

## Version gate (QSV-02)

| Question | Options | Selected |
|----------|---------|----------|
| Criterion | rev ≥ 4634 / rev OR version ≥ 8.32 | rev ≥ 4634 |
| Unparseable | fail closed / warn | fail closed |
| Bypass | none / allow at JOBS=1 / env flag | none |
| Location | run_encode + run_pipeline preflight / run_encode only | both, before detection |

## Regression test (COR-02)

| Question | Options | Selected |
|----------|---------|----------|
| Test shape | invert in place, keep ffmpeg test / new file | invert in place |
| Command | production chunk_command / harness / both | production chunk_command |
| Non-vacuity | one-time r4604 from scratch / permanent negative control / rely on Phase 6 | one-time r4604 |
| Intensity | as Phase 6 (3×8 committed; 3/5/8×≥20 once) / parametrize | as Phase 6 |

## Upstream VA-API backend

| Question | Options | Selected |
|----------|---------|----------|
| Pin backend | `--backend qsv` in chunk_command / rely on auto | `--backend qsv` |
| Non-concurrency check | hardware tier + determinism / + quality vs r4604 | hardware tier + determinism |

**Notes:** User asked for the source of the "VA-API incompatible with --avhw" claim. Source: upstream `QSVEncC_Options.en.md` §`--backend` @45003f1 ("VA-API does not support `--avhw` …"). The claim that this yields a hard error (vs warning) was an inference, not documented — marked UNVERIFIED in CONTEXT D-12.

## Deferred Ideas
- Upstream release switch (quick task), permanent negative control, quality comparison vs r4604, ffmpeg backend (999.1).
