# Reproducibility

Recommended Windows path: Docker Desktop (Linux containers), `START_DEMO.cmd`, and `TEST_PROJECT.cmd`. Recommended native Linux/macOS path: install uv 0.12.23, `make setup`, `make ci`, `make demo`. Python 3.12.14 is pinned; the lock pins runtime/dev distributions and hashes. Build-system versions and transitive build constraints are pinned separately. The Docker base image is pinned by an independently queried registry digest.

The clean-checkout path uses bundled pinned databases. `make data` verifies them without a network request. `python scripts/materialize_data.py` downloads only the checksum-pinned official snapshot if omitted and reconstructs the exact harmless injection fixture. Existing changed databases are never silently overwritten.

`make eval` executes strict offline regression using synthetic recorded model responses, current tools, and the current grader. `make eval MODE=replay` plays back saved responses/tools exactly. `uv run --no-sync arh eval --mode fixture --all` executes synthetic scripts against current tools. No command silently switches modes or contacts a provider.

Outputs live under `artifacts/<run-id>/`: immutable manifest, attempt registry, versioned trace envelopes, event JSONL, runtime metadata, and summary JSON. Resuming requires `arh eval --resume PATH` with matching source/config/dependency/task provenance. Interrupted started attempts remain visible and are not replaced. Replay timestamps/usage belong to the original recording; playback runtime is stored separately.

The trusted initial regression reference is `tests/regression/baseline.json`, anchored by git history. It is explicitly synthetic and not human-approved. PR CI reads the baseline from the target commit through `ARH_BASELINE_FILE`; candidate changes do not silently choose a new reference. Hashes alongside mutable data do not independently prove authenticity.

Generation uses fixed local seed 20261018 where sampling is needed. Live manifests record provider identity, actual usage, hardware, Python/SQLite, source/lock/task/database/split/config hashes, and seed support. Live execution currently sends no provider seed. Provider outputs are not guaranteed deterministic.

Platform limits and SQLite versions can change observable output. An exact request mismatch fails clearly; never silently substitute another recording. If a reviewed request truly changes, collect new authorized recordings as a separate versioned change. Ordinary numeric grading has explicit tolerances; recording lookup does not silently apply tolerant matching.

Run `make report` to rebuild the available report from the bundled synthetic demo. Headline empirical plots/results remain pending rather than being synthesized. Release evidence records exactly which checks ran in each environment.
