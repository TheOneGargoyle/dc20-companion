#!/usr/bin/env python3
"""Generate builds/builder.html - the rung-3 character-builder SKELETON (Tanrielle only).

Bakes the real engine + option catalog + ledger + a small Python glue module into ONE
self-contained page as base64 (the builds/spikes/pyodide-spike.html approach), so the page
runs the true tools/build_engine.py in the browser via Pyodide with no external data
dependency (works straight from file://). The page ALSO tries a live fetch() of the sibling
source files first, so a deployed https copy reads fresh data; the base64 bake is the
fallback that makes file:// (and the current Pages layout) work.

SCRIPTED - regenerate whenever the engine, catalog, or ledger change, so the page can never
drift from them (same discipline as tools/catalog_build.py):

    python3 tools/builder_build.py

De-risking scope (RUNG3_PLAN section 7 step 3): the whole level-up loop end-to-end on ONE
character and ONE editable decision (Tanrielle's L4 ancestry-trait spend), to prove Pyodide
before fanning out to the other five classes.
"""
import argparse
import base64
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)  # tools/.. == campaign/repo root

DEFAULTS = {
    "engine": os.path.join(REPO, "tools", "build_engine.py"),
    "ledger": os.path.join(REPO, "builds", "tanrielle.yaml"),
    "cls":    os.path.join(REPO, "builds", "catalog", "spellblade.yaml"),
    "anc":    os.path.join(REPO, "builds", "catalog", "ancestries.yaml"),
    "sch":    os.path.join(REPO, "builds", "catalog", "spell_schools.yaml"),
    "out":    os.path.join(REPO, "builds", "builder.html"),
}

# ---- Python glue that runs inside Pyodide (wraps the real engine + catalog) ----
API_PY = r"""
import yaml, json
import build_engine as eng

class BuilderAPI:
    # Loads the ledger + catalog and exposes a tiny JSON API to the page.
    # ONE decision is editable in this skeleton: the L4 ancestry-trait spend.
    def __init__(self, ledger_path, catalog_paths):
        self.ledger = yaml.safe_load(open(ledger_path, encoding='utf-8'))
        self.catalog = {k: yaml.safe_load(open(p, encoding='utf-8'))
                        for k, p in catalog_paths.items()}
        self.edit_level = 4
        lv = self.ledger.get('levels', {}).get(self.edit_level, []) or []
        self.edit_idx = next((i for i, e in enumerate(lv)
                              if e.get('slot') == 'ancestry_trait'), None)

    def _entry(self):
        return self.ledger['levels'][self.edit_level][self.edit_idx]

    def _ancestry_options(self):
        e = self._entry()
        src = e.get('source', 'Elf')
        lst = self.catalog['ancestries']['ancestries'].get(src, []) or []
        return src, [{'name': o['name'], 'cost': o['cost']} for o in lst]

    def _sections(self, lines):
        stats, budgets, sect = [], [], None
        for ln in lines:
            if ln.startswith('## '):
                h = ln[3:].strip()
                sect = ('budgets' if h.startswith('Point budgets')
                        else 'stats' if h.startswith('Derived') else None)
                continue
            if sect == 'stats' and ln.startswith('| '):
                c = [x.strip() for x in ln.strip('|').split('|')]
                if len(c) == 4 and c[0] not in ('Stat', '---'):
                    stats.append(c)
            elif sect == 'budgets' and ln.startswith('- '):
                budgets.append(ln[2:])
        return stats, budgets

    def _timeline(self):
        cg = self.ledger['chargen']
        cur = self.ledger.get('current_level')
        t = [{'level': 1, 'slot': 'chargen',
              'pick': 'attrs %s | schools %s | spells %s | maneuvers %s' % (
                  cg.get('attributes'), cg.get('spell_schools'),
                  cg.get('spells'), cg.get('maneuvers')),
              'cost': None, 'inferred': False, 'editable': False}]
        for lvl in sorted(self.ledger.get('levels', {})):
            if lvl > cur:
                continue
            for i, e in enumerate(self.ledger['levels'][lvl]):
                t.append({'level': lvl, 'slot': e.get('slot'), 'pick': e.get('pick'),
                          'cost': e.get('cost'), 'inferred': bool(e.get('inferred')),
                          'editable': (lvl == self.edit_level and i == self.edit_idx)})
        return t

    def state(self):
        cur = self.ledger['current_level']
        rep = eng.replay(self.ledger, cur)
        stats, budgets = self._sections(rep.lines)
        src, opts = self._ancestry_options()
        e = self._entry()
        planned = [l for l in sorted(self.ledger.get('levels', {})) if l > cur]
        return json.dumps({
            'character': self.ledger.get('character'),
            'klass': self.ledger.get('class'),
            'subclass': self.ledger.get('subclass'),
            'ancestry': self.ledger.get('ancestry'),
            'level': cur,
            'planned': planned,
            'edit': {'level': self.edit_level, 'source': src,
                     'current': e.get('pick'), 'current_cost': e.get('cost'),
                     'options': opts},
            'stats': stats, 'budgets': budgets, 'problems': rep.problems,
            'timeline': self._timeline(),
        })

    def set_ancestry(self, name):
        src, opts = self._ancestry_options()
        cost = next((o['cost'] for o in opts if o['name'] == name), None)
        e = self._entry()
        e['pick'] = name
        if cost is not None:
            e['cost'] = cost
        e['note'] = 'Edited in builder skeleton; cost %s from catalog (%s).' % (cost, src)
        e.pop('inferred', None)
        return self.state()

    def export_yaml(self):
        return yaml.dump(self.ledger, sort_keys=False, allow_unicode=True)
"""

TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DC20 Character Builder (skeleton) - Tanrielle</title>
<script src="https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js"></script>
<style>
:root{--ink:#1f2430;--muted:#6b7280;--line:#c9ced8;--paper:#f7f8fa;--accent:#3d5a80;
 --ok:#2e7d32;--bad:#b23;--warn:#b7791f}
*{box-sizing:border-box}
body{font-family:system-ui,Segoe UI,Arial,sans-serif;color:var(--ink);margin:0;background:#eef0f4;line-height:1.42}
.wrap{max-width:1060px;margin:0 auto;padding:1.3rem 1.3rem 3rem}
h1{font-size:1.35rem;margin:.1rem 0}
.badge{display:inline-block;font-size:.66rem;letter-spacing:.04em;text-transform:uppercase;
 background:var(--accent);color:#fff;border-radius:4px;padding:.12rem .45rem;vertical-align:middle}
.sub{color:var(--muted);font-size:.9rem;margin:.25rem 0 .9rem}
#status{font-size:.85rem;font-weight:600;background:#e9edf5;border:1px solid var(--line);
 border-radius:6px;padding:.5rem .75rem;margin-bottom:1rem}
#status.err{background:#fdecec;border-color:#f3b6b6;color:var(--bad)}
#status.ready{background:#e9f6ea;border-color:#a9d6ab;color:var(--ok)}
.builder{display:grid;grid-template-columns:150px 1fr;gap:1rem}
.card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:1rem}
h3.sec{font-size:.72rem;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin:.1rem 0 .55rem}
.rail ol{list-style:none;margin:0;padding:0}
.rail li{border:1px solid var(--line);border-radius:6px;padding:.4rem .5rem;margin-bottom:.35rem;font-size:.83rem;background:var(--paper)}
.rail li.cur{border-color:var(--accent);background:#eaf1f8;font-weight:600}
.rail li.next{border-style:dashed;color:var(--accent)}
.dec{border:1px solid var(--line);border-radius:7px;padding:.45rem .6rem;margin-bottom:.45rem;font-size:.86rem;display:flex;gap:.5rem;align-items:baseline}
.dec .lv{font-size:.7rem;color:#fff;background:var(--muted);border-radius:4px;padding:.05rem .4rem;min-width:26px;text-align:center}
.dec .slot{font-size:.7rem;color:var(--muted);text-transform:uppercase;letter-spacing:.03em;min-width:96px}
.dec .pick{flex:1}
.dec.inferred .pick{color:var(--muted);font-style:italic}
.dec.edit{border:1.5px solid var(--accent);background:#f4f8fc}
.dec.edit .slot{color:var(--accent)}
.wlabel{font-size:.64rem;text-transform:uppercase;letter-spacing:.05em;color:#fff;background:var(--accent);border-radius:4px;padding:.08rem .4rem}
.select{border:1px solid var(--accent);border-radius:6px;padding:.3rem .5rem;background:#fff;font-size:.85rem;min-width:230px}
table.derived{border-collapse:collapse;width:100%;font-size:.83rem;margin-top:.2rem}
table.derived th,table.derived td{border:1px solid var(--line);padding:.24rem .5rem;text-align:left}
table.derived th{background:var(--paper);color:var(--muted);font-weight:600;font-size:.72rem;text-transform:uppercase}
.mk-OK{color:var(--ok);font-weight:600}
.mk-MISMATCH{color:var(--bad);font-weight:700}
.budget{font-size:.82rem;margin:.15rem 0;color:#333}
.prob{background:#fdecec;border:1px solid #f3b6b6;color:var(--bad);border-radius:6px;padding:.5rem .7rem;font-size:.83rem;margin-top:.6rem}
.prob.clean{background:#e9f6ea;border-color:#a9d6ab;color:var(--ok)}
.prob ul{margin:.3rem 0 0;padding-left:1.1rem}
.exportbtn{margin-top:.7rem;background:var(--accent);color:#fff;border:none;border-radius:6px;padding:.5rem .95rem;font-size:.88rem;cursor:pointer}
.exportbtn:disabled{opacity:.5;cursor:default}
.foot{font-size:.76rem;color:var(--muted);margin-top:1rem}
.src{font-size:.72rem;color:var(--muted);margin-top:.4rem}
pre.yaml{background:#111;color:#c8e6c9;padding:.7rem;border-radius:6px;font-size:.76rem;white-space:pre-wrap;max-height:260px;overflow:auto;display:none}
</style></head>
<body><div class="wrap">
<h1>DC20 Character Builder <span class="badge">skeleton</span></h1>
<p class="sub">Rung-3 step 3: the whole level-up loop end-to-end on <b>one</b> character. The real
<code>build_engine.py</code> runs in your browser via Pyodide; edit the highlighted decision and the engine
re-validates live. Export writes the updated ledger YAML.</p>
<div id="status">Booting Pyodide (first load pulls a few MB from the CDN)&hellip;</div>

<div class="builder" id="app" style="display:none">
  <div class="card rail">
    <h3 class="sec">Levels</h3>
    <ol id="rail"></ol>
  </div>
  <div>
    <div class="card" style="margin-bottom:1rem">
      <h3 class="sec">Decisions <span class="wlabel">option-picker / ancestry-spend</span></h3>
      <div id="decisions"></div>
      <div class="src" id="srcinfo"></div>
    </div>
    <div class="card">
      <h3 class="sec">Review <span class="wlabel">live from replay()</span></h3>
      <table class="derived"><thead><tr><th>Stat</th><th>Derived</th><th>Sheet</th><th>Check</th></tr></thead>
        <tbody id="stats"></tbody></table>
      <div id="budgets" style="margin-top:.55rem"></div>
      <div id="problems"></div>
      <button class="exportbtn" id="export" disabled>&darr; Export tanrielle.yaml</button>
      <pre class="yaml" id="yamlout"></pre>
    </div>
  </div>
</div>

<p class="foot">Self-contained: engine, catalog and ledger are baked in (regenerate with
<code>tools/builder_build.py</code>). The page tries a live <code>fetch()</code> of the sibling source files first
and falls back to the bake, so it runs from <code>file://</code> or a server. Export is a clean re-serialisation
(inline YAML comments are not preserved yet - a v-next item); it round-trips cleanly through the engine.</p>

<script>
const B64 = {engine:"__ENGINE_B64__", ledger:"__LEDGER_B64__", cls:"__CLASS_B64__",
             anc:"__ANC_B64__", sch:"__SCH_B64__", api:"__API_B64__"};
const REL = {engine:"../tools/build_engine.py", ledger:"tanrielle.yaml",
             cls:"catalog/spellblade.yaml", anc:"catalog/ancestries.yaml", sch:"catalog/spell_schools.yaml"};
const dec = b => new TextDecoder().decode(Uint8Array.from(atob(b), c=>c.charCodeAt(0)));
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

async function srcText(key){
  // fetch-first (deployed https), base64 fallback (file:// or 404)
  if(REL[key]){ try{ const r = await fetch(REL[key]); if(r.ok) return {text:await r.text(), via:"fetch"}; }catch(e){} }
  return {text: dec(B64[key]), via:"baked"};
}

let api=null, viaNote="";
async function boot(){
  const pyodide = await loadPyodide();
  $('status').textContent = "Pyodide up. Installing PyYAML&hellip;";
  await pyodide.loadPackage("pyyaml");
  $('status').textContent = "Loading engine, catalog and ledger&hellip;";
  const vias = [];
  for(const [key,fname] of [["engine","build_engine.py"],["ledger","tanrielle.yaml"],
      ["cls","spellblade.yaml"],["anc","ancestries.yaml"],["sch","spell_schools.yaml"]]){
    const {text,via} = await srcText(key);
    pyodide.FS.writeFile(fname, text);
    vias.push(key+":"+via);
  }
  pyodide.FS.writeFile("builder_api.py", dec(B64.api));
  viaNote = vias.join("  ");
  await pyodide.runPythonAsync(
    "import builder_api\n" +
    "api = builder_api.BuilderAPI('tanrielle.yaml', {'class':'spellblade.yaml'," +
    "'ancestries':'ancestries.yaml','spell_schools':'spell_schools.yaml'})\n");
  api = pyodide.globals.get("api");
  render(JSON.parse(api.state()));
  $('app').style.display = "grid";
  $('status').className = "ready";
  $('status').textContent = "Ready - engine running in the browser. Edit the highlighted decision below.";
  $('export').disabled = false;
  $('export').onclick = doExport;
}

function render(s){
  document.title = "DC20 Builder - " + s.character;
  // rail
  let rail="";
  for(let l=1; l<=s.level; l++) rail += `<li class="${l===s.level?'cur':''}">L${l}${l===s.level?' &larr; editing':''}</li>`;
  for(const p of s.planned) rail += `<li class="next">+ L${p} <span style="font-size:.68rem">planned</span></li>`;
  $('rail').innerHTML = rail;
  // decisions
  let d="";
  for(const t of s.timeline){
    const cls = "dec" + (t.editable?" edit":"") + (t.inferred?" inferred":"");
    let body;
    if(t.editable){
      const opts = s.edit.options.map(o=>
        `<option value="${esc(o.name)}" ${o.name===s.edit.current?'selected':''}>${esc(o.name)} (cost ${o.cost})</option>`).join("");
      body = `<span class="pick"><select class="select" id="anc">${opts}</select>
        <span style="font-size:.75rem;color:var(--muted)"> from ${esc(s.edit.source)} traits</span></span>`;
    } else {
      const cost = (t.cost!==null && t.cost!==undefined) ? ` <span style="font-size:.72rem;color:var(--warn)">(cost ${t.cost})</span>`:"";
      body = `<span class="pick">${esc(t.pick)}${cost}${t.inferred?' <span style="font-size:.7rem">[inferred]</span>':''}</span>`;
    }
    d += `<div class="${cls}"><span class="lv">L${t.level}</span><span class="slot">${esc(t.slot)}</span>${body}</div>`;
  }
  $('decisions').innerHTML = d;
  $('srcinfo').textContent = "sources: " + viaNote;
  const sel = $('anc'); if(sel) sel.onchange = () => { render(JSON.parse(api.set_ancestry(sel.value))); };
  // stats
  $('stats').innerHTML = s.stats.map(r=>
    `<tr><td>${esc(r[0])}</td><td>${esc(r[1])}</td><td>${esc(r[2])}</td><td class="mk-${r[3]}">${esc(r[3])}</td></tr>`).join("");
  // budgets
  $('budgets').innerHTML = s.budgets.map(b=>`<div class="budget">&bull; ${esc(b)}</div>`).join("");
  // problems
  if(s.problems.length){
    $('problems').innerHTML = `<div class="prob"><b>${s.problems.length} problem(s) - engine rejected this build:</b>
      <ul>${s.problems.map(p=>`<li>${esc(p)}</li>`).join("")}</ul></div>`;
  } else {
    $('problems').innerHTML = `<div class="prob clean">&check; All checks passed - budgets balanced, no illegal picks.</div>`;
  }
}

function doExport(){
  const y = api.export_yaml();
  $('yamlout').style.display = "block";
  $('yamlout').textContent = y;
  const blob = new Blob([y], {type:"text/yaml"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = "tanrielle.yaml"; a.click();
  URL.revokeObjectURL(a.href);
}

boot().catch(e => { $('status').className="err";
  $('status').textContent = "ERROR: " + (e && e.stack ? e.stack : e); });
</script>
</div></body></html>
"""


def b64_file(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def b64_str(s):
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def main():
    ap = argparse.ArgumentParser(description="Generate builds/builder.html (Tanrielle skeleton).")
    for k, v in DEFAULTS.items():
        ap.add_argument("--" + k, default=v)
    args = ap.parse_args()
    subs = {
        "__ENGINE_B64__": b64_file(args.engine),
        "__LEDGER_B64__": b64_file(args.ledger),
        "__CLASS_B64__":  b64_file(args.cls),
        "__ANC_B64__":    b64_file(args.anc),
        "__SCH_B64__":    b64_file(args.sch),
        "__API_B64__":    b64_str(API_PY),
    }
    html = TEMPLATE
    for k, v in subs.items():
        html = html.replace(k, v)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)
    print("wrote %s (%d bytes)" % (args.out, len(html)))


if __name__ == "__main__":
    main()
