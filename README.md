# insure_anot (v1)

Interactive Streamlit calculator for comparing hospital insurance setups:

- Setup A vs Setup B with editable premium and care-path inputs
- Claim out-of-pocket scenarios (70k / 150k / 500k + custom)
- Premium projection with age-band schedules
- Opportunity-cost projections (cash-delta and total-delta views)
- Light guidance summary based on cost/protection trade-off

## Quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Tests

```bash
pytest -q
```

## Publish To GitHub + Streamlit Community Cloud

### 1) Initialize and commit locally

```bash
git init
git add .
git commit -m "Initial commit: insure_anot streamlit app"
git branch -M main
```

If commit fails, configure Git identity:

```bash
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

### 2) Create GitHub repository and push

Option A: with GitHub CLI (`gh`)

```bash
gh repo create insure_anot --public --source=. --remote=origin --push
```

Option B: manual remote

```bash
git remote add origin https://github.com/<your-username>/insure_anot.git
git push -u origin main
```

### 3) Deploy on Streamlit Community Cloud

1. Open `https://share.streamlit.io` and sign in with GitHub.
2. Click **Create app**.
3. Select:
   - Repository: `your-username/insure_anot`
   - Branch: `main`
   - Main file path: `app.py`
4. Optional: choose a custom app URL.
5. Open **Advanced settings** and choose Python version (Community Cloud defaults to Python 3.12).
6. Click **Deploy**.

After deployment, share the generated `*.streamlit.app` URL.

## How The Calculator Works

### Core idea

The app compares insurance setups using two dimensions:

- Cost over time (annual premiums and cumulative premiums).
- Protection at claim time (out-of-pocket for selected bill scenarios).

### Data model

- `PersonProfile`: date of birth and projection start date.
- `PolicySetup`: plan labels, toggle for rider/cash plans, premium age-bands, and care-path claim parameters.
- `PremiumBand`: age range + yearly premium split (`total`, `cash`, and inferred `medisave`).
- `CarePathParameters`: deductible, coinsurance, rider offsets, and rider loss limit.

### Claim math

For each bill scenario:

1. Base OOP = `deductible + coinsurance_rate * (bill - deductible)`.
2. If rider is included:
   - deductible is reduced by rider deductible coverage rate.
   - coinsurance is reduced by rider coinsurance coverage rate.
   - annual rider loss limit cap is applied if configured.

### Projection math

For each age from current ANB to end age:

1. App reads the matching premium band for each setup.
2. It sums annual totals and annual cash.
3. It builds cumulative totals and cumulative cash.
4. If age is beyond the last provided band, it can carry-forward the last known value and warns you.

### Opportunity cost

For two selected setups, the app computes yearly premium savings and compounds them at:

- low return
- base return
- high return

It shows both views:

- cash-only premium delta invested
- total premium delta invested (cash + medisave)

### Recommendation logic

The app ranks Setup A/B/C by:

- lower projected end-age cash outlay (cost rank),
- lower anchor scenario OOP (protection rank).

Combined score = `cost rank + protection rank`.  
Recommendation text explains:

- cheapest setup,
- best-protection setup,
- balanced pick (lowest combined score).

### Important limitation

The app is a decision aid, not advice. Results depend fully on:

- your entered premiums,
- care-path assumptions (panel vs non-panel),
- selected bill scenarios,
- selected return assumptions.
