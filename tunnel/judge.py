"""Judge each shopper's choice against the hidden truth, then draft page fixes (the fixer)."""
import json
from typing import Literal

from pydantic import BaseModel, Field
from strands import Agent
from strands.models import BedrockModel

from tunnel import config
from tunnel.personas import VISIBLE

Reason = Literal["Too small", "Too big", "Colour", "Uncomfortable"]

JUDGE = """You are a returns analyst for a shoe retailer. You see the hidden truth about the product the
shopper bought (they only saw the web page), their profile including the mistake they made in the past,
and their decision. Decide if this purchase would likely come back, and what the page failed to tell them.
- Size and colour checks are computed for you; trust them.
- Comfort: likely return if the product has a comfort issue and they spend long hours on their feet.
- If they didn't buy, likely_return is false; still name the page gap that made them leave, if any."""

FIXER = """You are the fixer in a pre-launch "returns wind tunnel". Virtual shoppers shopped a product page;
an analyst judged which purchases would come back and why. Draft the page fixes that would have prevented
those returns. Only fix weaknesses that shoppers actually hit AND that the hidden truth supports.
Write in a plain, factual retail voice, no hype. Never invent facts beyond the truth given."""


class Verdict(BaseModel):
    likely_return: bool
    reason: Reason | None
    page_gap: str | None = Field(description="what the page failed to say that would have prevented this; null if it did its job")
    evidence: str = Field(description="one sentence linking the shopper's words/choice to the truth")


class Weakness(BaseModel):
    gap: str
    count: int = Field(description="how many shoppers hit it")
    evidence: str = Field(description="a short shopper quote or fact showing it")


class FeedFacts(BaseModel):
    runs_small: str | None = Field(None, description='"half" if it runs half a size small')
    runs_large: str | None = Field(None, description='"half" if it runs half a size large')
    width: str | None = Field(None, description='"narrow" or "regular"')
    heel_cm: float | None = None
    colour_text: str | None = None
    comfort: str | None = None


class Fixes(BaseModel):
    weaknesses: list[Weakness] = Field(description="ranked, most returns first")
    fitNote: str | None = Field(description="1-2 sentence fit note for the size picker, or null")
    colourNote: str | None = Field(description="1-2 sentence honest colour description, or null")
    photoStatus: str | None = Field(description="photo shot list for staff (natural light, angles), or null")
    feedFacts: FeedFacts = Field(description="structured fit facts for the product feed / AI shoppers")
    site_wide: list[str] = Field(description="weaknesses of the site as a whole, beyond this product")


def _analyst(system):
    return Agent(model=BedrockModel(model_id=config.ANALYST_MODEL, region_name=config.REGION),
                 system_prompt=system, callback_handler=None)


def size_check(customer, decision, truth):
    t = truth.get(decision.product_id or "")
    if not (decision.bought and decision.size and t):
        return None
    expected = float(customer["usual_size"]) + t["size_offset"]
    if customer["foot_width"] == "wide" and t["width"] == "narrow toe box":
        expected += 0.5
    diff = decision.size - expected
    return {"expected": expected, "chosen": decision.size, "ok": abs(diff) <= 0.25,
            "result": "Too small" if diff < -0.25 else "Too big" if diff > 0.25 else None}


def colour_check(customer, decision, truth, page_fixes):
    """A colour return needs: the colourway whose photo misleads, nothing on the page correcting it,
    and a shopper who has returned shoes for colour/look before."""
    t = truth.get(decision.product_id or "")
    if not (decision.bought and t and t["colour_misleads"]):
        return None
    told = bool(page_fixes and (page_fixes.get("colourNote") or page_fixes.get("photos_reshot_in_natural_light")))
    misled = (decision.colour or "").lower() == t["misleading_colourway"].lower() and not told
    return {"misled_by_photo": misled, "colour_sensitive": customer["return_bucket"] == "look",
            "returns": misled and customer["return_bucket"] == "look"}


def judge(customer, decision, truth, page_fixes=None):
    """page_fixes: the wind-tunnel fixes shown on the page the shopper bought from (None on the original page)."""
    sc = size_check(customer, decision, truth)
    cc = colour_check(customer, decision, truth, page_fixes)
    t = truth.get(decision.product_id or "", {})
    # Judge on what the shopper knew plus their past outcome, not the preferences the shopper never saw.
    seen = {k: customer[k] for k in VISIBLE + ["past_product_id", "past_size_bought", "return_bucket", "raw_reason"]}
    payload = {"customer": seen, "decision": decision.model_dump(),
               "hidden_truth": {k: v for k, v in t.items() if k != "real_stats"}, "size_check": sc,
               "colour_check": cc, "page_fixes": page_fixes}
    v = _analyst(JUDGE)(json.dumps(payload, indent=1), structured_output_model=Verdict).structured_output
    # Size and colour rules are deterministic; they override the model for those outcomes.
    if v.reason in ("Too small", "Too big", "Colour"):
        v.likely_return, v.reason = False, None
    if cc and cc["returns"]:
        v.likely_return, v.reason = True, "Colour"
    if sc and not sc["ok"]:
        v.likely_return, v.reason = True, sc["result"]
    return v, sc


def fix(product, truth, results):
    page = {k: v for k, v in product.items() if k not in ("aldoStats", "images")}
    shoppers = [{"persona": r["label"], "decision": r["decision"], "verdict": r["verdict"]} for r in results]
    # real_stats (ALDO return history) lets the fixer cite evidence, e.g. "70% of size returns: too small".
    payload = {"product_page": page, "hidden_truth": truth, "shoppers": shoppers}
    return _analyst(FIXER)(json.dumps(payload, indent=1), structured_output_model=Fixes).structured_output
