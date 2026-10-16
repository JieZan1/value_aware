"""Judge each shopper's choice against the hidden truth, then draft page fixes (the fixer)."""
import json
from typing import Literal

from pydantic import BaseModel, Field
from strands import Agent
from strands.models import BedrockModel

from tunnel import config
from tunnel.personas import VISIBLE

Reason = Literal["Too small", "Too big", "Too small (calf)", "Colour", "Not as described", "Uncomfortable"]

JUDGE = """You are a returns analyst for a shoe retailer. The outcome of this purchase has already been decided by
fixed rules (outcome + checks below); don't second-guess it. You see the hidden truth about the product (the shopper
only saw the web page), the shopper's profile including their past mistake, their decision, and what the page said
(page_fixes, null on the original page). Explain what the page failed to tell them that would have prevented this
return, or, if it's kept, whether the page did its job. If they didn't buy, name the gap that made them leave, if any."""

FIXER = """You are the fixer in a pre-launch "returns wind tunnel". Virtual shoppers shopped a product page;
an analyst judged which purchases would come back and why. Draft the page fixes that would have prevented
those returns. Only fix weaknesses that shoppers actually hit AND that the hidden truth supports.
Write in a plain, factual retail voice, no hype. Never invent facts beyond the truth given.
If a colour changes with the light, say how it looks in each light and ask for photos in each."""


class Gap(BaseModel):
    page_gap: str | None = Field(description="ONE short sentence (under 25 words): what the page failed to say that "
                                             "would have prevented this; null if it did its job")
    evidence: str = Field(description="one sentence linking the shopper's words/choice to the truth")


class Verdict(BaseModel):
    likely_return: bool
    reason: Reason | None
    page_gap: str | None
    evidence: str


class Weakness(BaseModel):
    gap: str
    count: int = Field(description="how many shoppers hit it")
    evidence: str = Field(description="a short shopper quote or fact showing it")


class FeedFacts(BaseModel):
    runs_small: str | None = Field(None, description='"half" if it runs half a size small')
    runs_large: str | None = Field(None, description='"half" if it runs half a size large')
    width: str | None = Field(None, description='"narrow" or "regular"')
    toe_box: str | None = Field(None, description='e.g. "narrow, pointed"')
    calf_fit: str | None = Field(None, description='shaft circumference and who it fits, e.g. "34 cm, slim to regular calves"')
    heel_cm: float | None = None
    colour_text: str | None = None
    colour_by_light: str | None = Field(None, description="how the colour looks in daylight vs indoors")
    material: str | None = Field(None, description="what the upper is really made of")
    comfort: str | None = None


class Fixes(BaseModel):
    weaknesses: list[Weakness] = Field(description="ranked, most returns first")
    fitNote: str | None = Field(description="1-2 sentence fit note for the size picker (length, toe box, calf, heel), or null")
    colourNote: str | None = Field(description="1-2 sentence honest colour description, per light if it shifts, or null")
    materialNote: str | None = Field(description="1 sentence on what the material really is, or null")
    comfortNote: str | None = Field(description="1-2 sentences on comfort for long wear, or null")
    photoStatus: str | None = Field(description="photo shot list for staff (natural light, angles), or null")
    feedFacts: FeedFacts = Field(description="structured fit facts for the product feed / AI shoppers")
    site_wide: list[str] = Field(description="weaknesses of the site as a whole, beyond this product")


def _analyst(system):
    return Agent(model=BedrockModel(model_id=config.ANALYST_MODEL, region_name=config.REGION),
                 system_prompt=system, callback_handler=None)


def checks(customer, decision, truth, page_fixes):
    """Deterministic return rules, one per kind of hidden issue. Returns (checks, likely_return, reason)."""
    t = truth.get(decision.product_id or "")
    if not (decision.bought and t):
        return {}, False, None
    told = lambda *keys: bool(page_fixes and any(page_fixes.get(k) for k in keys))
    out = {}
    if decision.size:
        expected = float(customer["usual_size"]) + t["size_offset"]
        if customer["foot_width"] == "wide" and t["width"] == "narrow toe box":
            expected += 0.5
        if customer["heel_slips"] == "yes" and t["roomy_heel"]:
            expected -= 0.5
        diff = decision.size - expected
        out["size"] = {"expected": expected, "chosen": decision.size, "ok": abs(diff) <= 0.25,
                       "result": "Too small" if diff < -0.25 else "Too big" if diff > 0.25 else None}
    if t["calf"] != "regular":
        wide = customer["calf_width"] == "wide"
        out["calf"] = {"wide_calves": wide, "returns": wide}  # no size fixes a tight shaft
    if t["colour_misleads"]:
        misled = (decision.colour or "").lower() == t["misleading_colourway"].lower() and not told(
            "colourNote", "photos_reshot_in_natural_light")
        particular = customer["colour_particular"] == "yes"
        out["colour"] = {"misled_by_photo": misled, "colour_particular": particular, "returns": misled and particular}
    if t["material_misleads"]:
        wants = customer["wants_real_leather"] == "yes"
        out["material"] = {"wants_real_leather": wants, "told": told("materialNote"), "returns": wants and not told("materialNote")}
    if t["comfort_issue"]:
        long_days = float(customer["hours_on_feet"]) >= 8
        out["comfort"] = {"long_days": long_days, "told": told("comfortNote"), "returns": long_days and not told("comfortNote")}

    if "size" in out and not out["size"]["ok"]:
        return out, True, out["size"]["result"]
    for key, reason in [("calf", "Too small (calf)"), ("colour", "Colour"), ("material", "Not as described"),
                        ("comfort", "Uncomfortable")]:
        if out.get(key, {}).get("returns"):
            return out, True, reason
    return out, False, None


def judge(customer, decision, truth, page_fixes=None):
    """page_fixes: the wind-tunnel fixes shown on the page the shopper bought from (None on the original page)."""
    found, likely, reason = checks(customer, decision, truth, page_fixes)
    t = truth.get(decision.product_id or "", {})
    # Judge on what the shopper knew plus their past outcome, not the preferences the shopper never saw.
    seen = {k: customer[k] for k in VISIBLE + ["past_product_id", "past_size_bought", "return_bucket", "raw_reason"]}
    payload = {"customer": seen, "decision": decision.model_dump(),
               "hidden_truth": {k: v for k, v in t.items() if k != "real_stats"},
               "outcome": {"likely_return": likely, "reason": reason}, "checks": found, "page_fixes": page_fixes}
    gap = _analyst(JUDGE)(json.dumps(payload, indent=1), structured_output_model=Gap).structured_output
    return Verdict(likely_return=likely, reason=reason, page_gap=gap.page_gap, evidence=gap.evidence), found


def fix(product, truth, results):
    page = {k: v for k, v in product.items() if k not in ("aldoStats", "images", "omsStyle")}
    shoppers = [{"persona": r["label"], "decision": r["decision"], "verdict": r["verdict"]} for r in results]
    # real_stats (ALDO return history) lets the fixer cite evidence, e.g. "70% of size returns: too small".
    payload = {"product_page": page, "hidden_truth": truth, "shoppers": shoppers}
    return _analyst(FIXER)(json.dumps(payload, indent=1), structured_output_model=Fixes).structured_output
