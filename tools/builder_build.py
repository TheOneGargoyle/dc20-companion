#!/usr/bin/env python3
"""Generate builds/builder.html - the rung-3 character builder, ALL SIX characters
plus new-from-scratch mode.

Build-order step 5 (RUNG3_PLAN section 7) on top of the step-4 generalisation. The page:

- loads any of the six ledgers by handle (?char=tanrielle|... plus an on-page switcher),
  renders the full decision timeline, and edits decisions through the five reusable widgets
  (point-buy, option-picker, ancestry-spend, skill/trade allocator, review);
- ADD-A-LEVEL (the level-up-night flow): bumps current_level, generates the new level's
  decision slots from the class spine (talent/path/subclass/ancestry-points/attribute/
  spell/maneuver per level), or PROMOTES an existing plan level (e.g. Tanrielle's locked L5);
  the sheet-total 'expected' block is demoted to 'expected_at_L<n>' history because the new
  level's numbers now come FROM the builder;
- NEW-FROM-SCRATCH (?new=<class> or the switcher): a blank L1 ledger for any of the five
  walked classes, chargen driven entirely by the widgets (point-buy, ancestry pick + spend,
  spell schools, class L1 choices, background skill/trade/language points), exporting a
  valid new YAML;
- RESPEC POLISH (section 8): a loud you-are-editing-canon banner once a canonical ledger is
  dirty, respec export to <handle>.respec.yaml vs a confirm-gated canon export to
  <handle>.yaml, in-progress persistence via localStorage, and a load-your-own-YAML input
  (the section 5 self-serve round trip; the engine re-validates anything loaded);
- COMMENT-PRESERVING EXPORT: export_yaml() re-anchors the source ledger's own YAML
  comments (header provenance, EOL notes, aligned continuation blocks, section
  markers) onto the re-serialised file using composer line-paths (format-neutral,
  PyYAML only - no new deps); the expected <-> expected_at_L<n> rename is followed,
  and any comment whose anchor was edited away is collected, clearly marked, at the
  bottom of the file instead of being silently dropped.

Every edit re-runs the REAL tools/build_engine.py via Pyodide; the catalog files supply
option lists and the catalog-level legality pass; a builder-level pass reports undecided
slots. Bakes engine + full catalog + ALL SIX ledgers + a scripted spells-metadata extract
+ the glue module into ONE self-contained page (base64), fetch()-first with the bake as
the file:// fallback.

SCRIPTED - regenerate whenever the engine, catalog, or any ledger changes, so the page can
never drift from them (same discipline as tools/catalog_build.py):

    python3 tools/builder_build.py

Headless regression harness: python3 tools/builder_verify.py
"""
import argparse
from datetime import datetime, timezone
import base64
import json
import os

import yaml   # CH-11: model_strings() reads the catalogs and ledgers for the linkable index

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)  # tools/.. == campaign/repo root
import sys
sys.path.insert(0, HERE)
from rules_corpus import build_rules_data, corpus_embed, linkable_index  # FR-6 corpus, CH-11 index

CHARS = ["tanrielle", "runt", "minimus", "bonan", "scaletrix", "xanwyn"]
NEWCLASSES = ["spellblade", "warlock", "commander", "barbarian", "druid"]
CATALOG = NEWCLASSES + ["ancestries", "spell_schools", "spell_sources", "maneuvers",
           "talents", "skills_trades", "languages", "metamagic", "stamina_regen",
           "class_spines",  # FR-12.0: baked bare so the engine's load_class_tables() finds it in the Pyodide FS
           "class_features"]  # BUG-19/22: named class features per class per level (+ their effects)
CATPATHS_EXCLUDE = {"class_spines"}   # BUG-31: baked + FS-written, but loaded by the ENGINE, not BuilderAPI

# ---- scripted spells-metadata extract (the tag/school data the pickers need) ----

def extract_spell_meta(spells_md_path):
    meta = {}
    lines = open(spells_md_path, encoding="utf-8").read().splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith("School:") and i >= 2 and lines[i - 1].startswith("Source:"):
            name = lines[i - 2].strip()
            srcs = [s.strip() for s in lines[i - 1].split(":", 1)[1].split(",")]
            school = ln.split(":", 1)[1].strip()
            tags = []
            if i + 1 < len(lines) and lines[i + 1].startswith("Tags:"):
                tags = [t.strip() for t in lines[i + 1].split(":", 1)[1].split(",")]
            meta[name] = {"sources": srcs, "school": school, "tags": tags}
    return meta


# ---- load the Pyodide-side glue (tools/builder_api.py, wraps the real engine + catalog) ----
# The builder's client-side Python lives in tools/builder_api.py and is read at build
# time, not held here as a string literal. It used to be an r"""...""" payload on this
# line, which cost more than it looked: as a string it was invisible to lint and to
# py_compile, so nothing checked it; a stray triple quote anywhere inside it silently
# terminated the literal instead of erroring; and a constant defined at this module's
# level was invisible from inside it, so a reference to one fell through to a silent
# fallback rather than a NameError. That is trap 1 in CLAUDE.md and the root cause of
# BUG-31 and BUG-32. Keep it a real file. Constants the API needs go in that file,
# beside GRANT_CHILD_SLOTS, never here.
#
# builder_api.py opens with a blank line on purpose. The old literal began with the
# newline that followed its opening quotes, so that blank line is what keeps the payload
# byte-identical to the pre-CH-9 string. Do not tidy it away.
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "builder_api.py"),
          encoding="utf-8") as _f:
    API_PY = _f.read()


# ---- the single-file HTML shell: markup, CSS, JS, Pyodide bootstrap ----
TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DC20 Character Builder</title>
<script src="https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js"></script>
<style>
:root{--ink:#1f2430;--muted:#6b7280;--line:#c9ced8;--paper:#f7f8fa;--accent:#3d5a80;
 --ok:#2e7d32;--bad:#b23;--warn:#b7791f}
*{box-sizing:border-box}
body{font-family:system-ui,Segoe UI,Arial,sans-serif;color:var(--ink);margin:0;background:#eef0f4;line-height:1.42}
.wrap{max-width:1120px;margin:0 auto;padding:1.3rem 1.3rem 3rem}
h1{font-size:1.35rem;margin:.1rem 0;display:inline-block}
.apphead{display:flex;align-items:center;flex-wrap:wrap;gap:.4rem .6rem;margin:.1rem 0 .3rem}
.apphead #sheetbtn{margin-left:auto}
.badge{display:inline-block;font-size:.66rem;letter-spacing:.04em;text-transform:uppercase;
 background:var(--accent);color:#fff;border-radius:4px;padding:.12rem .45rem;vertical-align:middle}
.sub{color:var(--muted);font-size:.9rem;margin:.25rem 0 .9rem}
#charsel{border:1px solid var(--accent);border-radius:6px;padding:.3rem .5rem;background:#fff;
 font-size:.9rem;margin-left:.8rem;vertical-align:middle}
.loadlbl{font-size:.78rem;color:var(--muted);margin-left:.8rem}
#status{font-size:.85rem;font-weight:600;background:#e9edf5;border:1px solid var(--line);
 border-radius:6px;padding:.5rem .75rem;margin-bottom:1rem}
#status.err{background:#fdecec;border-color:#f3b6b6;color:var(--bad)}
#status.ready{background:#e9f6ea;border-color:#a9d6ab;color:var(--ok)}
#resume{display:none;font-size:.85rem;background:#fff8e6;border:1px solid #e4c86a;border-radius:6px;
 padding:.5rem .75rem;margin-bottom:1rem}
#canonbar{display:none;font-size:.9rem;font-weight:700;background:#fdecec;border:2px solid var(--bad);
 color:var(--bad);border-radius:8px;padding:.6rem .8rem;margin-bottom:1rem}
.builder{display:grid;grid-template-columns:170px 1fr;gap:1rem}
.card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:1rem;margin-bottom:1rem}
h3.sec{font-size:.72rem;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin:.1rem 0 .55rem}
.rail ol{list-style:none;margin:0;padding:0}
.rail li{border:1px solid var(--line);border-radius:6px;padding:.4rem .5rem;margin-bottom:.35rem;font-size:.83rem;background:var(--paper)}
.rail li.cur{border-color:var(--accent);background:#eaf1f8;font-weight:600}
.rail li.next{border-style:dashed;color:var(--accent)}
.dec{border:1px solid var(--line);border-radius:7px;padding:.45rem .6rem;margin-bottom:.45rem;font-size:.86rem;display:flex;gap:.5rem;align-items:baseline;flex-wrap:wrap}
.dec .lv{font-size:.7rem;color:#fff;background:var(--muted);border-radius:4px;padding:.05rem .4rem;min-width:26px;text-align:center}
.dec .slot{font-size:.7rem;color:var(--muted);text-transform:uppercase;letter-spacing:.03em;min-width:104px}
.dec .pick{flex:1;min-width:230px}
.dec.inferred .pick{color:var(--muted);font-style:italic}
.dec.edit{border:1.2px solid var(--accent);background:#f4f8fc}
.dec.edit .slot{color:var(--accent)}
.dec.plan{opacity:.62;border-style:dashed}
/* FR-36: colour the left accent by category (FR20_CAT rank). Replaces the old amber
   'Added in builder' border - that cue now rides the amber note text in the row body.
   Placed after .edit/.plan so the coloured left border wins on those rows too. Colour-
   blind-safe set: attributes blue, class coral, ancestry teal, resources amber. Class is a
   warm coral (not a blue-family purple) so it never blurs against the adjacent blue attributes
   accent (Darryl live-verify 2026-07-18). */
.dec.cat0{border-left:4px solid #185FA5}
.dec.cat1{border-left:4px solid #C2410C}
.dec.cat2{border-left:4px solid #1D9E75}
.dec.cat3{border-left:4px solid #BA7517}
/* FR-21: light category sub-headers inside a long level section (no extra collapse layer) */
.deccat{font-size:.66rem;font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin:.55rem .45rem .15rem;padding:.08rem .45rem;border-left:3px solid var(--muted)}
/* FR-6 rule links + rule panel */
.rlink{color:var(--accent);border-bottom:1px dotted var(--accent);cursor:pointer}
.rulei{font-size:.68rem;margin-left:.35rem;white-space:nowrap;opacity:.9}
#ruleScrim{display:none;position:fixed;inset:0;background:rgba(15,20,28,.35);z-index:7000}
#rulePanel{display:none;position:fixed;top:0;right:0;height:100%;width:min(460px,92vw);background:#fff;border-left:1px solid var(--line);box-shadow:-6px 0 24px rgba(0,0,0,.18);z-index:7001;overflow:auto;padding:1rem 1.15rem 2.4rem}
#rulePanel .rpbar{display:flex;align-items:center;gap:.6rem;position:sticky;top:0;background:#fff;padding:.1rem 0 .45rem;border-bottom:1px solid var(--line);margin-bottom:.6rem}
#rulePanel .rpf{font-size:.72rem;color:var(--accent);text-transform:uppercase;letter-spacing:.04em}
#rulePanel .rpclose{margin-left:auto;cursor:pointer;border:1px solid var(--line);border-radius:6px;background:var(--paper);padding:.2rem .55rem;font-size:.85rem}
#rulePanel h2{font-size:1.05rem;margin:.2rem 0 .5rem}
#rulePanel h3{font-size:.92rem;margin:.7rem 0 .3rem}
#rulePanel table{border-collapse:collapse;margin:.4rem 0}#rulePanel td,#rulePanel th{border:1px solid var(--line);padding:.2rem .45rem;font-size:.82rem}
.wlabel{font-size:.64rem;text-transform:uppercase;letter-spacing:.05em;color:#fff;background:var(--accent);border-radius:4px;padding:.08rem .4rem}
.select{border:1px solid var(--accent);border-radius:6px;padding:.28rem .45rem;background:#fff;font-size:.84rem;max-width:420px}
input.select{max-width:180px}
.pb{display:flex;gap:1rem;flex-wrap:wrap;align-items:center}
.pb label{font-size:.8rem;color:var(--muted);text-transform:capitalize}
.pb .spent{font-size:.82rem;font-weight:600}
.pb .spent.bad{color:var(--bad)}
table.derived{border-collapse:collapse;width:100%;font-size:.83rem;margin-top:.2rem}
table.derived th,table.derived td{border:1px solid var(--line);padding:.24rem .5rem;text-align:left}
table.derived th{background:var(--paper);color:var(--muted);font-weight:600;font-size:.72rem;text-transform:uppercase}
.mk-OK{color:var(--ok);font-weight:600}
.mk-MISMATCH{color:var(--bad);font-weight:700}
.budget{font-size:.82rem;margin:.15rem 0;color:#333}
.prob{background:#fdecec;border:1px solid #f3b6b6;color:var(--bad);border-radius:6px;padding:.5rem .7rem;font-size:.83rem;margin-top:.6rem}
.prob.clean{background:#e9f6ea;border-color:#a9d6ab;color:var(--ok)}
.prob.adv{background:#fff8e6;border-color:#e4c86a;color:#8a6d1a}
details.lvlgrp{border:1px solid var(--line);border-radius:8px;margin-bottom:.5rem;background:var(--paper)}
details.lvlgrp>summary{cursor:pointer;font-size:.8rem;font-weight:600;color:var(--accent);padding:.4rem .6rem;user-select:none}
details.lvlgrp[open]>summary{border-bottom:1px solid var(--line)}
details.lvlgrp>.dec{margin:.45rem .45rem}
details.lvlgrp.plan>summary{color:var(--muted);font-style:italic}
details.lvlgrp>summary .lvlprev{font-weight:400;font-style:normal;color:var(--muted);font-size:.72rem}
.prob ul{margin:.3rem 0 0;padding-left:1.1rem}
.alloc{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:.4rem}
.alloc .row,.langs .row{border:1px solid var(--line);border-radius:6px;padding:.3rem .5rem;font-size:.82rem;display:flex;justify-content:space-between;align-items:center;gap:.4rem;background:var(--paper)}
.alloc .row .nm{overflow:hidden;text-overflow:ellipsis}
.capraise{font-size:.66rem;white-space:nowrap}
.capraise input{vertical-align:middle;margin:0 .1rem 0 0}
.langs{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:.4rem;margin-top:.3rem}
.addrow{margin-top:.55rem;display:flex;gap:.4rem;align-items:center;flex-wrap:wrap}
.exportbtn{margin-top:.7rem;background:var(--accent);color:#fff;border:none;border-radius:6px;padding:.5rem .95rem;font-size:.88rem;cursor:pointer}
.exportbtn:disabled{opacity:.5;cursor:default}
.exportbtn.small{margin-top:0;padding:.3rem .6rem;font-size:.8rem}
.exportbtn.canonbtn{background:var(--bad)}
.lvlbtn{width:100%;margin-top:.5rem}
.planbtn{background:transparent;color:var(--muted);border:1px dashed var(--muted)}
.planbtn:hover{color:var(--accent);border-color:var(--accent)}
a.rm{color:var(--bad);text-decoration:none;font-weight:700;font-size:.95rem;padding:0 .2rem}
.foot{font-size:.76rem;color:var(--muted);margin-top:1rem}
.stamp{opacity:.75;font-variant-numeric:tabular-nums}   /* FR-43: did this page actually rebuild? */
.src{font-size:.72rem;color:var(--muted);margin-top:.4rem}
pre.yaml{background:#111;color:#c8e6c9;padding:.7rem;border-radius:6px;font-size:.76rem;white-space:pre-wrap;max-height:260px;overflow:auto;display:none}
@media (max-width:640px){
  .wrap{padding:.8rem .8rem 3rem}
  #charsel{margin-left:0;margin-top:.5rem;width:100%}
  .loadlbl{display:block;margin-left:0;margin-top:.5rem}
  .builder{grid-template-columns:1fr;gap:.7rem}
  .dec{gap:.35rem}
  .dec .slot{min-width:0;flex-basis:100%}
  .dec .pick{min-width:0;flex-basis:100%}
  .select{max-width:100%;width:100%}
  .alloc,.langs{grid-template-columns:1fr}
  .card{padding:.75rem}
}
/* ---- character sheet (feature 3) ---- */
.sheetbtn{border:1px solid var(--accent);background:var(--accent);color:#fff;border-radius:6px;padding:.32rem .7rem;font-size:.85rem;cursor:pointer;margin-left:.6rem;vertical-align:middle}
.sheetbtn:disabled{opacity:.45;cursor:default}
#sheetOverlay{display:none;position:fixed;inset:0;background:rgba(15,20,28,.55);z-index:6000;overflow:auto;padding:18px}
#sheetOverlay .sheetbar{width:794px;max-width:100%;margin:0 auto 10px;display:flex;justify-content:space-between;align-items:center;color:#fff;font-size:.85rem}
#sheetOverlay .sheetbar button{border:1px solid #fff;background:transparent;color:#fff;border-radius:6px;padding:.4rem .8rem;font-size:.85rem;cursor:pointer;margin-left:.5rem}
#sheetOverlay .sheetbar .prbtn{background:#fff;color:#25405f;font-weight:600}
.sh-paper{width:794px;max-width:100%;margin:0 auto;background:#fff;color:#1b1f27;padding:16px 18px;border-radius:4px;font-family:system-ui,Segoe UI,Arial,sans-serif;font-size:12px;line-height:1.3;box-shadow:0 4px 20px rgba(0,0,0,.35)}
.sh-head{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:2px solid var(--accent);padding-bottom:8px;margin-bottom:10px}
.sh-head h2{margin:0;font-size:22px}
.sh-who{margin:2px 0 0;color:#5b6472;font-size:12px}
.sh-chips{display:flex;gap:6px}
.sh-chip{border:1px solid #c7ccd6;border-radius:8px;padding:3px 9px;text-align:center;min-width:48px;background:#f6f7f9}
.sh-chip .k{font-size:8px;letter-spacing:.06em;text-transform:uppercase;color:#5b6472}
.sh-chip .v{font-size:16px;font-weight:700;color:#25405f}
.sh-cols{display:grid;grid-template-columns:196px 214px 1fr;gap:10px}
.sh-sec{border:1px solid #c7ccd6;border-radius:8px;padding:6px 8px;margin-bottom:9px;break-inside:avoid}
.sh-sec>h3{margin:0 0 5px;font-size:8.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);border-bottom:1px solid #e2e5ec;padding-bottom:3px}
.sh-attr{display:flex;align-items:center;justify-content:space-between;padding:4px 2px;border-bottom:1px solid #e2e5ec}
.sh-attr:last-child{border-bottom:none}
.sh-attr .nm{font-weight:700;font-size:12px}
.sh-attr .nm .pr{display:block;font-size:7.5px;font-weight:700;letter-spacing:.05em;color:#fff;background:var(--accent);border-radius:3px;padding:0 4px;width:max-content;margin-top:2px}
.sh-attr .mod{font-size:18px;font-weight:700;min-width:34px;text-align:right}
.sh-big{display:flex;gap:6px;margin-bottom:6px}
.sh-box{flex:1;border:1px solid #c7ccd6;border-radius:7px;text-align:center;padding:5px 2px;background:#f6f7f9}
.sh-box .k{font-size:8px;text-transform:uppercase;letter-spacing:.05em;color:#5b6472}
.sh-box .v{font-size:19px;font-weight:700;color:#25405f}
.sh-box .sub{font-size:8px;color:#5b6472}
.sh-kv{display:flex;justify-content:space-between;padding:2.5px 0;border-bottom:1px solid #e2e5ec;font-size:11.5px}
.sh-kv:last-child{border-bottom:none}
.sh-kv .lbl{color:#5b6472}
.sh-kv .val{font-weight:700}
.sh-gh{font-size:8px;text-transform:uppercase;letter-spacing:.05em;color:#8a6d1a;margin:4px 0 1px}
.sh-row{display:flex;justify-content:space-between;padding:1.5px 0;font-size:11px}
.sh-row .v{font-weight:700}
.sh-feat{margin:0;padding:0;list-style:none;font-size:11px}
.sh-feat li{padding:3px 0;border-bottom:1px solid #e2e5ec}
.sh-feat li:last-child{border-bottom:none}
.sh-feat .cat{font-size:7.5px;text-transform:uppercase;letter-spacing:.04em;color:#5b6472;background:#f1f2f5;border-radius:3px;padding:0 4px;margin-right:4px}
.sh-tag{display:inline-block;font-size:8px;color:#5b6472;background:#f6f7f9;border:1px solid #e2e5ec;border-radius:3px;padding:0 4px;margin:1px 2px 0 0}
.sh-note{font-size:8.5px;color:#5b6472;margin-top:3px}
.sh-foot{display:flex;gap:20px;justify-content:center;flex-wrap:wrap;margin-top:8px;padding-top:6px;border-top:1px solid #e2e5ec;font-size:11.5px}
.sh-foot b{color:#5b6472;font-weight:600}
/* BUG-4: mobile-responsive character sheet - stack the fixed 3-col grid, size the
   paper fluidly, tighten padding, and darken the backdrop so the builder does not
   bleed through. Same max-width:640px pattern the builder UI already uses. */
@media (max-width:640px){
  #sheetOverlay{padding:8px;background:rgba(15,20,28,.82)}
  #sheetOverlay .sheetbar{width:100%;font-size:.8rem;flex-wrap:wrap;gap:.35rem}
  .sh-paper{width:100%;max-width:100%;padding:12px 12px}
  .sh-head{flex-wrap:wrap;gap:6px}
  .sh-chips{flex-wrap:wrap}
  .sh-cols{grid-template-columns:1fr;gap:8px}
  .sh-big{flex-wrap:wrap}
}
@media print{
  body.sheeting .wrap{display:none!important}
  body.sheeting #sheetOverlay{position:static!important;background:none!important;padding:0!important;overflow:visible!important;display:block!important}
  body.sheeting #sheetOverlay .sheetbar{display:none!important}
  body.sheeting .sh-paper{box-shadow:none!important;width:auto!important;max-width:none!important;padding:0!important;border-radius:0!important}
  @page{size:A4;margin:10mm}
}
</style></head>
<body><div class="wrap">
<div class="apphead">
<h1>DC20 Character Builder</h1> <span class="badge" style="text-transform:none">v0.10.5</span>
<select id="charsel"></select>
<label class="loadlbl">or load a YAML: <input type="file" id="loadyaml" accept=".yaml,.yml"></label>
<button id="sheetbtn" class="sheetbtn" type="button">Character sheet</button>
</div>
<div id="status">Booting Pyodide (first load pulls a few MB from the CDN)&hellip;</div>
<div id="resume"></div>
<div id="canonbar"></div>

<div class="builder" id="app" style="display:none">
  <div class="card rail">
    <h3 class="sec">Levels</h3>
    <ol id="rail"></ol>
    <div id="levelctl"></div>
  </div>
  <div>
    <div class="card" id="metacard" style="display:none"></div>
    <div class="card">
      <h3 class="sec">Decisions <span class="wlabel">every level-up choice</span></h3>
      <div id="decisions"></div>
      <div class="addrow"><select class="select" id="tradd-lvl" style="max-width:80px"></select>
        <button class="exportbtn small" id="tradd">+ ancestry trait</button>
        <span class="src" id="ancpts"></span>
        <span class="src" id="resreadout" style="margin-left:.75rem"></span></div>
    </div>
    <div class="card">
      <h3 class="sec">Skills &amp; Trades <span class="wlabel">skill/trade allocator</span></h3>
      <div class="alloc" id="alloc"></div>
      <div class="addrow"><select class="select" id="ska-pick" style="max-width:220px"></select>
        <input class="select" id="ska-name" placeholder="custom name" style="display:none">
        <select class="select" id="ska-kind" style="max-width:100px;display:none"><option value="skills">skill</option><option value="trades">trade</option></select>
        <button class="exportbtn small" id="ska-btn">+ add</button></div>
      <h3 class="sec" style="margin-top:.8rem">Languages</h3>
      <div class="langs" id="langs"></div>
      <div class="addrow"><select class="select" id="lang-pick" style="max-width:200px"></select>
        <input class="select" id="lang-name" placeholder="custom name" style="display:none">
        <select class="select" id="lang-flu" style="max-width:110px"><option>Limited</option><option selected>Fluent</option></select>
        <button class="exportbtn small" id="lang-btn">+ add</button></div>
    </div>
    <div class="card">
      <h3 class="sec">Review <span class="wlabel">live from replay() + catalog</span></h3>
      <table class="derived"><thead id="statshead"><tr><th>Stat</th><th>Derived</th><th>Sheet</th><th>Check</th></tr></thead>
        <tbody id="stats"></tbody></table>
      <div class="src" id="sheetnote" style="display:none">No sheet to compare against (new character, or just
      levelled) &mdash; the builder is the source of truth now; this export becomes the sheet.</div>
      <div id="budgets" style="margin-top:.55rem"></div>
      <div id="problems"></div>
      <div id="exports"></div>
      <details id="yamlwrap" style="display:none;margin-top:.5rem"><summary class="src" style="cursor:pointer">view / copy the exported YAML</summary>
      <div style="margin:.35rem 0"><button class="exportbtn" id="yamlcopy" type="button">Copy to clipboard</button></div>
      <pre class="yaml" id="yamlout" style="display:block"></pre></details>
    </div>
  </div>
</div>

<p class="foot">Unofficial fan tooling for our home DC20 (v0.10.5) campaign. DC20 is by The Dungeon Coach,
released under the ORC License.<br><span class="stamp">Build: __BUILD_STAMP__</span></p>
<div id="ruleScrim"></div>
<aside id="rulePanel" aria-label="DC20 rule"><div class="rpbar"><span class="rpf" id="ruleF"></span><button class="rpclose" id="ruleClose" type="button">close &times;</button></div><div id="ruleBody"></div></aside>

<script>
const CHARS = __CHARS_JSON__;
const NEWC = __NEWC_JSON__;
const B64 = __B64_JSON__;
const REL = __REL_JSON__;
const dec64 = b => new TextDecoder().decode(Uint8Array.from(atob(b), c=>c.charCodeAt(0)));
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
/* ============ FR-6: rule text on a chosen option (shared corpus tools/rules_corpus.py + Companion linkify) ============ */
/* CH-11: the 2.1MB corpus is no longer baked here. Initial render only needs to know WHICH terms
   have a rule (it gates the per-option `rule` chip), so the page bakes the ~40KB answer set and
   fetches the corpus itself the first time a rule is actually opened. RULES_IDX is built by
   tools/rules_corpus.linkable_index and its parity with these functions is asserted by
   builder_verify's (17) section, which replays both implementations over every term. */
const RULES_IDX = __RULES_IDX__;
const RULES_URL = 'rules.json';
const _LD = new Set(RULES_IDX.d), _LM = new Set(RULES_IDX.m);
var RULES_DATA = null, CONDSECTIONS = [], _corpusPromise = null;
function ensureCorpus(){
  if (RULES_DATA) return Promise.resolve(RULES_DATA);
  if (_corpusPromise) return _corpusPromise;
  _corpusPromise = fetch(RULES_URL).then(function(r){
    if(!r.ok) throw new Error('rules.json '+r.status);
    return r.json();
  }).then(function(d){
    RULES_DATA = d;
    CONDSECTIONS = (function(){var a=[];for(var i=0;i<d.length;i++)if((d[i].t||'').toLowerCase()==='conditions')a.push(i);return a;})();
    return d;
  }).catch(function(e){ _corpusPromise = null; throw e; });
  return _corpusPromise;
}
function _clean(t){return String(t).replace(/\s*\(.*$/,'').replace(/[:;].*$/,'').replace(/\s+/g,' ').trim();}
function _corpusHas(k){return _LM.has(k);}
function _hasCost(t){return /\([^)]*\b(?:MP|AP|SP)\b/i.test(t);}
function _linkable(name){if(!name||name.length<4)return false;var c0=name.charAt(0);if(c0===c0.toLowerCase())return false;var k=name.toLowerCase();if(CONDS_SET.has(k))return true;return (k.indexOf(' ')>=0)?_corpusHas(k):_LD.has(k);}
function _mk(disp,name){return '<span class="rlink" data-q="'+_clean(name).replace(/&/g,'&amp;').replace(/"/g,'&quot;')+'">'+disp+'<\/span>';}
function linkifyTerms(html){return String(html)
  .replace(/<b>([^<]{3,40})<\/b>/g,function(m,inner){var nm=_clean(inner);if(_hasCost(inner)&&nm.indexOf(' ')<0)return m;return _linkable(nm)?'<b>'+_mk(inner,nm)+'<\/b>':m;})
  .replace(/<h3>([^<]{3,48}?)(\s*)(<span|<\/h3>)/g,function(m,name,ws,tail){return _linkable(_clean(name))?'<h3>'+_mk(name.trim(),name)+ws+tail:m;});}
const CONDS=['Exposed','Hindered','Impaired','Dazed','Taunted','Prone','Bleeding','Poisoned','Charmed','Frightened','Grappled','Stunned'];
const CONDS_SET=new Set(CONDS.map(function(c){return c.toLowerCase();}));
const _STOP=new Set(['same','each','both','more','move','hit','turn','target','attack','damage','with','when','your','this','that','from','into','also','next','once','they','their','then','than','only','used','gain','give','make','take','have']);
/* CH-11: DEFINED and CONDSECTIONS used to be derived here by scanning the baked corpus. DEFINED is
   now the baked `_LD` above (same set, computed at build time by rules_corpus.defined_words), and
   CONDSECTIONS is filled by ensureCorpus() because it is only ever read after a rule is opened.
   _STOP stays because the parity check replays it. */
function _esc(k){return k.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');}
function _wc(x,k){return (x.match(new RegExp('\\b'+_esc(k)+'\\b','g'))||[]).length;}
function _boldHasWord(html,k){return new RegExp('<(strong|b|h[1-6])[^>]*>[^<]*\\b'+_esc(k)+'\\b','i').test(html);}
function _headingHas(html,k){var re=/<(?:strong|b|h[1-6])[^>]*>([^<]{1,40})<\/(?:strong|b|h[1-6])>/ig,m;while(m=re.exec(html)){var t=m[1].toLowerCase().replace(/\s+x$/,'').replace(/[:.,;]+$/,'').trim();if(t===k)return true;}return false;}
function _hHas(html,k){var re=/<h[1-6][^>]*>([^<]{1,40})<\/h[1-6]>/ig,m;while(m=re.exec(html)){var t=m[1].toLowerCase().replace(/\s+x$/,'').replace(/[:.,;]+$/,'').trim();if(t===k)return true;}return false;}
function _home(key){var best=-1,bs=0;for(var i=0;i<RULES_DATA.length;i++){var c=_wc(RULES_DATA[i].x,key);if(!c)continue;var s=c+(_hHas(RULES_DATA[i].h,key)?100000:0)+(_headingHas(RULES_DATA[i].h,key)?10000:0)+(_boldHasWord(RULES_DATA[i].h,key)?1000:0)-(/changelog|errata|extraction/i.test((RULES_DATA[i].t||'')+(RULES_DATA[i].f||''))?800:0);if(s>bs){bs=s;best=i;}}return best;}
function _condTarget(key){for(var j=0;j<CONDSECTIONS.length;j++){var i=CONDSECTIONS[j];if(_headingHas(RULES_DATA[i].h,key))return i;}return -1;}
/* FR-6 additions: trailing rule affordance for a chosen option + a lightweight rule panel */
function ruleTag(name){var nm=_clean(name);if(!_linkable(nm))return "";return ' <span class="rlink rulei" data-q="'+nm.replace(/&/g,'&amp;').replace(/"/g,'&quot;')+'" title="Show the DC20 rule for &quot;'+esc(nm)+'&quot;">rule</span>';}
function _resolveRule(q){q=_clean(q);var key=q.toLowerCase(),b=-1;if(CONDS_SET.has(key)){b=_condTarget(key);if(b<0)b=_home(key);}else{b=_home(key);}return b;}
/* CH-11: the corpus arrives over the network now, so this is async. It FAILS LOUDLY on purpose:
   a missing rules.json is the one way this split can break in production while every local harness
   stays green (deploy.yml rebuilds the page fresh), so the panel says so rather than doing nothing. */
function openRulePanel(q){
  var nm=_clean(q);
  ensureCorpus().then(function(){
    var b=_resolveRule(nm); if(b<0)return;
    var sec=RULES_DATA[b];
    $('ruleF').textContent=sec.f||'';
    $('ruleBody').innerHTML='<h2>'+esc(sec.t)+'</h2>'+linkifyTerms(sec.h);
    $('rulePanel').style.display='block';$('ruleScrim').style.display='block';$('rulePanel').scrollTop=0;
  }).catch(function(e){
    $('ruleF').textContent='';
    $('ruleBody').innerHTML='<h2>Rules text unavailable</h2><p>Could not load <code>'+RULES_URL+'</code> ('+esc(String((e&&e.message)||e))+'). Everything else on this page still works.</p>';
    $('rulePanel').style.display='block';$('ruleScrim').style.display='block';$('rulePanel').scrollTop=0;
  });
}
/* Warm the corpus once the page is idle, so the first rule click is instant in practice. The page
   is useful long before this lands, which is the whole point of the split. */
(function(){var go=function(){ensureCorpus().catch(function(){});};
 if(window.requestIdleCallback)requestIdleCallback(go,{timeout:4000});else setTimeout(go,2000);})();
function closeRulePanel(){$('rulePanel').style.display='none';$('ruleScrim').style.display='none';}
document.addEventListener('click',function(e){var t=e.target;if(t&&t.classList&&t.classList.contains('rlink')){e.preventDefault();openRulePanel(t.getAttribute('data-q'));}});
document.addEventListener('keydown',function(e){if(e.key==='Escape')closeRulePanel();});
(function(){var c=$('ruleClose');if(c)c.onclick=closeRulePanel;var s=$('ruleScrim');if(s)s.onclick=closeRulePanel;})();

/* ---- character sheet (feature 3): print/PDF view rendered from api.sheet() ---- */
function shEsc(x){return esc(x==null?'':x);}
function shBuild(d){
  const A=['Might','Agility','Charisma','Intelligence'];
  const attrRows=A.map(a=>{
    const v=(d.attrs[a]||0);
    const pr=(v===d.prime)?'<span class="pr">Prime</span>':'';
    const sign=v>=0?'+':'';
    return `<div class="sh-attr"><div class="nm">${a}${pr}</div><div class="mod">${sign}${v}</div></div>`;
  }).join('');
  const c=d.core||{}, der=d.derived||{};
  const saves=der.saves||{};
  const saveHtml=A.map(a=>{const v=saves[a]; const sign=(v>=0?'+':'');
    return `<div class="sh-kv"><span class="lbl">${a}</span><span class="val">${v===undefined?'\u2014':sign+v}</span></div>`;}).join('');
  const dr=der.dr||{}; const drKeys=Object.keys(dr);
  const drStr=drKeys.length?drKeys.map(k=>`${k} ${dr[k].join(', ')}`).join(' &middot; '):'\u2014';
  // FR-23: Stamina Regen trigger(s), engine-derived (empty => no regen).
  const sr=d.stamina_regen||[];
  const srStr=sr.length
    ? sr.map(t=>`<b>${t.label}:</b> ${t.text}`).join('<br>')+(sr.length>1?'<br><span class="sh-note">Only 1 Stamina Regen benefit per Round.</span>':'')
    : 'None (no Stamina Regen)';
  // BUG-34: Combat Training (base + option-granted, e.g. the Warrior Discipline's Heavy Armor).
  // The row is HIDDEN when the list is empty rather than printed as "None recorded", because a
  // scratch build has no BASE training yet (a class's own training is not catalog data: FR-48), so
  // an empty line would read as "this character is trained in nothing", which is wrong rather than
  // merely incomplete. Canon ledgers hand-author the base list, so they show the full picture.
  // When FR-48 lands the base is always present and this guard stops mattering.
  const ct=d.combat_training||[];
  const ctRow=ct.length
    ? `<div class="sh-kv" style="display:block"><span class="lbl">Combat Training</span><div style="font-weight:400;font-size:11px;margin-top:2px">${ct.map(shEsc).join(' &middot; ')}</div></div>`
    : '';
  const order=['Prime','Might','Agility','Charisma','Intelligence'];
  const byAttr={};
  d.skills.forEach(s=>{(byAttr[s.attr]=byAttr[s.attr]||[]).push(s);});
  let skillHtml='';
  order.forEach(a=>{ if(!byAttr[a])return;
    skillHtml+=`<div class="sh-gh">${a}</div>`+byAttr[a].map(s=>{
      const sign=s.bonus>=0?'+':'';
      return `<div class="sh-row"><span>${shEsc(s.name)} <span class="sh-tag">${shEsc(s.tier||'')}</span></span><span class="v">${sign}${s.bonus}</span></div>`;
    }).join('');
  });
  const tradeHtml=(d.trades||[]).length?d.trades.map(t=>{
    const mb=t.mb||0; const sign=mb>=0?'+':'';
    return `<div class="sh-row"><span>${shEsc(t.name)} <span class="sh-tag">${shEsc(t.tier||'')}</span></span><span class="v">${sign}${mb}</span></div>`;
  }).join('')+'<div class="sh-note">Bonus = Mastery only; add the relevant attribute in play (it varies by use).</div>':'<div class="sh-note">None</div>';
  const langHtml=(d.languages||[]).map(l=>`<div class="sh-row"><span>${shEsc(l.name)}</span><span class="v">${shEsc(l.fluency)}</span></div>`).join('')||'<div class="sh-note">None</div>';
  // BUG-32: groups + labels + order come from the API (SHEET_GROUPS), never from a list held here.
  let featHtml='';
  (d.ability_groups||[]).forEach(g=>{
    if(!g.items||!g.items.length)return;
    featHtml+=`<li><span class="cat">${shEsc(g.label)}</span>${g.items.map(x=>shEsc(x.pick)).join(' &middot; ')}</li>`;
  });
  if(!featHtml)featHtml='<li class="sh-note">None recorded</li>';
  const spellHtml=(d.spells||[]).length?d.spells.map(s=>{
    const tags=(s.tags||[]).slice(0,4).map(t=>`<span class="sh-tag">${shEsc(t)}</span>`).join('');
    return `<li><b>${shEsc(s.name)}</b>${s.school?` <span class="cat">${shEsc(s.school)}</span>`:''}${tags?' '+tags:''}</li>`;
  }).join(''):'<li class="sh-note">None</li>';
  const eqHtml=(d.equipment||[]).length?d.equipment.map(it=>{
    const bonus=[]; if(it.pd)bonus.push(`+${it.pd} PD`); if(it.ad)bonus.push(`+${it.ad} AD`);
    const b=bonus.length?` <span class="sh-tag">${bonus.join(' ')}</span>`:'';
    const mods=it.mods?`<div class="sh-note">${shEsc(it.mods)}</div>`:'';
    return `<li><b>${shEsc(it.name)}</b>${b}${mods}</li>`;
  }).join(''):'<li class="sh-note">None recorded</li>';
  const pdN=(+c['PD'])||0, adN=(+c['AD'])||0;
  const sub=[d.ancestry, `${d.klass}${d.subclass?' ('+d.subclass+')':''}`, d.background?('Background: '+d.background):'', d.player?('Player: '+d.player):''].filter(Boolean).map(shEsc).join(' &middot; ');
  return `<div class="sh-paper">
    <div class="sh-head">
      <div><h2>${shEsc(d.character||'Unnamed')}</h2><p class="sh-who">${sub}</p></div>
      <div class="sh-chips">
        <div class="sh-chip"><div class="k">Level</div><div class="v">${d.level}</div></div>
        <div class="sh-chip"><div class="k">Combat Mastery</div><div class="v">${d.cm}</div></div>
        <div class="sh-chip"><div class="k">Prime</div><div class="v">+${d.prime}</div></div>
      </div>
    </div>
    <div class="sh-cols">
      <div>
        <div class="sh-sec"><h3>Attributes</h3>${attrRows}</div>
        <div class="sh-sec"><h3>Saves</h3>${saveHtml}</div>
        <div class="sh-sec"><h3>Defenses</h3>
          <div class="sh-big">
            <div class="sh-box"><div class="k">Precision</div><div class="v">${c['PD']}</div><div class="sub">Hvy ${pdN+5} &middot; Brutal ${pdN+10}</div></div>
            <div class="sh-box"><div class="k">Area</div><div class="v">${c['AD']}</div><div class="sub">Hvy ${adN+5} &middot; Brutal ${adN+10}</div></div>
          </div>
          <div class="sh-kv"><span class="lbl">Damage reduction</span><span class="val">${drStr}</span></div>
        </div>
        <div class="sh-sec"><h3>Vitals</h3>
          <div class="sh-big">
            <div class="sh-box"><div class="k">Health</div><div class="v">${c['HP']}</div><div class="sub">Blood ${der.bloodied} &middot; W-Blood ${der.well_bloodied}</div></div>
            <div class="sh-box"><div class="k">Death</div><div class="v">-${der.death_threshold}</div><div class="sub">Prime + CM</div></div>
          </div>
          <div class="sh-kv"><span class="lbl">Stamina (SP)</span><span class="val">${c['SP']}</span></div>
          <div class="sh-kv"><span class="lbl">Mana (MP)</span><span class="val">${c['MP']}</span></div>
          <div class="sh-kv"><span class="lbl">Grit</span><span class="val">${c['Grit']}</span></div>
          <div class="sh-kv"><span class="lbl">Rest points</span><span class="val">${der.rest_points}</span></div>
          <div class="sh-kv" style="display:block"><span class="lbl">Stamina Regen</span><div style="font-weight:400;font-size:11px;margin-top:2px">${srStr}</div></div>
        </div>
      </div>
      <div>
        <div class="sh-sec"><h3>Combat</h3>
          <div class="sh-big">
            <div class="sh-box"><div class="k">Attack / Spell</div><div class="v">+${c['Attack/Spell Check']}</div></div>
            <div class="sh-box"><div class="k">Save DC</div><div class="v">${c['Save DC']}</div></div>
          </div>
          <div class="sh-kv"><span class="lbl">Initiative</span><span class="val">+${c['Initiative']}</span></div>
          <div class="sh-kv"><span class="lbl">Spells / Maneuvers known</span><span class="val">${c['Spells known']} / ${c['Maneuvers known']}</span></div>
          ${ctRow}
        </div>
        <div class="sh-sec"><h3>Skills</h3>${skillHtml||'<div class="sh-note">None</div>'}</div>
        <div class="sh-sec"><h3>Trades</h3>${tradeHtml}</div>
        <div class="sh-sec"><h3>Languages</h3>${langHtml}</div>
      </div>
      <div>
        <div class="sh-sec"><h3>Features &amp; abilities</h3><ul class="sh-feat">${featHtml}</ul></div>
        <div class="sh-sec"><h3>Spells</h3><ul class="sh-feat">${spellHtml}</ul></div>
        <div class="sh-sec"><h3>Equipment &amp; attunements</h3><ul class="sh-feat">${eqHtml}</ul></div>
      </div>
    </div>
    <div class="sh-foot">
      <span><b>Move Speed</b> ${der.move} Spaces</span>
      <span><b>Jump Distance</b> ${der.jump} Spaces</span>
      <span><b>Mana / Stamina Spend Limit</b> ${der.spend_limit}</span>
    </div>
    <div class="sh-note" style="text-align:center;margin-top:6px">Unofficial fan-made sheet &middot; DC20 &copy; The Dungeon Coach, ORC License</div>
  </div>`;
}
function renderSheet(){
  if(!api){ $('status').className='err'; $('status').textContent='Pick or load a character first, then open the character sheet.'; return; }
  let d;
  try{ d = JSON.parse(api.sheet()); }
  catch(e){ $('status').className='err'; $('status').textContent='Sheet error: '+e; return; }
  let ov=$('sheetOverlay');
  if(!ov){ ov=document.createElement('div'); ov.id='sheetOverlay'; document.body.appendChild(ov); }
  const close=()=>{ ov.style.display='none'; document.body.classList.remove('sheeting'); };
  ov.innerHTML='<div class="sheetbar"><div>One page &mdash; print or Save as PDF</div>'
    +'<div><button type="button" class="prbtn" id="shPrint">Print / Save as PDF</button>'
    +'<button type="button" id="shClose">Close</button></div></div>'+shBuild(d);
  ov.style.display='block'; document.body.classList.add('sheeting');
  $('shPrint').onclick=()=>window.print();
  $('shClose').onclick=close;
  ov.onclick=(e)=>{ if(e.target===ov) close(); };
  document.addEventListener('keydown', function esc1(e){ if(e.key==='Escape'){ close(); document.removeEventListener('keydown', esc1); } });
}
if($('sheetbtn')) $('sheetbtn').onclick=renderSheet;

function modeFromURL(){
  const q = new URLSearchParams(location.search);
  const n = (q.get('new')||'').toLowerCase();
  if(NEWC.includes(n)) return {newClass:n};
  const h = q.get('char');
  if(CHARS.includes(h)) return {char: h};
  return {blank: true};  // no deep link: land on the chooser, load nobody's ledger
}
async function srcText(key){
  if(REL[key]){ try{ const r = await fetch(REL[key]); if(r.ok) return {text:await r.text(), via:"fetch"}; }catch(e){} }
  return {text: dec64(B64[key]), via:"baked"};
}

let api=null, pyodide=null, viaNote="", dirty=false, ST=null, renderedLevel=null;
let mode = modeFromURL();
let handle = mode.newClass ? "new-"+mode.newClass : (mode.char || null);
const storeKey = () => "dc20builder:" + handle;
const isCanon = () => ST && !ST.scratch && CHARS.includes(ST.handle);
const slug = s => ((s.character||"").trim().toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-+|-+$/g,"") || s.handle);

const RECENT_KEY = "dc20builder:recent";
function loadRecents(){                 // FR-14: per-device Recent Files (party handles only)
  try{ const a = JSON.parse(localStorage.getItem(RECENT_KEY)||"[]");
    return Array.isArray(a) ? a.filter(r=>r && CHARS.includes(r.handle)) : []; }
  catch(e){ return []; }
}
function addRecent(h, label){
  if(!h || !CHARS.includes(h)) return;  // only baked party canon handles resolve by ?char=
  let a = loadRecents().filter(r=>r.handle!==h);
  a.unshift({handle:h, label:label||h, ts:Date.now()});
  a = a.slice(0, 8);
  try{ localStorage.setItem(RECENT_KEY, JSON.stringify(a)); }catch(e){}
}
function currentSelValue(){
  if(mode.newClass) return "new:"+mode.newClass;
  if(handle && CHARS.includes(handle)) return handle;
  if(ST && ST.scratch) return "__loaded__";
  return "";
}
function buildCharSel(){                // FR-14 Level A (no baked party list) + FR-1 (sorted)
  const sel = $('charsel');
  let list = loadRecents();
  if(mode.char && !list.some(r=>r.handle===mode.char)) list = [{handle:mode.char, label:mode.char}].concat(list);
  const cur = currentSelValue();
  sel.innerHTML =
    (mode.blank ? '<option value="" selected disabled>&mdash; pick a character &mdash;</option>' : '') +
    (list.length ? '<optgroup label="recent files">' +
       list.map(r=>`<option value="${esc(r.handle)}" ${r.handle===cur?'selected':''}>${esc(r.label||r.handle)}</option>`).join("") +
       '</optgroup>' : '') +
    '<optgroup label="new from scratch">' +
       NEWC.slice().sort().map(c=>`<option value="new:${esc(c)}" ${("new:"+c)===cur?'selected':''}>new ${esc(c)}</option>`).join("") +
    '</optgroup>';
}
async function boot(){
  const sel = $('charsel');
  buildCharSel();
  sel.onchange = () => {
    if(sel.value === "__loaded__") return;   // synthetic entry for a file-loaded character
    // FR-5: switching character reloads the page; guard unsaved in-memory edits first.
    if(dirty && !confirm("You have unsaved changes to " + ((ST&&ST.character)||handle||"this character")
        + ".\n\nSwitching characters reloads the builder and discards them. Export first if you want to keep them.\n\nSwitch anyway?")){
      sel.value = currentSelValue(); return;
    }
    const u = new URL(location); u.searchParams.delete('char'); u.searchParams.delete('new');
    if(sel.value.startsWith('new:')) u.searchParams.set('new', sel.value.slice(4));
    else u.searchParams.set('char', sel.value);
    location.href = u;
  };
  pyodide = await loadPyodide();
  $('status').textContent = "Pyodide up. Installing PyYAML...";
  await pyodide.loadPackage("pyyaml");
  $('status').textContent = "Loading engine, catalog and ledgers...";
  const vias = {fetch:0, baked:0};
  for(const key of Object.keys(B64)){
    const fname = key === "engine" ? "build_engine.py" : key === "api" ? "builder_api.py"
                : key === "meta" ? "spells_meta.json" : key + ".yaml";
    const {text,via} = await srcText(key);
    pyodide.FS.writeFile(fname, text);
    vias[via]++;
  }
  viaNote = `sources: ${vias.fetch} fetched, ${vias.baked} baked`;
  await pyodide.runPythonAsync(
    "import builder_api\n" +
    // BUG-31: this map is GENERATED from builder_build.CATALOG at build time. It used to be a
    // hand-written literal, which silently diverged the day a catalog file was added (class_features
    // was baked into the page and written to the FS, but never passed to BuilderAPI, so every class
    // feature fell back to "not in the catalog" and its effects vanished). Never hand-edit it.
    "CATPATHS = __CATPATHS_PY__\n" +
    "def make_api(handle):\n" +
    "    return builder_api.BuilderAPI(handle, CATPATHS)\n" +
    "def make_api_new(cls):\n" +
    "    return builder_api.BuilderAPI(None, CATPATHS, new_class=cls)\n" +
    "def make_api_text(handle, text):\n" +
    "    return builder_api.BuilderAPI(handle, CATPATHS, ledger_text=text)\n");
  if(mode.blank){
    // blank landing: engine is up, nobody's ledger is loaded - wait for a pick
    $('status').className = "ready";
    $('status').textContent = "Ready - pick a party character above, start one new from scratch, or load an exported YAML.";
    return;
  }
  api = mode.newClass ? pyodide.globals.get("make_api_new")(mode.newClass)
                      : pyodide.globals.get("make_api")(handle);
  const s0 = JSON.parse(api.state());
  render(s0);
  if(mode.char){ addRecent(handle, s0.character); buildCharSel(); }  // FR-14: deeplink auto-adds to Recent Files
  $('app').style.display = "grid";
  $('status').className = "ready";
  $('status').textContent = "Ready - the engine is running in your browser. Edit any highlighted decision, adjust skills, trades and languages, or add a level; every change re-validates live.";
  checkWIP();
}

function checkWIP(){
  let w = null;
  try{ w = JSON.parse(localStorage.getItem(storeKey())||"null"); }catch(e){}
  if(!w || !w.yaml) return;
  $('resume').style.display = "block";
  $('resume').innerHTML = `In-progress work for <b>${esc(handle)}</b> saved ${esc(new Date(w.ts).toLocaleString())} in this browser.
    <a href="#" id="res-yes">Resume it</a> &middot; <a href="#" id="res-no">Discard it</a>`;
  $('res-yes').onclick = ev => { ev.preventDefault();
    api = pyodide.globals.get("make_api_text")(handle, w.yaml);
    dirty = true; $('resume').style.display = "none";
    render(JSON.parse(api.state())); };
  $('res-no').onclick = ev => { ev.preventDefault();
    localStorage.removeItem(storeKey()); $('resume').style.display = "none"; };
}

function saveWIP(){
  try{ localStorage.setItem(storeKey(), JSON.stringify({yaml: api.export_yaml(), ts: Date.now()})); }catch(e){}
}

function optHTML(options, current, curGroup){
  const isCur = o => o.name===current && (!curGroup || o.group===curGroup);
  const groups = {};
  let found = false;
  for(const o of options){ (groups[o.group||''] ||= []).push(o); if(isCur(o)) found=true; }
  if(!found && current!=null){  // fall back to name-only if the group hint missed
    curGroup = undefined;
    for(const o of options) if(o.name===current) found=true;
  }
  let h = (found || current==null || current==="") ? "" : `<option value="${esc(current)}" selected>${current==='(undecided)'?'&mdash; choose &mdash;':esc(current)+' (off-catalog)'}</option>`;
  for(const [g, os] of Object.entries(groups)){
    const inner = os.map(o=>`<option value="${esc(o.name)}" ${isCur(o)?'selected':''}>${esc(o.label||o.name)}</option>`).join("");
    h += g ? `<optgroup label="${esc(g)}">${inner}</optgroup>` : inner;
  }
  return h;
}

function render(s){
  ST = s;
  document.title = "DC20 Builder - " + s.character;
  // canon loudness
  const canon = !s.scratch && CHARS.includes(s.handle);
  if(canon && dirty){
    $('canonbar').style.display = "block";
    $('canonbar').innerHTML = `&#9888; EDITING CANON: these changes touch <b>${esc(s.character)}</b>'s canonical
      ledger in-memory only. Nothing is saved until you export; a <b>respec export</b>
      (<code>${esc(s.handle)}.respec.yaml</code>) can never replace the party version, only the confirm-gated
      canon export can.`;
  } else $('canonbar').style.display = "none";
  // rail
  let rail="";
  for(let l=1; l<=s.level; l++) rail += `<li class="${l===s.level?'cur':''}">L${l}${l===s.level?' &larr; current':''}</li>`;
  for(const p of s.planned) rail += `<li class="next">+ L${p} <span style="font-size:.68rem">planned</span></li>`;
  $('rail').innerHTML = rail;
  let lv = "";
  if(s.next){
    lv += `<button class="exportbtn lvlbtn" id="addlevel">&#8679; ${s.next.has_plan ? 'Promote planned L'+s.next.level : 'Add level '+s.next.level}</button>
      <div class="src">${esc(s.next.summary)}${s.next.features.length? '<br>features: '+esc(s.next.features.join(', ')):''}</div>`;
  }
  if(s.can_plan) lv += `<button class="exportbtn lvlbtn planbtn" id="addplan">&#43; Add planned level L${s.plan_level}</button>`;
  if(s.undo_level) lv += `<div class="src"><a href="#" id="undolevel">undo add L${s.undo_level}</a></div>`;
  $('levelctl').innerHTML = lv;
  if($('addlevel')) $('addlevel').onclick = () => refresh(api.add_level());
  if($('addplan')) $('addplan').onclick = () => refresh(api.add_planned_level());
  if($('undolevel')) $('undolevel').onclick = ev => { ev.preventDefault(); refresh(api.undo_add_level()); };
  // meta card (new-from-scratch)
  if(s.scratch){
    const found = s.anc_lists_all.filter(a => (s.ancestry||"").includes(a));
    const ancSel = (id, cur, blankLbl) => `<select class="select" id="${id}" style="max-width:130px">` +
      `<option value="-" ${cur?'':'selected'}>${blankLbl}</option>` +
      s.anc_lists_all.map(a=>`<option ${a===cur?'selected':''}>${a}</option>`).join("") + `</select>`;
    $('metacard').style.display = "block";
    $('metacard').innerHTML = `<h3 class="sec">Character <span class="wlabel">new from scratch</span></h3>
      <div class="pb">
        <label>name <input class="select" id="m-character" value="${esc(s.character||'')}"></label>
        <label>player <input class="select" id="m-player" style="max-width:110px" value="${esc(s.player||'')}"></label>
        <label>background <input class="select" id="m-background" style="max-width:130px" value="${esc(s.background||'')}"></label>
        <label>ancestry ${ancSel('m-anc1', found[0], '&mdash; choose &mdash;')} + ${ancSel('m-anc2', found[1], '-')}</label>
      </div>`;
    for(const f of ['character','player','background'])
      $('m-'+f).onchange = el => refresh(api.set_meta(f, $('m-'+f).value));
    const anc = () => refresh(api.set_ancestry($('m-anc1').value==='-'?'':$('m-anc1').value, $('m-anc2').value));
    $('m-anc1').onchange = anc; $('m-anc2').onchange = anc;
  } else {                              // FR-4: display-name rename for a canon / loaded character
    $('metacard').style.display = "block";
    $('metacard').innerHTML = `<h3 class="sec">Character <span class="wlabel">display name</span></h3>
      <div class="pb"><label>name <input class="select" id="m-character" value="${esc(s.character||'')}"></label></div>
      <div class="src">Renames the display name only; the file handle and deep link are unchanged, and the export filename follows this name.</div>`;
    $('m-character').onchange = () => refresh(api.set_meta('character', $('m-character').value));
  }
  // decisions - grouped by level into collapsers; current level (and anything
  // undecided) open, history + plan collapsed
  const undecAt = {};
  // count undecided picks that a player still has to make: current-and-below rows, plus
  // FR-3 editable plan rows (a builder-generated plan you can fill in). Locked plan rows
  // (Tanrielle) are fixed, so they never count and never force a group open.
  for(const t of s.decisions) if((!t.plan || t.editable) && String(t.pick)==="(undecided)" && !t.auto) undecAt[t.level]=(undecAt[t.level]||0)+1;
  const rowHTML = t => {
    if(t.widget === "pointbuy"){
      const sel = a => { let o=""; for(let v=-2; v<=t.limit; v++) o += `<option value="${v}" ${t.attrs[a]===v?'selected':''}>${v}</option>`; return o; };
      const bad = t.spent !== t.budget ? " bad" : "";
      return `<div class="dec edit"><span class="lv">L1</span><span class="slot">attributes</span>
        <span class="pick pb">` +
        Object.keys(t.attrs).map(a=>`<label>${a} <select class="select" style="max-width:70px" data-attr="${a}">${sel(a)}</select></label>`).join("") +
        `<span class="spent${bad}">point buy: ${t.spent}/${t.budget}</span></span></div>`;
    }
    // FR-36: the left accent is now the category colour (cat0..cat3 from FR20_CAT). The old
    // amber 'Added in builder' border is dropped entirely - it was dev bookkeeping, not player
    // UI, and the ledger notes it flagged are noise on the pickers (Darryl live-verify 2026-07-18);
    // fixed/inferred rows still surface their note in the else branch, editable pickers do not.
    const cls = "dec" + (t.editable?" edit":"") + (t.inferred?" inferred":"") + (t.plan?" plan":"") + " cat" + (t.cat==null?3:t.cat);
    let body;
    if(t.editable && t.options){
      // FR-17: a planned skill/trade slot carries a cap+ toggle - spend 1 extra point to raise this
      // Mastery Limit by 1, letting the pick sit one tier above the level cap (mirrors the allocator).
      const capctl = t.plan_pointbuy
        ? ` <label class="capraise" title="spend 1 extra ${t.plan_pointbuy==='skills'?'Skill':'Trade'} Point to raise this Mastery Limit by 1 (this pick may go one tier above the level cap)"><input type="checkbox" data-plr="${esc(t.id)}" ${t.capraise?'checked':''}> cap+</label>`
        : "";
      body = `<span class="pick"><select class="select" data-dec="${esc(t.id)}">${optHTML(t.options, t.current, t.current_group)}</select>` + capctl +
        ((t.cost!==null && t.cost!==undefined) ? ` <span style="font-size:.72rem;color:var(--warn)">(cost ${t.cost})</span>`:"") +
        (t.was_note ? ` <span style="font-size:.7rem;color:var(--warn)">${esc(t.was_note)} <a href="#" class="rm" data-dismiss="${esc(t.id)}" title="dismiss this note">&times;</a></span>`:"") +
        (t.removable ? ` <a href="#" class="rm" data-rm="${esc(t.id)}" title="remove this slot">&times;</a>`:"") + ruleTag(t.current) + `</span>`;
    } else {
      const cost = (t.cost!==null && t.cost!==undefined) ? ` <span style="font-size:.72rem;color:var(--warn)">(cost ${t.cost})</span>`:"";
      const allocHint = (!t.plan && (t.slot==='skill'||t.slot==='trade'))
        ? ' <span style="font-size:.7rem;color:var(--accent)">&rarr; apply mastery changes in the allocator below</span>' : '';
      const replHTML = (t.replaceable && t.options)
        ? ` <select class="select repl" data-dec="${esc(t.id)}" title="replace this with a single valid ${esc(t.slot)}"><option value="" selected>&mdash; replace &mdash;</option>${optHTML(t.options, null, null)}</select>`
        : '';
      body = `<span class="pick">${esc(t.pick)}${ruleTag(t.pick)}${cost}${t.inferred?' <span style="font-size:.7rem">[inferred]</span>':''}${t.plan?' <span style="font-size:.7rem">[plan]</span>':''}${t.note?` <span style="font-size:.7rem;color:var(--warn)">${esc(t.note)}</span>`:''}${allocHint}${replHTML}</span>`;
    }
    const slotLabel = (t.slot==='spell_tagged'||t.slot==='spell_sourced'||t.slot==='spell_any') ? 'spell'  // BUG-12(a): don't leak the internal slot kind
                    : (t.slot==='source_choice') ? 'sorcerer source'                 // FR-13a slice 2: Sorcerous Origin node
                    : (t.slot==='ancestry_origin') ? (t.slotlabel||'origin') : t.slot;  // BUG-24: per-ancestry Origin picker
    return `<div class="${cls}"><span class="lv">L${t.level}</span><span class="slot">${esc(slotLabel)}</span>${body}</div>`;
  };
  let d = `<div style="font-size:.85rem;margin-bottom:.5rem"><b>${esc(s.character)}</b> - ${esc(s.klass)} (${esc(s.subclass||'?')}) | ${esc(s.ancestry||'')}</div>`;
  // keep whatever the user opened/closed: snapshot the open states before the
  // re-render wipes them; computed defaults only apply to groups not seen before
  const prevOpen = {};
  document.querySelectorAll('#decisions details.lvlgrp[data-lvl]').forEach(el => { prevOpen[el.dataset.lvl] = el.open; });
  // level-up / undo: the NEW current level always re-opens (a promoted plan group
  // was collapsed a moment ago; keeping it shut would hide what was just promoted)
  if(renderedLevel !== s.level) delete prevOpen[String(s.level)];
  renderedLevel = s.level;
  const byLevel = {};
  for(const t of s.decisions) (byLevel[t.level] ||= []).push(t);
  for(const lvl of Object.keys(byLevel).map(Number).sort((a,b)=>a-b)){
    // FR-21: for a long level (>=5 rows, i.e. really just chargen L1) group the rows under
    // light category sub-headers so the list is scannable, without a second collapse layer.
    // Rows are already sorted by category (FR-20), so each category is a contiguous run;
    // short level-up levels (<5 rows) render flat as before.
    const dl = byLevel[lvl];
    let rows;
    if(dl.length >= 5){
      const CATLBL = {0:'Attributes',1:'Class',2:'Ancestry',3:'Resources'};
      const CATCOL = {0:'#185FA5',1:'#C2410C',2:'#1D9E75',3:'#BA7517'};
      let out = "", lastCat = null;
      for(const t of dl){
        const c = (t.cat==null?3:t.cat);
        if(c!==lastCat){ out += `<div class="deccat" style="border-left-color:${CATCOL[c]}">${CATLBL[c]}</div>`; lastCat = c; }
        out += rowHTML(t);
      }
      rows = out;
    } else {
      rows = dl.map(rowHTML).join("");
    }
    const plan = byLevel[lvl].every(t=>t.plan);
    // FR-3: an editable plan group (a builder-generated plan with fillable rows) opens by
    // default when it has undecided picks, so a freshly added plan is not hidden collapsed;
    // a locked plan (no editable rows) stays collapsed as before.
    const editablePlan = plan && byLevel[lvl].some(t=>t.editable);
    const defOpen = ((!plan || editablePlan) && (lvl===s.level || undecAt[lvl])) || (lvl===1 && s.level===1);
    const open = (String(lvl) in prevOpen) ? prevOpen[String(lvl)] : defOpen;
    const label = lvl===1 ? "Level 1 &mdash; character creation" : `Level ${lvl}` + (plan?" (plan)":"") +
      (lvl===s.level?" &larr; current":"") + (undecAt[lvl]?` &mdash; ${undecAt[lvl]} undecided`:"");
    // FR-10: echo each level's grants (numeric deltas + named features), sourced from
    // the class spine via state().level_grants, into that level's collapsible section
    // header - so every level of every character shows what it grants without being
    // expanded. Supersedes the old cur+1-only next-level gate (the sidebar Add-level
    // button still uses s.next). L1's chargen starting kit is included.
    let lvlPrev = "";
    const lg = s.level_grants && s.level_grants[lvl];
    if(lg){
      const parts = [];
      if(lg.summary) parts.push(esc(lg.summary));
      if(lg.features && lg.features.length) parts.push(esc(lg.features.join(', ')));
      if(parts.length) lvlPrev = ` <span class="lvlprev">grants: ${parts.join(' &middot; ')}</span>`;
    }
    d += `<details class="lvlgrp${plan?' plan':''}" data-lvl="${lvl}" ${open?'open':''}><summary>${label}${lvlPrev}</summary>${rows}</details>`;
  }
  $('decisions').innerHTML = d;
  document.querySelectorAll('[data-dec]').forEach(el => el.onchange = () => { if(el.value!=="") refresh(api.set_decision(el.dataset.dec, el.value)); });
  document.querySelectorAll('[data-plr]').forEach(el => el.onchange = () => refresh(api.set_plan_capraise(el.dataset.plr, el.checked)));   // FR-17 plan cap+ toggle
  document.querySelectorAll('[data-attr]').forEach(el => el.onchange = () => refresh(api.set_attr(el.dataset.attr, el.value)));
  document.querySelectorAll('[data-rm]').forEach(el => el.onclick = ev => { ev.preventDefault(); refresh(api.remove_decision(el.dataset.rm)); });
  document.querySelectorAll('[data-dismiss]').forEach(el => el.onclick = ev => { ev.preventDefault(); refresh(api.dismiss_note(el.dataset.dismiss)); });
  // + ancestry trait control
  $('tradd-lvl').innerHTML = s.anc_levels.map(l=>`<option value="${l}">L${l}</option>`).join("");
  $('tradd').onclick = () => refresh(api.add_trait($('tradd-lvl').value));
  // FR-9: live ancestry-point readout, mirroring the skills allocator's budget line
  if($('ancpts')){
    const sp=s.anc_spent, bu=s.anc_budget;
    let col='var(--muted)', tail='';
    if(sp>bu){ col='var(--bad)'; tail=' &mdash; over budget'; }
    else if(sp<bu){ col='var(--warn)'; tail=` &mdash; ${bu-sp} to spend`; }
    else { col='var(--ok)'; tail=' &mdash; balanced'; }
    $('ancpts').innerHTML = `Ancestry points: <b style="color:${col}">${sp} of ${bu} spent</b>${tail}`;
  }
  if($('resreadout')){
    // grants-only auto-heal: show maneuver/spell "N of M recorded" while the count is not met (a gap
    // the ready slot heals); silent when complete, to avoid clutter. BUG-28: OVER the count is not
    // silent either - it reads red with the overflow spelled out, because going quiet was exactly how
    // a shrunken grant hid its orphaned picks.
    const bits=[];
    const resbit=(label,have,budget)=>{
      if(have<budget) bits.push(`${label}: <b style="color:var(--warn)">${have} of ${budget} recorded</b>`);
      else if(have>budget) bits.push(`${label}: <b style="color:var(--bad)">${have} recorded, only ${budget} granted</b>`);
      // complete: still say so (green), mirroring the always-on "N of M spent" ancestry readout.
      // Vanishing on completion read as the readout breaking rather than the count being met.
      else bits.push(`${label}: <b style="color:var(--ok)">${have} of ${budget} recorded</b>`);
    };
    if(s.man_budget>0 || s.man_have>0) resbit('Maneuvers', s.man_have, s.man_budget);
    if(s.spell_budget>0 || s.spell_have>0) resbit('Spells', s.spell_have, s.spell_budget);
    $('resreadout').innerHTML = bits.join(' &middot; ');
  }
  // skills / trades allocator
  $('alloc').innerHTML = s.alloc.map(a => {
    const capctl = a.purchasable
      ? `<label class="capraise" title="spend 1 ${a.kind==='skills'?'Skill':'Trade'} Point to raise this Mastery Limit by 1"><input type="checkbox" data-lr="${esc(a.id)}" ${a.purchased?'checked':''}> cap+</label>`
      : (a.limit_raise?`<span class="capraise" style="color:var(--muted)" title="Mastery Limit already raised (${esc(a.limit_raise)})">cap&uarr;</span>`:'');
    return `<div class="row"><span class="nm" title="${esc(a.name)}">${esc(a.kind==='skills'?'':'[T] ')}${esc(a.name)}${a.limit_raise?' *':''}</span>
     <span><select class="select" style="max-width:100px" data-mast="${esc(a.id)}">` +
     a.options.map(o=>`<option value="${esc(o)}" ${String(a.mastery)===o?'selected':''}>${o==='None'?'-':esc(o)}</option>`).join("") +
     `</select> ${capctl}${a.removable?` <a href="#" class="rm" data-mastrm="${esc(a.id)}">&times;</a>`:''}</span></div>`;
  }).join("");
  document.querySelectorAll('[data-mast]').forEach(el => el.onchange = () => refresh(api.set_mastery(el.dataset.mast, el.value)));
  document.querySelectorAll('[data-lr]').forEach(el => el.onchange = () => refresh(api.set_limit_raise(el.dataset.lr, el.checked)));
  document.querySelectorAll('[data-mastrm]').forEach(el => el.onclick = ev => { ev.preventDefault(); refresh(api.remove_mastery(el.dataset.mastrm)); });
  const stg = {};
  for(const o of s.skill_trade_options) (stg[o.group] ||= []).push(o);
  $('ska-pick').innerHTML = Object.entries(stg).map(([g,os]) =>
      `<optgroup label="${esc(g)}">${os.map(o=>`<option value="${esc(o.kind)}|${esc(o.name)}">${esc(o.name)}</option>`).join("")}</optgroup>`
    ).join("") + `<option value="::custom">custom&hellip;</option>`;
  const skaCustom = () => { const c = $('ska-pick').value === "::custom";
    $('ska-name').style.display = c ? "" : "none"; $('ska-kind').style.display = c ? "" : "none"; };
  $('ska-pick').onchange = skaCustom; skaCustom();
  $('ska-btn').onclick = () => {
    const v = $('ska-pick').value;
    if(v === "::custom"){ const n = $('ska-name').value.trim(); if(n) refresh(api.add_mastery($('ska-kind').value, n)); }
    else { const [kind, name] = [v.slice(0, v.indexOf('|')), v.slice(v.indexOf('|')+1)]; refresh(api.add_mastery(kind, name)); }
  };
  // languages
  $('langs').innerHTML = s.languages.map(l =>
    `<div class="row"><span class="nm">${esc(l.name)}</span>
     <span><select class="select" style="max-width:100px" data-lang="${l.i}" ${l.fixed?'disabled':''}>` +
     ['Limited','Fluent'].map(f=>`<option ${l.fluency===f?'selected':''}>${f}</option>`).join("") +
     `</select> <span style="font-size:.72rem;color:var(--warn)">(${l.cost} LP)</span>` +
     (l.fixed?'':` <a href="#" class="rm" data-langrm="${l.i}">&times;</a>`) + `</span></div>`).join("");
  document.querySelectorAll('[data-lang]').forEach(el => el.onchange = () => refresh(api.set_language(el.dataset.lang, el.value)));
  document.querySelectorAll('[data-langrm]').forEach(el => el.onclick = ev => { ev.preventDefault(); refresh(api.remove_language(el.dataset.langrm)); });
  const lg = {};
  for(const o of (s.language_options||[])) (lg[o.group] ||= []).push(o);
  $('lang-pick').innerHTML = Object.entries(lg).map(([g,os]) =>
      `<optgroup label="${esc(g)}">${os.map(o=>`<option value="${esc(o.name)}">${esc(o.name)}</option>`).join("")}</optgroup>`
    ).join("") + `<option value="::custom">custom&hellip;</option>`;
  const langCustom = () => { $('lang-name').style.display = $('lang-pick').value === "::custom" ? "" : "none"; };
  $('lang-pick').onchange = langCustom; langCustom();
  $('lang-btn').onclick = () => {
    const v = $('lang-pick').value;
    const n = v === "::custom" ? $('lang-name').value.trim() : v;
    if(n) refresh(api.add_language(n, $('lang-flu').value));
  };
  // stats (collapse the Sheet/Check columns when there is no sheet to compare against)
  const noSheet = s.stats.every(r=>r[2]==='-');
  $('statshead').innerHTML = noSheet ? `<tr><th>Stat</th><th>Derived</th></tr>`
    : `<tr><th>Stat</th><th>Derived</th><th>Sheet</th><th>Check</th></tr>`;
  $('sheetnote').style.display = noSheet ? "block" : "none";
  $('stats').innerHTML = s.stats.map(r=> noSheet
    ? `<tr><td>${esc(r[0])}</td><td>${esc(r[1])}</td></tr>`
    : `<tr><td>${esc(r[0])}</td><td>${esc(r[1])}</td><td>${esc(r[2])}</td><td class="mk-${r[3]}">${esc(r[3])}</td></tr>`).join("");
  // budgets
  $('budgets').innerHTML = s.budgets.map(b=>`<div class="budget">&bull; ${esc(b)}</div>`).join("");
  // problems (engine + catalog + builder) + advisories (legal but probably unfinished)
  const probs = s.problems.map(p=>"engine: "+p).concat(s.catalog_problems).concat(s.builder_problems);
  let ph = "";
  if(probs.length){
    ph = `<div class="prob"><b>${probs.length} problem(s):</b>
      <ul>${probs.map(p=>`<li>${esc(p)}</li>`).join("")}</ul></div>`;
  } else {
    ph = `<div class="prob clean">&check; All checks passed - budgets balanced, no illegal picks.</div>`;
  }
  if((s.advisories||[]).length){
    ph += `<div class="prob adv"><b>Unspent points</b> (legal, but level-up night usually spends them):
      <ul>${s.advisories.map(p=>`<li>${esc(p)}</li>`).join("")}</ul></div>`;
  }
  $('problems').innerHTML = ph;
  // exports
  let eb;
  if(s.scratch){
    eb = `<button class="exportbtn" id="exp-new">&darr; Export ${esc(slug(s))}.yaml</button>`;
  } else if(canon){
    eb = `<button class="exportbtn" id="exp-respec">&darr; Respec export &rarr; ${esc(s.handle)}.respec.yaml</button>
          <button class="exportbtn canonbtn" id="exp-canon">&darr; CANON export &rarr; ${esc(s.handle)}.yaml</button>
          <div class="src">Respec = a scratch file for what-ifs; it is never in the party include set. CANON is the
          level-up-night export: once committed it REPLACES ${esc(s.handle)}.yaml for the whole party.</div>`;
  } else {
    eb = `<button class="exportbtn" id="exp-new">&darr; Export ${esc(s.handle)}.yaml</button>`;
  }
  $('exports').innerHTML = eb;
  const undecided = s.builder_problems.length;
  if($('exp-new')) $('exp-new').onclick = () => doExport((s.scratch ? slug(s) : s.handle) + ".yaml");
  if($('exp-respec')) $('exp-respec').onclick = () => doExport(s.handle + ".respec.yaml");
  if($('exp-canon')) $('exp-canon').onclick = () => {
    let msg = `CANON export: committing ${s.handle}.yaml REPLACES ${s.character}'s canonical ledger for the whole party.\n\nFor a what-if, cancel and use the respec export instead.`;
    if(undecided) msg = `${undecided} builder problem(s) are still open (undecided picks).\n\n` + msg;
    if(probs.length && !undecided) msg = `${probs.length} problem(s) are still flagged in the review panel.\n\n` + msg;
    if(confirm(msg)) doExport(s.handle + ".yaml");
  };
}

function refresh(stateJson){
  dirty = true;
  render(JSON.parse(stateJson));
  saveWIP();
}

function doExport(fname){
  const y = api.export_yaml();
  $('yamlwrap').style.display = "block";
  $('yamlout').textContent = y;
  const blob = new Blob([y], {type:"text/yaml"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = fname; a.click();
  URL.revokeObjectURL(a.href);
}

$('yamlcopy').onclick = async () => {
  const t = $('yamlout').textContent;
  let done = false;
  try{ await navigator.clipboard.writeText(t); done = true; }catch(e){}
  if(!done){  // fallback for file:// / older browsers: select + execCommand
    try{
      const r = document.createRange(); r.selectNodeContents($('yamlout'));
      const sl = getSelection(); sl.removeAllRanges(); sl.addRange(r);
      done = document.execCommand('copy'); sl.removeAllRanges();
    }catch(e){}
  }
  $('yamlcopy').textContent = done ? "Copied \u2713" : "Copy failed - select the text manually";
  setTimeout(() => { $('yamlcopy').textContent = "Copy to clipboard"; }, 2000);
};

$('loadyaml').onchange = async ev => {
  const f = ev.target.files[0]; if(!f || !pyodide) return;
  try{
    const text = await f.text();
    const base = f.name.replace(/\.ya?ml$/i, "");
    handle = base.split('.')[0];
    api = pyodide.globals.get("make_api_text")(handle, text);
    dirty = true;
    const st = JSON.parse(api.state());
    render(st);
    $('app').style.display = "grid";  // the blank landing keeps it hidden until now
    // reflect the loaded character in the picker (a loaded file need not be a party handle)
    const csel = $('charsel');
    let lopt = csel.querySelector('option[value="__loaded__"]');
    if(!lopt){ lopt = document.createElement('option'); lopt.value = "__loaded__";
      csel.insertBefore(lopt, csel.firstChild); }
    lopt.textContent = "loaded: " + (st.character || f.name);
    csel.value = "__loaded__";
    $('status').className = "ready";
    $('status').textContent = `Loaded ${f.name} - the engine has re-validated it (see Review).`;
  }catch(e){
    $('status').className = "err";
    $('status').textContent = "Could not load that YAML: " + e;
  }
};

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


def model_strings():
    """Every string the model could put on a decision row, for CH-11's linkable index.

    `ruleTag` is called on a row's current pick or its fixed text, so the phrases it can ever ask
    about are exactly the strings living in the catalogs and the six ledgers. Harvesting them
    wholesale is deliberate: an over-broad candidate set costs a few KB, because only phrases that
    actually occur in the rules survive the corpus filter, while a MISSED one silently drops a
    `rule` chip and no harness would see it.
    """
    out = set()

    def walk(o):
        if isinstance(o, str):
            out.add(o)
        elif isinstance(o, dict):
            for k, v in o.items():
                out.add(str(k))
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    cat_dir = os.path.join(REPO, "builds", "catalog")
    paths = [os.path.join(REPO, "builds", c + ".yaml") for c in CHARS]
    paths += [os.path.join(cat_dir, f) for f in sorted(os.listdir(cat_dir)) if f.endswith(".yaml")]
    for p in paths:
        with open(p, encoding="utf-8") as f:
            walk(yaml.safe_load(f))
    return out


def main():
    ap = argparse.ArgumentParser(description="Generate builds/builder.html (six characters + scratch mode).")
    ap.add_argument("--out", default=os.path.join(REPO, "builds", "builder.html"))
    args = ap.parse_args()

    meta = extract_spell_meta(os.path.join(REPO, "rules", "spells.md"))
    b64 = {"engine": b64_file(os.path.join(REPO, "tools", "build_engine.py")),
           "api": b64_str(API_PY),
           "meta": b64_str(json.dumps(meta, ensure_ascii=False))}
    rel = {"engine": "../tools/build_engine.py"}
    for c in CHARS:
        b64[c] = b64_file(os.path.join(REPO, "builds", c + ".yaml"))
        rel[c] = c + ".yaml"
    for c in CATALOG:
        b64[c] = b64_file(os.path.join(REPO, "builds", "catalog", c + ".yaml"))
        rel[c] = "catalog/" + c + ".yaml"

    # BUG-31: the in-page CATPATHS must cover every catalog the BuilderAPI needs, so generate it from
    # CATALOG rather than hand-maintaining a second list. class_spines is excluded on purpose: the
    # ENGINE loads it itself by bare filename (load_class_tables), it is not a BuilderAPI catalog.
    catpaths = {c: c + ".yaml" for c in CATALOG if c not in CATPATHS_EXCLUDE}

    # FR-43: build stamp, deliberately the SAME recipe as the Companion's About-tab stamp
    # (companion-src/build.py): Sydney wall clock + the short SHA the Action was run against, or
    # "local" when generated by hand. It answers "did the deployed page actually rebuild?" without
    # having to diff a 2.5 MB file, which is exactly the question that cost us a round trip on
    # 2026-07-27. Note it names the commit the build ran FROM, so a freshly regenerated page
    # committed alongside its sources shows the PREVIOUS SHA until the Action rebuilds it.
    try:
        from zoneinfo import ZoneInfo
        _now = datetime.now(ZoneInfo("Australia/Sydney"))
    except Exception:
        _now = datetime.now(timezone.utc)
    stamp = _now.strftime("%Y-%m-%d %H:%M %Z") + " \u00b7 " + (os.environ.get("GITHUB_SHA", "local")[:7])

    # CH-11: the corpus is a SIBLING ARTIFACT now, not a baked literal. It is written next to the
    # page because the page fetches it by relative URL, which is what makes the same file work in
    # builds/ (harness + smoke test, served over http from the repo root) and in dist/ (deploy).
    corpus = build_rules_data(REPO)
    idx = linkable_index(corpus, model_strings())
    rules_path = os.path.join(os.path.dirname(os.path.abspath(args.out)), "rules.json")
    with open(rules_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(corpus, ensure_ascii=False))

    html = (TEMPLATE
            .replace("__BUILD_STAMP__", stamp)
            .replace("__CATPATHS_PY__", repr(catpaths))
            .replace("__CHARS_JSON__", json.dumps(CHARS))
            .replace("__NEWC_JSON__", json.dumps(NEWCLASSES))
            .replace("__B64_JSON__", json.dumps(b64))
            .replace("__REL_JSON__", json.dumps(rel))
            .replace("__RULES_IDX__", corpus_embed(idx)))
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)
    print("wrote %s (%d bytes; %d spells in meta)" % (args.out, len(html), len(meta)))
    print("wrote %s (%d bytes, %d sections; index %d terms in %d bytes)"
          % (rules_path, os.path.getsize(rules_path), len(corpus),
             len(idx["d"]) + len(idx["m"]), len(corpus_embed(idx))))


if __name__ == "__main__":
    main()
