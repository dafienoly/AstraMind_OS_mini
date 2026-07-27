# Vibe-Coding Workflow

The project is expected to be built primarily through coding agents. The environment
therefore optimizes for small context windows, stable contracts, fast proof, and low
file collision.

## Principle: context locality

A task should be understandable by reading:

1. the root rules;
2. one context glossary;
3. one requirement and phase;
4. one feature directory;
5. its tests and public contracts.

If a routine task requires loading the whole repository, the module boundary is wrong
or the task is too broad.

## Work package lifecycle

1. Copy `work-package-template.md` into a task note or issue.
2. Define one observable outcome and non-goals.
3. Reserve the feature directory and identify high-contention files.
4. Resolve requirement and UI proposal status.
5. Change contracts before adapters where a contract change is necessary.
6. Implement the smallest vertical slice.
7. Run affected checks.
8. Review the diff for scope drift, file budgets, hidden state, and documentation.
9. Capture screenshots for user-visible work.
10. Hand off changed files, proof, and remaining decisions.

## Branch and worktree model

- One concurrent task uses one branch/worktree.
- Default branch prefix: `codex/`.
- A work package owns a directory where possible.
- A task that needs a shared contract coordinates that contract change before feature
  implementations fan out.
- Do not run broad formatting or dependency updates inside an unrelated feature task.

## Hotspot reduction

Avoid repeatedly edited central files:

- feature route registration is one file per feature;
- strategy registration is one file per strategy version/family;
- dataset registration is one file per dataset;
- migrations are append-only;
- UI tokens are centralized but changed only by visual-system work packages;
- generated API clients are replaced through generation, never patched.

Use a small deterministic composition root. Do not replace it with hidden filesystem
magic that makes startup or dependency order hard to understand.

## Module shape

Backend context:

```text
context/
  domain/
  contracts/
  application/
  ports/
  adapters/
  api.py
  public.py
  CONTEXT.md (when source directories exist)
```

Frontend feature:

```text
features/<feature>/
  api/
  model/
  components/
  pages/
  tests/
  index.ts
```

The public file exposes only what another context or the app shell needs.

## File budgets

| Unit | Target | Warning | Block |
| --- | ---: | ---: | ---: |
| Python/TypeScript module | 250 | 350 | 500 |
| React component | 180 | 250 | 350 |
| Function | 60 | 80 | 120 |
| React render body | 120 | 160 | 220 |

The automated check may exempt generated code, migrations, fixtures, and cohesive
tests. A split must create a meaningful responsibility boundary.

## Fast development loop

Planned stable commands:

```text
make doctor       environment and dependency diagnosis
make dev          local API, web, and background worker development
make check        affected lint, types, unit, contract, and doc checks
make e2e-smoke    focused browser workflow from the visible application
make test-long    explicit long-running historical/model tests
```

`make check` targets under 90 seconds on the development machine. Long historical
rebuilds and model training are never implicit.

## Deterministic fixtures

- Maintain small point-in-time fixtures with provider metadata.
- Use a fixed Golden Slice for calculations and UI empty/blocked states.
- Never include tokens, broker accounts, or real order payloads.
- Historical test data records why each date or symbol was selected.
- Fixtures are immutable once shared; a semantic change creates a new fixture version.

## Architecture checks

The default check should eventually enforce:

- forbidden cross-context imports;
- public contract imports only;
- file and function budgets;
- no secret-like files;
- no hand-edited generated code;
- one-way UI feature dependencies;
- OpenAPI/client drift;
- docs links and proposal status;
- no user-facing page implementation without an approved proposal reference.

## UI feedback loop

1. Proposal SVG and page contract.
2. Explicit user approval.
3. UI Lab components and states.
4. Vertical feature implementation.
5. Desktop and narrow-screen screenshots.
6. Visual comparison and accessibility check.
7. User review where the implemented screen materially differs.

## Agent handoff

Every handoff states:

- outcome;
- work package and requirement;
- files changed;
- tests/checks run;
- screenshots when applicable;
- assumptions;
- protected actions not taken;
- the exact next safe action.
