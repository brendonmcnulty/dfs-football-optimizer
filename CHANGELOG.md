## v5.1.7 — Week Results & Portfolio Tracking

### Added
- Save all generated optimizer lineups to the database in one click, while safely skipping lineups already saved individually.
- New Week Results page for importing raw DraftKings contest-standings ZIP files.
- Optional DraftKings Contest Entry History import for personal entry identification, winnings, cash rate, and ROI.
- Contest standings, actual ownership, and actual fantasy points persistence.
- Automatic write-back of DraftKings player actuals into Historical Results and the Historical Warehouse.
- Projection-vs-actual and projected-ownership-vs-actual-ownership post-slate review.

## v5.1.6 — DraftKings interleaved entry parsing fix

### Fixed
- Reads all reserved DraftKings entries even when the embedded salary table begins before the final entry row.
- Supports DKEntries files where contest-entry columns and salary-table columns coexist on the same rows.
- Prevents Weekly Update and DraftKings Export from undercounting reserved entries in this DraftKings file layout.

## v5.1.5 — Provider floor compatibility

### Fixed
- Allows legitimate negative DFS floor estimates from projection providers.
- Keeps validation for invalid/negative projections and ceilings.
- Prevents CPenn downside estimates from blocking lineup generation.

## v5.1.4 - Ownership provenance readiness fix

- Preserves whether projected ownership was actually supplied by an imported provider.
- Treats an imported 0.0% ownership estimate as valid populated ownership instead of missing data.
- Keeps the conservative positive-ownership fallback for older/manual player pools without provenance metadata.
- Prevents CPenn-style feeds from being falsely blocked when low-owned projected players legitimately carry 0.0% ownership.

## v5.1.3 — Live-slate readiness fix

### Fixed
- Leverage/ownership readiness now measures coverage only across players with
  positive projections instead of every DraftKings-listed deep reserve.
- Low full-pool projection coverage remains an informational warning rather
  than blocking optimization when the projected candidate pool is healthy.

## v5.1.2 — Native CPenn DFS projection import

### Added
- Native aliases for CPenn DFS `DK Proj`, `DK Floor`, `DK Ceil`, and `DK pOWN%` columns.
- Provider-formatted numeric parsing for percentages, dollar signs, and comma-separated values.
- Projection-source report now lists the metrics detected from each uploaded source.
- Weekly Update explicitly documents raw CPenn DFS CSV support.

### Week 1 workflow
- Upload the real DraftKings `DKEntries.csv` as the player-pool foundation.
- Upload the untouched CPenn `nfl_projections.csv` as a projection source.
- No manual spreadsheet renaming or percentage cleanup is required.

## v5.1.0 — Contest strategy presets

### Added
- Cash, Single-Entry GPP, 3-Max GPP, 20-Max GPP, and 150-Max GPP presets.
- Preset previews explaining recommended salary, correlation, uniqueness, ownership, and exposure defaults.
- One-click application of presets while keeping every optimizer control editable.
- Applied preset metadata saved with generated lineup settings.

### Notes
- Presets are starting points, not guarantees of profitability.
- Player exposure defaults should be reviewed against the slate, contest size, and projection confidence.

## v5.0.0 — Week 1 Ready

### Added
- Week 1 Readiness Center with a unified pre-lock checklist.
- Portfolio health reporting for salary usage, projection, ceiling, ownership,
  duplicate lineups, unique players, QB exposure, team exposure, game exposure,
  QB stack frequency, and opponent bring-backs.
- Direct links from failed readiness checks to the page that resolves them.
- Upload-readiness status combining DKEntries, active player pool, projection
  coverage, generated lineup count, reserved entries, and export validation.

### Changed
- Home workflow now identifies Week 1 Readiness as the final command center.
- Preseason feature expansion is frozen in favor of reliability and live-week use.

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

## v5.1.8 — Reserved-entry results matching

### Added
- Persists DraftKings reserved entry IDs with saved slates for automatic post-slate matching.
- Week Results can use the slate's DKEntries.csv directly for older slates; full Contest Entry History is no longer required to identify your entries.
- Adds an unmatched-player audit so DraftKings results that do not map to the saved slate are visible and downloadable.

### Changed
- Contest Entry History is now optional finance detail for exact winnings, places-paid, cash-rate, and ROI.
- Weekly Update saves active DraftKings entry metadata whenever the slate is saved.
