"""One-time data refinement (no LLM).

Writes three files:
  storefront/src/data/visual.json  photo cues + popularity the site shows (what a shopper "sees")
  data/truth.json                  hidden fit/calf/colour/material/comfort truth per product (judge only)
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
    "Metallic faux leather": "high-shine metallic finish",
    "Patent": "high-gloss patent",
    "Rubber": "matte moulded rubber",
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
    "nevada": ("light warm beige", "cool grey-brown taupe"),
    "alanie": ("pale peachy nude", "deeper tan nude"),
    "dorenna": ("bright cherry red", "dark wine burgundy"),
    "lagoon": ("soft champagne gold", "bright brassy yellow-gold with a high shine"),
}
COMFORT = {
    "dorenna": "heavy platform with a rigid sole, tiring on long walks",
    "veadith": "unstructured mule, heel slips out; thin footbed with little cushioning",
}

# The representative cases, hand-written after looking at each product photo:
# "cues" is what the picture shows (the shopper sees it as "Photo shows: ..."), "truth" is what it hides.
CASES = {
    "rosewood": {  # pink velvet heeled sock boot, photographed from behind
        "cues": {"texture": "soft velvety suede", "shape": "shot from behind, so the toe shape isn't visible",
                 "colour_as_seen": "bright rosy pink", "style": "heeled ankle boot with a block heel"},
        "natural_light": "deep red-brown with a slight purple cast, darker than on most screens",
        "truth": {"size_offset": 0.0, "width": "narrow toe box", "colour_misleads": True},
        "issues": ["Narrow toe box: wide feet need half a size up", "Photo reads bright pink; the boot is deep red-brown"],
    },
    "oneameth": {  # cream and black pointed stiletto pumps
        "cues": {"texture": "fine textured finish with a soft sheen", "shape": "sharply pointed, narrow toe",
                 "colour_as_seen": "pale cream nude", "style": "stiletto pump"},
        "truth": {"size_offset": 0.0, "width": "narrow toe box"},
        "issues": ["Forefoot too narrow: the pointed toe box pinches wide feet (length is true to size)"],
    },
    "marigold": {  # metallic horsebit loafers on a cool grey-blue studio backdrop
        "cues": {"texture": "high-shine metallic leather-look", "shape": "softly rounded toe with a horsebit trim",
                 "colour_as_seen": "pale champagne gold under cool studio light", "style": "metallic loafer"},
        "natural_light": "brassy yellow-gold in sunlight · warm coppery gold under indoor light",
        "truth": {"colour_misleads": True, "colour_shift": True},
        "issues": ["Runs half a size small",
                   "Metallic gold changes with the light: pale champagne in the photo, brassy or coppery in real life"],
    },
    "guavaberry": {  # black crinkled-patent pointed slingback on white
        "cues": {"texture": "high-gloss crinkled patent", "shape": "sharp pointed toe, slingback strap",
                 "colour_as_seen": "jet black on a white studio backdrop", "style": "slingback with a sculpted ball heel"},
        "natural_light": "deep oxblood red in daylight · near-black indoors",
        "truth": {"colour_misleads": True, "colour_shift": True, "material_misleads": True,
                  "material_truth": "coated synthetic (PU) patent, not leather; creases stiffly across the toe"},
        "issues": ["Reads jet black online; deep oxblood red in daylight", "Coated synthetic patent, not leather"],
    },
    "ebariel": {  # taupe suede knee-high boots on a slim leg
        "cues": {"texture": "soft napped suede", "shape": "almond toe, slim fitted shaft (worn on a slim leg)",
                 "colour_as_seen": "mushroom taupe-brown", "style": "knee-high boot with a block heel"},
        "truth": {"size_offset": 0.0, "calf": "tight: 34 cm shaft, fits slim to regular calves only"},
        "issues": ["Calf too tight for wide calves (34 cm shaft); length is true to size",
                   "Real data: 97% of its size returns say 'too small', which is what a tight calf looks like"],
    },
    "stormport": {  # olive rubber rain boots with a lug sole
        "cues": {"texture": "matte moulded rubber", "shape": "rounded toe, tall straight shaft",
                 "colour_as_seen": "olive green", "style": "rain boot with a chunky lug sole"},
        "truth": {"size_offset": 0.0, "roomy_heel": True, "comfort_issue": True,
                  "comfort": "stiff, heavy rubber shaft rubs the shin; flat footbed with no arch support, tiring on long days"},
        "issues": ["Roomy heel: narrow heels slip and need half a size down", "Stiff, heavy rubber: uncomfortable on long days"],
    },
    "clementinne": {  # burnished cognac horsebit loafers on a dark navy backdrop
        "cues": {"texture": "glossy burnished leather", "shape": "rounded almond toe, low-cut slip-on throat",
                 "colour_as_seen": "warm cognac brown", "style": "horsebit loafer"},
        "truth": {"size_offset": -0.5},
        "issues": ["Runs half a size large: most feet need half a size down",
                   "Real data: 82% of its size returns say 'too big'"],
    },
    "adrauder": {  # black toe-post slide with a wide cognac strap
        "cues": {"texture": "smooth leather-look with a contrast cognac strap", "shape": "open toe-post (thong) front",
                 "colour_as_seen": "black with a cognac strap", "style": "toe-post slide sandal"},
        "truth": {"comfort_issue": True,
                  "comfort": "toe post and stiff strap rub between the toes and across the top of the foot; flat footbed"},
        "issues": ["Runs half a size small", "Toe post and stiff strap rub on long days"],
    },
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


def fit_text(offset):
    return "runs half a size small" if offset > 0 else "runs half a size large" if offset < 0 else "true to size"


def build_visual_and_truth(products):
    sold = [p for p in products if p["aldoStats"] and p["aldoStats"]["unitsSoldSample"]]
    rank = {p["id"]: i for i, p in enumerate(sorted(sold, key=lambda p: -p["aldoStats"]["unitsSoldSample"]))}
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
        else:
            offset, narrow, uncomfortable_share = 0.0, False, 0.0
        truth[p["id"]] = {
            "size_offset": offset,
            "width": "narrow toe box" if narrow else "regular",
            "calf": "regular",
            "roomy_heel": False,
            "photo_colour": seen,
            "true_colour": true_colour or seen,
            "colour_misleads": true_colour is not None,
            "colour_shift": False,
            "material_misleads": False,
            "material_truth": d["material"],
            "comfort": COMFORT.get(p["id"], "no known comfort issue"),
            "comfort_issue": p["id"] in COMFORT,
            "uncomfortable_share": round(uncomfortable_share, 3),
            "real_stats": s,
        }
        case = CASES.get(p["id"])
        if case:
            visual[p["id"]] |= case["cues"]
            visual[p["id"]]["colour_natural_light"] = case.get("natural_light", case["cues"]["colour_as_seen"])
            truth[p["id"]] |= case["truth"]
            truth[p["id"]]["photo_colour"] = case["cues"]["colour_as_seen"]
            if truth[p["id"]]["colour_misleads"]:
                truth[p["id"]]["true_colour"] = case["natural_light"]
        t = truth[p["id"]]
        t["fit"] = fit_text(t["size_offset"])
        t["misleading_colourway"] = p["colours"][0]["name"] if t["colour_misleads"] else None  # the colour in the photo
        t["issues"] = case["issues"] if case else [x for x in [
            t["fit"].capitalize() if t["size_offset"] else None,
            "Narrow toe box" if t["width"] != "regular" else None,
            f"Photo reads {seen}; really {t['true_colour']}" if t["colour_misleads"] else None,
            t["comfort"].capitalize() if t["comfort_issue"] else None] if x]
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
    # Only the original styles: adding the new ones to the pool would reshuffle the seeded sample.
    products = [p for p in products if "omsStyle" not in p]
    by_id = {p["id"]: p for p in products}
    lines = load_return_lines(products)
    counts = {b: len(v) for b, v in lines.items()}
    plan = allocate(counts, n)
    rows = []
    for bucket, k in plan.items():
        for row in random.sample(lines[bucket], k):
            rows.append(make_profile(len(rows) + 1, row, bucket, by_id[row["pid"]]))
    return rows, counts


def add_traits(rows):
    """Visible traits that set off the hidden cases. A separate RNG keeps the 50 base rows unchanged."""
    rng = random.Random(7)
    yes = lambda p: "yes" if rng.random() < p else "no"
    for r in rows:
        b = r["return_bucket"]
        r["calf_width"] = rng.choices(["wide", "regular", "slim"], [0.35, 0.5, 0.15] if b == "too_small" else [0.2, 0.6, 0.2])[0]
        r["colour_particular"] = "yes" if b == "look" else yes(0.2)
        r["wants_real_leather"] = yes(0.5 if b == "look" else 0.15)
        r["heel_slips"] = yes(0.6 if b == "too_big" else 0.1)
    return rows


def main():
    products = json.loads(config.PRODUCTS.read_text())
    visual, truth = build_visual_and_truth(products)
    config.VISUAL.write_text(json.dumps(visual, indent=2) + "\n")
    config.TRUTH.write_text(json.dumps(truth, indent=2) + "\n")
    for pid in visual:
        print(f"{pid:12} {'CASE ' if pid in CASES else '     '}{' | '.join(truth[pid]['issues']) or 'no hidden issue'}")

    rows, counts = build_customers(products)
    add_traits(rows)
    with open(config.CUSTOMERS, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("\nreal fixable return lines across the 19 styles:", counts)
    print("50 customers by bucket:", dict(Counter(r["return_bucket"] for r in rows)))
    print("50 customers by past category:", dict(Counter(r["past_category"] for r in rows)))
    for k in ("calf_width", "colour_particular", "wants_real_leather", "heel_slips"):
        print(f"  {k}:", dict(Counter(r[k] for r in rows)))


if __name__ == "__main__":
    main()
