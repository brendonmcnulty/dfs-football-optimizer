# Changelog

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
