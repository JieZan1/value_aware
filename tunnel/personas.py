"""Persona builder: reads past-customer rows and turns them into shopper briefs.

Only visible profile columns reach the LLM; the past product, size and return outcome stay hidden,
so the simulation replays the moment *before* the original purchase.
"""
import csv
import json

from pydantic import BaseModel, Field
from strands import Agent
from strands.models import BedrockModel

from tunnel import config

# Budget stays out: price isn't what this tunnel tests.
VISIBLE = ["persona_id", "usual_size", "foot_width", "calf_width", "brands_worn", "occasion", "hours_on_feet",
           "colour_particular", "wants_real_leather", "heel_slips", "notes"]
# Taste only for browsing shoppers, so their choices spread across the category; ad shoppers liked the ad.
TASTE = ["preferred_colours", "preferred_textures"]


def entry_for(i):
    """Every third shopper browses the category; the rest arrive from an ad for the target style."""
    return "browse" if i % 3 == 2 else "ad"


# Hidden issue -> the visible trait that makes a shopper fall for it.
TRIGGERS = {
    "narrow toe box": (lambda t: t["width"] != "regular", lambda c: c["foot_width"] == "wide"),
    "tight calf": (lambda t: t["calf"] != "regular", lambda c: c["calf_width"] == "wide"),
    "colour": (lambda t: t["colour_misleads"], lambda c: c["colour_particular"] == "yes"),
    "material": (lambda t: t["material_misleads"], lambda c: c["wants_real_leather"] == "yes"),
    "comfort": (lambda t: t["comfort_issue"], lambda c: float(c["hours_on_feet"]) >= 8),
    "roomy heel": (lambda t: t["roomy_heel"], lambda c: c["heel_slips"] == "yes"),
}

SYSTEM = """You turn customer profile rows into short briefs for role-playing shoppers.
Use only the facts in each row. Don't invent fit problems or outcomes, and don't mention gender or age."""


class ShopperBrief(BaseModel):
    persona_id: str
    label: str = Field(description='short public label, e.g. "Size 8, wide feet, office"')
    brief: str = Field(description="2-4 sentences in second person ('You wear a US 8...'), from the row only")
    shopping_goal: str = Field(description="one line: what they're shopping for today, in the given category")


class Briefs(BaseModel):
    briefs: list[ShopperBrief]


# One made-up customer for the quick test. Their traits hit a different return reason on each quick-test shoe:
# wide feet (too small on a narrow toe box), trusts their usual size (too big on a style that runs large),
# particular about colour (colour on a misleading photo), 10-hour days (uncomfortable on a stiff boot).
MOCK = {"persona_id": "M01", "customer_uid": "MOCK", "banner": "ALDO_US", "return_channel": "Web",
        "usual_size": "8.0", "foot_width": "wide", "calf_width": "regular", "brands_worn": "Steve Madden, Clarks",
        "preferred_colours": "black, burgundy", "preferred_textures": "smooth leather",
        "occasion": "retail floor, on feet all day", "hours_on_feet": "10", "budget": "110",
        "notes": "Usually orders my normal size without checking a size guide.",
        "colour_particular": "yes", "wants_real_leather": "no", "heel_slips": "no",
        "past_product_id": "aahliyah", "past_category": "Boots", "past_size_bought": "8.0",
        "return_bucket": "too_small", "raw_reason": "Too small"}
MOCK_BRIEF = ShopperBrief(
    persona_id="M01", label="Mock customer · US 8, wide feet, 10-hour days",
    brief="You wear a US 8 and have wide feet. You work on a retail floor and are on your feet about 10 hours a day, "
          "usually in Steve Madden or Clarks. You order your normal size without checking a size guide, and you're "
          "particular about colour: you buy what the photo shows.",
    shopping_goal="a pair you can wear to work and out, probably the one in the ad")


def load_customers():
    with open(config.CUSTOMERS, newline="") as f:
        return list(csv.DictReader(f))


def pick(customers, product, truth, n):
    """About a third of the shoppers are at risk from this product's hidden issues (one per issue, round-robin),
    the rest are controls. At-risk shoppers take the ad slots, so browsers (who may wander off) are controls."""
    active = [hit for has, hit in TRIGGERS.values() if has(truth)]
    ordered = sorted(customers, key=lambda c: c["past_category"] != product["category"])
    k = min(max(len(active), n // 3), n // 2) if active else 0
    at_risk = []
    while len(at_risk) < k:
        before = len(at_risk)
        for hit in active:
            c = next((c for c in ordered if hit(c) and c not in at_risk), None)
            if c and len(at_risk) < k:
                at_risk.append(c)
        if len(at_risk) == before:
            break
    controls = [c for c in ordered if c not in at_risk and not any(hit(c) for hit in active)]
    picked = []
    for i in range(n):
        first, second = (controls, at_risk) if entry_for(i) == "browse" else (at_risk, controls)
        if first or second:
            picked.append((first or second).pop(0))
    return picked


def build_briefs(rows, product, cues):
    agent = Agent(model=BedrockModel(model_id=config.ANALYST_MODEL, region_name=config.REGION),
                  system_prompt=SYSTEM, callback_handler=None)
    visible = [{k: r[k] for k in VISIBLE + (TASTE if r["entry"] == "browse" else [])} | {"entry": r["entry"]}
               for r in rows]
    look = ", ".join([cues["texture"], cues["shape"], cues["colour_as_seen"], cues["style"]])
    category = product["category"].lower()
    result = agent(
        f'Rows with entry "ad" saw an ad for {product["name"]} ({look}) and liked the look; say so in the brief. '
        f"Their goal: a pair of {category}, probably {product['name']}.\n"
        f'Rows with entry "browse" are shopping {category} for their occasion with their own taste; '
        f"their goal: the pair of {category} that suits them best. Don't mention {product['name']} for them.\n"
        f"Write one brief per row:\n{json.dumps(visible, indent=1)}",
        structured_output_model=Briefs,
    )
    by_id = {b.persona_id: b for b in result.structured_output.briefs}
    return [by_id[r["persona_id"]] for r in rows]
