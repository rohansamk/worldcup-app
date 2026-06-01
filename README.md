# World Cup 2026 Prediction League

A Streamlit web app where your friends predict the 2026 FIFA World Cup (48 teams, 12 groups, Round of 32 onward). Google Sheets is the database, so there's no server to run — players, results, and predictions all live in tabs you can audit and edit by hand.

## What it does

- **Login**: pick your name from a dropdown, enter a passcode (low-security, fine for a casual sweepstake). The player list is read live from the `Players` tab — add a row, they show up.
- **Make Predictions**: one continuous, editable page. All sections share **one deadline** (`deadline_group` in the Config tab) — until then, you can revise anything; once it passes, the whole page locks at once.
  - All 72 group matches (winner or draw, 1 pt each).
  - Group standings: 1st / 2nd / 3rd for every group (2 pts / 1 pt for correct 1st/2nd).
  - R32: pick which 8 of your 12 third-placed teams advance.
  - Knockout rounds R16 → QF → SF → Finalists → Champion. **Cascading**: your R16 options are restricted to your R32 set, QF to your R16 picks, etc.
- **Leaderboard**: live, ranks everyone, breaks points down per category.
- **Admin** (passcode-gated): enter actual match results, group standings, and round-by-round actual advancers.

You're free to contradict yourself — picking a team to lose all its matches but still advance from the group just costs you points; nothing breaks.

## Setup, step by step

### 1. Create the Google Sheet

Create a new Google Sheet. Note the **Sheet ID** from the URL — it's the long string between `/d/` and `/edit`:

```
https://docs.google.com/spreadsheets/d/THIS_IS_THE_SHEET_ID/edit
```

You'll need 8 tabs. **Tab names must match exactly** (case-sensitive). The app will auto-create any missing tab with the right header on first read, but you can also create them up-front:

| Tab name                 | Header row (row 1)                                |
| ------------------------ | ------------------------------------------------- |
| `Players`                | `Name` · `Passcode` · `Active`                    |
| `Config`                 | `Key` · `Value`                                   |
| `Matches`                | `MatchID` · `Group` · `Team1` · `Team2`           |
| `MatchResults`           | `MatchID` · `Result`                              |
| `ActualGroupStandings`   | `Group` · `First` · `Second` · `Third`            |
| `ActualBracket`          | `Round` · `Team`                                  |
| `PredictionsMatches`     | `Player` · `MatchID` · `Pick` · `UpdatedAt`       |
| `PredictionsBracket`     | `Player` · `Round` · `Team` · `UpdatedAt`         |

**Populate `Players`** with one row per friend, e.g.:

| Name   | Passcode | Active |
| ------ | -------- | ------ |
| Rohan  | hunter2  | TRUE   |
| Alex   | wcup26   | TRUE   |
| Sam    | letmein  | FALSE  |

`Active` accepts `TRUE` / `true` / `1` / `yes` (anything else = inactive).

**Populate `Config`** with the admin passcode and the single shared predictions deadline:

| Key              | Value                |
| ---------------- | -------------------- |
| `admin_passcode` | `your-admin-secret`  |
| `deadline_group` | `2026-06-11 06:00`   |

`deadline_group` locks the entire Make Predictions page — group matches, group standings, and the whole knockout cascade through Champion all lock together at this single time. Interpreted as **NZT (UTC+12)** if no timezone is specified. Accepted formats: `YYYY-MM-DD HH:MM` or full ISO-8601. Leave it blank to keep predictions permanently open.

`Matches`, `MatchResults`, `ActualGroupStandings`, `ActualBracket`, and the two `Predictions*` tabs you can leave empty — the app fills them. The admin **Setup** page has a one-click "Seed all 72 group matches" button for `Matches`.

### 2. Create a Google Cloud service account

The app uses a service account to read/write your sheet (no per-user OAuth flow). Five-minute process:

1. Open <https://console.cloud.google.com/> and create a project (or reuse one).
2. Enable two APIs for that project:
   - **Google Sheets API**: <https://console.cloud.google.com/apis/library/sheets.googleapis.com>
   - **Google Drive API**: <https://console.cloud.google.com/apis/library/drive.googleapis.com>
3. **IAM & Admin → Service Accounts → Create service account**. Name it e.g. `wc-app`. Skip the optional role grants.
4. On the new service account, **Keys → Add key → Create new key → JSON**. A `.json` file downloads — this is your credentials file. Keep it safe.
5. Open that JSON file. Copy the value of `client_email` (looks like `wc-app@your-project.iam.gserviceaccount.com`).
6. Back in your Google Sheet, click **Share** and share it with that `client_email` as **Editor**. The app can't access the sheet without this step.

### 3. Configure credentials

**Locally**: drop the JSON file you downloaded in step 2.4 into `.streamlit/service_account.json`:

```bash
mkdir -p .streamlit
mv ~/Downloads/your-project-xxxx.json .streamlit/service_account.json
```

That's it — no copying values, no editing TOML. The Sheet ID is already hardcoded in `config.py` (`SHEET_ID`). The file is gitignored.

**On Streamlit Community Cloud** (no filesystem at deploy time): use the Secrets UI instead — see step 5 below. The app picks up local JSON when present and falls back to `st.secrets` otherwise.

### 4. Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

The app opens at <http://localhost:8501>. Sign in as one of your `Players` rows. To bootstrap the matches list, sign in, go to **Admin**, enter the admin passcode, and click **Seed all 72 group matches** on the Setup tab.

### 5. Deploy to Streamlit Community Cloud

1. Push this repo to GitHub. `.gitignore` excludes `service_account.json` and `secrets.toml` so your credentials don't leak.
2. Go to <https://share.streamlit.io/> and sign in with GitHub.
3. **New app** → pick your repo and branch, set the main file to `app.py`, click **Deploy**.
4. Once it's building, open **Settings → Secrets**. Paste the contents of `.streamlit/secrets.toml.example` and fill in every field from your downloaded service account JSON (the `[gcp_service_account]` section). Save.
5. The app redeploys with the secrets loaded. Share the URL with your league.

## Day-of-tournament workflow

- **Before `deadline_group`**: friends log in and fill out everything in one sitting — group matches, group standings, R32, R16, QF, SF, Final, Champion. They can re-save any section as many times as they like. Once the deadline passes the whole page locks.
- **After each match**: the admin opens **Admin → Match results**, sets the winner/draw, and clicks Save. The leaderboard updates the next time anyone hits Refresh.
- **After group stage**: admin opens **Admin → Group standings** and enters 1st/2nd/3rd for each group, then **Knockout actuals → ThirdPlaced** for the 8 third-placed teams that advanced.
- **After each knockout round**: admin enters the survivors in that round's section on **Knockout actuals**.

## Scoring (configurable in `config.py`)

| Category                          | Points per correct |
| --------------------------------- | ------------------ |
| Group match result                | 1                  |
| Group winner (1st)                | 2                  |
| Group runner-up (2nd)             | 1                  |
| R32 advancement                   | 2                  |
| R16 advancement                   | 3                  |
| QF advancement                    | 4                  |
| SF advancement                    | 5                  |
| Finalist                          | 7                  |
| Champion                          | 10                 |

R32 is scored against your full predicted R32 set (your Group 1st + 2nd + 8 third-placed picks). Subsequent rounds score against your picks for that round.

## File layout

```
worldcup-app/
├── app.py                     entry point + auth gate + sidebar nav
├── config.py                  groups, scoring weights, sheet schema
├── matches.py                 generates the 72 round-robin group matches
├── sheets_client.py           gspread wrapper with cached reads + upserts
├── scoring.py                 pure scoring engine
├── views/
│   ├── login.py
│   ├── predictions.py         the cascading bracket UI
│   ├── leaderboard.py
│   └── admin.py
├── requirements.txt
├── .gitignore
├── .streamlit/
│   └── secrets.toml.example
└── README.md
```
