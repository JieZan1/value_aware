# Returns Wind Tunnel (MVP)

Virtual shoppers, built from past ALDO return data, shop a product page in a real browser
(Strands agent + Playwright MCP + Claude on Bedrock). A judge checks each purchase against the
hidden truth about the shoe, and a fixer writes page fixes straight into the storefront.

## Run

```sh
uv sync
uv run python -m tunnel.build_data        # once: visual.json, data/truth.json, data/customers.csv
(cd storefront && npm install && npm run dev)   # http://localhost:5173
uv run python -m tunnel.run --product rosewood --n 6 --verify
```

Flags: `--headless` (don't show the browser), `--customers C01,C07` (pick personas),
`--verify` (re-test the same shoppers on the fixed page to fill the "after" rate).
Env: `SHOPPER_MODEL`, `ANALYST_MODEL`, `SITE_URL`, `AWS_REGION`; Bedrock auth via `AWS_BEARER_TOKEN_BEDROCK`.

## How it works

1. **Data** (`tunnel/build_data.py`, no LLM): the OMS CSV only has returns, so it is refined into
   - `storefront/src/data/visual.json` — what each photo shows (texture, shape, colour as seen, style) + popularity;
   - `data/truth.json` — hidden fit/colour/comfort truth, derived from the real `aldoStats` (made up for Rosewood);
   - `data/customers.csv` — 50 made-up profiles, each tied to a real return line and its reason.
2. **Personas** (`tunnel/personas.py`): picks customers (one per return reason, same category first) and
   writes briefs from the *visible* columns only. Past product, size and outcome stay hidden.
3. **Shopper** (`tunnel/shopper.py`): most shoppers arrive from an ad on `/?sim=1#/product/<id>`; every third
   one browses the category instead. Sim mode hides prices and wind-tunnel output and shows "Photo shows: …"
   captions, which is how the agent sees the pictures.
4. **Judge + fixer** (`tunnel/judge.py`): deterministic size and colour checks plus an LLM verdict per shopper;
   then one fixer call drafts the fit note, colour note, photo shot list and feed facts.
5. **Output**: reviews appear live on the product page (`reviews.json`), fixes show under
   "After wind tunnel" (`tunnel.json`, `approved: false`), and `runs/<ts>/report.html` shows every
   agent's output (also `report.md` and `results.json`). Re-render any run with
   `uv run python -m tunnel.html_report runs/<ts>`.

Original sample entries are kept in `data/reviews.sample.json` and `data/tunnel.sample.json`.
`data/demo_reviews.json` and `data/demo_tunnel.json` hold the Rosewood demo state (50% → 0%); copy them
back into `storefront/src/data/` (as `reviews.json` / `tunnel.json`) to restore it after other runs.
