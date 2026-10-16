"""Render a run's results.json as a self-contained HTML report, one section per agent.

  uv run python -m tunnel.html_report [runs/<timestamp>]     # default: latest run
"""
import csv
import json
import sys
from collections import Counter
from html import escape

from tunnel import config

# Customer-pool return reasons -> (label, categorical slot). Fixed order: colour follows the reason.
BUCKETS = {"too_small": ("Too small", 1), "too_big": ("Too big", 2),
           "uncomfortable": ("Uncomfortable", 3), "look": ("Colour / look", 4)}

CSS = """
.viz-root {
  color-scheme: light;
  --page: #f9f9f7; --surface-1: #fcfcfb; --text-primary: #0b0b0b; --text-secondary: #52514e; --muted: #898781;
  --grid: #e1e0d9; --axis: #c3c2b7; --border: rgba(11,11,11,0.10); --success-text: #006300;
  --series-1: #2a78d6; --series-2: #eb6834; --series-3: #1baf7a; --series-4: #eda100; --series-1-soft: #86b6ef;
  --good: #0ca30c; --critical: #d03b3b; --warning: #fab219;
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) .viz-root {
    color-scheme: dark;
    --page: #0d0d0d; --surface-1: #1a1a19; --text-primary: #f0efec; --text-secondary: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10); --success-text: #0ca30c;
    --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70; --series-4: #c98500; --series-1-soft: #184f95;
  }
}
* { box-sizing: border-box; }
body { margin: 0; }
.viz-root { background: var(--page); color: var(--text-primary); min-height: 100vh;
  font: 14px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; padding: 32px 24px 64px; }
.wrap { max-width: 1120px; margin: 0 auto; }
h1 { font-size: 26px; margin: 0; } h2 { font-size: 18px; margin: 0 0 4px; } h3 { font-size: 14px; margin: 0 0 6px; }
.sub, .muted { color: var(--text-secondary); } .tiny { font-size: 12px; color: var(--muted); }
section { margin-top: 36px; }
.card { background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; padding: 18px; }
.agent-tag { display: inline-block; font-size: 11px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase;
  color: var(--text-secondary); border: 1px solid var(--border); border-radius: 999px; padding: 2px 9px; margin-bottom: 8px; }
.kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 20px; }
.tile .label { color: var(--text-secondary); font-size: 13px; }
.tile .value { font-size: 34px; font-weight: 600; line-height: 1.15; margin-top: 4px; }
.tile .value small { font-size: 16px; font-weight: 500; color: var(--text-secondary); }
.tile .delta { font-size: 13px; margin-top: 4px; color: var(--text-secondary); }
.tile .delta.good { color: var(--success-text); font-weight: 600; }
/* range chart */
.range { margin-top: 12px; }
.range-row { display: grid; grid-template-columns: 120px 1fr 110px; align-items: center; gap: 12px; height: 40px; }
.track { position: relative; height: 28px; }
.track .grid { position: absolute; top: 0; bottom: 0; width: 1px; background: var(--grid); }
.track .base { position: absolute; left: 0; right: 0; top: 50%; height: 1px; background: var(--axis); }
.track .band { position: absolute; top: 7px; height: 14px; border-radius: 4px; background: var(--series-1); opacity: .18; }
.track .dot { position: absolute; top: 50%; width: 14px; height: 14px; margin: -7px 0 0 -7px; border-radius: 50%;
  background: var(--series-1); box-shadow: 0 0 0 2px var(--surface-1); }
.track .hit { position: absolute; top: 0; bottom: 0; cursor: default; }
.axis-row { display: grid; grid-template-columns: 120px 1fr 110px; gap: 12px; }
.axis { position: relative; height: 16px; font-size: 11px; color: var(--muted); font-variant-numeric: tabular-nums; }
.axis span { position: absolute; transform: translateX(-50%); }
.range-val { font-weight: 600; font-variant-numeric: tabular-nums; }
/* pipeline */
.pipeline { display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; margin-top: 12px; }
.step { position: relative; background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; padding: 12px; }
.step:not(:last-child)::after { content: "→"; position: absolute; right: -10px; top: 50%; transform: translate(50%, -50%);
  color: var(--muted); font-size: 14px; }
.step .n { font-size: 11px; color: var(--muted); font-weight: 600; }
.step .name { font-weight: 600; margin: 2px 0 4px; }
.step .out { font-size: 12px; color: var(--text-secondary); }
.step .llm { font-size: 10.5px; color: var(--muted); margin-top: 6px; }
/* outcome matrix */
table { border-collapse: collapse; width: 100%; }
th { text-align: left; font-size: 12px; font-weight: 600; color: var(--text-secondary); padding: 8px 10px; border-bottom: 1px solid var(--axis); }
td { padding: 10px; border-bottom: 1px solid var(--grid); vertical-align: top; }
.outcome { display: flex; gap: 8px; align-items: flex-start; border-radius: 8px; padding: 8px 10px; }
.outcome .icon { flex: none; width: 20px; height: 20px; border-radius: 50%; color: #fff; font-size: 12px; font-weight: 700;
  display: flex; align-items: center; justify-content: center; margin-top: 1px; }
.outcome.good { background: color-mix(in srgb, var(--good) 10%, transparent); } .outcome.good .icon { background: var(--good); }
.outcome.bad { background: color-mix(in srgb, var(--critical) 10%, transparent); } .outcome.bad .icon { background: var(--critical); }
.outcome.none { background: color-mix(in srgb, var(--muted) 12%, transparent); } .outcome.none .icon { background: var(--muted); }
.outcome .lbl { display: block; } .outcome .what { font-size: 12px; color: var(--text-secondary); }
.chip { display: inline-block; font-size: 11.5px; border: 1px solid var(--border); border-radius: 999px; padding: 1px 8px;
  margin: 2px 4px 2px 0; color: var(--text-secondary); background: var(--surface-1); }
.chip.hidden { border-style: solid; background: color-mix(in srgb, var(--warning) 14%, transparent); color: var(--text-primary); }
.other { font-size: 11px; color: var(--muted); margin-top: 2px; }
/* data refinement */
.two { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
dl { display: grid; grid-template-columns: 130px 1fr; gap: 4px 12px; margin: 0; font-size: 13px; }
dt { color: var(--text-secondary); } dd { margin: 0; }
.stack { display: flex; gap: 2px; height: 24px; margin-top: 10px; }
.stack div { border-radius: 0; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; }
.stack div:first-child { border-radius: 4px 0 0 4px; } .stack div:last-child { border-radius: 0 4px 4px 0; }
.legend { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 8px; font-size: 12.5px; color: var(--text-secondary); }
.legend i { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 6px; vertical-align: -1px; }
details.table-view { margin-top: 8px; font-size: 12.5px; } details.table-view summary { cursor: pointer; color: var(--text-secondary); }
details.table-view td, details.table-view th { padding: 4px 8px; font-variant-numeric: tabular-nums; }
/* persona cards */
.persona { margin-top: 14px; }
.persona-head { display: flex; justify-content: space-between; gap: 12px; align-items: baseline; flex-wrap: wrap; }
summary.persona-head { cursor: pointer; list-style: none; align-items: center; }
summary.persona-head::-webkit-details-marker { display: none; }
summary.persona-head h2::before { content: "▸ "; color: var(--muted); }
details[open] > summary.persona-head h2::before { content: "▾ "; }
.mini { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; border-radius: 999px; padding: 3px 10px 3px 4px; margin-left: 6px; }
.mini .icon { width: 16px; height: 16px; border-radius: 50%; color: #fff; font-size: 10px; font-weight: 700; display: inline-flex; align-items: center; justify-content: center; }
.mini.good { background: color-mix(in srgb, var(--good) 10%, transparent); } .mini.good .icon { background: var(--good); }
.mini.bad { background: color-mix(in srgb, var(--critical) 10%, transparent); } .mini.bad .icon { background: var(--critical); }
.mini.none { background: color-mix(in srgb, var(--muted) 12%, transparent); } .mini.none .icon { background: var(--muted); }
details.more summary { cursor: pointer; font-size: 12px; color: var(--text-secondary); margin: -4px 0 8px; }
.brief { margin: 10px 0 4px; padding: 10px 12px; border-left: 3px solid var(--series-1); background: var(--page); border-radius: 0 6px 6px 0; }
.runs { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 12px; }
.run { border: 1px solid var(--border); border-radius: 8px; padding: 12px; }
.run h4 { margin: 0 0 8px; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: var(--text-secondary); }
.timeline { list-style: none; margin: 6px 0 10px; padding: 0 0 0 14px; border-left: 1px solid var(--axis); font-size: 12.5px; }
.timeline li { position: relative; padding: 2px 0 2px 6px; color: var(--text-secondary); }
.timeline li::before { content: ""; position: absolute; left: -19px; top: 9px; width: 8px; height: 8px; border-radius: 50%;
  background: var(--series-1); box-shadow: 0 0 0 2px var(--surface-1); }
.timeline li b { color: var(--text-primary); font-weight: 600; }
.quote { font-style: italic; margin: 8px 0; }
.kv { font-size: 12.5px; margin-top: 6px; } .kv span { color: var(--text-secondary); }
.judge { margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--grid); font-size: 13px; }
/* fixer */
.weak { display: grid; grid-template-columns: 1fr 200px; gap: 16px; padding: 12px 0; border-bottom: 1px solid var(--grid); }
.weak:last-child { border-bottom: 0; }
.bar-track { position: relative; height: 10px; margin-top: 6px; }
.bar-track .bar { position: absolute; left: 0; top: 0; bottom: 0; background: var(--series-1); border-radius: 0 4px 4px 0; }
.bar-label { font-size: 12px; color: var(--text-secondary); margin-top: 4px; font-variant-numeric: tabular-nums; }
.fixes { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 12px; }
.note { border-radius: 8px; padding: 10px 12px; background: var(--page); border: 1px solid var(--border); }
.note b { display: block; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: var(--text-secondary); margin-bottom: 4px; }
ol.shots { margin: 4px 0 0; padding-left: 18px; }
.method { font-size: 13px; color: var(--text-secondary); }
.method code { font-size: 12.5px; }
#tip { position: fixed; pointer-events: none; background: var(--surface-1); color: var(--text-primary); border: 1px solid var(--border);
  border-radius: 6px; padding: 6px 9px; font-size: 12px; box-shadow: 0 4px 16px rgba(0,0,0,.12); display: none; max-width: 280px; }
#tip strong { display: block; font-size: 13px; }
@media (max-width: 900px) { .kpis, .pipeline { grid-template-columns: repeat(2, 1fr); } .two, .runs, .fixes { grid-template-columns: 1fr; }
  .step::after { display: none; } }
"""

# Tooltips enhance, never gate: every value is also printed on the page. Text goes in via textContent.
JS = """
const tip = document.getElementById('tip');
document.querySelectorAll('[data-tip-value]').forEach(el => {
  const show = (x, y) => {
    tip.replaceChildren();
    const v = document.createElement('strong'); v.textContent = el.dataset.tipValue;
    const l = document.createElement('span'); l.textContent = el.dataset.tipLabel || '';
    tip.append(v, l); tip.style.display = 'block';
    tip.style.left = Math.min(x + 12, innerWidth - 300) + 'px'; tip.style.top = (y + 12) + 'px';
  };
  el.addEventListener('pointermove', ev => show(ev.clientX, ev.clientY));
  el.addEventListener('pointerleave', () => tip.style.display = 'none');
  el.tabIndex = 0;
  el.addEventListener('focus', () => { const r = el.getBoundingClientRect(); show(r.left, r.bottom); });
  el.addEventListener('blur', () => tip.style.display = 'none');
});
"""


def e(x):
    return escape("" if x is None else str(x))


def pct(x):
    return f"{round(x * 100)}%"


def size(x):
    return "—" if x is None else f"{x:g}"


def outcome(r, pid, names):
    """Status of one shopping session for the tested style: good / bad / none, with icon + label."""
    d, v = r["decision"], r["verdict"]
    what = f"{names.get(d['product_id'], d['product_id'])} · colour {d['colour'] or '—'} · size {size(d['size'])}"
    if not d["bought"]:
        return "none", "–", "Didn't buy", "left without buying", None
    other = None if d["product_id"] == pid else "other style, not counted in this page's rate"
    if v["likely_return"]:
        return "bad", "✕", f"Likely return · {v['reason']}", what, other
    return "good", "✓", "Keeps it", what, other


def outcome_cell(r, pid, names):
    if r is None:
        return "<td class='tiny'>not re-tested</td>"
    cls, icon, label, what, other = outcome(r, pid, names)
    return (f"<td><div class='outcome {cls}'><span class='icon' aria-hidden='true'>{icon}</span><div>"
            f"<b class='lbl'>{e(label)}</b><div class='what'>{e(what)}</div>"
            + (f"<div class='other'>{e(other)}</div>" if other else "") + "</div></div></td>")


def range_chart(before, after, counts):
    rows = [("Original page", before, counts[0])] + ([("After fixes", after, counts[1])] if after else [])
    grid = "".join(f"<div class='grid' style='left:{t}%'></div>" for t in (0, 25, 50, 75, 100))
    out = []
    for name, r, (ret, n) in rows:
        lo, hi = max(0.0, r["rate"] - r["range"]), min(1.0, r["rate"] + r["range"])
        tipv = f"{pct(r['rate'])} ± {pct(r['range'])}"
        tipl = f"{name}: {ret} of {n} buyers likely return · range {pct(lo)}–{pct(hi)}"
        out.append(
            f"<div class='range-row'><div>{e(name)}</div><div class='track'>{grid}<div class='base'></div>"
            f"<div class='band' style='left:{lo*100}%;width:{(hi-lo)*100}%'></div>"
            f"<div class='dot' style='left:{r['rate']*100}%'></div>"
            f"<div class='hit' style='left:{lo*100-2}%;width:{(hi-lo)*100+4}%' data-tip-value='{e(tipv)}' data-tip-label='{e(tipl)}'></div>"
            f"</div><div class='range-val'>{e(tipv)}</div></div>")
    axis = "".join(f"<span style='left:{t}%'>{t}%</span>" for t in (0, 25, 50, 75, 100))
    return "".join(out) + f"<div class='axis-row'><div></div><div class='axis'>{axis}</div><div></div></div>"


def tally(rs, pid):
    bought = [r for r in rs if r["decision"]["bought"] and r["decision"]["product_id"] == pid]
    return sum(r["verdict"]["likely_return"] for r in bought), len(bought)


def clean_step(s):
    s = s.replace(config.SITE_URL, "").replace("/?sim=1&v=tunnel", "").replace("/?sim=1", "")
    verb, _, arg = s.partition(": ")
    if verb == "snapshot" or arg.startswith(("target=", "ref=")):  # snapshot args and bare element ids say nothing
        arg = "" if verb == "snapshot" else "a page element"
    verb = {"navigate": "Open", "click": "Click", "snapshot": "Read the page", "navigate_back": "Go back"}.get(verb, verb)
    return f"<b>{e(verb)}</b> {e(arg)}" if arg else f"<b>{e(verb)}</b>"


def timeline(steps, keep=6):
    """Browsing steps with repeats collapsed; long sessions fold after the first few."""
    items = []
    for s in map(clean_step, steps):
        if items and items[-1][0] == s:
            items[-1][1] += 1
        else:
            items.append([s, 1])
    lis = [f"<li>{s}{f' <span class=tiny>×{n}</span>' if n > 1 else ''}</li>" for s, n in items]
    head = f"<ol class='timeline'>{''.join(lis[:keep])}</ol>"
    if len(lis) <= keep:
        return head
    return head + (f"<details class='more'><summary>Show {len(lis) - keep} more steps</summary>"
                   f"<ol class='timeline'>{''.join(lis[keep:])}</ol></details>")


def session(r, pid, names, title):
    if r is None:
        return f"<div class='run'><h4>{e(title)}</h4><p class='tiny'>Not re-tested (run with --verify).</p></div>"
    d, v, sc = r["decision"], r["verdict"], r["size_check"]
    cls, icon, label, what, other = outcome(r, pid, names)
    chips = lambda xs: "".join(f"<span class='chip'>{e(x)}</span>" for x in xs) or "<span class='tiny'>none</span>"
    size_line = (f"Expected size <b>{size(sc['expected'])}</b> · chose <b>{size(sc['chosen'])}</b> → "
                 + ("fits" if sc["ok"] else e(sc["result"].lower()))) if sc else "No size check (no purchase)."
    return f"""
<div class='run'><h4>{e(title)}</h4>
  <div class='tiny'>Shopper agent · {len(r['steps'])} browser actions</div>
  {timeline(r['steps'])}
  <div class='kv'><span>Decision:</span> {e(what if d['bought'] else "didn't buy")} · rated {d['rating']}/5</div>
  <p class='quote'>“{e(d['quote'])}”</p>
  <div class='kv'><span>Photo cues used:</span><br>{chips(d['visual_cues_used'])}</div>
  <div class='kv'><span>Wished the page said:</span><br>{chips(d['info_wished_for'])}</div>
  <div class='judge'><div class='agent-tag'>Judge</div>
    <div class='outcome {cls}'><span class='icon' aria-hidden='true'>{icon}</span><div><b class='lbl'>{e(label)}</b>
      <div class='what'>{size_line}</div>{f"<div class='other'>{e(other)}</div>" if other else ""}</div></div>
    <div class='kv'><span>Page gap:</span> {e(v['page_gap'] or 'none: the page did its job')}</div>
    <div class='kv'><span>Evidence:</span> {e(v['evidence'])}</div>
  </div>
</div>"""


def render(run_dir):
    res = json.loads((run_dir / "results.json").read_text())
    pid = res["product"]
    products = {p["id"]: p for p in json.loads(config.PRODUCTS.read_text())}
    names = {k: p["name"] for k, p in products.items()}
    product, truth = products[pid], json.loads(config.TRUTH.read_text())[pid]
    cues = json.loads(config.VISUAL.read_text())[pid]
    with open(config.CUSTOMERS, newline="") as f:
        customers = list(csv.DictReader(f))
    by_id = {c["persona_id"]: c for c in customers}
    results, retest = res["results"], res.get("retest") or []
    re_by_id = {r["persona_id"]: r for r in retest}
    before, after, fixes = res["before"], res.get("after"), res["fixes"]
    b_ret, b_n = tally(results, pid)
    a_ret, a_n = tally(retest, pid) if retest else (0, 0)
    chose = sum(r["decision"]["product_id"] == pid for r in results)
    steps_total = sum(len(r["steps"]) for r in results + retest)

    # --- KPI tiles
    delta = ""
    if after:
        pts = round((after["rate"] - before["rate"]) * 100)
        delta = f"<div class='delta {'good' if pts < 0 else ''}'>{'↓' if pts < 0 else '↑'} {abs(pts)} pts vs original page</div>"
    kpis = f"""
<div class='kpis'>
  <div class='card tile'><div class='label'>Predicted return rate, original page</div>
    <div class='value'>{pct(before['rate'])} <small>± {pct(before['range'])}</small></div>
    <div class='delta'>{b_ret} of {b_n} {e(product['name'])} buyers</div></div>
  <div class='card tile'><div class='label'>After wind-tunnel fixes</div>
    <div class='value'>{pct(after['rate']) if after else '—'} <small>{('± ' + pct(after['range'])) if after else 'not re-tested'}</small></div>
    {delta or "<div class='delta'>run with --verify</div>"}</div>
  <div class='card tile'><div class='label'>Shoppers who chose {e(product['name'])}</div>
    <div class='value'>{chose} <small>of {len(results)}</small></div>
    <div class='delta'>others bought a different style</div></div>
  <div class='card tile'><div class='label'>Page weaknesses found</div>
    <div class='value'>{len(fixes['weaknesses'])}</div>
    <div class='delta'>{sum(1 for k in ('fitNote', 'colourNote', 'photoStatus') if fixes.get(k))} page fixes drafted</div></div>
</div>"""

    # --- pipeline strip
    pipeline_steps = [
        ("Data refinement", f"OMS returns → photo cues, hidden truth, {len(customers)} customer profiles", "Python, no LLM"),
        ("Persona builder", f"{len(results)} shoppers built from the {len(customers)} profiles", "Claude on Bedrock"),
        ("Shoppers", f"{len(results) + len(retest)} browsing sessions · {steps_total} browser actions", "Strands + Playwright MCP"),
        ("Judge", f"{b_ret} of {b_n} likely returns on the original page", "rules + Claude"),
        ("Fixer", f"{len(fixes['weaknesses'])} weaknesses → fit note, colour note, shot list, feed facts", "Claude on Bedrock"),
        ("Re-test", f"same shoppers on the fixed page: {pct(after['rate'])}" if after else "skipped", "Strands + Playwright MCP"),
    ]
    pipeline = "".join(
        f"<div class='step'><div class='n'>Agent {i}</div><div class='name'>{e(n)}</div>"
        f"<div class='out'>{e(o)}</div><div class='llm'>{e(t)}</div></div>"
        for i, (n, o, t) in enumerate(pipeline_steps, 1))

    # --- outcome matrix
    rows = []
    for r in results:
        c = by_id.get(r["persona_id"], {})
        entry = "Arrived from an ad" if r.get("entry", "ad") == "ad" else f"Browsed {product['category'].lower()}"
        past = f"Returned {names.get(c.get('past_product_id'), c.get('past_product_id'))} · {c.get('raw_reason', '')}"
        rows.append(f"<tr><td><b>{e(r['label'])}</b><br><span class='chip'>{e(entry)}</span>"
                    f"<span class='chip hidden'>{e(past)}</span></td>"
                    f"{outcome_cell(r, pid, names)}{outcome_cell(re_by_id.get(r['persona_id']), pid, names) if retest else ''}</tr>")
    matrix = (f"<table><thead><tr><th style='width:34%'>Shopper</th><th>Original page</th>"
              + ("<th>After fixes</th>" if retest else "") + "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>")

    # --- data refinement: what shoppers see vs hidden truth, and the customer pool
    stats = truth.get("real_stats")
    stats_html = (f"<dt>Real ALDO data</dt><dd>{stats['returns']:,} returns of {stats['unitsSoldSample']:,} sold "
                  f"({pct(stats['returnRate'])}); {pct(stats['tooSmallShareOfSizeReturns'])} of size returns say too small</dd>"
                  if stats else "<dt>Real ALDO data</dt><dd>new style, no return history yet</dd>")
    pool = Counter(c["return_bucket"] for c in customers)
    total = sum(pool.values())
    ink = {1: "#fff", 2: "#0b0b0b", 3: "#0b0b0b", 4: "#0b0b0b"}
    segs = "".join(
        f"<div style='flex:{pool[b]};background:var(--series-{s});color:{ink[s]}' "
        f"data-tip-value='{pool[b]} customers' data-tip-label='{e(lbl)} · {pct(pool[b] / total)} of the pool'>"
        f"{pool[b] if pool[b] / total >= 0.05 else ''}</div>"
        for b, (lbl, s) in BUCKETS.items() if pool[b])
    legend = "".join(f"<span><i style='background:var(--series-{s})'></i>{e(lbl)} · {pool[b]}</span>"
                     for b, (lbl, s) in BUCKETS.items() if pool[b])
    pool_table = "".join(f"<tr><td>{e(lbl)}</td><td>{pool[b]}</td><td>{pct(pool[b] / total)}</td></tr>"
                         for b, (lbl, s) in BUCKETS.items())
    page_details = product["details"]
    data_section = f"""
<div class='two'>
  <div class='card'><div class='agent-tag'>What shoppers see</div><h3>{e(product['name'])} product page + photo cues</h3>
    <dl><dt>Photo shows</dt><dd>{e(cues['texture'])} · {e(cues['shape'])} · <b>{e(cues['colour_as_seen'])}</b> · {e(cues['style'])}</dd>
      <dt>Description</dt><dd>{e(product['description'])}</dd>
      <dt>Details</dt><dd>{e(page_details['material'])} · {e(page_details['toe'])} · {page_details['heelCm']} cm heel · width “{e(page_details['width'])}”</dd>
      <dt>Colours</dt><dd>{e(', '.join(c['name'] for c in product['colours']))}</dd>
      <dt>Fit guidance</dt><dd class='muted'>none on the original page</dd></dl></div>
  <div class='card'><div class='agent-tag'>Hidden truth · judge only</div><h3>What the shoe is really like</h3>
    <dl><dt>Fit</dt><dd>{e(truth['fit'])}</dd><dt>Width</dt><dd><b>{e(truth['width'])}</b></dd>
      <dt>True colour</dt><dd><b>{e(truth['true_colour'])}</b>{' (photo misleads)' if truth['colour_misleads'] else ''}</dd>
      <dt>Comfort</dt><dd>{e(truth['comfort'])}</dd>{stats_html}</dl></div>
</div>
<div class='card' style='margin-top:12px'><h3>Customer pool: {total} made-up profiles, each tied to a real OMS return line</h3>
  <div class='tiny'>Split by the reason they returned their past purchase, in proportion to the real return mix</div>
  <div class='stack'>{segs}</div><div class='legend'>{legend}</div>
  <details class='table-view'><summary>Table view</summary><table><tr><th>Return reason</th><th>Customers</th><th>Share</th></tr>{pool_table}</table></details>
</div>"""

    # --- persona cards: persona builder -> shopper -> judge, original vs after
    cards = []
    for r in results:
        c = by_id.get(r["persona_id"], {})
        visible = [f"US {c.get('usual_size')}", f"{c.get('foot_width')} feet", c.get("brands_worn"), c.get("occasion"),
                   f"{c.get('hours_on_feet')} h on feet", c.get("notes")]
        if r.get("entry") == "browse":
            visible += [f"likes {c.get('preferred_colours')}", c.get("preferred_textures")]
        hidden = [f"bought {names.get(c.get('past_product_id'), c.get('past_product_id'))} in {c.get('past_size_bought')}",
                  f"returned: {c.get('raw_reason')}"]
        re_r = re_by_id.get(r["persona_id"])
        badges = "".join(
            f"<span class='mini {o[0]}'><span class='icon' aria-hidden='true'>{o[1]}</span>{e(t)}: {e(o[2])}</span>"
            for t, o in [("Original", outcome(r, pid, names)), ("After", outcome(re_r, pid, names) if re_r else None)] if o)
        cards.append(f"""
<details class='card persona'{' open' if not cards else ''}>
  <summary class='persona-head'><h2>{e(r['persona_id'])} · {e(r['label'])}</h2><span>{badges}</span></summary>
  <div class='tiny' style='margin:6px 0 8px'>customer {e(c.get('customer_uid'))} · {e(c.get('banner'))}</div>
  <div class='agent-tag'>Persona builder</div>
  <div>{''.join(f"<span class='chip'>{e(x)}</span>" for x in visible)}
    {''.join(f"<span class='chip hidden' title='Hidden from the shopper; used by the judge'>🔒 {e(x)}</span>" for x in hidden)}</div>
  <div class='brief'>{e(r['brief'])}<div class='tiny' style='margin-top:4px'>Goal: {e(r['goal'])} ·
    {'arrives from an ad' if r.get('entry', 'ad') == 'ad' else 'starts on the category page'}</div></div>
  <div class='runs'>{session(r, pid, names, 'Original page')}
    {session(re_by_id.get(r['persona_id']), pid, names, 'After fixes') if retest else ''}</div>
</details>""")

    # --- fixer
    n = len(results)
    weak = "".join(
        f"<div class='weak'><div><b>{i}. {e(w['gap'])}</b><div class='muted' style='margin-top:4px'>“{e(w['evidence'])}”</div></div>"
        f"<div><div class='bar-track' data-tip-value='{w['count']} of {n} shoppers' data-tip-label='hit this weakness'>"
        f"<div class='bar' style='width:{min(w['count'], n) / n * 100}%'></div></div>"
        f"<div class='bar-label'>{w['count']} of {n} shoppers</div></div></div>"
        for i, w in enumerate(fixes["weaknesses"], 1))
    shots = [s.strip(" -•") for s in (fixes.get("photoStatus") or "").replace(". ", ".\n").split("\n") if s.strip(" -•")]
    feed = "".join(f"<span class='chip'>{e(k)}: {e(v)}</span>" for k, v in (fixes.get("feedFacts") or {}).items() if v is not None)
    fixer = f"""
<div class='card'><div class='agent-tag'>Fixer</div><h3>Weaknesses, ranked by how many shoppers hit them</h3>{weak}</div>
<div class='fixes'>
  <div class='note'><b>Fit note (shown under the size picker)</b>{e(fixes.get('fitNote') or '—')}</div>
  <div class='note'><b>Colour note</b>{e(fixes.get('colourNote') or '—')}</div>
  <div class='note'><b>Photo shot list for staff</b><ol class='shots'>{''.join(f'<li>{e(s)}</li>' for s in shots) or '—'}</ol></div>
  <div class='note'><b>Product-feed facts (for AI shoppers)</b>{feed or '—'}</div>
</div>
<div class='card' style='margin-top:12px'><h3>Site-wide weaknesses</h3>
  <ul>{''.join(f'<li>{e(s)}</li>' for s in fixes.get('site_wide', []))}</ul>
  <div class='tiny'>All fixes are drafts: tunnel.json marks them approved: false until a merchandiser signs off.</div></div>"""

    return f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Wind tunnel · {e(product['name'])}</title><style>{CSS}</style></head>
<body><div class='viz-root'><div class='wrap'>
<header><div class='tiny'>Returns wind tunnel · run {e(run_dir.name)}</div>
  <h1>{e(product['name'])} · {e(product['type'])}</h1>
  <div class='sub'>Virtual shoppers built from past ALDO returns shopped this page. Would they repeat their past mistake, and what should the page say?</div></header>
{kpis}
<section><h2>Predicted return rate, with range</h2>
  <div class='tiny'>Share of {e(product['name'])} buyers whose purchase would likely come back. The band is the range (±1 standard error).</div>
  <div class='card range'>{range_chart(before, after, [(b_ret, b_n), (a_ret, a_n)])}</div></section>
<section><h2>The agent pipeline</h2><div class='pipeline'>{pipeline}</div></section>
<section><h2>Every shopper, before and after the fixes</h2>
  <div class='tiny'>Yellow chips are hidden from the shopper: they're the real past return this persona carries.</div>
  <div class='card' style='margin-top:10px'>{matrix}</div></section>
<section><h2>Agent 1 · Data refinement</h2>{data_section}</section>
<section><h2>Agents 2–4 · Persona builder → shopper → judge</h2><div class='tiny'>One card per shopper. Click a card to open it.</div>{''.join(cards)}</section>
<section><h2>Agent 5 · Fixer</h2>{fixer}</section>
<section><h2>How to read the numbers</h2><div class='card method'>
  <p><b>Return rate</b> = likely returns ÷ shoppers who bought {e(product['name'])}. Shoppers who bought another style are judged too, but not counted here.</p>
  <p><b>Range</b> = ±1 standard error of that share: <code>max(5%, √(p × (1 − p) ÷ n))</code>. It's widest when shoppers disagree (p near 50%) and shrinks as more shoppers run (√n). About 68% confidence; double it for about 95%. The 5% floor stops 0% or 100% from looking certain with only a handful of shoppers.</p>
  <p><b>Judge rules.</b> Size is deterministic: expected = usual size + the style's fit offset, plus ½ for wide feet on a narrow toe box. Colour is a return only when the shopper bought the colourway whose photo misleads, the page didn't correct it, and they have returned shoes for colour or look before. Claude judges comfort and writes the page gap.</p>
</div></section>
</div><div id='tip' role='tooltip'></div></div><script>{JS}</script></body></html>"""


def write(run_dir):
    path = run_dir / "report.html"
    path.write_text(render(run_dir))
    return path


if __name__ == "__main__":
    run = config.ROOT / sys.argv[1] if len(sys.argv) > 1 else max(config.RUNS.iterdir())
    print(write(run))
