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
