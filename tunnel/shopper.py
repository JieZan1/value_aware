"""Virtual shopper: a Strands agent that browses the storefront through the Playwright MCP server."""
import re
import tempfile
from pathlib import Path

from mcp import StdioServerParameters, stdio_client
from pydantic import BaseModel, Field
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient

from tunnel import config

ALLOWED = {"browser_navigate", "browser_snapshot", "browser_click", "browser_navigate_back"}
LOCATOR = re.compile(r"getBy(\w+)\('([^']*)'(?:, \{ name: '([^']*)')?")
# Playwright MCP writes page snapshots and console logs; keep them out of the project folder.
MCP_OUTPUT = str(Path(tempfile.gettempdir()) / "wind-tunnel-playwright")

SYSTEM = """You are a real online shopper. Stay in character.

{brief}

{entry}
You will buy exactly one pair on this site today; price is not a concern.

How you shop:
- You only know what this website shows you. Don't use outside knowledge about these shoes or this brand.
- Lines starting with "Photo shows:" describe the product photo. Treat them as what your eyes see.
- You trust your usual size. Keep it unless the page itself says the style runs small or large, or tells you how
  to size. Your own foot shape alone is not a reason to change size.
- Pick the colour that matches what you liked in the photo, unless the page tells you something that changes your mind.
- To buy: on the product page click a colour swatch, click a size, then click "Add to bag". Then stop.
- Be quick, like a real shopper: about 12 browser actions at most. Think out loud in a sentence or two as you go.
"""

# How the shopper arrives. Ad shoppers mostly buy the advertised style; browsers spread across the category.
ENTRY = {
    "ad": "You came to this style's page from an ad because you liked its look. You may glance at one or two "
          "other styles, then buy the pair you like best.",
    "browse": "You're browsing this store's {category} to find the pair that suits you best. Open a few product "
              "pages and compare before you choose.",
}


class ShopperDecision(BaseModel):
    product_id: str | None = Field(description="id from the product URL (#/product/<id>) of what you bought, null if nothing")
    colour: str | None
    size: float | None
    bought: bool
    rating: int = Field(ge=1, le=5, description="how you feel about this product page, 1-5")
    quote: str = Field(description="1-2 sentences in your own voice, as you'd write in a review")
    visual_cues_used: list[str] = Field(description="what in the photo influenced you")
    site_facts_used: list[str] = Field(description="text on the page you relied on (fit, details, description)")
    info_wished_for: list[str] = Field(description="things you looked for but the page did not tell you")


def _locator(result_text):
    """Readable target from the Playwright code the MCP server ran, e.g. getByRole('button', { name: '8' })."""
    m = LOCATOR.search(result_text)
    if not m:
        return ""
    kind, first, name = m.groups()
    return f"“{name}” {first}" if kind == "Role" and name else f"“{first}”"


def _steps(messages):
    """Browser actions the shopper took, for the evidence trail."""
    results = {}
    for m in messages:
        for block in m.get("content", []):
            if res := block.get("toolResult"):
                results[res["toolUseId"]] = " ".join(c.get("text", "") for c in res.get("content", []))
    out = []
    for m in messages:
        for block in m.get("content", []):
            use = block.get("toolUse")
            if use and use["name"] in ALLOWED:
                inp = use["input"]
                arg = inp.get("element") or inp.get("url") or _locator(results.get(use["toolUseId"], ""))
                out.append(f"{use['name'].removeprefix('browser_')}: {arg}".strip(": "))
    return out


def shop(brief, goal, pid, category, entry="ad", after=False, headless=False):
    start = f"/product/{pid}" if entry == "ad" else f"/search?q={category}"
    url = f"{config.SITE_URL}/?sim=1{'&v=tunnel' if after else ''}#{start}"
    args = ["-y", "@playwright/mcp@latest", "--isolated", "--output-dir", MCP_OUTPUT] + (["--headless"] if headless else [])
    browser = MCPClient(lambda: stdio_client(StdioServerParameters(command="npx", args=args)), startup_timeout=60)
    with browser:
        tools = [t for t in browser.list_tools_sync() if t.tool_name in ALLOWED]
        agent = Agent(
            model=BedrockModel(model_id=config.SHOPPER_MODEL, region_name=config.REGION),
            system_prompt=SYSTEM.format(brief=brief, entry=ENTRY[entry].format(category=category.lower())),
            tools=tools,
        )
        result = agent(
            f"Open {url}. You're shopping for: {goal}. Choose your pair, colour and size, and add it to your bag.",
            structured_output_model=ShopperDecision,
        )
    return result.structured_output, _steps(agent.messages)


if __name__ == "__main__":
    decision, steps = shop(
        "You wear a US 8 with wide feet, usually in Steve Madden or Nike. You like soft suede and warm pinks.",
        "a heeled ankle boot for the office",
        "rosewood",
        "Boots",
    )
    print("\nSTEPS:", steps)
    print("DECISION:", decision.model_dump_json(indent=2))
