# GitHub Actions disabled (Mosca Nero Digital)

Workflow YAML files were removed from this repository on **2026-07-07** as part of an org-wide policy: **no billable GitHub Actions minutes** on `moscanerodigital` repositories.

- Repository setting: **Actions disabled** (`PUT .../actions/permissions` → `enabled: false`).
- Do **not** re-add `.yml` / `.yaml` workflow files here without explicitly re-enabling Actions and accepting billing risk.

## Run checks locally

Use each project’s README or package scripts (e.g. `npm test`, `pytest`, `make verify`). This repo’s historical CI steps are not run on GitHub anymore.

## Re-enabling (owners only)

1. Org billing: confirm Actions spend limit is acceptable.
2. Re-enable Actions on the repo via GitHub Settings → Actions.
3. Restore workflows from git history if needed.

