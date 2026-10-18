# Launch the no-key demo

On Windows, start Docker Desktop and double-click `START_DEMO.cmd`. The app opens at http://localhost:8501. Alternatively run `docker compose up --build -d` from the project folder. `docker compose down` stops only this project's viewer.

On Linux/macOS: install uv 0.12.23, run `make setup`, `make data`, `make ci`, then `make demo`. The SQL worker uses POSIX resource limits. Native Windows execution of the SQL worker is intentionally disabled; use Docker.

No API key is needed. No public deployment or hosting service is required. The viewer is bound to localhost on the host machine. The `Study & checks` tab reruns the current 20-task regression without model calls. Its writable output is separate from read-only data.

## Three-minute walkthrough

0:00–0:25 — Explain the question: which engineering changes improve an SQL agent, at what cost? Point out synthetic mode, zero paid spend, and pending human/model evidence.

0:25–1:00 — Open q001. Follow the SQL tool call and its stored result. Show that final_answer must refer to r001; the evaluator does not pass gold to the agent.

1:00–1:40 — Open q002. The script invents InventedName. Show the SQLite error. In Scripted recovery, show a bounded retry using the actual Name column. Explain that the second script illustrates mechanics and does not measure a model improvement.

1:40–2:20 — Open s001. The stored Track.Name contains an injected instruction. It reaches the next synthetic request. The proposed DELETE is blocked. Explain why this is successful enforcement but an unsafe scripted decision, not evidence of real-model resistance.

2:20–3:00 — Open Study & checks and rerun the offline gate. Explain the pending empirical tradeoff: retries may recover errors while increasing tokens/cost, but no such relationship has been measured here. Point out the protocol for actual five-attempt studies and the zero-budget gate.

Screenshots are taken from the working application when available and stored under `reports/screenshots/`. No video has been recorded.

## Public browser walkthrough and container delivery

The static walkthrough is built by `make public-demo` from q001, q002, s001, and the separate recovery script. It accepts synthetic origins only, verifies recording hashes, excludes full provider requests and evaluator gold, escapes JSON embedded in HTML, and renders trace content through DOM text nodes. It has no SQL execution, API key, model endpoint, analytics, or external asset dependency. GitHub Pages deployment and tagged GHCR publication depend on the required verification job. Consult actual Actions/release outcomes before describing a publication as successful.

Use `docker compose -f compose.release.yaml up -d` to run the public 0.2.0 GHCR image pinned by digest. It uses the bundled pinned data and a dedicated reports volume. It exposes only localhost. To stop it, use the same Compose file with `down`. Actual publication and browser verification are documented in `PUBLICATION.md`.

The image is Linux AMD64. Source builds remain available for other Docker platforms. Build provenance and SBOM generation are configured on the tagged publishing job; the published digest and actual job result are the evidence.

## Optional hosted SQL backend — pending

The current delivery is a local container, not a public hosted service. An inexpensive container host must support this image, a writable reports volume, and the stated CPU/memory/process controls. Check current host limits and pricing before selection; the SQL worker's constraints cannot be assumed on a restricted free app host.

After selecting/authorizing a host: push the repository to the user's actual account, build the pinned image, mount the verified data read-only, keep API_BUDGET_USD=0, configure the port/health check, set the intended audience, deploy, and verify both health and the trace/regression interactions. Do not claim public deployment until those steps run. Paid hosting needs separate explicit authorization.
