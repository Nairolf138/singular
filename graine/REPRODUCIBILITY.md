# Reproducibility

Runs record seeds, configurations, and snapshots to enable deterministic replay.

## Replay Procedure

1. Checkout the commit hash associated with the run.
2. Recreate the Python environment and install dependencies.
3. Use the recorded seed and configuration to rerun the experiment:
   `python -m graine --seed <seed> --config <file>`.
4. Compare the output with the stored snapshot.

## Audit Procedure

Audit trails consist of hashes of inputs, outputs, and patches. To audit a
run:

1. Verify that the commit hash and recorded hashes match the repository state.
2. Ensure the replay procedure yields identical results.
3. Document any discrepancies and report them to maintainers.
