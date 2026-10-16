"""Run the wind tunnel on one product page.

  uv run python -m tunnel.run --product rosewood --n 6 [--verify] [--headless] [--customers C01,C07]

Writes live into the storefront (reviews.json, tunnel.json) and a report to runs/<timestamp>/.
"""
import argparse
import json
import math
from datetime import datetime

from tunnel import config, html_report
from tunnel.judge import fix, judge
from tunnel.personas import build_briefs, entry_for, load_customers, pick
from tunnel.shopper import shop


def read(path):
    return json.loads(path.read_text())


def write(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def rate(results, pid):
    """Predicted return rate of the tested style, over the shoppers who bought it."""
    bought = [r for r in results if r["decision"]["bought"] and r["decision"]["product_id"] == pid]
    if not bought:
        return {"rate": 0.0, "range": 0.0}
    p = sum(r["verdict"]["likely_return"] for r in bought) / len(bought)
    return {"rate": round(p, 2), "range": round(max(0.05, math.sqrt(p * (1 - p) / len(bought))), 2)}


def run_shoppers(rows, briefs, product, truth, after, headless, on_result=None):
    results = []
    tunnel = read(config.TUNNEL) if after else {}
    for row, b in zip(rows, briefs):
        print(f"\n=== {b.persona_id} · {b.label} · {row['entry']} · {'after fixes' if after else 'original page'} ===")
        decision, steps = shop(b.brief, b.shopping_goal, product["id"], product["category"], entry=row["entry"],
                               after=after, headless=headless)
        t = tunnel.get(decision.product_id or "")
        page_fixes = t and {"fitNote": t.get("fitNote"), "colourNote": t.get("colourNote"),
                            "photos_reshot_in_natural_light": bool(t.get("photoStatus"))}
        verdict, sc = judge(row, decision, truth, page_fixes)
        r = {"persona_id": b.persona_id, "label": b.label, "entry": row["entry"], "brief": b.brief, "goal": b.shopping_goal,
             "past": {k: row[k] for k in ("past_product_id", "past_size_bought", "return_bucket", "raw_reason")},
             "decision": decision.model_dump(), "steps": steps, "size_check": sc, "verdict": verdict.model_dump()}
        results.append(r)
        print(f"--> {decision.product_id} size {decision.size} | likely return: {verdict.likely_return} "
              f"({verdict.reason}) | gap: {verdict.page_gap}")
        if on_result:
            on_result(r)
    return results


def review(r, product, names):
    d, v = r["decision"], r["verdict"]
    persona = r["label"]
    if not d["bought"]:
        persona += " · didn't buy"
    elif d["product_id"] != product["id"]:
        persona += f" · bought {names.get(d['product_id'], d['product_id'])} instead"
    return {"persona": persona, "kind": "shopper", "size": d["size"] if d["bought"] else "—",
            "rating": d["rating"], "text": d["quote"], "likelyReturn": v["likely_return"], "reason": v["reason"]}


def report(product, before, after, fixes, results, retest):
    lines = [f"# Wind tunnel: {product['name']} ({product['type']})", "",
             f"**Predicted return rate, original page:** {before['rate']:.0%} ± {before['range']:.0%}"]
    if after:
        lines.append(f"**After fixes:** {after['rate']:.0%} ± {after['range']:.0%}")
    lines += ["", "## Weaknesses found", ""]
    lines += [f"{i}. **{w.gap}** ({w.count} shoppers) — {w.evidence}" for i, w in enumerate(fixes.weaknesses, 1)]
    lines += ["", "## Suggested fixes (need merchandiser approval)", "",
              f"- **Fit note:** {fixes.fitNote}", f"- **Colour note:** {fixes.colourNote}",
              f"- **Photo shot list:** {fixes.photoStatus}",
              f"- **Feed facts:** `{json.dumps(fixes.feedFacts.model_dump(exclude_none=True))}`",
              "", "## Site-wide weaknesses", ""] + [f"- {s}" for s in fixes.site_wide]
    for title, rs in [("Shoppers, original page", results), ("Shoppers, after fixes", retest or [])]:
        if not rs:
            continue
        chose = sum(r["decision"]["product_id"] == product["id"] for r in rs)
        lines += ["", f"## {title}", "", f"{chose} of {len(rs)} chose {product['name']}.", "",
                  "| Persona | Entry | Past return | Chose | Expected size | Likely return | Page gap | Quote |",
                  "|---|---|---|---|---|---|---|---|"]
        for r in rs:
            d, v, sc = r["decision"], r["verdict"], r["size_check"] or {}
            chose = f"{d['product_id']} {d['colour']} {d['size']}" if d["bought"] else "didn't buy"
            lines.append(f"| {r['label']} | {r['entry']} | {r['past']['raw_reason']} ({r['past']['past_product_id']}) | {chose} | "
                         f"{sc.get('expected', '—')} | {'yes: ' + v['reason'] if v['likely_return'] else 'no'} | "
                         f"{v['page_gap'] or '—'} | {d['quote']} |")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--product", default="rosewood")
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--customers", help="comma-separated persona ids, e.g. C01,C07")
    ap.add_argument("--verify", action="store_true", help="re-test the same shoppers on the fixed page")
    ap.add_argument("--headless", action="store_true")
    a = ap.parse_args()

    products = read(config.PRODUCTS)
    product = next(p for p in products if p["id"] == a.product)
    truth = read(config.TRUTH)
    customers = load_customers()
    if a.customers:
        ids = a.customers.split(",")
        rows = [c for c in customers if c["persona_id"] in ids]
    else:
        rows = pick(customers, product["category"], a.n)

    for i, r in enumerate(rows):
        r["entry"] = entry_for(i)
    print(f"Building {len(rows)} shoppers from past customers: {[r['persona_id'] for r in rows]}")
    briefs = build_briefs(rows, product, read(config.VISUAL)[a.product])

    # Replace the illustrative sample reviews for this product; append live as each shopper finishes.
    reviews = read(config.REVIEWS)
    reviews[a.product] = []

    names = {p["id"]: p["name"] for p in products}

    def publish(r):
        reviews[a.product].append(review(r, product, names))
        write(config.REVIEWS, reviews)

    results = run_shoppers(rows, briefs, product, truth, after=False, headless=a.headless, on_result=publish)
    before = rate(results, a.product)

    print("\nDrafting fixes...")
    fixes = fix(product, truth[a.product], results)
    tunnel = read(config.TUNNEL)
    tunnel[a.product] = {"before": before, "fitNote": fixes.fitNote, "colourNote": fixes.colourNote,
                         "photoStatus": fixes.photoStatus, "feedFacts": fixes.feedFacts.model_dump(exclude_none=True),
                         "approved": False, "illustrative": False}
    write(config.TUNNEL, tunnel)

    after, retest = None, None
    if a.verify:
        retest = run_shoppers(rows, briefs, product, truth, after=True, headless=a.headless)
        after = rate(retest, a.product)
        tunnel[a.product]["after"] = after
        write(config.TUNNEL, tunnel)

    out = config.RUNS / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True)
    write(out / "results.json", {"product": a.product, "before": before, "after": after, "fixes": fixes.model_dump(),
                                 "results": results, "retest": retest})
    (out / "report.md").write_text(report(product, before, after, fixes, results, retest))
    html_report.write(out)
    print(f"\nBefore: {before}" + (f"  After: {after}" if after else ""))
    print(f"Report: {out / 'report.html'}")


if __name__ == "__main__":
    main()
