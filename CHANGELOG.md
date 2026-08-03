## v4.6.0 — Projection readiness and salary safeguards

### Added
- Blocks optimization when the active pool has no usable projections.
- Verifies positive projection coverage by roster position.
- Verifies ceiling, floor, and ownership coverage when the selected strategy uses them.
- Displays projection-readiness errors and warnings directly on Optimizer.

### Changed
- Default minimum salary is now $49,000 for the standard $50,000 cap.
- The minimum remains editable for unusual slates and deliberate salary-leaving strategies.

## v4.5.0 — Single-upload DraftKings workflow

### Changed
- `DKEntries.csv` is now uploaded once on Weekly Update.
- Weekly Update extracts the reserved entries, contest metadata, DraftKings IDs,
  salaries, and embedded player list.
- DraftKings Export reuses the active contest automatically and no longer asks
  for a second file upload.
- Export count remains limited to the number of entries actually reserved in
  DraftKings.

### Added
- Shared `DraftKingsContestService` for session-level contest context.

# Changelog

## v4.4.0 — Season-ready DraftKings workflow

### Added
- DraftKings DKEntries.csv parser and bulk-entry exporter.
- Pre-upload validation for roster slots, salary cap, player IDs, and duplicate lineups.
- DraftKings embedded salary-list import for a clean ID-based active player pool.
- Projection import reports for source matching, coverage, duplicate rows, and unmatched rows.

### Improved
- Projection column aliases and case-insensitive column detection.
- Projection matching by DraftKings ID first, then normalized name and team.
- Preservation of DraftKings Name + ID, roster eligibility, and game information.

All notable changes to this project will be documented in this file.

## [4.2.0] - 2026-08-02

### Added

- Deterministic `SlateNarrativeService` that converts structured slate analysis into readable, evidence-backed explanations.
- AI Slate Analyst Streamlit page with executive summary, value plays, tournament targets, cash plays, leverage, fades, games, stacks, alerts, and player-level explanations.
- CSV export and structured JSON inspection for generated slate analysis.
- Unit tests for narrative generation and player explanations.

### Notes

- The AI Slate Analyst does not call an external language model.
- Every statement is derived from the active player pool and `SlateAnalysisService` output.
