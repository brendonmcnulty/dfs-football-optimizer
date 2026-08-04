# DFS Football Optimizer

A Phase 1 DraftKings NFL Classic optimizer built with Python, Streamlit,
pandas, and Google OR-Tools.

## Current features

- Upload a salary/player-pool CSV
- Upload a separate projections CSV, if needed
- Edit projections in the dashboard
- Lock or exclude players
- Enforce DraftKings-style NFL Classic roster construction
- Enforce a configurable salary cap and minimum salary
- Maximize total projected fantasy points
- Download the optimized lineup as a CSV

## Roster currently modeled

- 1 QB
- 2 RB
- 3 WR
- 1 TE
- 1 FLEX (RB, WR, or TE)
- 1 DST

## Windows setup

Open PowerShell in the project folder.

### 1. Create a virtual environment

```powershell
py -m venv .venv
```

### 2. Activate it

```powershell
.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, run this once in the current window:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Then activate the environment again.

### 3. Install packages

```powershell
py -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Run the dashboard

```powershell
streamlit run app.py
```

## CSV requirements

The loader recognizes common column names, including:

- Name or Player
- Position or Pos
- Team or TeamAbbrev
- Opponent or Opp
- Salary
- Projection, Proj, or FPTS

A sample file is included at:

```text
data/sample/sample_players.csv
```

## Next development milestone

Phase 2 will generate multiple lineups and add:

- Maximum exposure
- Minimum exposure
- Maximum lineup overlap
- QB/pass-catcher stacks
- Opponent bring-backs
- Team limits


## Custom optimization strategies

The optimizer supports Projection, Ceiling, Floor, Balanced, Cash, Single Entry, Large-Field GPP, and Custom Formula strategies. Custom formulas blend projection, ceiling, floor, salary-adjusted value, and ownership-adjusted leverage. Custom weights must total 100%.


## Weekly Data Pipeline (v1.3)

The **Weekly Update** page combines a DraftKings salary CSV with up to three
projection or ownership provider CSVs. It supports projection, ceiling, floor,
and ownership fields; matches players by player ID or normalized name/team; and
can blend matching values using average, median, or first-source priority.

Each run includes source match rates, metric coverage, unmatched rows, a player
pool preview, CSV download, session activation, database save, and a local update
audit trail. Automatic provider API downloads are intentionally left for a later
release; v1.3 establishes the provider-neutral pipeline they will use.


## The Odds API setup

1. Open the **Settings** page in the app.
2. Paste and save your private The Odds API key.
3. Return to **Weekly Update** and click **Fetch current NFL odds**.

The key is stored only in `.env`, which is excluded from Git. The app retrieves
NFL moneylines, spreads, and totals, calculates consensus implied team totals,
and attaches those fields to the weekly player pool.

## v1.5 — Transparent in-house projection engine

The Weekly Update page can generate rule-based projections without a paid
projection provider. It uses an imported projection when one is available and
otherwise creates a salary-based baseline. It then applies separate Vegas,
home/away, and spread adjustments and calculates ceiling, floor, and a data
confidence score.

This first model is intentionally transparent and deterministic. It does not
yet claim to use historical usage, injuries, weather, or matchup statistics;
those inputs will be added as their data services are implemented.

## Weekly Update workflow

The Weekly Update page can now start from one of three player-pool foundations:

- A current DraftKings salary CSV
- The active Player Pool already loaded in the app
- The included sample player pool for offseason testing

Vegas results are filtered to the selected season/week before they are displayed,
cached, or merged into players. After a player-pool foundation is selected, the
page reveals the in-house projection engine.


## Historical Slate Manager

The Historical Slates page imports past DraftKings salary files, optional historical projections, and optional actual fantasy results. Saved historical slates can be loaded into the optimizer and evaluated with MAE, RMSE, bias, correlation, and floor-to-ceiling coverage.

## Projection Backtester v1.7

The Projection Backtester evaluates any saved historical slate that has matched
actual DraftKings fantasy results. It reports overall MAE, RMSE, bias,
correlation, floor/ceiling coverage, and accuracy by position, salary tier, and
confidence tier. It also compares the current projection with a transparent
salary-only baseline and provides position-level additive calibration ideas for
future model tests.

## Historical DFS Warehouse v2.0

The **Historical DFS Warehouse** page consolidates every saved slate into a
cross-season player-week dataset. Re-running a sync updates existing rows rather
than creating duplicates. The warehouse currently stores salaries, model
projections, ceiling, floor, ownership, confidence, actual DraftKings points,
and available Vegas context.

The schema also reserves stable columns for targets, carries, snaps, routes,
red-zone touches, weather, and injury status. Future connectors will populate
those fields without requiring the backtester or research tools to be redesigned.
The warehouse page supports season, week, position, team, salary, and actual-result
filters plus CSV export for external analysis.

## v2.1 NFL usage integration

The Weekly Update page can download official nflverse weekly player statistics
and merge a rolling average from completed weeks before the selected slate.
This leak-free window includes passing attempts, carries, targets, receptions,
rushing/receiving/passing yards, and recent PPR fantasy points.

The projection engine converts position-specific opportunity into a capped
usage adjustment and raises confidence when one or more prior games are
available. Usage fields are saved with slates and synchronized into the
Historical DFS Warehouse for later backtesting. Snap counts, routes, red-zone
touches, injuries, and weather are not included in this release.

## v2.2 Defensive Matchup Engine

The weekly workflow can now download nflverse player statistics and build leak-free rolling defensive matchup ratings for QB, RB, WR, and TE. Ratings use only completed weeks before the selected week.

New player-pool fields include:

- `matchup_rating` (0-100; higher is more favorable)
- `matchup_label`
- `fantasy_points_allowed`
- `matchup_games`
- `matchup_adjustment`

The projection engine applies a capped position-specific matchup adjustment and displays it separately from Vegas and recent-usage adjustments. The **Defensive Matchups** page provides position-by-position rankings and CSV export.

## Simulation Lab (v2.3)

The Simulation Lab runs correlated Monte Carlo simulations for saved lineups.
It uses each player's projection, floor, and ceiling to estimate volatility,
reuses the same simulated player result across every lineup containing that
player, and adds modest shared team and game factors.

Results include simulated mean, median, 10th/75th/90th/95th percentiles,
portfolio first-place rate, portfolio top-20% rate, a configurable target-score
hit rate, and average portfolio rank. CSV exports are available for lineup
summaries, every simulated lineup score, and player outcome distributions.

The portfolio first-place metric compares only the selected saved lineups. It
is not a literal contest win probability because the opposing contest field is
not currently simulated.


## v3.0 Sunday Dashboard

The Sunday Dashboard provides a single decision page for the active or saved slate:

- slate-level health and data coverage alerts
- top values, ceilings, leverage targets, and potential ownership fades
- game-environment rankings
- automatically scored QB stacks with optional bring-backs
- saved-lineup exposure and duplicate detection
- latest Simulation Lab takeaways when available in the session

The stack score is a transparent research heuristic based on ceiling, projection,
team implied total, and combined projected ownership. It is not a guarantee of contest results.

## DFS Coach (v3.1)

The DFS Coach converts the platform's projections and portfolio analytics into
transparent research recommendations. It includes:

- Player coach scores and recommendation tiers
- Plain-language reasons based on projection, ceiling, value, ownership, Vegas, usage, and matchups
- Position and ownership filters
- Lineup coaching with salary, projection, ceiling, ownership, QB stacks, and bring-backs
- Optional Simulation Lab context for median, upside, target-hit rate, and portfolio-first rate
- CSV export of the complete player recommendation table

Coach recommendations are model-based research signals and should be reviewed
alongside late injury news and contest-specific strategy.


## Developer diagnostics and offseason fixture

The **Developer Diagnostics** page checks imports, SQLite connectivity, sample files,
and active-player data coverage. It also loads `data/sample/enriched_sample_players.csv`,
a fully populated illustrative slate for testing the optimizer, Sunday Dashboard, DFS
Coach, and Slate Analysis service during the offseason. The values in that file are test
data only and must not be treated as real projections.

## Active Player Pool Manager

The application uses `services/player_pool_service.py` as the shared interface for the active player pool. CSV uploads, saved slates, historical slates, Weekly Update, the Optimizer, Sunday Dashboard, DFS Coach, and Developer Diagnostics now read or write the pool through the same service.

The service keeps the existing Streamlit session keys synchronized for compatibility while also tracking:

- player-pool source
- active slate name and database ID
- season, week, site, and slate name
- player count
- load timestamp
- revision number

Developer Diagnostics displays this metadata and a common data-coverage report.

## Week 1 live-slate workflow

1. Reserve the desired DraftKings entries and download `DKEntries.csv`.
2. Upload `DKEntries.csv` on **Weekly Update**.
3. Import or generate projections and, when available, ownership.
4. Refresh Vegas, prior-week usage, and defensive matchup data.
5. Activate the updated player pool.
6. Generate the requested portfolio on **Optimizer**.
7. Review **Week 1 Readiness** for projection coverage, salary usage,
   duplicates, exposures, QB stacks, bring-backs, and entry-count coverage.
8. Build and validate the file on **DraftKings Export**.
9. Upload `DKEntries_completed.csv` to DraftKings and review its confirmation
   screen before accepting changes.

The application intentionally limits the export to the number of entries that
were actually reserved in the uploaded `DKEntries.csv`.
