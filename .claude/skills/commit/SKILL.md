---
name: commit
description: Prepare and execute Git commits safely, in a standardized and controlled way. Use whenever the user asks to commit, create a commit, or run `/commit` — runs a mandatory branch check, staging check, secret/sensitive-data scan, auto-classification, and message generation before ever calling `git commit`, and never commits without explicit user confirmation.
---

# commit

Turn "make a commit" into a controlled pipeline that never runs `git commit` blind. The
guiding principle: **never commit what has not been inspected, never commit suspected
secrets, and always know which branch you are committing to.** Security, traceability and
consistency always outrank speed.

This skill is the standardized commit workflow for **F1Scope**. Follow the steps below in
order. Stop immediately on any critical security or validation failure. Do not skip steps
to save time.

## Commit granularity — atomic commits only

Commits must be **atomic**: each commit captures one focused, self-contained change — one
new implementation, one bug fix, one issue/milestone item resolved or advanced — never a
bundle of unrelated work accumulated over a whole stage/phase of the project.

- Never batch multiple unrelated changes, issues, or milestone items into a single commit
  just because they landed in the same session or the same day. A "commit everything from
  this stage" request is not a request for one giant commit — split it.
- Before staging, look at what's actually modified (`git status --short`) and group it into
  the smallest set of coherent, self-contained changes. If what's currently staged spans
  more than one logical change, stop and propose splitting it: unstage the unrelated files
  (`git restore --staged <file>`) and commit each group separately instead of writing one
  commit that covers all of it.
- When a commit resolves or advances a tracked GitHub issue, reference it in the commit body
  (e.g. `Refs #12`, or `Closes #12` when it fully resolves the issue) so history stays
  traceable back to the issue/milestone it belongs to.
- A commit's diff should read as one coherent unit of work: someone reviewing `git show
  <hash>` should be able to describe it in a single sentence without an "and also...".

## Pipeline

```
Inspect repository
       ↓
Validate current branch
       ↓
Check protected / detached branch
       ↓
Check staging
       ↓
Security scan
       ↓
Sensitive-data detection
       ↓
Analyze changes
       ↓
Determine commit type
       ↓
Generate standardized message
       ↓
Show complete preview
       ↓
User confirmation
       ↓
git commit
       ↓
Post-commit validation
```

## 1. Repository validation

- Confirm the current directory is a Git repository (`git rev-parse --is-inside-work-tree`
  or equivalent). If it is not, stop and clearly tell the user.
- Run `git status --short` to see the overall state.

## 2. Branch validation

- Get the current branch with `git branch --show-current`.
- Always show the current branch explicitly to the user.

**Protected branches** (minimum list, extendable if the repo's own conventions define
more): `main`, `master`, `production`, `prod`, `release`. F1Scope currently only has
`main`, so in practice almost every direct commit will hit this check until feature
branches are in regular use.

- If the current branch is protected: do **not** commit automatically. Show a clear
  warning (see template below) and ask for explicit confirmation, separate from the final
  commit confirmation.

  ```
  ⚠ Branch validation

  Current branch: main

  WARNING:
  You are attempting to commit directly to a protected branch.

  Protected branches:
  - main
  - master
  - production
  - prod
  - release

  Direct commits to protected branches may bypass the expected
  feature/fix/review workflow.

  Do you explicitly want to continue? [y/N]
  ```

- If the branch is not protected, continue normally. Optionally show:

  ```
  ✓ Branch validation passed

  Current branch: feature/3d-replay-track-loader
  ```

- **Detached HEAD**: if `git branch --show-current` returns nothing, check for detached
  HEAD. If detected, warn, do not commit automatically, explain the commit may end up
  unreferenced, and ask for explicit confirmation:

  ```
  ⚠ Branch validation

  Repository is currently in detached HEAD state.

  Committing now will create a commit that is not attached
  to a normal branch unless it is subsequently referenced.

  Do you explicitly want to continue? [y/N]
  ```

- **Never** create or switch branches automatically, and never run `git checkout`,
  `git switch`, merge, or rebase on behalf of the user. If a different branch looks more
  appropriate, say so and stop or ask for explicit authorization — do not act on it
  yourself.

## 3. Staging validation

- Check for staged files with `git diff --cached --name-only`.
- If nothing is staged: do not run `git commit`. Tell the user there is nothing staged,
  optionally show unstaged modified files, and tell them to `git add` first.
- **Never** run `git add .`, `git add -A`, or stage anything automatically without
  explicit user authorization.

## 4. Inspect staged content only

- Analyze `git diff --cached` — the security review must look at what will actually be
  committed, not just filenames.
- Do not treat `.gitignore`'d status as a proxy for safety (a file can be staged despite
  matching `.gitignore` rules, or rules can be wrong).
- Inspect file **content**, not just names.

## 5. Sensitive-data detection

Scan the staged diff thoroughly for, at minimum:

- **Credentials**: password, pass, passwd, pwd, username/password pairs, database
  credentials, login credentials (e.g. `password=...`, `DB_PASSWORD=...`,
  `"password": "..."`).
- **API keys/tokens**: API keys/tokens, access tokens, auth tokens, bearer tokens, private
  tokens, client secrets, application secrets (e.g. `API_KEY=...`, `API_SECRET=...`,
  `ACCESS_TOKEN=...`, `AUTH_TOKEN=...`). For F1Scope specifically, watch for an
  **OpenF1 sponsor-tier API key** if/when the project upgrades from the free tier
  (`OPENF1_API_KEY=...` or similar).
- **App secrets**: `SECRET_KEY`, `DJANGO_SECRET_KEY`, `FLASK_SECRET_KEY`, `CLIENT_SECRET`,
  `APP_SECRET`, `ENCRYPTION_KEY`, `SIGNING_KEY`.
- **Cloud/provider credentials**: AWS, Azure, GCP, GitHub, GitLab, Docker registries,
  Cloudinary, Firebase, Supabase, OpenAI, Anthropic, Stripe, Twilio — and don't limit
  detection to only this list; look for any provider-shaped credential.
- **Crypto material**: JWTs, bearer/OAuth tokens, SSH/RSA/OpenPGP private keys, private
  certificates, blocks like `-----BEGIN PRIVATE KEY-----`, `-----BEGIN RSA PRIVATE
  KEY-----`, `-----BEGIN OPENSSH PRIVATE KEY-----`.
- **Dangerous files staged**: `.env`, `.env.*`, `*.pem`, `*.key`, `*.p12`, `*.pfx`,
  `credentials.json`, `secrets.json`, `service-account.json`, and equivalent/variant names.

Also watch for **confidential-but-not-a-secret** information: physical addresses, emails,
phone numbers, private IPs, internal server/hostnames, internal URLs, corporate domains,
database names, connection strings, sensitive internal paths, customer/account
identifiers, financial data, personal data, proprietary company information. Distinguish
clearly-public info (e.g. `https://github.com/AbimaelFranco/F1Scope`, `https://api.openf1.org`)
from likely-confidential info (e.g. internal deployment URLs, private Docker registry
paths, personal cache/log files that leaked into the diff).

Use heuristics beyond plain regex: suspicious variable names (`password`, `passwd`,
`secret`, `token`, `api_key`, `apikey`, `access_key`, `private_key`, `client_secret`,
`auth_token`, `database_url`, `connection_string`, `credentials`), key-like patterns,
string entropy, known token formats, file extensions/names, surrounding code context,
URLs/hostnames, comments, and config files. A line like `password = "..."` must raise an
alert even if the value doesn't match any known API-key format.

### Severity and action

| Severity | Examples | Action |
|---|---|---|
| CRITICAL | Secrets, passwords, API keys, private keys, valid tokens/credentials | **Block the commit** |
| HIGH | Internal servers, partially exposed credentials, DB connection strings, `.env` files, private infra info | **Block the commit and request review** |
| MEDIUM | Potentially sensitive info that may be legitimate depending on context | Warn and require explicit confirmation |
| LOW | Likely false positives / probably-not-sensitive info | Inform, but allow to continue |

### Handling detected secrets

- Never print a full secret. Show a redacted form only, e.g. `API_KEY=sk-proj-************************`.
- For each finding: block the commit, identify file and approximate line, show the secret
  type, show the redacted value, and explain how to unstage it, e.g.:

  ```bash
  git restore --staged archivo.env
  ```

- If the secret may already exist elsewhere in history, warn that unstaging it does **not**
  mean it's no longer exposed in Git history. Never rewrite history automatically to fix
  this.

## 6. Determine commit type

Once security checks pass, infer the commit category from the actual diff (not just
filenames) — what was added/removed/modified, the apparent purpose, tests, docs, UI
changes, bug fixes. Use exactly one of:

- `feat` — new functionality/capability (e.g. `feat: add 3D track location renderer`)
- `bugfix` — fixes incorrect behavior (e.g. `bugfix: fix lap time parsing for out-laps`)
- `refactor` — internal changes with no new functionality or direct bug fix (e.g.
  `refactor: simplify OpenF1 client request handling`)
- `test` — adds/modifies tests (e.g. `test: add unit tests for telemetry cache service`)
- `doc` — documentation (e.g. `doc: update API integration notes`)
- `design` — visual/UX/UI or visual-architecture changes (e.g. `design: apply cyberpunk
  HUD theme to replay controls`)

If several kinds of change are mixed, pick the category that best represents the primary
purpose. If it truly can't be determined, ask the user instead of guessing.

## 7. Generate the commit message

Format (in English by default, consistent across the repo):

```
<type>: <short description>

- <change 1>: <reason>
- <change 2>: <reason>
- <change 3>: <reason>
```

Example:

```
feat: add driver telemetry comparison chart

- Add speed/throttle/brake comparison chart: let users contrast two drivers over a lap
- Add OpenF1 car_data client method: fetch telemetry samples for a session/driver
- Add in-memory cache for car_data responses: stay within OpenF1's free-tier rate limits
```

The first line is short and names the main change. Each bullet states what changed and
why — be specific. Never write generic bullets like "Updated files", "Made improvements",
"Fixed code".

## 8. Preview and confirmation

Before running `git commit`, show a full preview:

```
Commit validation
-----------------
Branch: feature/telemetry-comparison-chart

Staged files:
- app/services/openf1_client.py
- app/static/js/charts/telemetry_compare.js
- tests/test_openf1_client.py

Security scan:
✓ No credentials detected
✓ No API keys detected
✓ No private keys detected
✓ No suspicious configuration files detected
✓ No obvious confidential information detected

Commit type:
feat

Commit message:
feat: add driver telemetry comparison chart

- Add speed/throttle/brake comparison chart: let users contrast two drivers over a lap
- Add OpenF1 car_data client method: fetch telemetry samples for a session/driver
- Add in-memory cache for car_data responses: stay within OpenF1's free-tier rate limits
```

Then ask:

```
Proceed with this commit? [y/N]
```

Do not run `git commit` until this explicit confirmation is given (separate from the
branch-protection/detached-HEAD confirmations, if those triggered).

## 9. Execute the commit

After confirmation:

```bash
git commit -m "<subject>" -m "<body>"
```

Check the result. If it fails, show the error, do not attempt to auto-fix anything
potentially destructive, and report that the commit was not created.

## 10. Post-commit validation

After a successful commit, show:

```
Commit created successfully.

Commit:
a81f32c feat: add driver telemetry comparison chart

Branch:
feature/telemetry-comparison-chart

Files committed:
- app/services/openf1_client.py
- app/static/js/charts/telemetry_compare.js
- tests/test_openf1_client.py

Repository status:
Working tree clean.
```

(commit hash via `git log -1 --oneline`/`git rev-parse --short HEAD`, files via
`git show --name-only`, and repo status via `git status`.)

## Hard rules — never violate these

1. Never run `git commit` with nothing staged.
2. Never run `git add` automatically.
3. Never ignore a CRITICAL finding.
4. Never deliberately include secrets in a commit.
5. Never print full secrets on screen — always redact.
6. Never assume `.gitignore` makes a file safe.
7. Always analyze the real staged content, not just filenames.
8. Never rewrite history automatically.
9. Never use `--no-verify` to skip hooks.
10. Never perform destructive operations without explicit authorization.
11. If there's reasonable doubt about confidential information, stop and ask for review.
12. Always validate the branch before committing.
13. Always warn and require explicit confirmation for commits directly on a protected branch.
14. Always warn and require explicit confirmation in detached HEAD state.
15. Never switch branches automatically.
16. Security always takes priority over completing the commit.
17. Never bundle multiple unrelated changes/issues into a single commit — keep commits
    atomic, one logical change at a time, and traceable to the issue/milestone it advances.
