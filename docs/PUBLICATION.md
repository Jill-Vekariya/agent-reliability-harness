# Verified public delivery

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
