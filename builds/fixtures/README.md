# Harness fixtures

**Audience: table-facing** (copies of the build ledgers, no GM content).

`L4/` holds the six party ledgers frozen exactly as they stood at Level 4 (origin `8fbdf47`,
2026-09-27). `tools/builder_verify.py` stages THESE, not the live `builds/<pc>.yaml`, for its
behaviour checks: those checks pin known numbers (Tanrielle PD 17, Awareness +7, Runt's L5
add-level riders and so on), so they need a fixture that does not move when the party levels up.

The live ledgers are still checked directly: the builder page's ledger blobs, `ledger_fmt`
house format, `catalog_verify` reconciliation, and section (56), which replays every live
ledger at its `current_level` and requires zero problems and a clean `expected:` match.

Never edit a fixture to make a check pass. If the party levels again, leave `L4/` alone.
