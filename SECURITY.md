# Security scope

See `docs/THREAT_MODEL.md` for trust boundaries and enforced limits. This is a research/portfolio project over a public fixture, not an arbitrary-code execution service.

Do not expose the Streamlit app as an unrestricted public SQL or model endpoint. The public browser demo contains only selected synthetic traces. API execution defaults to a zero budget and requires matching explicit approval metadata.

For a suspected vulnerability, use GitHub's private vulnerability reporting feature when enabled. Include the affected commit, a minimal non-destructive reproduction using the bundled fixture, expected behavior, and actual behavior. Avoid including credentials or private datasets in reports. Public engineering bugs that reveal no exploit or sensitive information can use the issue template.

The maintainer has no promised response SLA. Security fixes should include a regression test for the violated boundary and a review of the actual Docker/runtime controls.
