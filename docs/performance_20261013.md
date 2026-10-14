# Study delivery performance: evidence and reproduction

Status: full tests and the ordinary fresh-run comparison passed. Completed reuse,
interrupted recovery and Git delivery are being finished using the same inputs.

## Measured input and starting evidence

The workload is the first twelve 870 C merged frames (0004–0015) from the public
APS VTMA thermo-mechanical scan distributed by SasView. It contains 4,255 points.
The 30 C baseline and the raw/merged duplicates are excluded. This is measured
data; the repository's prior sphere-model smoke inputs are separate engineering
fixtures. The previously referenced Ti15 measurement path is unavailable.

- [Official data description](https://www.sasview.org/docs/user/example_data/testdata_help.html)
- [Pinned upstream source](https://github.com/SasView/sasdata/blob/066ef088eda50056f327727e825dbb3285409097/sasdata/example_data/1d_data/VTMA.h5)
- HDF5 SHA-256: `65e9e45e71f063c4da775c3854314b4a9ad4753ed4b30faf93ecd39e8c29b86a`.
- Original HDF5 remains intact. CSV extraction preserves Q/I/Idev/Qdev separately
  using 17 significant digits, with binary64 round-trip checks. Q/Qdev are in
  A^-1, I/Idev in cm^-1; frame time and temperature remain explicit metadata.
- Analysis: unknown sample type, shape models off, same-method fallback on,
  sequence axis time_s, range sensitivity on; no guessed Dmax or resolution model.
- Full delivery: PNG/SVG/PDF at 200 dpi, 24 curves per overview page, all data,
  diagnostics, source copies, manifests, indices and both ZIP bundles.
- Starting code: `17a09c9`. Windows/Python 3.12.10, NumPy 2.1.2, SciPy 1.18.0,
  pandas 2.2.3, Matplotlib 3.11.1, sequential analyses, BLAS/OpenMP threads capped
  at one. Inputs and output roots are disjoint.

The starting profiled process completed in 58.0508 seconds, with status
`completed_with_limitations`, zero failed inputs and 196 package artifacts.
Profiling changes runtime and is excluded from formal speedup evidence.

| Traced operation | Starting profile evidence | Change |
| --- | --- | --- |
| Automatic region detection | 24 scans, 20.526 cumulative instrumented s; 12 fallback rescans, 10.081 s | Share one detection per unchanged curve/q boundary within the run |
| Figure rendering/serialization | Collection drawing alone: 1,008 calls, 4.769 instrumented s; all required backends retained | Remaining necessary work; no output reduction |
| Overview source preparation | 96 preparations, 2.545 instrumented s; per-point pandas row construction | Reuse the existing row-index column as an array |
| Manifest/output hashing | 0.251/0.173 instrumented s | Retain required integrity boundaries |

Profile cumulative times overlap and are not summed into a total wall time.

## Ordinary first run: measured complete delivery

Each side starts with a new output directory and an empty job cache. The paired
ordinary processes ran serially on 2026-10-13, at 10:30:31 and 10:33:14 UTC,
after the coordinated heavy tasks finished. The 58.0508 s profile is excluded.

| Same twelve-frame workload | Before | After | Result |
| --- | ---: | ---: | --- |
| CLI startup through final publication, s | 20.839185 | 15.915090 | 1.3094x; 23.63% less time |
| Independent complete inventory/ZIP verification, s | 0.500616 | 0.637963 | Retained on both sides |
| Delivery plus independent verification, s | 21.339802 | 16.553054 | **1.2892x; 22.43% less time** |
| Sampled process CPU, s | 18.1719 | 14.5781 | 19.78% less CPU time |
| Sampled peak process-tree RSS, MiB | 259.242 | 244.832 | 5.56% lower |
| Sampled logical read bytes | 2,509,493,265 | 2,509,960,113 | Essentially unchanged |
| Sampled logical write bytes | 86,302,515 | 86,302,890 | Essentially unchanged |

The host has 16 physical/32 logical CPUs and 65,905,455,104 bytes of RAM.
Both runs use one analysis process and the same five BLAS/OpenMP environment
caps of one. Native ancillary threads peaked at seven/eight; these are not
additional analysis workers. Resource sampling is every 0.1 s and can miss the
last interval or very short-lived processes. Logical I/O is not physical disk
traffic. The external equivalence comparison is a separate one-time experiment;
its cost is not part of normal study delivery or the claimed speedup.

This is one paired observation, with uncontrolled OS file/font caches. It proves
the measured representative workload, without estimating statistical variability
or a cold-OS-cache advantage. The full output scope and binary64 precision are
identical. Each result has 196 package artifacts and 207 verified ZIP members.
The comparison checks 137 CSVs, eight JSON files, 15 exact-pixel PNGs and 30 SVG/PDF
artifacts. All scientific values, errors, missing positions, units, applicability
gates, source/frame metadata, indices and figure content agree. Numeric table
comparison is exact; no numerical tolerance was relaxed. SVG/PDF bytes differ
because of generated IDs/document metadata; XML structure and PDF
geometry/text/drawings/200-dpi pixels agree. ZIP members match their own published
files byte for byte, including source copies; random IDs and metadata prevent a
claim of byte-identical archives across independent runs.

The sole study-snapshot schema difference is the new exact runtime dependency
record. The comparison explicitly binds both original timing receipts to their
output directories and fingerprints and verifies identical versions before
accepting this addition. Generated curve UUIDs are bound to source identity;
unordered consensus-support sets are compared after that mapping. Acquisition
metadata, per-curve support counts and related-analysis links remain checked.

Evidence remains outside Git in
`E:/Vibe_coding/_artifacts/SasCurve_Analyzer/performance-20261012`: `before.json`,
`after.json`, `comparison-accepted.json`, `full-tests.log`,
`full-tests.receipt.json` and `accepted-source-provenance.json`. The last record
binds the tested/measured production files to SHA-256 and the preserved shutdown
snapshot. Full tests and optimized timing share dirty-diff digest
`8a09fe33cde6f9bc41b7b43fa4b34f3c13bea643232c7ffb847a68fa8ab68887`.
Subsequent comparator-only repairs do not change production computation.

## Correctness and reliability checks

The selector's full suite passed **738 tests in 77.72 s** (82.22 s including its
wrapper), Windows/Python 3.12 with Qt offscreen and numerical threads capped at
one. Seven warnings comprise three existing SciPy peak-property warnings and
four missing CJK glyph warnings in an unthemed test fixture. After repairs to
generated-identity comparison, its **12 focused tests passed in 2.26 s**. The
production code has not changed since the full run; that evidence is reused.

Tests cover changed curve content/q bounds, failed-scan sharing, dependency
invalidation before writes, same-output process contention, simultaneous first
creation, independent output locks, lock release after abrupt process exit and
index-publication failure followed by repair using the valid package. The source
and cross-run/publication hash checks remain in place. No scientific window,
model, reporting gate, precision or export is reduced.

## Reproduction

Run each timed job separately on the same host/runtime, with no competing test or
analysis workload. Fresh before/after outputs must be new directories with empty
compute caches. Do not compare a profiled process with an ordinary process.

```powershell
py -3.12 scripts/prepare_vtma_benchmark.py --output-root E:/benchmarks/vtma

py -3.12 scripts/benchmark_study_delivery.py --repo <baseline-checkout> `
  --input E:/benchmarks/vtma/inputs --config E:/benchmarks/vtma/config.json `
  --output E:/benchmarks/vtma/before --receipt E:/benchmarks/vtma/before.json

py -3.12 scripts/benchmark_study_delivery.py --repo <optimized-checkout> `
  --input E:/benchmarks/vtma/inputs --config E:/benchmarks/vtma/config.json `
  --output E:/benchmarks/vtma/after --receipt E:/benchmarks/vtma/after.json

py -3.12 scripts/benchmark_study_delivery.py --compare `
  E:/benchmarks/vtma/before E:/benchmarks/vtma/after `
  --before-receipt E:/benchmarks/vtma/before.json `
  --after-receipt E:/benchmarks/vtma/after.json `
  --receipt E:/benchmarks/vtma/comparison.json

py -3.12 scripts/benchmark_study_delivery.py --repo <optimized-checkout> `
  --input E:/benchmarks/vtma/inputs --config E:/benchmarks/vtma/config.json `
  --output E:/benchmarks/vtma/after --resume `
  --receipt E:/benchmarks/vtma/resume.json
```

Preparation needs h5py/NumPy; timing/resource sampling needs psutil; image checks
need Pillow, and PDF geometry/text/drawing/pixel checks need PyMuPDF. SVG checks
compare XML vector structure after generated-ID and RDF metadata normalization.
These are optional benchmark dependencies. The application keeps
its existing runtime dependency set. The original input download is outside the
timed analysis interval because the CLI consumes already reduced 1D curves.

```powershell
py -3.12 -m pip install h5py psutil PyMuPDF
```

Pillow is installed with Matplotlib. Resource receipts record these optional
preparation/verification dependency versions as well as the application versions.

Receipts identify Git HEAD/dirty content, commands, input/config snapshots,
dependencies, process CPU, sampled RSS and logical process I/O. Process I/O
counters are not physical disk throughput. CLI process timing includes startup,
analysis, required validation, files, ZIPs and final publication; independent
full output verification is also reported separately and in the combined total.
Completed resume and interrupted recovery are reported separately from fresh
work; their shorter time is never described as fresh computation speedup.

## Remaining scope and limits

Completed-result reuse and paired interruption/recovery measurements remain to
be recorded before Git delivery. Existing process tests already cover concurrent
writers; repeating the full suite adds no evidence for unchanged code.

The remaining necessary costs are per-curve region scans, numerical analyses and
multi-format figure layout/rendering/serialization. Profile timings identify
these candidates but are not ordinary wall-clock stage measurements. There is
no evidence that more workers, a persistent scan cache or weaker hashing would
improve total delivery on this workload. Any such future change needs its own
same-resource end-to-end measurement and bounded memory/I/O policy.

Ti15 input is unavailable. Larger campaigns, cold OS caches, network-filesystem
locks, other Python/dependency combinations and scientific model acceptance are
unverified. Qdev is preserved without introducing resolution smearing. Existing
`completed_with_limitations` and exploratory gates remain visible; a successful
software delivery does not resolve those scientific limitations.
