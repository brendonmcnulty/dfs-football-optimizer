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
