# Verified public delivery

## Current verified delivery: v0.3.1

Patch PR #11 fixed stale demo labels and incomplete screenshot captures. The viewer derives its label from package metadata; the public counter uses a checksum-bound release record and displays its release. Tampered paths/hashes and invalid Boolean counts are tested. The current public page shows **148 tests (v0.3.1)**; fresh screenshots were checked after rendering settled and scrolling reached the hero.

Release source: `394f42c2674d1d2135adaf0606f9fc789fef967c`. Hosted PR/main/tag checks passed. The anonymously downloaded image passed **148 tests in 61.93 seconds**, all 37 offline cases passed their gate (29/30 ordinary scripted matches; no regressions/incompatibilities), and installed-source/resource/budget probes passed. Public desktop/mobile controls and the local 0.3.1 viewer regression button passed. Image: `ghcr.io/jill-vekariya/agent-reliability-harness:0.3.1@sha256:4254993a830a5b827300f5c415fcbad4a1aaa4176c0a08130ff55cf02b8004da`.

Evidence, commands, probes, browser checks, screenshots, and checksums are in `reports/releases/0.3.1/`. The [publication receipt](../reports/releases/0.3.1-receipt.json) records actual uploaded asset identities/digests. Earlier release/audit evidence is retained with its original version and scope. Human reviews, genuine held-out tasks, real model attempts, and paid API spend remain zero.

Current hosted evidence: [patch PR](https://github.com/Jill-Vekariya/agent-reliability-harness/actions/runs/39152580419), [patch main/Pages](https://github.com/Jill-Vekariya/agent-reliability-harness/actions/runs/39152751839), [patch tag/container](https://github.com/Jill-Vekariya/agent-reliability-harness/actions/runs/39152759313), and [public evidence deployment](https://github.com/Jill-Vekariya/agent-reliability-harness/actions/runs/39153456023). The tagged source selects 0.3.1; verified main pins its actual digest.

## Historical delivery: v0.3.0

The audit is now published through merged PR #9. Hosted PR, main/Pages, and tag/container workflows succeeded at release revision `2e0d20e36a5c507f951d2de1b63cab62d7e6007f`. The actual GHCR image passed 145 tests in 67.64 seconds, the 37-case offline gate (29/30 ordinary scripted matches), an anonymous inspection/pull, installed-source/checksum checks, and the documented non-root/read-only/network/resource probes. SPDX SBOM and SLSA provenance predicates are present.

Current image: `ghcr.io/jill-vekariya/agent-reliability-harness:0.3.0@sha256:15b7c4c6ea5c73cdb38eab5a06c3aa82d8bb13e3dfb3ae86bceafcfb7bf15e5d`. The Windows launcher passed 145 tests in 59.16 seconds and the fixed regression. Public/mobile and local regression-button browser checks passed; the local viewer now runs the pinned 0.3.0 image at http://localhost:8501. Follow-up PR #10 and main run 39150428931 verified the Ubuntu 24.04 and Node 24 checkout/Pages maintenance.

See `reports/releases/0.3.0/verification.json`, companion command outputs/screenshots, and `SHA256SUMS`. Pre-release audit evidence below keeps its original revision and source hash; package version metadata changed for 0.3.0 and is separately verified in the published-image probe. Human review, genuine held-out tasks, live model calls, and paid spend remain zero.

The current hosted runs are [release PR](https://github.com/Jill-Vekariya/agent-reliability-harness/actions/runs/39149568475), [release main/Pages](https://github.com/Jill-Vekariya/agent-reliability-harness/actions/runs/39149726886), [tag/container](https://github.com/Jill-Vekariya/agent-reliability-harness/actions/runs/39149733068), and [CI maintenance main/Pages](https://github.com/Jill-Vekariya/agent-reliability-harness/actions/runs/39150428931). The tagged source selects version 0.3.0; verified main pins its immutable digest after publication.

Release ID **416605780** includes 12 assets. The verification asset is **654096041** (SHA-256 `cec159e41ba6206c2c7e784e6619da0e7e6ae0b8c5070c01821affaef606a77c`); SHA256SUMS is asset **654096023**. Every uploaded asset digest was compared with its local bytes. See the [publication receipt](../reports/releases/0.3.0-receipt.json) for all IDs, URLs, sizes, and digests.

## Historical 0.2.x delivery

The 0.2.1 packaging patch removes a stale image name from the Windows test launcher. Its actual publication, verification, and immutable image digest are recorded in the [patch release](https://github.com/Jill-Vekariya/agent-reliability-harness/releases/tag/v0.2.1). The 0.2.0 evidence below is retained as historical evidence of the first public delivery.

Read-only audit checks on 2026-10-18 reconfirmed v0.2.1 at `d3eb1e002afe99638df1cce60bda76a25148c7fa`: [main run 39129538947](https://github.com/Jill-Vekariya/agent-reliability-harness/actions/runs/39129538947) and [tag run 39129542108](https://github.com/Jill-Vekariya/agent-reliability-harness/actions/runs/39129542108) succeeded. The tag verify/container jobs succeeded; Pages was correctly skipped for the tag. The public walkthrough returned HTTP 200, and the existing released Docker viewer remained healthy. `reports/audit-external.json` records these reads; they do not validate the unpublished audit branch.

Release ID **416455012** contains `release-evidence.json` (asset **653509752**, SHA-256 `71aaf3195c52285ebe0dff809c63f8e97c6815a835e5c83659b78c615abf8ed8`) and `verification.json` (asset **653509751**, SHA-256 `7f9292ee60115cd0708fda71ded16e40217d1b42cb50f6ba2254d8197e0f7e75`). The v0.2.1 index is `sha256:f9eb1a7412e5830fea9ec46c88f33de2410f4953f4ba1bf3bfe88858cda835f8`; the audit's `compose.release.yaml` pins it explicitly. The local `audit-local` Docker image is separate and has not been pushed.

* Repository: https://github.com/Jill-Vekariya/agent-reliability-harness
* Static browser walkthrough: https://jill-vekariya.github.io/agent-reliability-harness/
* First public source/Pages workflow: https://github.com/Jill-Vekariya/agent-reliability-harness/actions/runs/39127910554 — successful verification and Pages deployment.
* Versioned container workflow: https://github.com/Jill-Vekariya/agent-reliability-harness/actions/runs/39128143092 — successful verification and container publication.

The 0.2.0 image was built from commit `5e86778dd799fa67c86cf6ade44634af147d3e66`. Its public OCI index is:

```text
ghcr.io/jill-vekariya/agent-reliability-harness@sha256:730eddd981aa3b658f51ab331bbd0b2f967be61a7fa5c2a0541e86a5dbcccc7d
```

The Linux AMD64 runtime manifest is `sha256:f67d9a0b801001e67ddb26df451fb019a45afd6f5d8b30d40217fd5178ee69a2`. The separate attestation manifest is included in the index. The publishing job generated SBOM and build-provenance attestations. A fresh empty Docker client configuration successfully inspected and downloaded the image without registry credentials. The downloaded image then passed the 20-task offline regression with networking disabled (19 synthetic matches, no regressions or incompatibilities).

The full 64-test suite passed natively, in Docker on the connected Windows machine, and in GitHub CI. The Windows Docker run took 30.63 seconds and emitted an expected pytest cache warning because the root filesystem was read-only. No failures or skipped tests were reported. Offline regression passed against its fixed synthetic baseline; 19/20 scripted result matches are not model accuracy.

The public walkthrough returned HTTP 200. Its four case controls, supported count, schema error, blocked-query state, scripted recovery, and 375-pixel layout were exercised in a dedicated headless Edge profile. No browser exceptions or horizontal overflow were observed. See `reports/public-demo-browser.json` and `reports/screenshots/public-demo.png`.

A follow-up on main makes the maintainer's browser-capture helper wait for selection state after instantaneous scrolling. The generated walkthrough and Python runtime are unchanged by that helper fix. The later audit corrects `compose.release.yaml` to pin the verified v0.2.1 digest explicitly; the original tagged configuration used its version tag.

The public site is a static trace walkthrough. Docker runs the real worker and regression. There is no public free-text SQL/model backend. Human review, the final frozen benchmark, live provider compatibility, and empirical results remain pending. Paid model API spend and unresolved reservations remain USD 0.
