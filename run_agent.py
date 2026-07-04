#!/usr/bin/env python3
# Copyright 2026 Google LLC
# Apache-2.0 License
#
# run_agent.py — Antigravity SDK PR Review Agent
# ─────────────────────────────────────────────────────────────────────────────
# Custom review policies enforced by this agent:
#
#   1. TypeScript type safety
#      • Flags `any`, missing return types, implicit `any` from untyped function
#        parameters, and disabled strictness directives (ts-ignore, ts-expect-error).
#
#   2. Performance regression detection (critical paths)
#      • Inspects files under src/services, src/middleware, and packages/shared
#        for O(n²) loops, synchronous I/O
#        in async contexts, unbounded cache growth, and removed memoization.
#
#   3. Security compliance
#      • Checks for hardcoded secrets, eval/exec usage, missing input sanitisation,
#
#   4. Unit test coverage
#      • Flags new exported functions with no corresponding test file in the same PR.
#
#      Security detail: checks for insecure crypto primitives, SSRF-prone URL
#        construction, SQL injection patterns, and CVE advisories on dependencies.
#
# Environment variables consumed (set by action.yml):
#   ANTIGRAVITY_API_KEY / GEMINI_API_KEY  – required
#   GITHUB_TOKEN / GITHUB_PERSONAL_ACCESS_TOKEN – required
#   PULL_REQUEST_NUMBER / GITHUB_PR_NUMBER – PR to review
#   REPOSITORY / GITHUB_REPOSITORY        – owner/repo
#   ADDITIONAL_CONTEXT                    – policy flags injected by workflow
#   PROMPT                                – command string (e.g. /antigravity-review)
#   TRUST_WORKSPACE                       – "true" | "false"
#   GITHUB_OUTPUT                         – path for composite action outputs
# ─────────────────────────────────────────────────────────────────────────────

import asyncio
import os
import re
import sys
import uuid

# ── SDK import ────────────────────────────────────────────────────────────────
try:
    from google.antigravity import Agent, LocalAgentConfig, types
    from google.antigravity.hooks import policy
except ImportError:
    print(
        "::error::Google Antigravity SDK is not installed. "
        "Run: pip install google-antigravity"
    )
    sys.exit(1)

# ── TOML parser with graceful fallback ───────────────────────────────────────
try:
    import tomllib

    def _load_toml(f) -> dict:
        return tomllib.load(f)

except ImportError:
    try:
        import tomli  # type: ignore

        def _load_toml(f) -> dict:
            return tomli.load(f)

    except ImportError:
        class _SimpleToml:
            @staticmethod
            def load(f) -> dict:
                content = f.read().decode("utf-8")
                data: dict = {}
                m = re.search(r'prompt\s*=\s*"""(.*?)"""', content, re.DOTALL)
                if m:
                    data["prompt"] = m.group(1).strip()
                m2 = re.search(r'description\s*=\s*["\'](.+?)["\']', content)
                if m2:
                    data["description"] = m2.group(1).strip()
                return data

        def _load_toml(f) -> dict:
            return _SimpleToml.load(f)


# ─────────────────────────────────────────────────────────────────────────────
# System prompt: adversarial code auditor persona
# ─────────────────────────────────────────────────────────────────────────────
BASE_SYSTEM_INSTRUCTIONS = """\
You are an expert, adversarial code auditor embedded inside a CI pipeline.
Your sole purpose is to review pull request changes with maximum rigour before
they reach production. You have NO interest in being encouraging or diplomatic —
you surface every concrete risk, defect, and standards violation you find.

## Review Priorities (apply in order)

### 1 · TypeScript Type Safety  (CRITICAL — always enforce)
Examine every `.ts`, `.tsx`, `.js`, `.jsx`, `.mts`, and `.cts` file in the diff.
Flag any of the following as BLOCKER severity:
- Explicit `any` type annotations or casts
- Missing return-type annotations on exported functions/methods
- Implicit `any` caused by untyped function parameters
- `@ts-ignore` or `@ts-expect-error` directives that suppress real errors
- `as unknown as T` double-cast patterns used to bypass the type system
- Disabled tsconfig strictness flags (strict, noImplicitAny, strictNullChecks)
For each finding output:
  [TS-SAFETY] <file>:<line> — <description> — Suggested fix: <fix>

### 2 · Performance Regression Detection  (applied to CRITICAL PATHS only)
Critical paths: src/services/**, src/middleware/**, packages/shared/**.
Flag as PERF-REGRESSION severity when you detect:
- O(n²) or worse algorithmic complexity introduced in hot loops
- Synchronous file I/O or network calls inside async/event-loop contexts
- Unbounded in-memory caches (no TTL, no max-size)
- Removal of memoization, caching layers, or rate-limiting logic
- Unnecessary re-renders in React components (missing useMemo/useCallback)
- Database queries inside loops without batching
For each finding output:
  [PERF] <file>:<line> — <description> — Impact: <estimated impact>

### 3 · Security Compliance  (CRITICAL — always enforce)
Flag as SECURITY severity when you detect:
- Hardcoded secrets, tokens, passwords, or private keys
- `eval()`, `exec()`, `Function()`, or `new Function()` usage
- Unsanitised user input passed to SQL, shell commands, or file paths
- Insecure crypto: MD5/SHA1 for password hashing, ECB mode, weak key sizes
- SSRF-prone patterns: user-controlled URLs passed to fetch/axios/http.request
- Open redirect vulnerabilities
- Missing CSRF protection on state-mutating endpoints
- Dependency additions — cross-reference against the GitHub Advisory Database;
  flag any package with a known CVE at HIGH or CRITICAL severity
For each finding output:
  [SECURITY] <file>:<line> — <description> — CVE/reference: <if applicable>

### 4 · Unit Test Coverage  (applied to all new public functions)
For every new public function, method, or component introduced in the diff,
verify that a corresponding unit test exists in the same PR.

#### TypeScript / JavaScript (`*.ts`, `*.tsx`, `*.js`, `*.jsx`, `*.mts`, `*.cts`)
Coverage is required for any newly added line matching:
  `export function`, `export const`, `export class`, `export default`,
  or `export async function`.
Accepted test file locations (relative to the source file):
  - `<name>.test.ts` / `<name>.spec.ts` / `<name>.test.tsx` / `<name>.spec.tsx`
  - `<name>.test.js` / `<name>.spec.js`
  - `__tests__/<name>.test.*` adjacent to the source file

#### Python (`*.py`)
Coverage is required for any newly added top-level `def` or `class` statement
that is NOT preceded by a leading underscore (i.e. it is public by convention).
Accepted test file locations:
  - `test_<module>.py` or `<module>_test.py` in the same directory
  - `tests/test_<module>.py` one level up
  - Any file matching `test_*.py` or `*_test.py` inside a `tests/` directory
    adjacent to the source
Do NOT flag Python `def` inside a class body as requiring its own separate test
file — coverage at the class level is sufficient.

#### Both language families
Flag as BLOCKER severity when:
- A new public symbol is added with no corresponding test case covering its
  primary code path in the same PR.
- An existing public symbol is refactored (signature change, return-type change)
  and no updated test is included in the PR.
Flag as WARNING severity when:
- Tests exist but clearly cover only the happy path (no error, edge, or boundary
  case assertions).
For each finding output:
  [TEST-MISSING] <source-file>:<line> — `<symbolName>` — No test found in <expected-test-file>
  [TEST-WARNING]  <source-file>:<line> — `<symbolName>` — Tests present but edge cases not covered
Do NOT flag:
- Private symbols: names starting with `_` (Python) or marked `private`/`#` (TS)
- Type aliases, `interface`, `enum`, or pure re-exports (`export { x } from`)
- Files that are themselves test files (`*.test.*`, `*.spec.*`, `__tests__/**`,
  `test_*.py`, `*_test.py`, `tests/**`)
- Existing symbols that are unchanged in this PR

## Output Format
Structure your review as follows:

### Summary
One paragraph describing the PR's intent and your overall risk assessment.

### Findings
List each finding using the tagged format above, grouped by severity:
  BLOCKER → TEST-MISSING → SECURITY → PERF-REGRESSION → WARNING → INFO

### Verdict
One of: APPROVE | REQUEST_CHANGES | NEEDS_DISCUSSION
Followed by a one-line rationale.

## Hard Rules
- Never approve a PR that has unresolved BLOCKER, TEST-MISSING, or SECURITY findings.
- Do not speculate; only report what you can confirm from the diff or file contents.
- Always use the GitHub MCP tools to fetch file contents — do not hallucinate code.
- Post your findings as a structured PR review via pull_request_review_write.
"""


# ─────────────────────────────────────────────────────────────────────────────
# Custom policy-aware addendum injected from workflow context
# ─────────────────────────────────────────────────────────────────────────────
def _build_policy_addendum(additional_context: str) -> str:
    """
    Parse the ADDITIONAL_CONTEXT flag string injected by the workflow and
    append targeted instructions when specific policy flags are set.
    """
    lines: list[str] = []

    if "ENFORCE_TS_TYPE_SAFETY=true" in additional_context:
        lines.append(
            "\n## Active Policy Override: TypeScript Type Safety (ENFORCED)\n"
            "The diff contains TypeScript/JavaScript files. Apply §1 of your review "
            "priorities with MAXIMUM strictness. Treat every `any` usage as a BLOCKER "
            "regardless of surrounding context."
        )

    if "FLAG_PERF_REGRESSIONS=true" in additional_context:
        lines.append(
            "\n## Active Policy Override: Performance Regression (ENFORCED)\n"
            "The diff touches critical-path directories. Perform a detailed algorithmic "
            "complexity analysis on every changed function. Include Big-O estimates."
        )

    if "ENFORCE_SECURITY_COMPLIANCE=true" in additional_context:
        lines.append(
            "\n## Active Policy Override: Security Compliance (ENFORCED)\n"
            "The diff touches security-sensitive paths. Cross-reference every dependency "
            "change against the GitHub Advisory Database. Flag any package with a known "
            "HIGH or CRITICAL CVE as a BLOCKER."
        )

    if "ENFORCE_TEST_COVERAGE=true" in additional_context:
        lines.append(
            "\n## Active Policy Override: Unit Test Coverage (ENFORCED)\n"
            "The diff contains new public symbols (TypeScript exports or Python def/class). "
            "Apply Policy 4 with MAXIMUM strictness:\n"
            "  • TypeScript/JS: flag every new `export function`, `export const`, "
            "`export class`, `export default`, or `export async function` that has no "
            "matching `*.test.ts`, `*.spec.ts`, `*.test.tsx`, `*.spec.tsx`, `*.test.js`, "
            "`*.spec.js`, or `__tests__/` test in this PR.\n"
            "  • Python: flag every new top-level `def <name>` or `class <name>` where "
            "`<name>` does NOT start with `_`, and no `test_<module>.py`, "
            "`<module>_test.py`, or `tests/test_<module>.py` file is present in this PR.\n"
            "Flag any missing test as [TEST-MISSING] BLOCKER. "
            "Skip private symbols, type-only exports, re-exports, test files themselves, "
            "and symbols unchanged in this PR."
        )

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# GitHub MCP server configuration
# ─────────────────────────────────────────────────────────────────────────────
def _build_github_mcp() -> types.McpStdioServer:
    return types.McpStdioServer(
        name="github",
        command="docker",
        args=[
            "run", "-i", "--rm",
            "-e", "GITHUB_PERSONAL_ACCESS_TOKEN",
            "ghcr.io/github/github-mcp-server:v0.27.0",
        ],
        enabled_tools=[
            # PR review tools
            "add_comment_to_pending_review",
            "pull_request_read",
            "pull_request_review_write",
            # Issue / comment tools
            "add_issue_comment",
            "issue_read",
            "list_issues",
            "search_issues",
            # PR navigation
            "list_pull_requests",
            "search_pull_requests",
            # Code reading
            "get_commit",
            "get_file_contents",
            "list_commits",
            "search_code",
        ],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Safety policies
# ─────────────────────────────────────────────────────────────────────────────
def _build_review_policies(github_mcp: types.McpStdioServer) -> list:
    """
    Minimal allow-list policy for review mode:
      • Deny everything by default (no shell execution, no filesystem writes)
      • Allow GitHub MCP tools (read PR, post review)
      • Allow read-only file operations within the workspace
    """
    return [
        policy.deny_all(),
        policy.allow(github_mcp),
        policy.allow("view_file"),
        policy.allow("find_file"),
        policy.allow("search_file_content"),
        policy.allow("list_directory"),
    ]


def _build_goal_policies(trust_workspace: bool) -> list:
    """Policy set for general goal/one-shot mode."""
    if trust_workspace:
        return [policy.allow_all()]
    return policy.confirm_run_command()


# ─────────────────────────────────────────────────────────────────────────────
# TOML command loading with variable interpolation
# ─────────────────────────────────────────────────────────────────────────────
def _load_command(
    command_name: str,
    action_path: str,
    env_context: dict[str, str],
) -> str | None:
    """
    Load a .toml command file from .github/commands/<name>.toml and interpolate
    environment variables using the !{ echo $VAR_NAME } syntax.
    Returns the interpolated prompt string, or None if the file does not exist.
    """
    # Guard against path traversal
    if ".." in command_name or "/" in command_name or "\\" in command_name:
        print(f"::error::Invalid command name: {command_name!r}")
        sys.exit(1)

    command_file = os.path.join(action_path, ".github", "commands", f"{command_name}.toml")
    if not os.path.exists(command_file):
        return None

    print(f"Loading custom command config from: {command_file}")
    with open(command_file, "rb") as f:
        data = _load_toml(f)

    raw_prompt: str = data.get("prompt", "")

    def _replace(match: re.Match) -> str:
        return env_context.get(match.group(1), "")

    return re.sub(r"!\{\s*echo\s+\$([A-Za-z0-9_]+)\s*\}", _replace, raw_prompt)


# ─────────────────────────────────────────────────────────────────────────────
# Write outputs back to the composite action
# ─────────────────────────────────────────────────────────────────────────────
def _write_github_output(full_text: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    delimiter = f"EOF_{uuid.uuid4().hex}"
    try:
        with open(output_path, "a", encoding="utf-8") as f:
            f.write(f"response<<{delimiter}\n{full_text}\n{delimiter}\n")
            f.write("stats={}\n")
    except OSError as exc:
        print(f"Warning: Could not write to GITHUB_OUTPUT: {exc}", file=sys.stderr)


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────
async def main() -> None:
    # ── 1. Collect environment variables ─────────────────────────────────────
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("ANTIGRAVITY_API_KEY")
    github_token = (
        os.environ.get("GITHUB_TOKEN")
        or os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")
    )
    pr_number = os.environ.get("PULL_REQUEST_NUMBER") or os.environ.get("GITHUB_PR_NUMBER")
    repository = os.environ.get("REPOSITORY") or os.environ.get("GITHUB_REPOSITORY")
    additional_context = os.environ.get("ADDITIONAL_CONTEXT", "")
    prompt_text = os.environ.get("PROMPT", "").strip()
    trust_workspace = os.environ.get("TRUST_WORKSPACE", "false").lower() == "true"
    action_path = os.environ.get("GITHUB_ACTION_PATH", "")

    if not api_key:
        print("::error::API key missing. Set ANTIGRAVITY_API_KEY or GEMINI_API_KEY.")
        sys.exit(1)

    if not github_token:
        print("::error::GitHub token missing. Set GITHUB_TOKEN.")
        sys.exit(1)

    # Propagate token so the Docker MCP process inherits it
    os.environ["GITHUB_PERSONAL_ACCESS_TOKEN"] = github_token

    # ── 2. Build system instructions ─────────────────────────────────────────
    system_instructions = BASE_SYSTEM_INSTRUCTIONS
    chat_prompt = prompt_text
    is_review_mode = prompt_text.startswith("/")

    if is_review_mode:
        command_name = prompt_text[1:]
        env_context = {
            **os.environ,
            "REPOSITORY": repository or "",
            "PULL_REQUEST_NUMBER": pr_number or "",
            "ISSUE_NUMBER": os.environ.get("GITHUB_ISSUE_NUMBER", ""),
            "ADDITIONAL_CONTEXT": additional_context,
        }

        loaded = _load_command(command_name, action_path, env_context)
        if loaded:
            # Command file provides its own instructions; augment with policies
            system_instructions = loaded
        else:
            print(
                f"Warning: .github/commands/{command_name}.toml not found. "
                "Falling back to built-in review instructions."
            )

        # Append runtime policy overrides derived from the workflow context
        policy_addendum = _build_policy_addendum(additional_context)
        if policy_addendum:
            system_instructions += policy_addendum

        # Provide PR-specific context in the chat turn
        chat_prompt = (
            f"Run the command: {prompt_text}\n\n"
            f"Repository: {repository}\n"
            f"PR number: {pr_number}\n"
            f"Additional context: {additional_context}"
        )
    else:
        # Non-review goal/one-shot: inject context as a preamble
        if additional_context:
            chat_prompt = f"Context: {additional_context}\n\nTask: {prompt_text}"

    # ── 3. Configure MCP + policies ───────────────────────────────────────────
    github_mcp = _build_github_mcp()

    if is_review_mode:
        policies = _build_review_policies(github_mcp)
    else:
        policies = _build_goal_policies(trust_workspace)

    # ── 4. Initialize agent ───────────────────────────────────────────────────
    config = LocalAgentConfig(
        api_key=api_key,
        system_instructions=system_instructions,
        mcp_servers=[github_mcp],
        policies=policies,
        workspaces=[os.getcwd()],
    )

    print("=" * 60)
    print("Starting Antigravity Agent")
    print(f"  Repository : {repository}")
    print(f"  PR number  : {pr_number}")
    print(f"  Mode       : {'review' if is_review_mode else 'goal'}")
    print(f"  Trust ws   : {trust_workspace}")
    print("=" * 60)

    async with Agent(config) as agent:
        response = await agent.chat(chat_prompt)

        print("\n::: Agent Response Start :::")
        tokens: list[str] = []
        async for token in response:
            sys.stdout.write(token)
            sys.stdout.flush()
            tokens.append(token)
        print("\n::: Agent Response End :::")

        _write_github_output("".join(tokens))


if __name__ == "__main__":
    asyncio.run(main())
