"""Render a run as a simple HTML page: one card per shopper, showing whether they're likely to return.

  uv run python -m tunnel.html_report [runs/<timestamp>]     # default: latest run
"""
import json
import re
import sys
from html import escape

from tunnel import config

# The page note that answers each return reason (shown as "Fix" on the after-fixes line).
FIX_FOR = {"Too small": "fitNote", "Too big": "fitNote", "Too small (calf)": "fitNote", "Colour": "colourNote",
           "Not as described": "materialNote", "Uncomfortable": "comfortNote"}

CSS = """
.viz-root {
  color-scheme: light;
  --page: #f9f9f7; --surface-1: #fcfcfb; --text-primary: #0b0b0b; --text-secondary: #52514e; --muted: #898781;
  --grid: #e1e0d9; --border: rgba(11,11,11,0.10); --good: #0ca30c; --critical: #d03b3b;
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) .viz-root {
    color-scheme: dark;
    --page: #0d0d0d; --surface-1: #1a1a19; --text-primary: #f0efec; --text-secondary: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --border: rgba(255,255,255,0.10);
  }
}
* { box-sizing: border-box; }
body { margin: 0; }
.viz-root { background: var(--page); color: var(--text-primary); min-height: 100vh;
  font: 14px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; padding: 32px 24px 64px; }
.wrap { max-width: 1040px; margin: 0 auto; }
h1 { font-size: 24px; margin: 0; }
.sub, .muted { color: var(--text-secondary); } .tiny { font-size: 12px; color: var(--muted); }
.card { background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; padding: 16px; }
.kpis { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 20px 0 28px; }
.kpi .label { font-size: 13px; color: var(--text-secondary); }
.kpi .value { font-size: 30px; font-weight: 600; margin-top: 2px; }
.kpi .value small { font-size: 15px; font-weight: 500; color: var(--text-secondary); }
.grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; }
.head { display: flex; gap: 12px; align-items: center; }
.head img { width: 64px; height: 64px; object-fit: cover; border-radius: 8px; background: var(--grid); flex: none; }
.head .name { font-weight: 600; font-size: 16px; }
.hides { font-size: 12px; color: var(--text-secondary); margin-top: 2px; }
.shopper { font-size: 13px; color: var(--text-secondary); margin: 12px 0 8px; }
.verdict { display: flex; gap: 10px; align-items: center; border-radius: 10px; padding: 12px; }
.verdict .icon { flex: none; width: 28px; height: 28px; border-radius: 50%; color: #fff; font-weight: 700;
  display: flex; align-items: center; justify-content: center; }
.verdict b { font-size: 17px; } .verdict .reason { font-size: 13px; color: var(--text-secondary); }
.bad { background: color-mix(in srgb, var(--critical) 11%, transparent); } .bad .icon { background: var(--critical); }
.good { background: color-mix(in srgb, var(--good) 11%, transparent); } .good .icon { background: var(--good); }
.none { background: color-mix(in srgb, var(--muted) 13%, transparent); } .none .icon { background: var(--muted); }
.line { font-size: 13px; margin-top: 8px; } .line span { color: var(--text-secondary); }
.after { margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--grid); }
.after .verdict { padding: 8px 10px; } .after .verdict b { font-size: 14px; }
.after .verdict .icon { width: 22px; height: 22px; font-size: 12px; }
@media (max-width: 800px) { .grid, .kpis { grid-template-columns: 1fr; } }
"""


def e(x):
    return escape("" if x is None else str(x))


def size(x):
    return "—" if x is None else f"{x:g}"


def verdict(r, pid, names):
    """(css class, icon, headline, sub-line) for one shopping session."""
    d, v = r["decision"], r["verdict"]
    if not d["bought"]:
        return "none", "–", "Didn't buy", "left without buying"
    other = "" if d["product_id"] == pid else f" · bought {names.get(d['product_id'], d['product_id'])} instead"
    if v["likely_return"]:
        return "bad", "✕", "Likely to return", f"{v['reason']}{other}"
    return "good", "✓", "Likely to keep", other.lstrip(" ·") or "the page did its job"


def first_sentence(text):
    return re.split(r"(?<=[.!?])\s", text or "", maxsplit=1)[0]


def bought_line(r, names):
    d, sc = r["decision"], r.get("size_check")
    if not d["bought"]:
        return "Didn't buy"
    text = f"Bought {names.get(d['product_id'], d['product_id'])} · {d['colour'] or '—'} · size {size(d['size'])}"
    if sc and not sc["ok"]:
        text += f" (should be {size(sc['expected'])})"
    return text


def card(r, re_r, product, truth, fixes, names):
    pid = product["id"]
    cls, icon, head, sub = verdict(r, pid, names)
    img = (product.get("images") or [""])[0]
    entry = "arrived from an ad" if r.get("entry", "ad") == "ad" else "browsed the category"
    html = f"""
<div class='card'>
  <div class='head'>{f"<img src='{e(img)}?auto=format&fit=crop&w=160&h=160&q=70' alt=''>" if img else ''}
    <div><div class='name'>{e(product['name'])} <span class='tiny'>{e(product['type'])}</span></div>
      <div class='hides'>What the page hides: {e(' · '.join(truth.get('issues', [])) or 'nothing known')}</div></div></div>
  <div class='shopper'>{e(r['label'])} · {entry}</div>
  <div class='verdict {cls}'><span class='icon' aria-hidden='true'>{icon}</span>
    <div><b>{e(head)}</b><div class='reason'>{e(sub)}</div></div></div>
  <div class='line'>{e(bought_line(r, names))}</div>
  <div class='line'><span>Why:</span> {e(first_sentence(r['verdict']['page_gap']) or 'the page gave them what they needed')}</div>"""
    if re_r:
        acls, aicon, ahead, asub = verdict(re_r, pid, names)
        note = fixes.get(FIX_FOR.get(r["verdict"]["reason"], ""))
        html += f"""
  <div class='after'><div class='tiny'>After the fixer's page fixes</div>
    <div class='verdict {acls}'><span class='icon' aria-hidden='true'>{aicon}</span>
      <div><b>{e(ahead)}</b><div class='reason'>{e(asub)} · {e(bought_line(re_r, names))}</div></div></div>
    {f"<div class='line'><span>Fix:</span> {e(note)}</div>" if note else ''}</div>"""
    return html + "\n</div>"


def render(run_dir):
    products = {p["id"]: p for p in json.loads(config.PRODUCTS.read_text())}
    names = {k: p["name"] for k, p in products.items()}
    truth = json.loads(config.TRUTH.read_text())
    cards, n, ret_before, ret_after, n_after = [], 0, 0, 0, 0
    for f in sorted(run_dir.glob("*.json"), key=lambda f: f.stat().st_mtime):  # run order
        res = json.loads(f.read_text())
        pid = res["product"]
        re_by_id = {r["persona_id"]: r for r in res.get("retest") or []}
        for r in res["results"]:
            re_r = re_by_id.get(r["persona_id"])
            cards.append(card(r, re_r, products[pid], truth[pid], res["fixes"], names))
            n += 1
            ret_before += r["verdict"]["likely_return"]
            if re_r:
                n_after += 1
                ret_after += re_r["verdict"]["likely_return"]
    after_tile = (f"<div class='value'>{ret_after} <small>of {n_after}</small></div>" if n_after
                  else "<div class='value'>— <small>run with --verify</small></div>")
    return f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Wind tunnel · {e(run_dir.name)}</title><style>{CSS}</style></head>
<body><div class='viz-root'><div class='wrap'>
<div class='tiny'>Returns wind tunnel · run {e(run_dir.name)}</div>
<h1>Would these shoppers send it back?</h1>
<div class='sub'>Each card is one virtual shopper on one product page, judged against what the photo and page hide.</div>
<div class='kpis'>
  <div class='card kpi'><div class='label'>Shopping runs</div><div class='value'>{n}</div></div>
  <div class='card kpi'><div class='label'>Likely to return, original page</div>
    <div class='value'>{ret_before} <small>of {n}</small></div></div>
  <div class='card kpi'><div class='label'>Likely to return, after fixes</div>{after_tile}</div>
</div>
<div class='grid'>{''.join(cards)}</div>
</div></div></body></html>"""


def write(run_dir):
    path = run_dir / "report.html"
    path.write_text(render(run_dir))
    return path


if __name__ == "__main__":
    run = config.ROOT / sys.argv[1] if len(sys.argv) > 1 else max(p for p in config.RUNS.iterdir() if p.is_dir())
    print(write(run))
