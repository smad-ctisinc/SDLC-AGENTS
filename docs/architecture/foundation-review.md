# Six-phase foundation review

Current status: Step 01.10 remediation implemented. See the stabilization results
at the end of this document; the original review below is retained as history.

Review scope: contracts and packaging, registry, policy/tools, runner/providers,
context storage, and CLI. Production implementation was reviewed without changing
its behavior. CI and regression coverage additions are described below.

## Original confirmed findings (remediated in Step 01.10)

1. **P1: declared Typer minimum cannot start the CLI.** `pyproject.toml:15`
   permits Typer 0.16.0, while `cli.py:87` uses `Literal["fake"]`. Installing
   that permitted version in the separate wheel-validation environment and running
   `python -m sdlc_agents --help` raises `RuntimeError: Type not yet supported`.
   Even list/help fail during command construction. Raise the minimum to a tested
   compatible release or use a compatible Enum, and test dependency lower bounds.

2. **P2: malformed YAML can escape the documented error boundary.**
   `loader.py:70` does not catch a plain ValueError from YAML scalar conversion.
   A file containing `contract_version: ` followed by 5,000 decimal digits is below
   the byte limit but raises ValueError under Python 3.13's default integer limit,
   rather than ContractLoadError. Registry callers and CLI list/validate therefore
   lose their controlled error handling. Normalize this parser failure and cover
   loader, registry, and CLI diagnostics with regression tests.

3. **P2: usage aggregation can discard a completed run's result and metadata.**
   `runtime.py:105` sums finite costs without checking the total. Two individually
   valid responses with `estimated_cost_usd=1e308` produce infinity. Construction of
   UsageMetrics then raises ValidationError at `runner.py:200`, outside the runner's
   error handler. Reproduced through LocalAgentRunner with two fake model calls:
   no ExecutionResult returned and zero run records retained. Define overflow
   semantics and ensure accounting failures cannot bypass result/record creation.

4. **P2: schema validation accepts non-portable Python values.**
   `contracts.py:66` checks JSON encodability, not JSON-native types. For example,
   `PayloadSchema.model_validate({'schema': {'type': 'object', 'default': (1, 2)}})`
   accepts and retains a tuple. Serialization converts it to a list, violating the
   strict portable contract boundary. The existing JSON-native checker already
   rejects tuples in payloads and context; apply equivalent validation to schemas.
   Add coverage for defaults/examples/custom annotation values and round trips.

## Phase assessment

| Phase | Assessment |
| --- | --- |
| 1 | Strict fields, independent versions, inline schemas, and src packaging are present; findings 2 and 4 affect validation consistency. |
| 2 | Explicit roots, deterministic ordering, explicit ambiguous-version handling, and link rejection are present. Loader errors need the normalization in finding 2. |
| 3 | Contract/policy/grant intersection, denied effects, hardlink rejection, and output redaction remain intact in inspected code. Added native symlink coverage outside registry. |
| 4 | Explicit factories and provider-neutral interfaces keep implementations out of definitions; finding 3 bypasses the structured result guarantee. |
| 5 | Project hashing, revision checks, atomic replacement, and explicit persistence preserve boundaries. No newly confirmed storage defect; trusted stable filesystems and stale-lock recovery remain documented limitations. |
| 6 | CLI composes existing services with denied capabilities; finding 1 is a supported-dependency packaging failure. |

No imports from concrete agents, root adapters, workflows, or provider SDKs were
found. Shared model modules remain below runtime/storage/CLI services. RunRecord
retains identical public and legacy runner imports. New installed-source tests
check these boundaries. This is not an OS sandbox or a proof against malicious
concurrent filesystem changes; cooperative cancellation and best-effort redaction
remain existing limitations.

## Changes and validation

- Added `.github/workflows/foundation.yml`: Linux/Windows x Python 3.11/3.13,
  editable tests, dependency check, and isolated wheel verification. Permissions
  are read-only and checkout credentials are not persisted.
- Added `.github/scripts/verify_wheel.py`: fresh virtual environment, wheel content
  checks, import-origin assertion, installed command invocation, and full suite
  outside the checkout. Uses a dedicated temporary pytest directory.
- Updated registry symlink helper: link creation errors cannot silently skip Linux.
- Added `test_symlink_boundaries.py`: storage root/file/ancestor/broken links,
  file tool escapes, and CLI input links; only Windows privilege failures skip.
- Added `test_dependency_boundaries.py`: installed-source dependency checks and
  RunRecord import compatibility.
- Latest local Python 3.13.0 suite: **295 passed, 13 skipped**; pip check and
  git diff --check passed. All skips are Windows native symlink privilege limits.
- Python 3.11 was not found in the Python commands, pyenv installations, or usual
  per-user Python installation directory. Python 3.12 and 3.13 are installed.
  Python 3.11/Linux runtime results await CI; no remote CI run was triggered.
- Fresh wheel build, installation, dependency check, import assertion, and console
  command passed. Its tests initially hit an existing Windows pytest-temp ACL
  conflict (113 passed, 195 setup errors). The helper now supplies its own basetemp;
  the complete rerun remains unverified because automatic approval review hit an
  account usage limit. This was not a determination that the operation is unsafe.
- Minimum Typer reproduction ran in `.venv/wheel-validation`, which still has
  Typer 0.16.0 for diagnosis. Main `.venv` remains on 0.27.3. Restoration of the
  diagnostic environment did not execute after the approval-review failure.

The four findings above are not repaired by the passing suite. Missing regression
coverage includes dependency minima, pathological YAML scalars, aggregation
overflow, and non-JSON schema annotations. No production code was changed, and no
branch switch, commit, push, or global dependency installation was performed.


## Step 01.10 stabilization results

All four production findings are fixed without changing the foundation architecture
or raising dependency minimums. The public terminal model remains ExecutionResult
(the existing equivalent of RunResult); persistence remains explicit and optional.

| Finding / root cause | Remediation |
| --- | --- |
| CLI used Literal unsupported by minimum Typer | String Enum plus explicit runtime guard; unsupported or omitted executor cannot run. Typer minimum remains 0.16.0. |
| YAML scalar conversion raised uncaught ValueError | Preserve existing ContractLoadError diagnostics; normalize ValueError/OverflowError at the loading boundary with sanitized text and suppressed exception context. No integer limit changes. |
| Finite individual costs overflowed during final usage construction | Detect overflow after responses and again during finalization. Return failed/usage_accounting_failed with no output, retained identities/timing/call counts and available token totals; unrepresentable cost is None. Record the terminal attempt through runner.records(). |
| JSON encoding silently accepted tuples | Validate schema input before model conversion using the existing recursive JSON-native checker, then apply existing inline/dialect/schema checks. Invalid annotations are rejected rather than converted. |

Cost overflow means representational failure, not a newly introduced monetary
budget feature. Unknown provider costs remain unknown and do not independently
fail execution. Known nonnegative costs are checked even when another model call
failed and complete usage is unavailable. An executor cannot suppress overflow by
catching the call error. Call budgets still reserve counts before invocation;
rejected calls do not add usage, and failed/cancelled admitted calls retain their
counts. Existing concurrent-budget, failed-provider, tool-budget, cancellation,
and project-isolation tests remain in the suite.

### Exact files changed during stabilization

Production:
- `foundation/src/sdlc_agents/cli.py`
- `foundation/src/sdlc_agents/contracts.py`
- `foundation/src/sdlc_agents/loader.py`
- `foundation/src/sdlc_agents/runtime.py`
- `foundation/src/sdlc_agents/runner.py`

Tests:
- `tests/foundation/test_cli.py`
- `tests/foundation/test_contracts.py`
- `tests/foundation/test_loader.py`
- `tests/foundation/test_runner.py`
- `tests/foundation/test_registry.py` (short parameter IDs for pytest 8/Windows)

Validation and documentation:
- `.github/constraints/minimum.txt` (new direct-dependency lower-bound constraints)
- `.github/workflows/foundation.yml` (minimum-version suite on each OS/Python job)
- `.github/scripts/verify_wheel.py` (isolate pytest cache as well as base temp)
- `docs/architecture/foundation-review.md`

### Regression coverage

40 additional test cases cover all command help pages; safe YAML integer failures
through loader, registry, and CLI; nested tuple/set/bytes/non-string-key/nonfinite
schema annotations; invalid schema roots; valid JSON round trips; cost overflow
with and without executor interception; retained model/tool usage and explicit
record persistence; representable/unknown costs; and overflow followed by another
failed model call. Existing smoke tests exercise list, validate, and synthetic run,
including rejection of omitted/unsupported executor values.

Minimum testing also exposed oversized pytest parameter IDs exceeding Windows'
environment-variable limit under pytest 8. Short explicit IDs preserve those
payload tests without changing their inputs or weakening assertions.

### Verification and merge readiness

| Check | Final result |
| --- | --- |
| Windows / Python 3.13.0 / current editable dependencies | 335 passed, 0 failed, 13 skipped |
| Windows / Python 3.13.0 / minimum direct dependencies | 335 passed, 0 failed, 13 skipped; 2 upstream Typer/Click deprecation warnings |
| Fresh isolated wheel / Python 3.13.0, outside checkout | 335 passed, 0 failed, 13 skipped; helper exit code 0 |
| Editable reinstall | Passed in main and minimum-dependency environments |
| Wheel build, contents, import origin, installed console command | Passed |
| CLI help/list/validate/fake run, explicit selection and rejection | Passed with current and minimum dependencies |
| pip check | Passed in all three environments |
| Python 3.11 source grammar | Passed; not a substitute for runtime tests |
| Python 3.11 runtime / Linux / remote Windows CI | Not available or executed locally; configured in CI, results pending |
| git diff --check | Passed |

The minimum environment pins Pydantic 2.10.0, PyYAML 6.0.3, jsonschema 4.23.0,
Typer 0.16.0, and pytest 8.0.0; transitive dependencies are resolver-selected.
The 13 skipped tests require native Windows symlink privileges. Linux fails
rather than skips if link creation is unavailable. The CI matrix now tests both
current and minimum direct dependencies on Linux/Windows and Python 3.11/3.13.

The corrected isolated-wheel helper was rerun successfully after explicit approval
in Step 01.10. Its private base-temp directory resolved the previous fixture setup
permission failure; a private pytest cache also removes the cache ACL warning.
No tooling/account-limit block remains for this validation.

**Merge readiness:** all four confirmed production findings are remediated and
locally verified, including lowest direct dependency versions and wheel packaging.
Ready for review, but final cross-platform merge clearance should wait for the
Python 3.11/Linux/Windows CI matrix to pass. Remaining risks are unverified remote
CI, two upstream minimum-version deprecation warnings, and the documented trusted
filesystem/cooperative-executor limitations. No new monetary budget mechanism,
provider, agent, or implicit persistence was introduced. No commit, push, merge,
or branch switch was performed. Stop here pending approval.
