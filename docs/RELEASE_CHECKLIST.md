# Release checklist

- [x] `make setup` / committed lock accepted.
- [x] `make data`, task lint, lint/format, typing, tests, regression and replay pass.
- [x] Docker build and offline `--network none` regression verified.
- [x] Local viewer health and core interactions verified.
- [x] Actual verification outputs saved in release evidence.
- [x] No secrets/private traces in archive or image.
- [ ] Synthetic/provider/replay labels remain visible.
- [ ] User reviews at least 15 tasks; every final curated task reviewed.
- [ ] Final 150-task corpus, 20 sourced adaptations, grouped split and experiment freeze complete.
- [ ] Scoped paid pilot approval and safe pricing bounds before any live requests.
- [ ] Five fresh attempts per frozen task/config; missing coverage disclosed.
- [ ] Actual held-out human labels obtained; no manufactured agreement score.
- [ ] Headline statistics/Pareto/ablations/safety regenerated from actual live artifacts.
- [ ] Public repository/host authorized and verified before publication claims.

Pending R1/R2 items do not imply the offline engineering release is unusable. Executed checks are recorded authoritatively in `reports/release-evidence.json`, not inferred from these unchecked boxes.
