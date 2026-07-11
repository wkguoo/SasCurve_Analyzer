# Issue tracker: GitHub

Issues and PRDs for this repository live as GitHub Issues in `wkguoo/SasCurve_Analyzer`. Use the `gh` CLI for issue operations when a skill requires tracker interaction.

## Conventions

- Create an issue: `gh issue create --title "..." --body "..."`.
- Read an issue: `gh issue view <number> --comments`.
- List issues: `gh issue list --state open` with the required label/filter options.
- Comment, label, or close: use `gh issue comment`, `gh issue edit`, and `gh issue close`.

## Pull requests as a triage surface

PRs as a request surface: no.

## Skill mapping

When an engineering skill says to publish a ticket, create a GitHub Issue. When it says to fetch a ticket, use `gh issue view <number> --comments` from this repository.
