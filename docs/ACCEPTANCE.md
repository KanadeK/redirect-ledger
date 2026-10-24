# Acceptance and review

Target workflow: a static-site maintainer exports a small exact-path redirect table, supplies the replacement site's page inventory, finds loops/missing terminals/chains, exports a conservative plan, and re-audits it before configuring a server.

Acceptance conditions:

- Invalid schemas, canonical duplicate sources, unsupported routing semantics, oversized/non-UTF-8 data, and unsafe URL forms fail visibly.
- Every source reaches an explicit terminal or an identified cycle, including upstream tails.
- Missing internal terminals and shadowed live pages fail the audit.
- Only uniform 301/308 chains are shortened; input and existing output files remain unchanged.
- Plan re-auditing and observed local HTTP hops agree with the graph model.
- Random graph results agree with an independent naive walk. A 20,000-hop chain works without recursion.
- Installation into an empty virtual environment from the built wheel runs the full suite without checkout imports.

Review boundaries: this is an explicit functional-graph model, not a production routing engine. Absolute targets are intentionally terminal, and inventory membership is not a network existence check. Limiting URL syntax and refusing duplicate sources avoids silently selecting a rule. Reports escape URL strings in text and JSON, never include OS error paths, and the runtime has no network or subprocess capability.

The source and tests are original. No runtime dependencies or third-party assets are distributed. Python standard-library APIs and CSV/URL format knowledge are used under their normal interfaces. Build backend setuptools (MIT), build (MIT), Ruff (MIT/Apache-2.0), and coverage.py (Apache-2.0) are development tools rather than bundled code.
