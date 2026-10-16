"""Persona builder: reads past-customer rows and turns them into shopper briefs.

Only visible profile columns reach the LLM; the past product, size and return outcome stay hidden,
so the simulation replays the moment *before* the original purchase.
"""
import csv
import json
from collections import defaultdict

from pydantic import BaseModel, Field
from strands import Agent
from strands.models import BedrockModel

from tunnel import config

# Budget stays out: price isn't what this tunnel tests.
VISIBLE = ["persona_id", "usual_size", "foot_width", "brands_worn", "occasion", "hours_on_feet", "notes"]
# Taste only for browsing shoppers, so their choices spread across the category; ad shoppers liked the ad.
TASTE = ["preferred_colours", "preferred_textures"]


def entry_for(i):
    """Every third shopper browses the category; the rest arrive from an ad for the target style."""
    return "browse" if i % 3 == 2 else "ad"
BUCKET_ORDER = ["too_small", "too_big", "uncomfortable", "look"]

SYSTEM = """You turn customer profile rows into short briefs for role-playing shoppers.
Use only the facts in each row. Don't invent fit problems or outcomes, and don't mention gender or age."""


class ShopperBrief(BaseModel):
    persona_id: str
    label: str = Field(description='short public label, e.g. "Size 8, wide feet, office"')
    brief: str = Field(description="2-4 sentences in second person ('You wear a US 8...'), from the row only")
    shopping_goal: str = Field(description="one line: what they're shopping for today, in the given category")


class Briefs(BaseModel):
    briefs: list[ShopperBrief]


def load_customers():
    with open(config.CUSTOMERS, newline="") as f:
        return list(csv.DictReader(f))


def pick(customers, category, n):
    """Round-robin across return reasons so every kind of past mistake is tested; same category first."""
    pools = defaultdict(list)
    for c in sorted(customers, key=lambda c: c["past_category"] != category):
        pools[c["return_bucket"]].append(c)
    picked = []
    while len(picked) < n and any(pools.values()):
        for bucket in BUCKET_ORDER:
            if pools[bucket] and len(picked) < n:
                picked.append(pools[bucket].pop(0))
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
