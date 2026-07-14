# Repository guidelines

## Tooling and workflow

- Use mise only to install and select repository tools.
- Use uv for Python dependency management and command execution.
- Pin every direct runtime and development dependency to an exact version in
  `pyproject.toml`.
- Keep `uv.lock` committed and synchronized with `pyproject.toml`.
- Never read, print, commit, or copy values from `.env`. Document variables with
  empty values in `sample.env`.
- Use Conventional Commits for every commit.

## Python

- Type every function parameter and return value. Add explicit variable types
  whenever inference does not communicate the complete intended type.
- Do not use `Any`, `typing.cast()`, unchecked downcasts, or suppression comments
  to force a value through the type checker.
- Do not coerce untrusted values into the desired type. Parse and validate them,
  and fail with a specific error when validation fails.
- Use strict Pydantic v2 models at untrusted boundaries such as environment
  configuration, GitHub payloads, and Devin API responses. Enable strict
  validation with `ConfigDict(strict=True)`; choose and document the appropriate
  `extra` behavior for each external contract.
- Keep raw webhook bytes unchanged until signature verification is complete.
- Prefer explicit models, enums, discriminated unions, and type narrowing over
  unstructured dictionaries or runtime type assertions.
- Add a package as a direct dependency when application code imports it, even if
  another dependency already installs it transitively.

## Testing

- Use pytest, including AnyIO for asynchronous tests.
- Do not use mocks, fakes, stubs, monkeypatching, or patched internal functions
  for code owned by this repository.
- Exercise real internal components together. Use isolated real resources such
  as temporary directories or temporary databases when state is required.
- Test externally observable behavior rather than private implementation details.
- A test double is allowed only at a boundary with a third-party system we do not
  own, such as GitHub or Devin. Keep the substitution at that network boundary;
  do not replace an internal repository service to make a test pass.
- Simulated third-party requests and responses must be based on the provider's
  official documentation. Put the exact documentation URL beside the fixture or
  test and identify the documented event, endpoint, and schema version when one
  exists.
- Do not make live third-party network calls in the default test suite.
- Keep tests deterministic. Do not use arbitrary sleeps or depend on test order.
- Run opt-in live integration tests with
  `uv run pytest -m live tests/integration`; these use `.env` credentials and
  may create isolated third-party resources that the tests must clean up.

Run the complete quality gate before pushing:

```shell
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest
```
