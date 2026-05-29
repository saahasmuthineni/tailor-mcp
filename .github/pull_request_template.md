<!-- Thanks for the contribution! Please fill in the sections below. -->

## Intent — is this the right thing to ship to `main`?

<!-- CI (tests/ruff) and the bot reviewers (Claude, Copilot) check whether the
     diff is correct and safe. They CANNOT check whether it is the RIGHT change.
     That judgment is yours. Confirm before merging: -->

- [ ] This is the change I actually intended to ship — not merely green and clean.
- [ ] I have read the Claude and Copilot review comments and resolved or dismissed each.

## Summary

<!-- 1-3 sentences on what this PR does and why. -->

## Type of change

- [ ] Bug fix
- [ ] New feature / new child MCP
- [ ] Refactor (no behavior change)
- [ ] Docs
- [ ] CI / tooling

## Test plan

- [ ] `pytest -v` passes locally
- [ ] `python tests/security_probe.py` passes locally
- [ ] `ruff check src tests` passes
- [ ] `tailor --help` works
- [ ] (if relevant) tested against a real Strava account / Claude Desktop

## Security / privacy checklist

- [ ] No secrets (tokens, client secrets, API keys) are logged or committed.
- [ ] If this change touches the security pipeline (ParamValidator / CircuitBreaker / ConsentGate / CostGate / AuditLog), `tests/security_probe.py` has been updated.
- [ ] If this change exposes a new biosensor data type, `ConsentInfo.data_types` has been updated on the relevant child.

## Related issues

<!-- e.g. "Closes #42" -->
