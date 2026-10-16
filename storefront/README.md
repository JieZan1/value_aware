# Wind Tunnel prototype store (React + Vite)

A simple shoe store with 20 styles for the Returns Wind Tunnel demo.

## Run it

```sh
cd storefront
npm install
npm run dev        # opens http://localhost:5173
```

## What's on the site

- **All shoes**: 20 styles (9 boots, 5 shoes, 5 sandals + the new "Rosewood" boot), filter by category.
- **Product page**: drawn images (3 views), colour and size pickers, description, details, add to bag.
- **Wind-tunnel reviews**: what the simulated shoppers and AI assistants said about the style.
- **Toggle in the header**: "Original page" vs "After wind tunnel". After the tunnel, the page shows the agent's fit note, colour note, "natural-light photos coming" and the predicted return rate.

## Where the agents plug in (all in `src/data/`)

| File | Who writes it | What it holds |
| --- | --- | --- |
| `products.json` | us (synthetic) | The product page AND the product feed. Virtual AI buyers should read only `name, category, type, price, colours, sizes, details`. `aldoStats` is real ALDO data for the backtest; never show it to virtual shoppers. |
| `reviews.json` | virtual shopper agents | `{ "<productId>": [ { persona, kind: "shopper" | "ai", size, rating (1-5 or null), text, likelyReturn, reason } ] }` |
| `tunnel.json` | director / analyst / fixer agents | `{ "<productId>": { before: {rate, range, aiRate, aiRange}, after: {...}, fitNote, colourNote, photoStatus, feedFacts, approved, illustrative } }` |

Rates are fractions (0.22 = 22%). Set `illustrative: false` once the numbers come from real agent runs. The site re-renders when you save a JSON file while `npm run dev` is running, so the agents' Python scripts can simply overwrite these files.

Rosewood and Elliette already have sample entries; replace them with real agent output.

## Notes

- Product photos are free-licence Unsplash photos of similar shoes (not the actual ALDO styles); if a photo fails to load, a drawing is shown instead. Colours, materials and descriptions are synthetic.
- Style names, categories, prices (median refund) and `aldoStats` come from the ALDO OMS data, Feb 2024 – Jan 2026.
- Checkout is not connected.
