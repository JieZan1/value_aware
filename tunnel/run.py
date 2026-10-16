"""Run the wind tunnel on one or more product pages, one after another.

  uv run python -m tunnel.run --list                                   # what each case tests
  uv run python -m tunnel.run --product quick --verify --headless      # 1 mock customer x 4 return reasons, ~5 min
  uv run python -m tunnel.run --product rosewood,ebariel --n 6 [--verify] [--headless] [--customers C01,C07]

Writes live into the storefront (reviews.json, tunnel.json) and one report for the whole run:
runs/<timestamp>/report.html (one card per shopper), plus <product>.json with every detail.
"""
import argparse
import json
import math
import sys
import time
from datetime import datetime

from tunnel import config, html_report
from tunnel.build_data import CASES
from tunnel.judge import fix, judge
from tunnel.personas import MOCK, MOCK_BRIEF, build_briefs, entry_for, load_customers, pick
from tunnel.shopper import shop

# Rosewood's demo shoppers (50% -> 0%), kept fixed so the headline case stays repeatable.
PINNED = {"rosewood": "C01,C37,C25,C22,C04,C40"}
NOTES = ("fitNote", "colourNote", "materialNote", "comfortNote", "photoStatus")
# Named sets for --product. "quick": the mock customer on one shoe per main return reason
# (too small, too big, colour, uncomfortable).
SETS = {"quick": "oneameth,clementinne,guavaberry,stormport", "all": ",".join(CASES)}


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
        page_fixes = t and {k: t.get(k) for k in NOTES if k != "photoStatus"} | {
            "photos_reshot_in_natural_light": bool(t.get("photoStatus"))}
        verdict, found = judge(row, decision, truth, page_fixes)
        r = {"persona_id": b.persona_id, "label": b.label, "entry": row["entry"], "brief": b.brief, "goal": b.shopping_goal,
             "past": {k: row[k] for k in ("past_product_id", "past_size_bought", "return_bucket", "raw_reason")},
             "decision": decision.model_dump(), "steps": steps, "size_check": found.get("size"), "checks": found,
             "verdict": verdict.model_dump()}
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


def run_product(pid, a, products, truth, customers, out):
    product = next(p for p in products if p["id"] == pid)
    if a.mock:
        rows, briefs = [dict(MOCK)], [MOCK_BRIEF]
    else:
        ids = a.customers.split(",") if a.customers else PINNED.get(pid, "").split(",")[: a.n]
        if ids != [""]:
            by_id = {c["persona_id"]: c for c in customers}
            rows = [dict(by_id[i]) for i in ids]
        else:
            rows = [dict(c) for c in pick(customers, product, truth[pid], a.n)]
    for i, r in enumerate(rows):
        r["entry"] = entry_for(i)
    print(f"\n##### {product['name']}: shoppers {[r['persona_id'] for r in rows]}")
    if not a.mock:
        briefs = build_briefs(rows, product, read(config.VISUAL)[pid])

    # Replace the illustrative sample reviews for this product; append live as each shopper finishes.
    reviews = read(config.REVIEWS)
    reviews[pid] = []
    names = {p["id"]: p["name"] for p in products}

    def publish(r):
        reviews[pid].append(review(r, product, names))
        write(config.REVIEWS, reviews)

    results = run_shoppers(rows, briefs, product, truth, after=False, headless=a.headless, on_result=publish)
    before = rate(results, pid)

    print("\nDrafting fixes...")
    fixes = fix(product, truth[pid], results)
    tunnel = read(config.TUNNEL)
    tunnel[pid] = {"before": before, **{k: getattr(fixes, k) for k in NOTES},
                   "feedFacts": fixes.feedFacts.model_dump(exclude_none=True), "approved": False, "illustrative": False}
    write(config.TUNNEL, tunnel)

    after, retest = None, None
    if a.verify:
        retest = run_shoppers(rows, briefs, product, truth, after=True, headless=a.headless)
        after = rate(retest, pid)
        tunnel[pid]["after"] = after
        write(config.TUNNEL, tunnel)

    write(out / f"{pid}.json", {"product": pid, "before": before, "after": after, "fixes": fixes.model_dump(),
                                "results": results, "retest": retest})
    print(f"\n{product['name']}  Before: {before}" + (f"  After: {after}" if after else ""))


def main():
    sys.stdout.reconfigure(line_buffering=True)  # progress shows up promptly even when piped to a log
    ap = argparse.ArgumentParser()
    ap.add_argument("--product", default="rosewood", help=f"an id, a comma-separated list, or a set: {', '.join(SETS)}")
    ap.add_argument("--n", type=int, help="shoppers per product (default 6)")
    ap.add_argument("--mock", action="store_true", help="shop with the one mock customer (always on for quick)")
    ap.add_argument("--list", action="store_true", help="list the test cases and sets, then exit")
    ap.add_argument("--customers", help="comma-separated persona ids, e.g. C01,C07 (kept in this order)")
    ap.add_argument("--verify", action="store_true", help="re-test the same shoppers on the fixed page")
    ap.add_argument("--headless", action="store_true")
    a = ap.parse_args()
    if a.list:
        truth = read(config.TRUTH)
        for pid in CASES:
            print(f"{pid:11} {' | '.join(truth[pid]['issues'])}")
        print("\nsets: " + "  ".join(f"{k} = {v}" for k, v in SETS.items()))
        return
    a.mock = a.mock or a.product == "quick"
    a.n = a.n or 6
    pids = SETS.get(a.product, a.product).split(",")

    products, truth, customers = read(config.PRODUCTS), read(config.TRUTH), load_customers()
    out = config.RUNS / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True)
    start = time.monotonic()
    for pid in pids:
        t0 = time.monotonic()
        run_product(pid, a, products, truth, customers, out)
        print(f"({pid} took {(time.monotonic() - t0) / 60:.1f} min)")
    print(f"\nTotal: {(time.monotonic() - start) / 60:.1f} min for {len(pids)} product(s)")
    print(f"Report: {html_report.write(out)}")


if __name__ == "__main__":
    main()
