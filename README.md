# Returns Wind Tunnel (MVP)

Virtual shoppers, built from past ALDO return data, shop a product page in a real browser
(Strands agent + Playwright MCP + Claude on Bedrock). A judge checks each purchase against the
hidden truth about the shoe, and a fixer writes page fixes straight into the storefront.

## Run the frontend

In its own terminal, and leave it running:

```sh
cd storefront
npm install
npm run dev        # http://localhost:5173
```

Open http://localhost:5173 to see the store. Reviews and fixes from the agent appear there live; use the
"Original page" / "After wind tunnel" toggle in the header to compare.

## Run the agent

In a second terminal, from the project root, with the frontend running:

```sh
uv sync
uv run python -m tunnel.build_data                  # once: visual.json, data/truth.json, data/customers.csv
uv run python -m tunnel.run --product quick --verify   # about 5 min
```

A Chrome window opens for each shopper so you can watch it browse, pick a size and add to bag
(add `--headless` to hide it). When the run ends it prints the path to `runs/<ts>/report.html`.

### Choosing what to run

`--product` takes one id, a comma list, or a named set. `--list` prints every case and set.

| Command | What runs | Time |
|---|---|---|
| `--product quick --verify` | one mock customer on 4 shoes, one per main return reason: Oneameth (too small), Clementinne (too big), Guavaberry (colour), Stormport (uncomfortable) | ~5 min |
| `--product ebariel --n 2 --verify` | one case, 2 shoppers | ~1.5 min |
| `--product rosewood --verify` | the tuned demo, its 6 pinned shoppers (50% → 0%) | ~6 min |
| `--product all --verify` | all 8 cases × 6 shoppers | ~50 min (~15 min with `--n 2`) |

Rule of thumb: about 45 seconds per shopper per product with `--verify`. Each run prints how long it took.

Flags: `--n` (shoppers per product), `--mock` (use the mock customer on any product), `--headless` (don't show the browser), `--customers C01,C07` (pick personas),
`--verify` (re-test the same shoppers on the fixed page to fill the "after" rate).
Env: `SHOPPER_MODEL`, `ANALYST_MODEL`, `SITE_URL`, `AWS_REGION`; Bedrock auth via `AWS_BEARER_TOKEN_BEDROCK`.

## The cases

Each case is a kind of return the product photo hides, backed by the real return mix of an OMS style.
Photo cues and hidden issues are hand-written in `CASES` in `tunnel/build_data.py`, from looking at each photo.

| Product | What the photo hides | Real-data signal |
|---|---|---|
| Rosewood (heeled ankle boot) | narrow toe box (toe not in shot); reads bright pink, really deep red-brown | new style (pinned demo shoppers) |
| Oneameth (pointed pump) | forefoot too narrow for wide feet; length true to size | 57% return rate |
| Clementinne (horsebit loafer) | runs half a size large | 82% of size returns "too big" |
| Marigold (metallic loafer) | gold shifts with light: champagne in studio, brassy outdoors, coppery indoors; runs ½ small | `Goldao2eyetn_mm`: 243 colour/look returns |
| Guavaberry (patent slingback) | reads jet black, deep oxblood in daylight; coated synthetic, not leather | `Guavaberry`: 10% look returns |
| Ebariel (knee-high boot) | calf too tight for wide calves (34 cm shaft); length true to size | `Ebariel`: 97% of size returns "too small" |
| Stormport (rain boot) | roomy heel (narrow heels slip); stiff, heavy rubber on long days | `Seaprtstorm_wm`: 19% uncomfortable |
| Adrauder (toe-post slide) | toe post and strap rub; runs ½ small | 18% uncomfortable, 70% of size returns too small |

Shoppers carry visible traits (foot width, calf width, colour-particular, wants real leather, heel slips, hours on feet).
For each product about a third of them are at risk from its hidden issues and the rest are controls.

## How it works

1. **Data** (`tunnel/build_data.py`, no LLM): the OMS CSV only has returns, so it is refined into
   - `storefront/src/data/visual.json` — what each photo shows (texture, shape, colour as seen, style) + popularity;
   - `data/truth.json` — hidden fit/calf/colour/material/comfort truth: rules from the real `aldoStats`, plus the 7 hand-written cases;
   - `data/customers.csv` — 50 made-up profiles, each tied to a real return line and its reason, with visible traits.
2. **Personas** (`tunnel/personas.py`): picks shoppers at risk from the product's hidden issues plus controls, and
   writes briefs from the *visible* columns only. Past product, size and outcome stay hidden.
3. **Shopper** (`tunnel/shopper.py`): most shoppers arrive from an ad on `/?sim=1#/product/<id>`; every third
   one browses the category instead. Sim mode hides prices and wind-tunnel output and shows "Photo shows: …"
   captions, which is how the agent sees the pictures.
4. **Judge + fixer** (`tunnel/judge.py`): fixed rules decide each return (size, calf, colour, material, comfort) and
   Claude explains the page gap; then one fixer call drafts fit, colour, material and comfort notes, a photo shot list
   and feed facts.
5. **Output**: reviews appear live on the product page (`reviews.json`), fixes show under
   "After wind tunnel" (`tunnel.json`, `approved: false`), and `runs/<ts>/report.html` has one card per
   shopper: likely to return or not, why, and (with `--verify`) the result after the fix. Every detail is in
   `runs/<ts>/<product>.json`. Re-render a run with `uv run python -m tunnel.html_report runs/<ts>`.

Original sample entries are kept in `data/reviews.sample.json` and `data/tunnel.sample.json`.
`data/demo_reviews.json` and `data/demo_tunnel.json` hold the Rosewood demo state (50% → 0%); copy them
back into `storefront/src/data/` (as `reviews.json` / `tunnel.json`) to restore it after other runs.
