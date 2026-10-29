# Prepared upstream documentation contribution

**Prepared only; not submitted, accepted or attributed as an owner contribution.**

Target: [Docker Compose startup-order documentation](https://docs.docker.com/compose/how-tos/startup-order/).
Source inspected at Docker docs main commit
`6a5bbded169026418c5fe97bafcf012954505142`, file
`content/manuals/compose/how-tos/startup-order.md`, blob
`156eda0d7ebbe6001815950de9249b742687a3af`.

The example uses a PostgreSQL readiness probe without a host. The proposed
[patch](upstream-startup-order.patch) adds TCP loopback and a short explanation.
This addresses the temporary Unix-only initialization-server window observed in
the local deployment investigation. [Official entrypoint source](https://github.com/docker-library/postgres/blob/master/docker-entrypoint.sh)
and the exact pinned 16.15 image's inspected script support that distinction.

## Executed validation

The patch applies to the captured source, and its YAML/escaped variables validate.
The analogous probe also passed the flagship's complete PostgreSQL 16.15 restore.
The separate version-18 check is [VERIFIED locally](evidence/upstream-postgres18.json):

| Check | Actual observation |
| --- | --- |
| Selected image | `postgres@sha256:979bccfde35445db618c65107d27d08c6c21339d8dc3ad4c830c6633947be0e4`; server version number `180006` |
| Controlled initialization | An explicit gate held initialization open. Unix `pg_isready` returned 0, TCP returned 2, and the corrected container health stayed unhealthy. |
| Final startup | TCP health became healthy and a TCP SQL query returned the custom database/user and initialized marker. |
| Existing volume | Restart preserved the marker; initialization ran once. |
| Failed initialization | Controlled exit 23; no successful TCP health check. |
| Compose interpolation | Escaped source variables became the expected container-shell variables. |
| Resource and cleanup scope | Two sequential network-none fixtures, no published ports, each limited to 512 MiB/one CPU/128 PIDs. Both containers removed; two volumes retained. |

Health intervals were shortened for this bounded fixture. The initialization gate
was fault injection, not a recommended production startup sleep. TCP readiness
does not by itself establish application schema readiness or production availability.

## Contribution review and external next steps

The inspected [contribution guidance](https://github.com/docker/docs/blob/main/CONTRIBUTING.md)
had blob `f11a8280d6fd121a13960ceb3a7b853abe0cae33`; the [style guide](https://github.com/docker/docs/blob/main/STYLE.md)
had blob `6909b4b28a4cc38dd047f951ccfb491bd05934aa`. Narrow open issue/PR searches
for `pg_isready` returned no matches; that is not an exhaustive duplicate search.

The linked [AI policy](https://github.com/moby/.github/blob/main/AI_POLICY.md),
blob `73b318169ec55c57302ef616b080727b2fea9258`, requires human review and AI-use
disclosure. For a previously unreported AI-assisted change, first obtain the
owner's authorization to open an issue, allow maintainer verification and approval,
then consider an authorized PR. This is a verified user-facing startup problem,
not a contribution-count exercise. No issue, fork, PR or accepted contribution
was created here. Owner understanding and maintainer approval remain pending.

Before external submission, refresh the target, follow the current guidance,
run its `docker buildx bake validate` and inspect the docs preview. Those upstream
site-wide checks have not been executed here; local patch/YAML/runtime validation
is distinct from an upstream build or maintainer review.

Only documentation is changed. This proposal does not alter Compose semantics,
certify database schema readiness, or claim that every Unix probe is invalid.
The owner should explain and validate the contribution before choosing to submit
it. Separate explicit authorization is required for an external issue or PR.
