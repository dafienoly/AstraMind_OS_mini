# AstraMind OS Mini repository instructions

These instructions apply to the whole repository. More specific `AGENTS.md` files may
add local constraints but must not weaken the product, data, UI-approval, risk, or
execution boundaries below.

## Product purpose

AstraMind OS Mini is a local-first, single-user A-share quantitative trading system.
Its first goal is to move a small number of stock strategies from reproducible research
to local Shadow and then, only after an explicit user decision, MiniQMT execution.

The product has two capital sleeves:

- tactical stock trading: CNY 50,000, normally one or two concurrent holdings;
- core stock investing: CNY 100,000, normally about five holdings, evaluated weekly.

ETF rotation is a later capability. Market and industry dashboards support both stock
and ETF decisions but are not independent execution engines.

## Required reading

Before changing files, read:

1. this `AGENTS.md`;
2. `docs/README.md`;
3. `CONTEXT-MAP.md` and the `CONTEXT.md` for every affected context;
4. `docs/product/product-baseline.md`;
5. the relevant requirement, ADR, UI proposal, data contract, and phase in
   `docs/planning/phased-implementation-plan.md`.

If documents and working behavior disagree, report the conflict before broadening the
change. Update the affected document and implementation together.

## Authorization boundaries

- Documentation, diagrams, fixtures, local tests, research, backtests, and local Shadow
  are not broker authorization.
- Do not connect MiniQMT, place a real order, enable Live, or use real capital without
  a separate explicit user instruction naming that step.
- Strategy-promotion approval does not automatically authorize broker connectivity.
- A standing mandate may automate routine orders inside its recorded limits. Orders
  outside the mandate, changes to mandate limits, and abnormal risk conditions require
  visible exception handling.
- Do not add enterprise identity, role, approval, or release machinery to a loopback
  single-user product unless the user explicitly asks for remote or multi-user access.
- Bind locally by default. Remote exposure is disabled unless separately designed and
  approved.

## UI schematic approval gate

No new user-facing page, substantial layout, navigation change, or visual redesign may
be implemented before an approved UI proposal exists.

A proposal must:

- live under `docs/ui/proposals/<NNNN>-<slug>/`;
- contain an SVG or equivalent visual schematic;
- state the page's single job, visible data, important states, primary action, and
  responsive behavior;
- have a version and status of `draft`, `awaiting_user_approval`, `approved`, or
  `superseded`;
- record the user's explicit approval before implementation begins.

Implementation must name the approved proposal and version in its work package. After
implementation, capture real screenshots and compare them with the approved proposal.
Small behavior-neutral typo, accessibility, and rendering fixes may reuse the current
approved proposal when they do not change layout or visual direction.

## Data and research invariants

- Preserve raw provider records separately from normalized observations and derived
  features.
- Every observation records provider, source identity, retrieval time, market date,
  availability time, units, and schema version where applicable.
- Backtests and models use point-in-time joins. Financial reports, shareholder counts,
  industry membership, 龙虎榜 data, and corporate events become available only at their
  actual publication or market-availability time.
- A T-day post-close signal cannot assume T-day execution.
- Preserve delisted securities, historical ST/suspension/limit states, corporate
  actions, and historical industry membership when the strategy needs them.
- Costs, slippage, T+1, lot size, price limits, suspensions, and liquidity constraints
  are part of every executable backtest.
- Treat every factor and strategy as a hypothesis until it passes its declared
  out-of-sample evidence. Do not label a backtest, sealed replay, or Shadow result as
  Live performance.
- One request uses one immutable data snapshot. Do not silently mix dataset versions.

## Architecture

Use a modular monolith with explicit ports:

`domain/contracts -> application services -> ports -> adapters -> composition root`

Planned top-level bounded contexts are Data, Market Regime, Strategy Research,
Portfolio & Risk, and Trading Execution. A context may import another context's public
contract but not its internal modules.

Keep these thin-waist contracts stable:

- `DataSnapshot`
- `FeatureSnapshot`
- `StrategyVersion`
- `PredictionBatch`
- `OptimizationProblem` / `OptimizationResult`
- `PortfolioTarget`
- `StandingMandate`
- `OrderPlan`
- `ExecutionEvent`

Research, Shadow, Paper, and Live must use the same `OrderPlan` and execution state
model. Broker-specific behavior belongs behind a gateway port.

Do not introduce a second data truth source, strategy registry, execution engine, job
system, or UI component system without recording the reason and migration path.

## Vibe-coding and collision control

Work from a bounded work package. Each work package states:

- goal and non-goals;
- allowed files or owned directory;
- affected contracts;
- acceptance checks;
- UI proposal reference when applicable;
- protected boundaries and required user decisions.

Prefer one feature directory per task. Do not make unrelated cleanup changes.

High-contention files include root configuration, shared contracts, design tokens,
application composition, schema migrations, and registries. Only one active work
package should edit a high-contention file at a time.

Use one branch or worktree per concurrent task. Database migrations are append-only;
do not edit an already shared migration. Generated clients and schemas are never hand
edited.

Avoid catch-all files such as `utils.py`, `helpers.ts`, `types.ts`, or one giant route
file. Each module exposes a small `public.py`, `api.py`, or `index.ts`.

## File and complexity budgets

Line limits are design smells, not a license for mechanical fragmentation:

- Python/TypeScript module: target <= 250 lines, warn > 350, block > 500;
- React component: target <= 180 lines, warn > 250, block > 350;
- function: target <= 60 lines;
- component render body: target <= 120 lines.

Generated code, migrations, fixtures, and unusually cohesive tests may be exempt with a
short reason. Split by responsibility and change frequency, never just by line count.

## UI implementation rules

- Follow `docs/ui/visual-direction.md`.
- Keep five top-level destinations: Today, Market, Strategy Arena, Portfolio, System.
- Market owns the broad-market, industry, and ETF-lifecycle views; do not add separate
  top-level navigation for each.
- Reveal detail progressively. Do not create card-within-card dashboards, multi-step
  modal chains, or pages whose primary action is unclear.
- Human attention is an exception inbox, not a sequence of routine approvals.
- Use real empty, loading, stale, blocked, disconnected, and error states. Never use a
  green state for unknown data.
- Market red/green must also use labels, arrows, or signs; color cannot carry meaning
  alone.
- A development UI Lab should show every shared component and important state.

## Testing and definition of done

Add focused proof with every implemented behavior:

- unit tests for pure domain and calculation logic;
- contract tests for ports and schemas;
- integration tests for data persistence and gateways;
- one visible browser workflow for a user-facing capability;
- screenshot comparison for an approved UI proposal;
- negative tests for point-in-time, risk, mandate, and execution boundaries.

Keep the default affected-scope check fast enough for iterative work; target under
90 seconds. Long backtests, full historical rebuilds, and extended Shadow observation
are separate commands and never hidden inside the default check.

An implemented user capability is complete only when it has behavior, persistence or a
rebuildable projection, visible progress/result/blocker states, refresh recovery,
documentation, and focused automated proof.

## Documentation

Keep documentation small and authoritative:

- glossary terms belong only in context `CONTEXT.md` files;
- hard-to-reverse trade-offs belong in concise ADRs;
- observable product behavior belongs in requirements;
- sequencing and dependencies belong in the phased plan;
- visual decisions belong in versioned UI proposals;
- implementation details belong near the code.

Do not create multiple authoritative documents for the same decision. Supersede or
update an older document when direction changes.

### Documentation language

Human-readable product documentation is written in Simplified Chinese. This includes
the root `README.md`, the documentation index, product baselines, requirements,
architecture, ADRs, data contracts, plans, decision logs, UI specifications, UI
proposals, and operating guides.

English is allowed only for agent-facing Vibe Coding internals:

- this `AGENTS.md`;
- `CONTEXT-MAP.md` and `docs/contexts/**/CONTEXT.md`;
- `docs/development/vibe-coding.md`;
- `docs/development/work-package-template.md`.

Code identifiers, API names, library names, and established execution states such as
Shadow, Paper, Live, Tushare, and MiniQMT may remain in English inside Chinese
documents. User-interface copy is Chinese unless a proper name or technical identity
would become ambiguous after translation.

## Git and safety

- Preserve user-owned and unrelated changes.
- Use the `codex/` prefix for implementation branches unless instructed otherwise.
- Do not commit secrets, Tushare tokens, broker credentials, account identifiers, or
  real order payloads.
- Do not use destructive Git or filesystem commands without explicit scope.
- Do not commit, push, merge, or open a pull request unless the user asks for that
  external action.
