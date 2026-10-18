# Changelog

## 0.2.1 — Windows packaging correction

* The Windows test launcher resolves its image from Compose instead of a stale hardcoded 0.1.0 tag. It also propagates regression failure and applies the PID limit to both test commands.
* Maintainer browser-capture helpers wait for rendered controls and settled selection, avoiding timing failures during a fresh Streamlit render or smooth scroll.
* Publication and published-image browser evidence from 0.2.0 are retained with their original identities; the patch's verification and image digest are recorded separately.

## 0.2.0 — public engineering release

* Added a static browser walkthrough exported from four explicitly selected, hash-validated synthetic traces. Provider requests and evaluator gold are excluded; hostile HTML is escaped and DOM content uses text nodes.
* Added CI-gated GitHub Pages delivery and versioned GHCR container publication, with pinned Actions dependencies, OCI metadata, build provenance, and SBOM generation.
* Added a hardened prebuilt-image Compose configuration, security policy, resume guidance, and implementation-linked interview preparation.
* Publication results and exact digests are recorded separately in release evidence; this changelog does not imply a successful hosted run.

## 0.1.0 — offline engineering release

Protected SQL execution, typed deterministic grading, recording/replay/regression, atomic spending reservations, candidate corpus, traces, statistics/reporting machinery, Streamlit viewer, Docker, and 60 executed engineering tests. No fresh model study or human benchmark review.
