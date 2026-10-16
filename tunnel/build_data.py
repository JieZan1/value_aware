"""One-time data refinement (no LLM).

Writes three files:
  storefront/src/data/visual.json  photo cues + popularity the site shows (what a shopper "sees")
  data/truth.json                  hidden fit/colour/comfort truth per product (judge only)
  data/customers.csv               50 made-up profiles, each anchored to a real OMS return line

Run: uv run python -m tunnel.build_data
"""
import csv
import json
import random
import re
from collections import Counter, defaultdict

from tunnel import config

random.seed(42)

TEXTURE = {
    "Suede": "soft matte napped suede",
    "Faux suede": "fine brushed faux suede with a flat sheen",
    "Leather": "smooth leather with a soft sheen",
    "Faux leather": "glossy smooth faux leather",
    "Textile": "knit-textured fabric",
}
SHAPE = {
    "Almond toe": "softly tapered almond toe",
    "Pointed toe": "sharp pointed toe, slim profile",
    "Round toe": "rounded toe, roomy-looking front",
    "Square toe": "squared-off toe",
    "Round open toe": "rounded open toe",
    "Open toe": "open toe",
    "Square open toe": "squared open toe",
}

# Photos that mislead on colour: (how the studio photo reads, the colour in daylight).
COLOUR_MISMATCH = {
    "rosewood": ("bright rosy pink", "deep red-brown with a slight purple cast, darker than on most screens"),
    "nevada": ("light warm beige", "cool grey-brown taupe"),
    "alanie": ("pale peachy nude", "deeper tan nude"),
    "dorenna": ("bright cherry red", "dark wine burgundy"),
    "lagoon": ("soft champagne gold", "bright brassy yellow-gold with a high shine"),
}
COMFORT = {
    "adrauder": "stiff faux-leather strap rubs the top of the foot; flat footbed with no arch support",
    "dorenna": "heavy platform with a rigid sole, tiring on long walks",
    "veadith": "unstructured mule, heel slips out; thin footbed with little cushioning",
}

BUCKETS = {
    "too small": "too_small", "return.page.reasons.too small": "too_small",
    "too big": "too_big", "return.page.reasons.too big": "too_big",
    "uncomfortable": "uncomfortable",
    "not what i expected": "look", "not satisfied with the colour": "look", "not as advertised": "look",
}

BRANDS = ["Nike", "Steve Madden", "Sam Edelman", "Converse", "Dr. Martens", "Vans", "Naturalizer", "Adidas"]
COMFORT_BRANDS = ["Clarks", "Skechers", "Birkenstock", "Ecco"]
COLOURS = ["black", "tan", "cognac", "burgundy", "taupe", "cream", "nude", "gold", "white"]
TEXTURES = ["suede", "smooth leather", "matte finishes", "glossy finishes", "knit"]
OCCASIONS = ["office", "weekend errands", "evenings out", "wedding guest", "everyday wear"]
LONG_SHIFTS = ["nurse, 12-hour shifts", "retail floor, on feet all day", "city commute, about 10k steps a day"]


def norm(name):
    return re.sub(r"[^a-z]", "", name.lower())


def build_visual_and_truth(products):
    ranked = sorted((p for p in products if p["aldoStats"]), key=lambda p: -p["aldoStats"]["unitsSoldSample"])
    rank = {p["id"]: i for i, p in enumerate(ranked)}
    visual, truth = {}, {}
    for p in products:
        d, s = p["details"], p["aldoStats"]
        seen, true_colour = COLOUR_MISMATCH.get(p["id"], (p["colours"][0]["name"].lower(), None))
        r = rank.get(p["id"])
        visual[p["id"]] = {
            "texture": TEXTURE[d["material"]],
            "shape": SHAPE[d["toe"]],
            "colour_as_seen": seen,
            "style": p["type"].lower(),
            "popularity": None if r is None else "Bestseller" if r < 5 else "Popular" if r < 12 else None,
            # what the natural-light reshoot (from the fixer's shot list) shows; used on the fixed page
            "colour_natural_light": true_colour or seen,
        }
        if s:
            small = s["tooSmallShareOfSizeReturns"]
            offset = 0.5 if small >= 0.65 else -0.5 if small <= 0.35 else 0.0
            narrow = offset > 0 and d["toe"] == "Pointed toe"
            uncomfortable_share = (s["uncomfortableReturns"] or 0) / s["returns"]
        else:  # Rosewood: new style, no history. Proposal's fit note: "Narrow toe. If your feet are wide, size up half."
            offset, narrow, uncomfortable_share = 0.0, True, 0.0
        truth[p["id"]] = {
            "size_offset": offset,
            "fit": "runs half a size small" if offset > 0 else "runs half a size large" if offset < 0 else "true to size",
            "width": "narrow toe box" if narrow else "regular",
            "photo_colour": seen,
            "true_colour": true_colour or seen,
            "colour_misleads": true_colour is not None,
            "misleading_colourway": p["colours"][0]["name"] if true_colour else None,  # the colour in the photo
            "comfort": COMFORT.get(p["id"], "no known comfort issue"),
            "comfort_issue": p["id"] in COMFORT,
            "uncomfortable_share": round(uncomfortable_share, 3),
            "real_stats": s,
        }
    return visual, truth


def load_return_lines(products):
    by_norm = {norm(p["name"]): p["id"] for p in products}
    lines = defaultdict(list)
    with open(config.OMS_CSV, newline="") as f:
        for row in csv.DictReader(f):
            pid = by_norm.get(norm(row["orderitem_product_name"]))
            bucket = BUCKETS.get(row["reason"].strip().lower())
            if pid and bucket:
                lines[bucket].append({**row, "pid": pid})
    return lines


def allocate(counts, n):
    total = sum(counts.values())
    exact = {k: n * v / total for k, v in counts.items()}
    out = {k: int(x) for k, x in exact.items()}
    for k in sorted(exact, key=lambda k: exact[k] - out[k], reverse=True)[: n - sum(out.values())]:
        out[k] += 1
    return out


def make_profile(i, row, bucket, product):
    usual = random.choice([6.0, 6.5, 7.0, 7.0, 7.5, 7.5, 8.0, 8.0, 8.5, 9.0, 9.5, 10.0])
    if bucket == "too_small":
        width, bought = random.choices(["wide", "regular"], [0.8, 0.2])[0], usual
    elif bucket == "too_big":
        width = random.choices(["narrow", "regular"], [0.6, 0.4])[0]
        bought = random.choice([usual, usual + 0.5])
    else:
        width, bought = random.choices(["regular", "wide", "narrow"], [0.6, 0.2, 0.2])[0], usual
    long_day = bucket == "uncomfortable"
    brands = random.sample(COMFORT_BRANDS if long_day else BRANDS, 2)
    notes = {
        "too_small": "Usually orders my normal size without checking a size guide.",
        "too_big": "Between sizes; my heel often slips in shoes.",
        "uncomfortable": "Comfort matters more than looks; I'm on my feet for hours.",
        "look": "Very particular about colour and finish; I buy what the photo shows.",
    }[bucket]
    return {
        "persona_id": f"C{i:02d}",
        "customer_uid": row["customer_uid"] or f"GUEST-{row['order_number']}",
        "banner": row["store_banner"],
        "return_channel": row["return_channel"],
        # visible to the shopper
        "usual_size": usual,
        "foot_width": width,
        "brands_worn": ", ".join(brands),
        "preferred_colours": ", ".join(random.sample(COLOURS, 2)),
        "preferred_textures": random.choice(TEXTURES),
        "occasion": random.choice(LONG_SHIFTS if long_day else OCCASIONS),
        "hours_on_feet": random.randint(8, 12) if long_day else random.randint(2, 7),
        "budget": random.choice([60, 75, 90, 110, 130]),
        "notes": notes,
        # hidden: the real outcome this persona carries
        "past_product_id": row["pid"],
        "past_category": product["category"],
        "past_size_bought": bought,
        "return_bucket": bucket,
        "raw_reason": row["reason"],
    }


def build_customers(products, n=50):
    by_id = {p["id"]: p for p in products}
    lines = load_return_lines(products)
    counts = {b: len(v) for b, v in lines.items()}
    plan = allocate(counts, n)
    rows = []
    for bucket, k in plan.items():
        for row in random.sample(lines[bucket], k):
            rows.append(make_profile(len(rows) + 1, row, bucket, by_id[row["pid"]]))
    return rows, counts


def main():
    products = json.loads(config.PRODUCTS.read_text())
    visual, truth = build_visual_and_truth(products)
    config.VISUAL.write_text(json.dumps(visual, indent=2) + "\n")
    config.TRUTH.write_text(json.dumps(truth, indent=2) + "\n")
    for pid in visual:
        t = truth[pid]
        print(f"{pid:12} {t['fit']:24} {t['width']:15} photo={visual[pid]['colour_as_seen']!r:24} "
              f"{'COLOUR-MISLEADS ' if t['colour_misleads'] else ''}{'COMFORT ' if t['comfort_issue'] else ''}"
              f"{visual[pid]['popularity'] or ''}")

    rows, counts = build_customers(products)
    with open(config.CUSTOMERS, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("\nreal fixable return lines across the 19 styles:", counts)
    print("50 customers by bucket:", dict(Counter(r["return_bucket"] for r in rows)))
    print("50 customers by past category:", dict(Counter(r["past_category"] for r in rows)))


if __name__ == "__main__":
    main()
