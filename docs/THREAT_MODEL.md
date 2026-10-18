# Threat model and enforced boundaries

Trusted: project code, pinned upstream database/schema, fixture preparation, evaluator gold, parent runtime, and dependency lock. Untrusted: model-generated SQL/arguments and stored table values. Arbitrary malicious Python agent code, a compromised host/kernel/SDK, malicious database files, and a hostile repository contributor are outside the claimed SQL boundary.

The agent gets no shell, Python, filesystem, or network tools. Only the provider client can call its API, and it cannot be constructed under the default zero budget. The SQL subprocess receives a fixed database path/allowlist from trusted code, no API credentials, a private temporary working directory, and a minimal environment.

Every query uses URI `mode=ro`, a fail-closed authorizer, no extension loading/UDFs, one `execute` statement, SQLite length/expression/compound/attachment limits, a progress budget, a monotonic deadline, and a parent output/deadline boundary. Linux adds CPU, virtual-address-space, file-size, and file-descriptor limits. Temporary SQL storage is in memory. The parent terminates, escalates to kill if needed, and reaps each worker.

Defaults: 2-second worker deadline, 2-second CPU budget, 192 MiB worker address space, 500,000 VM steps, 100 rows, 4 KiB cells, 64 KiB serialized output, 16 KiB SQL, 128 KiB SQLite value/row limit, 12 agent steps. See `Limits` for validated bounds. Progress callbacks are coarse, so the parent deadline remains mandatory.

The Docker reference adds non-root execution, a read-only filesystem/database mount, dropped capabilities, no-new-privileges, PID/CPU/memory limits, and bounded temporary storage. Offline test/regression containers are run with `--network none`. The localhost viewer needs a network interface to serve its UI and is not described as network-isolated.

Native Windows SQL execution is disabled: use the Linux Docker image. A Docker image is not a general security boundary against kernel vulnerabilities. A read-only database does not establish prompt-injection resistance. Blocking an unsafe SQL proposal records both successful enforcement and an unsafe agent decision.

The reporting-only prohibited-SQL detector is heuristic and unvalidated by humans. It does not enforce SQL policy. Its false positives/negatives must be measured before causal failure claims. Core OTel exports do not include API credentials or private chain-of-thought.
