# Antigravity PR Review — Setup Guide

Automates pull request code reviews using the [Google Antigravity SDK](https://github.com/google-antigravity/antigravity-sdk-python)
(`google-antigravity`). The agent runs as a composite GitHub Action, spawns the
GitHub MCP server inside an isolated Docker container, and posts structured
review comments enforcing three custom policies:

| Policy | Applies to |
|---|---|
| TypeScript type safety | All `.ts`, `.tsx`, `.js`, `.jsx`, `.mts`, `.cts` files |
| Performance regression detection | Critical paths: `src/services/`, `src/middleware/`, `packages/shared/` |
| Unit test coverage | All new exported functions, methods, and React components in the diff |
| Security compliance | All changed files + new dependencies |

Documentation-only PRs (only `*.md`, `*.rst`, `*.txt`, `docs/**`) are **automatically skipped**.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| GitHub repository | Any visibility |
| Ubuntu Actions runner | `ubuntu-latest` — Docker must be available on the host |
| Docker on the runner | Required for the GitHub MCP server container |
| Google Gemini / Antigravity API key | Obtained from [Google AI Studio](https://aistudio.google.com/) or the Antigravity console |

---

## Step 1 — Obtain an API key

1. Go to [Google AI Studio](https://aistudio.google.com/) and sign in.
2. Click **Get API key** → **Create API key in new project**.
3. Copy the key — you will not see it again.

> For production workloads requiring higher rate limits, subscribe to
> **AI Ultra** ($100/month) or use pay-as-you-go credits ($0.01 each).

---

## Step 2 — Add secrets to your repository

### Via the GitHub web UI

1. Navigate to your repository → **Settings** → **Secrets and variables** → **Actions**.
2. Click **New repository secret**.
3. Create the following secret:

| Name | Value |
|---|---|
| `ANTIGRAVITY_API_KEY` | Your Google Gemini / Antigravity API key |

`GITHUB_TOKEN` is provisioned automatically by the Actions runtime — you do
**not** need to create it manually.

### Via the GitHub CLI (`gh`)

```bash
# Authenticate with GitHub CLI (if not already done)
gh auth login

# Set the secret (prompts for value securely)
gh secret set ANTIGRAVITY_API_KEY --repo <owner>/<repo>

# Verify it was created
gh secret list --repo <owner>/<repo>
```

---

## Step 3 — Copy the action files into your repository

```
your-repo/
├── .github/
│   ├── commands/
│   │   └── antigravity-review.toml   ← review policy prompt
│   └── workflows/
│       └── antigravity-review.yml    ← workflow trigger & path filter
├── action.yml                         ← composite action definition
└── run_agent.py                       ← agent script with custom policies
```

```bash
# Example using this repo as a template
cp -r agy-pr-review/.github        your-repo/.github
cp agy-pr-review/action.yml        your-repo/action.yml
cp agy-pr-review/run_agent.py      your-repo/run_agent.py
```

---

## Step 4 — Pin the composite action SHA (production hardening)

The workflow references `rsamborski/run-agy-sdk@a3f1b2c` as a placeholder.
For production, pin to the exact commit SHA of the upstream action to prevent
supply-chain attacks from upstream changes.

```bash
# Get the latest SHA of the upstream action
gh api repos/rsamborski/run-agy-sdk/commits/main --jq '.sha'
```

Replace the `uses:` line in `.github/workflows/antigravity-review.yml`:

```yaml
# Before (placeholder)
uses: rsamborski/run-agy-sdk@a3f1b2c

# After (pinned)
uses: rsamborski/run-agy-sdk@<full-40-char-sha>
```

---

## Step 5 — Configure critical paths for your codebase

The performance regression policy applies only to directories listed as
"critical paths". Edit `run_agent.py` and `.github/commands/antigravity-review.toml`
to match your project layout.

In **`run_agent.py`** (the `path-filter` job also uses this):
```python
# Around line 237 in the BASE_SYSTEM_INSTRUCTIONS string
# Change:
Critical paths: src/services/**, src/middleware/**, packages/shared/**

# To match your structure, e.g.:
Critical paths: backend/core/**, services/payments/**, infrastructure/**
```

In **`.github/workflows/antigravity-review.yml`** (the shell path-filter step):
```bash
# Change the critical_pattern variable to match your directories
critical_pattern='^(src/(services|middleware)|packages/shared)'
```

---

## Step 6 — Authenticate the GitHub CLI in CI (optional)

The composite action uses the `GITHUB_TOKEN` from the Actions runtime, so
**no extra `gh auth` step is needed** for same-repo PRs. However, if you need
the `gh` CLI in your own additional steps:

```yaml
- name: 'Authenticate GitHub CLI'
  shell: bash
  run: echo "${{ secrets.GITHUB_TOKEN }}" | gh auth login --with-token
```

For cross-repository operations, create a GitHub App or a Personal Access Token
(PAT) with `pull-requests: write` and `contents: read` scopes, add it as a
repository secret (e.g. `GH_PAT`), and pass it as `github-token`:

```yaml
- uses: your-org/agy-pr-review@main
  with:
    api-key: '${{ secrets.ANTIGRAVITY_API_KEY }}'
    github-token: '${{ secrets.GH_PAT }}'
```

---

## How it works

### Workflow triggers

| Event | Behaviour |
|---|---|
| `pull_request` (opened / reopened) | Runs path filter → runs review if not docs-only |
| `issue_comment` containing `@agy /review` | Runs on-demand review; restricted to repo owners, members, and collaborators |
| `workflow_dispatch` | Manual trigger; accepts optional PR number |

### Docs-only skip logic

The `path-filter` job classifies every changed file against these patterns:

```
Documentation pattern : ^(docs/|.*\.(md|mdx|rst|txt|LICENSE|CHANGELOG|CONTRIBUTING))$
TypeScript pattern     : \.(ts|tsx|js|jsx|mts|cts)$
Critical-path pattern  : ^(src/(services|middleware)|packages/shared)
```

If **every** changed file matches the documentation pattern, the review job is
skipped and the agent posts a short notice on the PR explaining why.

### Policy flags

The `path-filter` job passes flags to the agent via `ADDITIONAL_CONTEXT`:

| Flag | Set when | Agent behaviour |
|---|---|---|
| `ENFORCE_TS_TYPE_SAFETY=true` | TS/JS files detected | Maximum strictness; every `any` is a BLOCKER |
| `FLAG_PERF_REGRESSIONS=true` | Critical-path files detected | Big-O analysis required for all changed functions |
| `ENFORCE_SECURITY_COMPLIANCE=true` | Critical-path files detected | Cross-reference all dependency changes against the GitHub Advisory Database |
| `ENFORCE_TEST_COVERAGE=true` | Any new `export` keyword detected in the diff | Treat every new exported function with no test as a `[TEST-MISSING]` BLOCKER |

### Safety policies (sandboxing)

The agent runs under a minimal allow-list in review mode — it cannot execute
shell commands or write to the filesystem:

```python
policy.deny_all()              # Block everything by default
policy.allow(github_mcp)       # Allow GitHub MCP tools only
policy.allow("view_file")      # Read-only workspace access
policy.allow("find_file")
policy.allow("search_file_content")
policy.allow("list_directory")
```

---

## Policy 4 — Unit Test Coverage

Policy 4 applies to **every PR**, regardless of which directories were changed.
It scans the diff for new `export` keywords and verifies that a matching test
file is included in the same PR.

### What it checks

| Trigger | Severity | Tag |
|---|---|---|
| New `export function`, `export const`, `export class`, or `export default` with no corresponding test | BLOCKER | `[TEST-MISSING]` |
| Exported function with changed signature/return type and no updated test | BLOCKER | `[TEST-MISSING]` |
| Tests exist but only cover the happy path (no error/edge cases) | WARNING | `[TEST-WARNING]` |

### Accepted test file locations

The agent accepts any of the following relative to the source file:

```
src/services/auth.ts          →  src/services/auth.test.ts
                                  src/services/auth.spec.ts
                                  src/services/__tests__/auth.test.ts
                                  src/services/__tests__/auth.spec.ts
```

Same conventions apply for `.tsx`, `.js`, and `.jsx` extensions.

### What is NOT flagged

- Internal (non-exported) helpers and private class members
- Type aliases, `interface`, `enum`, and pure re-exports (`export { x } from`)
- Files that are themselves test files (`*.test.*`, `*.spec.*`, `__tests__/**`)
- Existing exported functions that are **not modified** in the current PR

### How it is activated

The path-filter job detects `export` keywords in changed files and sets
`ENFORCE_TEST_COVERAGE=true` in `ADDITIONAL_CONTEXT`. The agent's
`_build_policy_addendum()` function reads this flag and injects targeted
instructions. If the flag is absent (e.g. a docs-only PR), the base
`BASE_SYSTEM_INSTRUCTIONS` still include the policy — it is always enforced.

### Verdict impact

Any `[TEST-MISSING]` finding triggers `event="REQUEST_CHANGES"` in the posted
review. The PR cannot be approved by the agent until all new exported functions
have a corresponding test in the same PR.

---

## Customising the review prompt

Edit `.github/commands/antigravity-review.toml` to add project-specific rules.
The `prompt` field is the agent's system instructions, interpolated with
environment variables using `!{ echo $VAR_NAME }` syntax.

```toml
prompt = """
... existing policies ...

═══════════════════════════════════════════════════════════════
POLICY 5 — Your Custom Policy
═══════════════════════════════════════════════════════════════
Applies to: src/payments/

Flag as [CUSTOM-BLOCKER] when:
  • Payment amounts are calculated without Decimal arithmetic
  • PCI DSS cardholder fields are logged
"""
```

---

## Triggering an on-demand review

Post a comment on any open PR:

```
@agy /review
```

Only users with `OWNER`, `MEMBER`, or `COLLABORATOR` association can trigger
this. The workflow checks `github.event.comment.author_association`.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `API key is missing` error | Secret not set or wrong name | Verify `ANTIGRAVITY_API_KEY` exists in repo secrets |
| `Docker daemon not available` | Self-hosted runner without Docker | Use `ubuntu-latest` or install Docker on your runner |
| Review triggered for fork PRs | `pull_request_target` used | Keep `pull_request` trigger; fork PRs use comment trigger |
| Infinite review loop | `synchronize` trigger present | Remove `synchronize` from `pull_request.types` |
| Agent posts no comments | GitHub token missing `pull-requests: write` | Add permission to the workflow job |
| TOML file not found warning | `.github/commands/` directory missing | Ensure the directory and TOML file are committed |

---

## Security notes

- The API key is stored only in GitHub Secrets and never logged.
- The GitHub MCP server runs inside an ephemeral Docker container that is
  removed after each run (`--rm` flag).
- `persist-credentials: false` on the checkout step prevents the GITHUB_TOKEN
  from being written to disk.
- Fork PRs cannot trigger automatic reviews — they must be initiated by a
  maintainer via comment or `workflow_dispatch`.
- Pin both this action and `rsamborski/run-agy-sdk` to specific commit SHAs
  in production to prevent supply-chain attacks.
