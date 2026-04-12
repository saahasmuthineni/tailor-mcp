<!-- Thanks for the contribution! Please fill in the sections below. -->

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
- [ ] `biosensor-mcp --help` works
- [ ] (if relevant) tested against a real Strava account / Claude Desktop

## Security / privacy checklist

- [ ] No secrets (tokens, client secrets, API keys) are logged or committed.
- [ ] If this change touches the security pipeline (ParamValidator / CircuitBreaker / ConsentGate / CostGate / AuditLog), `tests/security_probe.py` has been updated.
- [ ] If this change exposes a new biosensor data type, `ConsentInfo.data_types` has been updated on the relevant child.

## Related issues

<!-- e.g. "Closes #42" -->
