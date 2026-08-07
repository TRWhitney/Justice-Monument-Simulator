# Glossary of Terms
- Developer: The one talking to you and providing tasks
- Agent: An AI coding agent, not necessarily you
- User: A consumer of the product, potentially the developer

# When removing features
- Assume there are no current users of the product, if a developer requests something be removed, then remove it without attempting to support backward compatibility unless explicitly told otherwise
- Do not add tests to verify the feature is gone, we never need to test that a feature does not exist

# Before a task is complete
- Fixtures are updated.
- Documentation is updated.
- Security implications are considered.
- Refactoring is complete to ensure reuse of code, maintainability, and readability.
- You must verify Code compiles (if applicable) and runs.
- You must run the verification tier required by the change and verify its complete test set passes.
- You must verify type-checkers are clean.
- You must verify linters are all run and are clean.
- You must verify via playwright, see below for more details.
- You must verify that formatters are all run (if applicable).
- Commit as it makes sense, if the sandbox refuses, elevate to developer.
- If the issue is rework, then squash commits as necessary.

# Verification tiers
- Use Python 3.12 or newer; `pyproject.toml` and `uv.lock` are authoritative.
- `./scripts/validate_repo.sh` is the required everyday gate. It runs formatting, linting, schema validation, unit tests, GUI tests, and the smoke launch.
- Investigate verification-time regressions instead of removing behavioral coverage.
- Reduce duplicated setup, unnecessary output, or slow critical-path work before increasing concurrency. Do not change production rendering architecture solely to make verification faster.
- Documentation-only changes require no pipeline or test execution.
- Engine, persistence, planner, or CLI changes require `./scripts/validate_repo.sh` plus the directly affected unit tests.
- UI changes require `./scripts/validate_repo.sh` plus the exact affected GUI and Playwright interaction path.
- Changes involving layout, focus, selection, drag and drop, image decoding, or Qt platform behavior require the full repository gate and direct GUI verification artifacts.
- Changes to Playwright configuration or browser-specific behavior require the complete configured Playwright suite across every assigned browser engine.
- Release verification requires `./scripts/validate_repo.sh` plus any applicable packaging checks.
- Only an explicit artifact-producing workflow may update tracked review screenshots or comparison data. Other verification commands must leave review artifacts unchanged.
- Do not hide flaky tests with retries. A retry that recovers is still a failed verification run.

# Playwright
- Keep browser verification state isolated between tests. First-launch tests explicitly use empty state; generated state is additional evidence and does not replace any product-test assignment.
- Ordinary runs capture screenshots only when an assertion needs the pixels or Playwright records a failure. Use the repository's explicit artifact-producing workflow for success-only review captures.
- Keep Playwright reports, traces, and performance output ignored unless they are intentional review artifacts; they must not contain source, storage state, or application data.
- Playwright HTML reports never open automatically. Open the most recent report explicitly after the verification command has exited.
- Use Playwright to verify issues and features before and after changes, use question tool or prompt the developer for more information if you cannot verify an issue.
- When fixing a GUI visual issue, compare the fresh Playwright screenshot directly against the developer-reported problem before declaring success. If the screenshot still shows the complained-about issue, the task is not done.
- For any bug fix, define the acceptance criterion in terms of the developer-observable symptom before making changes.
- Do not treat implementation proxies such as code shape, DOM structure, intended layout, internal state, or partial improvement as proof that a bug is fixed; verify the exact reported symptom directly.
- If the direct verification artifact still shows the reported symptom, the task is not complete even if the implementation appears logically correct.
- Before editing code for a bug fix, write down the concrete acceptance checks that will be used to decide whether the bug is actually fixed.
- After making a bug-fix change, evaluate each acceptance check explicitly against the verification artifact or test result. Do not collapse multiple checks into a vague summary.
- Do not claim a bug is fixed without citing the exact artifact used for verification, such as the screenshot, test output, or reproduced developer flow.
- If the acceptance checks and the verification artifact disagree with the implementation reasoning, trust the artifact and continue debugging.
- For GUI bugs, Playwright verification must exercise the exact developer-reported interaction path, not a nearby, similar, or inferred path. Use the exact named control and action.
- A passing Playwright check for one UI path does not justify claims about a different UI path unless that different path was also exercised directly.
- When multiple similar UI targets exist, verify the specific target named in the report before generalizing from any other passing case.
- If Playwright fixtures, seed projects, or sample content were mutated during debugging, restore or recreate a known-clean baseline before using later verification runs as evidence.
- Do not mark a GUI bug fixed if the verified Playwright flow did not include the exact triggering action, the exact target element, and the exact post-action state described by the developer.

# Testing
- All changes and features, aside from changes which only include removing features or documentation only changes, require tests whether they be E2E, Gerhkin Style, or Unit Tests.
- If a Gerhkin or E2E test is included, likely a unit test is needed too.
- Dependency injection is highly encouraged to facilitate.
- Backend code should be separate from GUI representation to the fullest extent possible.
- Fuzzing and mutation testing (killing mutants) is encouraged.
- No vendor specific CI/CD infra, do not add a .github or any similar

# Documentation
- AGENTS.md and README.md should all be markdown at the top level of the repo.
- NEVER add a README.md unless explicitly directed to do so.
- Otherwise keep documentation in a separate folder structure and make all docuemntation HTML, CSS, and Javascript (as necessary).
- HTML documentation should include mockups and where necessary several options with sliders and tweaks to allow the developer to select a way forward.
- When a design choice is not clear, and the choice isn't necessary solvable by asking the user a simple question, use the above method to ask the developer to select an option; an export feature so they can tell you what they chose is also helpful.
- Write ADRs, look for ADRs to assist decision making.
- Documentation changes never require pipeline or testing verification

# Research
- When doing research, use the search tool.
- Be thorough and consider different approaches and resources.
- Look at multiple sources to develop a well-rounded approach.
