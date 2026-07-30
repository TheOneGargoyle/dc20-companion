#!/usr/bin/env python3
"""Headless regression harness for the rung-3 builder (builds/builder.html).

Runs the EXACT Python glue the page runs (builder_build.API_PY) in sandbox CPython
(== what Pyodide executes), against the real engine, catalog and ledgers, in a temp
dir laid out exactly like the page's Pyodide FS. One command, no browser:

    python3 tools/builder_verify.py

Checks (formalising the step-4 ad-hoc harness + the step-5 additions):
  (1) builds/builder.html blobs are byte-identical (sha256) to their sources
      (engine, six ledgers, ten catalog files, API glue, spells-meta extract),
      and the inline <script> parses (node --check, skipped if node is absent).
  (2) Baseline: all six ledgers load through BuilderAPI; every derived-stat row
      checks OK; engine problems match the known whitelist (runt/scaletrix 1-TP
      trade over-spends); no catalog or builder problems.
  (3) Widget trips: ancestry wrong-cost edit trips the budget and re-balances
      (tanrielle); point-buy trip (minimus); catalog spell-legality trip (xanwyn);
      allocator over-spend trip (tanrielle). Also: the expanded per-attribute
      'Attribute Increase (x)' options replay without crashing the engine.
  (4) NEW-FROM-SCRATCH: a fresh L1 character of each of the five classes, chargen
      driven entirely through the API (point-buy, ancestry, schools, class L1
      choices, spells/maneuvers, background skills/trades/languages), ends with
      ZERO problems (engine + catalog + builder) and its export round-trips clean.
  (5) ADD-A-LEVEL: tanrielle's L5 PROMOTES her locked plan level (allocator applies
      the planned mastery changes; ends 0 problems, expected demoted to history);
      minimus L5 GENERATES slots from the spine (undecided flagged, then filled to
      0 problems); undo_add_level restores the baseline; exports re-validate clean.
  (6) Received-file safety: an exported ledger carrying an illegal edit, reloaded
      as text (the self-serve round trip), still shows the problem.
  (7) Comment-preserving export: every comment line in each of the six source
      ledgers survives an untouched export (with no orphan section), the merged
      export still parses to the same data, EOL comments and aligned continuation
      blocks re-attach, the expected->expected_at_L<n> rename is followed on
      promote, comments survive a second round trip and an edited export, and a
      scratch export carries a generated header.
  (8) Bug-fix round 2: an ancestry-trait prerequisite trips when its required trait is
      dropped (xanwyn Spider Climb/Climb Speed); the languages picker offers grouped
      options and drops a taken language; a Skill/Trade Mastery-Limit raise bought with a
      point suppresses the above-limit flag (tanrielle Awareness); the Attribute Increase
      General Talent grants 2 Attribute Points (spawns 2 attribute riders, budget balanced).

Exit 0 on PASS, 1 on any failure.
"""
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import builder_build  # noqa: E402  (API_PY, extract_spell_meta, CHARS, CATALOG)

FAILS = []


# CH-8 token discipline. A full pass is ~770 checks and ok() printed a 78-char OK line for every
# one of them: ~60KB per run, all of it saying nothing. The CLAUDE.md workflow runs the harnesses
# 4 to 8 times per fix (fresh-clone baseline, post-edit, final, x3 --only chunks), so this output,
# not the actual work, was the dominant token cost of a session and it grew with the check count.
# --quiet prints failures only plus a one-line verdict. CI omits the flag and keeps the full log,
# because there the output is free and a human may want to read it.
QUIET = "--quiet" in sys.argv or "-q" in sys.argv
PASSES = 0


def ok(label, cond, detail=""):
    global PASSES
    if cond:
        PASSES += 1
        if not QUIET:
            print("  %-68s OK" % label)
    else:
        print("  %-68s FAIL %s" % (label, detail))
        FAILS.append(label + (" - " + str(detail) if detail else ""))


def sha(b):
    return hashlib.sha256(b).hexdigest()


# ---------------------------------------------------------------- (1) page blobs
def check_page():
    print("## (1) builder.html blobs vs sources + JS parse")
    path = os.path.join(REPO, "builds", "builder.html")
    html = open(path, encoding="utf-8").read()
    m = re.search(r"const B64 = (\{.*?\});\n", html)
    b64 = json.loads(m.group(1))
    import base64 as b64mod

    def blob(key):
        return b64mod.b64decode(b64[key])
    ok("engine blob == tools/build_engine.py",
       sha(blob("engine")) == sha(open(os.path.join(REPO, "tools", "build_engine.py"), "rb").read()))
    ok("api blob == builder_build.API_PY",
       blob("api").decode("utf-8") == builder_build.API_PY)
    meta = builder_build.extract_spell_meta(os.path.join(REPO, "rules", "spells.md"))
    ok("meta blob == fresh spells.md extract (%d spells)" % len(meta),
       json.loads(blob("meta").decode("utf-8")) == meta)
    for c in builder_build.CHARS:
        ok("ledger blob %s" % c,
           sha(blob(c)) == sha(open(os.path.join(REPO, "builds", c + ".yaml"), "rb").read()))
    for c in builder_build.CATALOG:
        ok("catalog blob %s" % c,
           sha(blob(c)) == sha(open(os.path.join(REPO, "builds", "catalog", c + ".yaml"), "rb").read()))
    ok("page has the copy-to-clipboard button (yamlcopy)",
       'id="yamlcopy"' in html and "navigator.clipboard.writeText" in html)
    ok("level collapsers carry data-lvl + open-state snapshot (no auto-collapse)",
       "data-lvl=" in html and "prevOpen[el.dataset.lvl] = el.open" in html)
    ok("no-deep-link URL lands blank (no CHARS[0] default)",
       "{blank: true}" in html and "CHARS.includes(h) ? h : CHARS[0]" not in html)
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    ok("exactly one inline <script>", len(scripts) == 1, len(scripts))
    node = shutil.which("node")
    if node:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
            f.write(scripts[0])
        r = subprocess.run([node, "--check", f.name], capture_output=True, text=True)
        os.unlink(f.name)
        ok("inline JS parses (node --check)", r.returncode == 0, r.stderr[:200])
    else:
        print("  inline JS parse: node not available, SKIPPED")


# ---------------------------------------------------------------- FS staging
def stage():
    tmp = tempfile.mkdtemp(prefix="builder_verify_")
    shutil.copy(os.path.join(REPO, "tools", "build_engine.py"), tmp)
    with open(os.path.join(tmp, "builder_api.py"), "w", encoding="utf-8") as f:
        f.write(builder_build.API_PY)
    meta = builder_build.extract_spell_meta(os.path.join(REPO, "rules", "spells.md"))
    with open(os.path.join(tmp, "spells_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    for c in builder_build.CHARS:
        shutil.copy(os.path.join(REPO, "builds", c + ".yaml"), tmp)
    for c in builder_build.CATALOG:
        shutil.copy(os.path.join(REPO, "builds", "catalog", c + ".yaml"), tmp)
    return tmp


KNOWN = {}  # runt trade over-spend retired 2026-07-16 (BUG-2: Deep Speech is a free Eldritch grant)
# no by-design table mismatches remain. BUG-7 (runt AD 12 vs 14) was CLOSED 2026-07-16:
# confirmed with Phil the armour is Deflecting Heavy (+2 PD / +0 AD) and Pact Armor's +1 is
# AD not PD, so RAW AD = 13 = the sheet (see runt.yaml).
KNOWN_MISMATCH = {}
MISMATCH_LABELS = {"Saves", "Move Speed", "Jump Distance", "AD"}
CATPATHS = None
builder_api = None


def st(api):
    return json.loads(api.state())


def probs(s):
    return s["problems"], s["catalog_problems"], s["builder_problems"]


def clean(s):
    e, c, b = probs(s)
    return not e and not c and not b


# ---------------------------------------------------------------- (2) baseline
def check_baseline():
    print("## (2) Baseline: six ledgers through BuilderAPI")
    for c in builder_build.CHARS:
        api = builder_api.BuilderAPI(c, CATPATHS)
        s = st(api)
        marks = [r[3] for r in s["stats"] if r[3]]
        mism = {r[0] for r in s["stats"] if r[3] == "MISMATCH"}
        e, cat, b = probs(s)
        ok("%-10s stats %d OK; mismatches == whitelist" % (c, marks.count("OK")),
           marks and all(m in ("OK", "MISMATCH") for m in marks)
           and mism == KNOWN_MISMATCH.get(c, set()), mism)
        # the whitelisted table mismatches also appear as problems; strip them, then the
        # remainder must equal the known non-table problem whitelist (trade over-spends)
        nonmism = [p for p in e if p.split(":")[0] not in MISMATCH_LABELS]
        ok("%-10s engine problems == known whitelist" % c,
           nonmism == KNOWN.get(c, []), e)
        ok("%-10s catalog+builder problems empty" % c, not cat and not b, (cat, b))


# ---------------------------------------------------------------- (3) widget trips
def find_dec(s, pred):
    return next(d for d in s["decisions"] if d.get("id") and pred(d))


def check_trips():
    print("## (3) Widget trips (the step-4 ad-hoc checks, formalised)")
    # ancestry wrong-cost trip + re-balance (tanrielle L4 trait)
    api = builder_api.BuilderAPI("tanrielle", CATPATHS)
    s = st(api)
    d = find_dec(s, lambda d: d["slot"] == "ancestry_trait" and d["level"] == 4)
    s2 = json.loads(api.set_decision(d["id"], "Quick Reactions"))
    ok("tanrielle L4 trait -> Quick Reactions trips ancestry budget",
       any("Ancestry points: 6 spent vs 7 budget" in p for p in s2["problems"]), s2["problems"])
    s3 = json.loads(api.set_decision(d["id"], "Speed Increase"))
    ok("tanrielle back to Speed Increase re-balances", s3["problems"] == [], s3["problems"])
    # per-attribute Attribute Increase options exist and replay (the parse-crash guard)
    s_opts = json.loads(api.state())
    d2 = find_dec(s_opts, lambda x: x["slot"] == "ancestry_trait" and x["level"] == 4)
    names = [o["name"] for o in d2["options"]]
    ok("trait options carry per-attribute 'Attribute Increase (x)' variants",
       "Attribute Increase (agility)" in names and "Attribute Increase" not in names, names[:6])
    s4 = json.loads(api.set_decision(d2["id"], "Attribute Increase (agility)"))
    ok("picking Attribute Increase (agility) replays without crashing",
       isinstance(s4["problems"], list))
    json.loads(api.set_decision(d2["id"], "Speed Increase"))
    # point-buy trip (minimus)
    api = builder_api.BuilderAPI("minimus", CATPATHS)
    s2 = json.loads(api.set_attr("might", 1))
    ok("minimus might 0->1 trips point buy",
       any("Point buy spends 13" in p for p in s2["problems"]), s2["problems"])
    s3 = json.loads(api.set_attr("might", 0))
    ok("minimus back to 0 re-balances", s3["problems"] == [], s3["problems"])
    # catalog spell-legality trip (xanwyn)
    api = builder_api.BuilderAPI("xanwyn", CATPATHS)
    s = st(api)
    d = find_dec(s, lambda d: d["slot"] == "spell" and d["editable"])
    orig = d["current"]
    s2 = json.loads(api.set_decision(d["id"], "Bless"))
    ok("xanwyn spell -> Bless trips catalog legality",
       any("not legal" in p for p in s2["catalog_problems"]), s2["catalog_problems"])
    s3 = json.loads(api.set_decision(d["id"], orig))
    ok("xanwyn back to %s re-cleans" % orig, s3["catalog_problems"] == [], s3["catalog_problems"])
    # ancestry current_group disambiguates same-named traits across lists
    api = builder_api.BuilderAPI("tanrielle", CATPATHS)
    s = st(api)
    d = find_dec(s, lambda d: d["slot"] == "ancestry_trait"
                 and str(d.get("current")) == "Trade Expertise")
    ok("Trade Expertise picker carries current_group == Human (ledger source)",
       d.get("current_group") == "Human", d.get("current_group"))
    # allocator over-spend trip (tanrielle)
    api = builder_api.BuilderAPI("tanrielle", CATPATHS)
    s2 = json.loads(api.set_mastery("skills:Athletics", "Adept"))
    ok("tanrielle Athletics -> Adept over-spends SP",
       any("Skill points over-spent" in p for p in s2["problems"]), s2["problems"])
    s3 = json.loads(api.set_mastery("skills:Athletics", "Novice"))
    ok("tanrielle Athletics back to Novice re-balances", s3["problems"] == [], s3["problems"])


# ---------------------------------------------------------------- (4) new-from-scratch
def drive_fresh(cls):
    api = builder_api.BuilderAPI(None, CATPATHS, new_class=cls)
    # point-buy: 3/1/0/0 = 5+3+2+2 = 12
    api.set_attr("might", 3); api.set_attr("agility", 1)
    api.set_attr("charisma", 0); api.set_attr("intelligence", 0)
    api.set_ancestry("Human", "-")
    # ancestry spend: exactly 5 from the Human list, greedy (skip Attribute traits so
    # the point-buy attributes stay within the L1 limit)
    s = json.loads(api.add_trait(1))
    d = find_dec(s, lambda d: d["slot"] == "ancestry_trait")
    opts = [(o["name"], o["cost"]) for o in d["options"]
            if o["group"] == "Human" and not o["name"].startswith("Attribute")]
    remaining, picks, used = 5, [], set()
    for nm, cost in sorted(opts, key=lambda x: -x[1]):
        if 0 < cost <= remaining and nm not in used:
            picks.append((nm, cost)); used.add(nm); remaining -= cost
        if remaining == 0:
            break
    assert remaining == 0, "could not hit 5 exactly from Human traits: %s" % opts
    api.set_decision(d["id"], picks[0][0])
    for nm, _ in picks[1:]:
        s = json.loads(api.add_trait(1))
        d2 = [x for x in s["decisions"] if x["slot"] == "ancestry_trait"][-1]
        api.set_decision(d2["id"], nm)
    # schools (schools-model classes)
    s = st(api)
    schools = {"spellblade": ["Invocation", "Divination"],
               "warlock": ["Invocation", "Elemental", "Nullification"]}.get(cls, [])
    for i, sch in enumerate(schools):
        api.set_decision("cg:school:%d" % i, sch)
    # class L1 choices (disciplines / pact boons)
    s = st(api)
    for d in s["decisions"]:
        if (d.get("id") or "").startswith("cg:choice:"):
            pick = d["options"][0]["name"] if d["options"] else None
            # spread across distinct options
            idx = int(d["id"].split(":")[-1])
            pick = d["options"][idx % len(d["options"])]["name"]
            api.set_decision(d["id"], pick)
    # spells and maneuvers: first legal option per slot
    s = st(api)
    for d in s["decisions"]:
        if not d.get("id"):
            continue
        if d["id"].startswith("cg:spell:"):
            api.set_decision(d["id"], d["options"][0]["name"])
        elif d["id"].startswith("cg:man:"):
            api.set_decision(d["id"], d["options"][0]["name"])
    # background: skills 5 + Int(0), trades 3, languages 2 LP
    for i, nm in enumerate(["Awareness", "Athletics", "Stealth", "Medicine", "Survival"]):
        api.add_mastery("skills", nm)
    for nm in ["Brewing", "Cooking", "Gaming"]:
        api.add_mastery("trades", nm)
    api.add_language("Elvish", "Fluent")
    return api


def check_scratch():
    print("## (4) New-from-scratch: fresh L1 x5 classes -> 0 problems + round-trip")
    for cls in builder_build.NEWCLASSES:
        api = drive_fresh(cls)
        s = st(api)
        e, c, b = probs(s)
        ok("fresh %-10s 0 engine / 0 catalog / 0 builder problems" % cls,
           clean(s), (e, c, b))
        y = api.export_yaml()
        api2 = builder_api.BuilderAPI("new-" + cls, CATPATHS, ledger_text=y)
        ok("fresh %-10s export round-trips clean" % cls, clean(st(api2)))
    # declared-ancestry legality: swapping ancestry flags the now-off-list traits
    api = drive_fresh("commander")
    s2 = json.loads(api.set_ancestry("Angelborn", "-"))
    ok("scratch ancestry swap Human->Angelborn flags off-list traits",
       any("not one of this character's ancestry lists" in p for p in s2["catalog_problems"]),
       s2["catalog_problems"])
    s3 = json.loads(api.set_ancestry("Human", "-"))
    ok("scratch ancestry swap back re-cleans", s3["catalog_problems"] == [], s3["catalog_problems"])
    # 'opens' reachability: Angelborn + Fallen unlocks Fiendborn trait options
    api = builder_api.BuilderAPI(None, CATPATHS, new_class="commander")
    api.set_ancestry("Angelborn", "-")
    s = json.loads(api.add_trait(1))
    d = [x for x in s["decisions"] if x["slot"] == "ancestry_trait"][-1]
    groups0 = {o["group"] for o in d["options"]}
    ok("Angelborn scratch: options are Angelborn-only before Fallen",
       groups0 == {"Angelborn"}, groups0)
    s = json.loads(api.set_decision(d["id"], "Fallen"))
    s = json.loads(api.add_trait(1))
    d2 = [x for x in s["decisions"] if x["slot"] == "ancestry_trait"][-1]
    groups1 = {o["group"] for o in d2["options"]}
    ok("taking Fallen OPENS the Fiendborn list in the pickers",
       groups1 == {"Angelborn", "Fiendborn"}, groups1)
    s = json.loads(api.set_decision(d2["id"], "Fiendish Magic"))
    ok("a Fiendborn pick via Fallen is catalog-legal",
       not any("ancestry" in p and "lists" in p for p in s["catalog_problems"]),
       s["catalog_problems"])
    # skill/trade picker options come from the curated catalog
    s = st(builder_api.BuilderAPI("tanrielle", CATPATHS))
    opts = s["skill_trade_options"]
    names = {(o["kind"], o["name"]) for o in opts}
    ok("skill/trade picker options: curated, minus already-present",
       ("skills", "Trickery") in names and ("trades", "Occultism") in names
       and ("skills", "Awareness") not in names and ("trades", "Herbalism") not in names,
       sorted(list(names))[:6])
    kn = {o["name"] for o in opts if o["group"] == "Knowledge Trades"}
    ok("knowledge trades grouped separately", "Occultism" in kn and "History" in kn, kn)


# ---------------------------------------------------------------- (5) add-a-level
def check_addlevel():
    print("## (5) Add-a-level: promote (tanrielle L5) + generate (minimus L5) + undo")
    # tanrielle: PROMOTE the locked L5 plan
    api = builder_api.BuilderAPI("tanrielle", CATPATHS)
    s0 = st(api)
    ok("tanrielle next-level info says promote L5", s0["next"]["has_plan"] and s0["next"]["level"] == 5)
    s = json.loads(api.add_level())
    ok("tanrielle current_level -> 5, plan now [6]", s["level"] == 5 and s["planned"] == [6],
       (s["level"], s["planned"]))
    ok("tanrielle expected demoted to history on level-up",
       "expected" not in api.ledger and "expected_at_L4" in api.ledger)
    ok("tanrielle promoted L5 has no undecided slots", s["builder_problems"] == [], s["builder_problems"])
    ok("tanrielle promoted L5 flags the unspent-points ADVISORY (green + amber)",
       not s["problems"] and any("SPARE" in a for a in s["advisories"]), s["advisories"])
    # apply the plan's allocator changes (Awareness->Expert, Herbalism->Expert, Arcana/Nature->Adept)
    api.set_mastery("skills:Awareness", "Expert")
    api.set_mastery("trades:Herbalism", "Expert")
    api.set_mastery("trades:Arcana", "Adept")
    s = json.loads(api.set_mastery("trades:Nature", "Adept"))
    ok("tanrielle L5 after plan allocator changes: 0 problems", not s["problems"] and not s["catalog_problems"],
       probs(s))
    ok("tanrielle L5 advisory clears once the plan's points are spent",
       s["advisories"] == [], s["advisories"])
    y = api.export_yaml()
    api2 = builder_api.BuilderAPI("tanrielle", CATPATHS, ledger_text=y)
    ok("tanrielle L5 export re-validates clean at L5",
       st(api2)["level"] == 5 and not st(api2)["problems"], st(api2)["problems"])
    # minimus: GENERATE slots from the spine (no plan level)
    api = builder_api.BuilderAPI("minimus", CATPATHS)
    base = st(api)
    ok("minimus next-level info says add L5 (no plan)", not base["next"]["has_plan"])
    s = json.loads(api.add_level())
    gen = [d for d in s["decisions"] if d["level"] == 5]
    slots = sorted(d["slot"] for d in gen)
    ok("minimus L5 slots generated from spine (attr+class_feature+maneuver)",
       slots == ["attribute", "class_feature", "maneuver"], slots)
    ok("minimus generated slots flagged undecided", len(s["builder_problems"]) == 2, s["builder_problems"])
    for d in gen:
        if d["slot"] == "attribute":
            s = json.loads(api.set_decision(d["id"], "charisma"))
            ok("minimus L5 charisma 3->4 legal at L5 (limit rises)",
               not any("limit" in p for p in s["problems"]), s["problems"])
        elif d["slot"] == "maneuver":
            s = json.loads(api.set_decision(d["id"], d["options"][0]["name"]))
    s = st(api)
    ok("minimus L5 decided: 0 engine / 0 catalog / 0 builder problems", clean(s), probs(s))
    # path-rider sync: add L6 (features Talent+Path) and pick a path
    s = json.loads(api.add_level())
    d = find_dec(s, lambda d: d["level"] == 6 and d["slot"] == "path")
    s = json.loads(api.set_decision(d["id"], "Spellcaster"))
    riders = [x for x in s["decisions"] if x["level"] == 6 and x["slot"] == "spell"]
    ok("builder-added Path pick spawns its rider slot (Spellcaster -> spell)", len(riders) == 1)
    s = json.loads(api.set_decision(d["id"], "Martial"))
    riders_m = [x for x in s["decisions"] if x["level"] == 6 and x["slot"] == "maneuver"
                and "path rider" in str(x.get("pick", "")) or
                (x["level"] == 6 and x["slot"] == "maneuver")]
    ok("changing the Path swaps the rider (Martial -> maneuver)",
       len([x for x in s["decisions"] if x["level"] == 6 and x["slot"] == "maneuver"]) == 1
       and not [x for x in s["decisions"] if x["level"] == 6 and x["slot"] == "spell"])
    # undo restores
    api = builder_api.BuilderAPI("minimus", CATPATHS)
    before = st(api)
    api.add_level()
    after_undo = json.loads(api.undo_add_level())
    ok("minimus undo_add_level restores level + decisions + expected",
       after_undo["level"] == before["level"]
       and len(after_undo["decisions"]) == len(before["decisions"])
       and "expected" in api.ledger and "expected_at_L4" not in api.ledger)
    # tanrielle undo restores the PLAN level (not deletes it)
    api = builder_api.BuilderAPI("tanrielle", CATPATHS)
    api.add_level()
    s = json.loads(api.undo_add_level())
    ok("tanrielle undo restores L5 as plan", s["level"] == 4 and s["planned"] == [5, 6],
       (s["level"], s["planned"]))
    # multi-level undo: the stack lets EVERY level added this session be removed in turn
    api = builder_api.BuilderAPI("minimus", CATPATHS)
    base_data = yaml.safe_load(api.export_yaml())
    ok("minimus baseline shows no undo link", st(api)["undo_level"] is None)
    s = json.loads(api.add_level())
    ok("after add L5 the undo link says L5", s["undo_level"] == 5, s["undo_level"])
    s = json.loads(api.add_level())
    ok("after add L6 the undo link says L6 (stacked)", s["undo_level"] == 6, s["undo_level"])
    s = json.loads(api.undo_add_level())
    ok("first undo -> L5, undo link now L5 (not gone)",
       s["level"] == 5 and s["undo_level"] == 5, (s["level"], s["undo_level"]))
    s = json.loads(api.undo_add_level())
    ok("second undo -> L4, undo link gone",
       s["level"] == 4 and s["undo_level"] is None, (s["level"], s["undo_level"]))
    ok("two adds + two undos restore the exact ledger data",
       yaml.safe_load(api.export_yaml()) == base_data)
    # same through a PROMOTE chain: tanrielle promote L5, generate L6, unwind both
    api = builder_api.BuilderAPI("tanrielle", CATPATHS)
    base_data = yaml.safe_load(api.export_yaml())
    api.add_level()
    s = json.loads(api.add_level())
    ok("tanrielle promote L5 then add L6 stacks the undo to L6",
       s["level"] == 6 and s["undo_level"] == 6, (s["level"], s["undo_level"]))
    api.undo_add_level()
    s = json.loads(api.undo_add_level())
    ok("unwinding both restores L4 with L5 back as plan",
       s["level"] == 4 and s["planned"] == [5, 6] and s["undo_level"] is None,
       (s["level"], s["planned"], s["undo_level"]))
    ok("tanrielle promote+add+unwind restores the exact ledger data",
       yaml.safe_load(api.export_yaml()) == base_data)


# ---------------------------------------------------------------- (6) received-file safety
def check_received():
    print("## (6) Received-file safety (self-serve round trip)")
    api = builder_api.BuilderAPI("tanrielle", CATPATHS)
    s = st(api)
    d = find_dec(s, lambda d: d["slot"] == "ancestry_trait" and d["level"] == 4)
    api.set_decision(d["id"], "Quick Reactions")  # cost-1: illegal budget
    y = api.export_yaml()
    api2 = builder_api.BuilderAPI("tanrielle", CATPATHS, ledger_text=y)
    s2 = st(api2)
    ok("illegal ancestry edit still caught after export+reload",
       any("Ancestry points" in p for p in s2["problems"]), s2["problems"])
    api = builder_api.BuilderAPI("xanwyn", CATPATHS)
    s = st(api)
    d = find_dec(s, lambda d: d["slot"] == "spell" and d["editable"])
    api.set_decision(d["id"], "Bless")
    y = api.export_yaml()
    api3 = builder_api.BuilderAPI("xanwyn", CATPATHS, ledger_text=y)
    ok("illegal spell edit still caught after export+reload",
       any("not legal" in p for p in st(api3)["catalog_problems"]), st(api3)["catalog_problems"])


# ---------------------------------------------------------------- (7) comments
def check_comments():
    print("## (7) Comment-preserving YAML export")
    import yaml as _yaml
    for c in builder_build.CHARS:
        src = open(c + ".yaml", encoding="utf-8").read()
        api = builder_api.BuilderAPI(c, CATPATHS)
        y = api.export_yaml()
        src_comments = [ln.strip() for ln in src.splitlines()
                        if ln.strip().startswith("#")]
        missing = [t for t in src_comments if t not in y]
        ok("%-10s all %d source comment lines survive export" % (c, len(src_comments)),
           not missing, missing[:3])
        ok("%-10s no orphan section on an untouched export" % c,
           "anchor was edited away" not in y)
        ok("%-10s merged export parses back to the same data" % c,
           _yaml.safe_load(y) == api.ledger)
    # the tanrielle specifics: header, EOL comments, aligned continuation, marker
    api = builder_api.BuilderAPI("tanrielle", CATPATHS)
    y = api.export_yaml()
    ok("tanrielle header provenance block stays at the top",
       y.startswith("# Build ledger: Tanrielle"))
    ok("tanrielle EOL comment re-attaches (allocation_confidence)",
       re.search(r"allocation_confidence: inferred\s+# totals verified", y))
    ok("tanrielle pd EOL comment + continuation block re-attach",
       re.search(r"pd: 17\s+# base incl", y) and "NOT a sheet error" in y)
    ok("tanrielle PLAN section marker survives", "# ---- PLAN" in y)
    # an edit does not disturb the comments
    s = st(api)
    d = find_dec(s, lambda d: d["slot"] == "ancestry_trait" and d["level"] == 4)
    api.set_decision(d["id"], "Quick Reactions")
    y2 = api.export_yaml()
    ok("comments survive an edited export",
       "# ---- PLAN" in y2 and "Quick Reactions" in y2
       and y2.startswith("# Build ledger: Tanrielle"))
    # promote: the expected block's EOL comment follows the rename
    api = builder_api.BuilderAPI("tanrielle", CATPATHS)
    api.add_level()
    y3 = api.export_yaml()
    m = [l for l in y3.splitlines() if l.startswith("expected_at_L4:")]
    ok("promote: expected's EOL comment follows the expected_at_L4 rename",
       bool(m) and "# from the L4 sheet" in m[0], m[:1])
    # second round trip: reload the exported text, export again
    api2 = builder_api.BuilderAPI("tanrielle", CATPATHS, ledger_text=y3)
    y4 = api2.export_yaml()
    ok("comments survive a second export round trip",
       y4.startswith("# Build ledger: Tanrielle") and "# ---- PLAN" in y4
       and "# from the L4 sheet" in y4 and _yaml.safe_load(y4) == api2.ledger)
    # a removed anchor goes to the marked orphan section, not silently dropped
    api3 = builder_api.BuilderAPI("tanrielle", CATPATHS)
    api3.ledger.pop("expected")
    y5 = api3.export_yaml()
    ok("a deleted anchor's comment lands in the marked orphan section",
       "anchor was edited away" in y5 and "from the L4 sheet" in y5)
    # scratch export gets a generated header
    napi = builder_api.BuilderAPI(None, CATPATHS, new_class="druid")
    ok("scratch export carries a generated header",
       napi.export_yaml().startswith("# Build ledger: New Druid"))



# ---------------------------------------------------------------- (8) round-2 bug fixes
def check_new_features():
    print("## (8) Bug-fix round 2: prereqs, languages picker, cap raise, Attribute Increase")

    # (item 1) ancestry-trait prerequisites: dropping xanwyn's Climb Speed makes his
    # Spider Climb (requires Climb Speed) illegal; restoring it clears the flag.
    api = builder_api.BuilderAPI("xanwyn", CATPATHS)
    s = st(api)
    d = find_dec(s, lambda d: d["slot"] == "ancestry_trait" and str(d.get("current")) == "Climb Speed")
    s2 = json.loads(api.set_decision(d["id"], "Tough"))
    ok("prereq: dropping Climb Speed trips 'Spider Climb requires Climb Speed'",
       any("Spider Climb requires Climb Speed" in p for p in s2["catalog_problems"]), s2["catalog_problems"])
    s3 = json.loads(api.set_decision(d["id"], "Climb Speed"))
    ok("prereq: restoring Climb Speed clears the prerequisite flag",
       not any("requires Climb Speed" in p for p in s3["catalog_problems"]), s3["catalog_problems"])

    # (item 2) languages picker: options are grouped, and a picked language is added
    # and then drops out of the remaining options.
    api = builder_api.BuilderAPI("tanrielle", CATPATHS)
    s = st(api)
    lo = s["language_options"]
    ok("languages: options present and grouped (Mortal/Exotic/Divine/Outer)",
       bool(lo) and set(o["group"] for o in lo) <= {"Mortal", "Exotic", "Divine", "Outer"},
       sorted(set(o["group"] for o in lo)))
    pick = lo[0]["name"]
    s2 = json.loads(api.add_language(pick, "Fluent"))
    ok("languages: a picked language is added to the ledger",
       any(l["name"] == pick for l in s2["languages"]), pick)
    ok("languages: a taken language drops out of the picker options",
       pick not in [o["name"] for o in s2["language_options"]])

    # (item 3) buy a Mastery-Limit raise with a point: tanrielle's Awareness is a Novice
    # skill raised to Adept via a purchased cap raise (clean baseline). Removing the
    # purchase flags it above the L4 limit; re-buying clears it.
    api = builder_api.BuilderAPI("tanrielle", CATPATHS)
    aw = next(a for a in st(api)["alloc"] if a["id"] == "skills:Awareness")
    ok("cap raise: Awareness starts as a purchased cap raise (purchased=True)", aw["purchased"] is True)
    s1 = json.loads(api.set_limit_raise("skills:Awareness", False))
    ok("cap raise: removing the purchase flags Awareness above the L4 limit",
       any("Awareness at Adept above L4 limit" in p for p in s1["problems"]), s1["problems"])
    s2 = json.loads(api.set_limit_raise("skills:Awareness", True))
    ok("cap raise: re-buying the raise clears the above-limit flag",
       not any("above L4 limit" in p for p in s2["problems"]), s2["problems"])

    # (item 5) Attribute Increase General Talent grants 2 Attribute Points: picking it on
    # tanrielle's L4 talent spawns two attribute rider slots, the engine's attribute
    # budget stays balanced (no mismatch), and two undecided attribute picks are flagged.
    api = builder_api.BuilderAPI("tanrielle", CATPATHS)
    s = st(api)
    base_attr4 = len([d for d in s["decisions"] if d["slot"] == "attribute" and d["level"] == 4])
    tal = find_dec(s, lambda d: d["slot"] == "talent" and d["level"] == 4)
    s2 = json.loads(api.set_decision(tal["id"], "Attribute Increase"))
    attr4 = [d for d in s2["decisions"] if d["slot"] == "attribute" and d["level"] == 4]
    ok("Attribute Increase talent spawns 2 attribute rider slots at L4",
       len(attr4) == base_attr4 + 2, len(attr4))
    ok("Attribute Increase: engine attribute budget stays balanced (no mismatch)",
       not any("Attribute points:" in p for p in s2["problems"]), s2["problems"])
    ok("Attribute Increase: the 2 new attribute picks flag as undecided",
       sum("attribute undecided" in p for p in s2["builder_problems"]) == 2, s2["builder_problems"])
    s3 = json.loads(api.set_decision(tal["id"], "Life Tap"))
    ok("changing the talent away removes the attribute riders",
       len([d for d in s3["decisions"] if d["slot"] == "attribute" and d["level"] == 4]) == base_attr4)


# ---------------------------------------------------------------- (9) character sheet
def check_sheet():
    import math
    print("## (9) Character sheet: api.sheet() well-formed for six ledgers")
    MB = {"Novice": 2, "Adept": 4, "Expert": 6, "Master": 8, "Grandmaster": 10}
    NEED = {"character", "level", "cm", "prime", "attrs", "core", "derived",
            "skills", "trades", "languages", "abilities", "spells", "equipment"}
    for c in builder_build.CHARS:
        d = json.loads(builder_api.BuilderAPI(c, CATPATHS).sheet())
        ok("%-10s sheet has all sections" % c, NEED <= set(d), NEED - set(d))
        hp = int(d["core"]["HP"])
        der = d["derived"]
        ok("%-10s bloodied/well/death/rest derived correctly" % c,
           der["bloodied"] == math.ceil(hp / 2) and der["well_bloodied"] == math.ceil(hp / 4)
           and der["death_threshold"] == d["prime"] + d["cm"] and der["rest_points"] == hp, der)
        bad = [s for s in d["skills"]
               if s["bonus"] != ((d["prime"] if s["attr"] == "Prime" else d["attrs"].get(s["attr"], 0)) + MB.get(s["tier"], 0))]
        ok("%-10s skill bonuses = governing attr + mastery bonus" % c, not bad, bad)
        picks = [x for v2 in d["abilities"].values() for x in v2]
        ok("%-10s abilities within current level, no blanks" % c,
           all(x.get("pick") and (not x.get("level") or x["level"] <= d["level"]) for x in picks), None)
        # sheet spell list = the consolidated reference view -> sorted ALPHABETICALLY by name
        # (provenance/grant-source lives in the builder decision list, not the sheet).
        names = [s["name"] for s in d["spells"]]
        ok("%-10s sheet spells sorted alphabetically (findability, not slot-kind order)" % c,
           names == sorted(names, key=lambda n: str(n).lower()), names)
    d = json.loads(builder_api.BuilderAPI("tanrielle", CATPATHS).sheet())
    aw = next((s["bonus"] for s in d["skills"] if s["name"] == "Awareness"), None)
    ok("tanrielle Awareness = +7 (Prime 3 + Adept 4)", aw == 7, aw)
    ok("tanrielle PD 17 and 6 equipment items", d["core"]["PD"] == "17" and len(d["equipment"]) == 6,
       (d["core"]["PD"], len(d["equipment"])))
    # FR-15: trades carry a numeric mastery bonus (Novice +2 .. Grandmaster +10), no attribute.
    for c in builder_build.CHARS:
        d = json.loads(builder_api.BuilderAPI(c, CATPATHS).sheet())
        bad_tr = [t for t in d["trades"] if t.get("mb") != MB.get(t["tier"], 0)]
        ok("%-10s trade bonus = mastery bonus only (no attribute)" % c, not bad_tr, bad_tr)
    xd = json.loads(builder_api.BuilderAPI("xanwyn", CATPATHS).sheet())
    arc = next((t for t in xd["trades"] if t["name"] == "Arcana"), None)
    ok("FR-15 xanwyn Arcana (Adept) shows mb +4", arc and arc["mb"] == 4, arc)
    html = open(os.path.join(REPO, "builds", "builder.html"), encoding="utf-8").read()
    ok("page has sheet button + renderer + print CSS",
       'id="sheetbtn"' in html and "function renderSheet(" in html and "api.sheet()" in html
       and "body.sheeting .wrap" in html and ".sh-paper" in html)
    ok("FR-15 sheet bakes the trade mastery-only note",
       "Bonus = Mastery only" in html)


# ---------------------------------------------------------------- (10) new derived stats
# Oracle = the companion CHARS hand-entered values (companion-src/template.html):
# per-attribute Saves, Move Speed, Jump Distance, Mana/Stamina Spend Limit.
ORACLE = {
    "tanrielle": dict(saves=dict(Might=4, Agility=5, Charisma=0, Intelligence=5), move=6, jump=3, spend=2),
    "minimus":   dict(saves=dict(Might=2, Agility=4, Charisma=5, Intelligence=2), move=5, jump=2, spend=2),
    "runt":      dict(saves=dict(Might=5, Agility=2, Charisma=1, Intelligence=5), move=5, jump=1, spend=2),
    "scaletrix": dict(saves=dict(Might=6, Agility=4, Charisma=5, Intelligence=2), move=5, jump=1, spend=2),
    "bonan":     dict(saves=dict(Might=5, Agility=2, Charisma=5, Intelligence=1), move=6, jump=6, spend=2),
    "xanwyn":    dict(saves=dict(Might=1, Agility=5, Charisma=2, Intelligence=5), move=5, jump=3, spend=2),
}
# Documented RAW-vs-companion deltas (engine reports the RAW base; the companion
# carries an item/feature overlay), parallel to the runt-PD / xanwyn-HP overlays:
SAVE_OVERLAY = {}   # no overlays: every item/feature effect is modelled in the engine
MOVE_DELTA = {}                  # bonan Fast Movement now modelled -> engine derives 6
JUMP_DELTA = {}                  # bonan Mighty Leap + Jumper + Titanic Leap now modelled -> engine derives 6


def check_newstats():
    print()
    print("## (10) New derived stats: saves / move / jump / spend-limit / DR vs companion oracle")
    for c, o in ORACLE.items():
        der = json.loads(builder_api.BuilderAPI(c, CATPATHS).sheet())["derived"]
        adj = SAVE_OVERLAY.get(c, 0)
        exp_saves = {k: v - adj for k, v in o["saves"].items()}
        ok("%-10s saves = attribute + CM%s" % (c, " (-%d amulet overlay)" % adj if adj else ""),
           der["saves"] == exp_saves, (der["saves"], exp_saves))
        ok("%-10s spend limit (MSL/SSL) = CM = %d" % (c, o["spend"]),
           der["spend_limit"] == o["spend"], der["spend_limit"])
        if c in MOVE_DELTA:
            ok("%-10s move = %d (RAW) vs companion %d (documented delta)" % (c, MOVE_DELTA[c], o["move"]),
               der["move"] == MOVE_DELTA[c], der["move"])
        else:
            ok("%-10s move speed = %d (matches oracle)" % (c, o["move"]), der["move"] == o["move"], der["move"])
        if c in JUMP_DELTA:
            ok("%-10s jump = %d (RAW=Agi min 1) vs companion %d (open Mighty-Leap audit)" % (c, JUMP_DELTA[c], o["jump"]),
               der["jump"] == JUMP_DELTA[c], der["jump"])
        else:
            ok("%-10s jump distance = %d (matches oracle)" % (c, o["jump"]), der["jump"] == o["jump"], der["jump"])
        if c == "runt":
            # BUG-6: Runt now declares DR - PDR Half (Defensive Heavy armour) + MDR Half (Pact Armor).
            ok("%-10s DR = PDR/MDR Half (armour + Pact Armor)" % c,
               der["dr"] == {"PDR": ["half"], "MDR": ["half"]}, der["dr"])
        else:
            ok("%-10s DR empty (plumbing; no structured DR declared yet)" % c, der["dr"] == {}, der["dr"])
    # DR plumbing end-to-end: inject a structured PDR/MDR onto an equipment item
    api = builder_api.BuilderAPI("runt", CATPATHS)
    api.ledger["equipment"][0]["pdr"] = "half"
    api.ledger["equipment"][0]["mdr"] = 1
    dd = json.loads(api.sheet())["derived"]["dr"]
    ok("DR plumbing: injected PDR/MDR surface through the engine onto the sheet",
       dd.get("PDR") == ["half"] and dd.get("MDR") == [1], dd)
    # page carries the new sheet furniture
    html = open(os.path.join(REPO, "builds", "builder.html"), encoding="utf-8").read()
    ok("page sheet has Saves section, DR row and the move/jump footer",
       ">Saves</h3>" in html and "Damage reduction" in html and "sh-foot" in html
       and "Move Speed" in html and "Spend Limit" in html)
    # FR-16A: the Companion bakes engine DR and renders a DR line (omitted when empty).
    cbp = open(os.path.join(REPO, "companion-src", "build.py"), encoding="utf-8").read()
    ctpl = open(os.path.join(REPO, "companion-src", "template.html"), encoding="utf-8").read()
    ok("FR-16A Companion build.py bakes engine-derived DR into party_derived",
       '"dr": _d.get("dr", {})' in cbp)
    ok("FR-16A Companion template merges DR + has fmtDR + renders the DR line",
       "if(d.dr!==undefined)c.dr=d.dr" in ctpl and "function fmtDR(" in ctpl
       and "drStr?'<br>DR: '+drStr" in ctpl)
    # FR-16 Part B: DR is now toggle-aware. Bonan's Rage toggle carries a DR payload
    # (PDR/EDR Half while raging); curDR() merges base engine DR with active-toggle DR
    # take-the-stronger (half beats numeric); the DR line reads fmtDR(curDR()).
    ok("FR-16B Bonan's Rage toggle carries a DR payload (PDR/EDR Half)",
       "dr:{PDR:['half'],EDR:['half']}" in ctpl)
    ok("FR-16B curDR() exists and the DR line is toggle-aware (fmtDR(curDR()))",
       "function curDR(" in ctpl and "const drStr=fmtDR(curDR());" in ctpl)
    # BUG-4: the sheet overlay is mobile-responsive - a max-width:640px block stacks .sh-cols
    # to one column and sizes .sh-paper fluidly (real-phone verification is Darryl's).
    ok("sheet overlay has mobile-responsive rules (BUG-4)",
       "@media (max-width:640px)" in html and ".sh-cols{grid-template-columns:1fr" in html
       and ".sh-paper{width:100%;max-width:100%" in html)


# ---------------------------------------------------------------- (11) composite re-pick escape hatch
def check_replace_hatch():
    UND = '(undecided)'
    print()
    print("## (11) Composite re-pick escape hatch")
    def find(st_, slot, lvl):
        return next((d for d in st_["decisions"] if d.get("slot") == slot and d.get("level") == lvl), None)
    def precon():
        # runt.yaml is now reconciled in canon; rebuild the historical L2 composite so the
        # composite/expand tests stay deterministic. Boon granted_maneuvers stay intact so
        # reconcile can re-harvest Cleave/Pathcarver (L1) and Brace/Side Step (L4).
        _a = builder_api.BuilderAPI("runt", CATPATHS)
        _a.ledger["chargen"]["maneuvers"] = []
        for _L in list(_a.ledger["levels"]):
            _a.ledger["levels"][_L] = [x for x in _a.ledger["levels"][_L] if x.get("slot") != "maneuver"]
        _a.ledger["levels"][2].append({"slot": "maneuver", "inferred": True,
            "pick": "Slam, Body Block, Throw Creature, Heroic Intimidate (4 General, order across L2 sources unknown)"})
        return _a
    api = precon()
    s0 = st(api)
    man = find(s0, "maneuver", 2)   # (historical) 4-maneuver composite row
    ok("composite maneuver row is replaceable + carries options, still shown as text",
       man["widget"] == "fixed" and man.get("replaceable") is True and len(man.get("options") or []) > 0,
       (man["widget"], man.get("replaceable")))
    anc = find(s0, "ancestry_trait", 1)  # 'remainder not itemised' placeholder
    ok("ancestry-trait placeholder is NOT replaceable (excluded slot)",
       not anc.get("replaceable"), anc.get("replaceable"))
    did = man["id"]
    s1 = json.loads(api.set_decision(did, "Slam"))
    e = api.ledger["levels"][2][int(did.split(":")[1])]
    ok("replacing a composite sets the single pick and preserves the original in a note",
       e["pick"] == "Slam" and str(e.get("note", "")).startswith("Replaced composite"), (e["pick"], e.get("note")))
    man2 = find(s1, "maneuver", 2)
    ok("the replaced row is now a normal editable picker (current = the new pick)",
       man2["widget"] == "picker" and man2.get("editable") and man2.get("current") == "Slam", man2)
    ok("the original is surfaced on the picker row as a 'was:' note",
       man2.get("was_note", "").startswith("Replaced composite") and "Body Block" in man2.get("was_note", ""),
       man2.get("was_note"))
    s1b = json.loads(api.set_decision(did, "Body Block"))   # re-pick again
    man3 = find(s1b, "maneuver", 2)
    ok("the 'was:' provenance is sticky across a further re-pick (not clobbered by the edit note)",
       man3.get("current") == "Body Block" and man3.get("was_note", "").startswith("Replaced composite"),
       (man3.get("current"), man3.get("was_note")))
    s1c = json.loads(api.dismiss_note(did))   # dismiss the provenance note once done
    man4 = find(s1c, "maneuver", 2)
    ok("dismiss_note clears the 'was:' note but keeps a normal editable picker",
       not man4.get("was_note") and man4.get("widget") == "picker" and man4.get("current") == "Body Block", man4)
    # (The one-click "expand into per-level slots" reconcile was RETIRED 2026-07-19 with the
    # grants-only unification - it flattened FIXED grants into the flat pool. Missing slots now
    # self-heal via the auto ready-slot; see the grants-only section below. The single-value
    # replace dropdown above is retained for a genuine composite.)
    # Expanded Boon's Pact Boon is now a first-class, catalog-driven pick (de-conflated from the talent)
    api3 = builder_api.BuilderAPI("runt", CATPATHS)
    boon = next((d for d in st(api3)["decisions"] if d.get("slot") == "pact_boon" and d.get("level") == 4), None)
    ok("Expanded Boon's Pact Boon is a first-class editable pick (current Pact Armor, 4 catalog options)",
       bool(boon) and boon["widget"] == "picker" and boon.get("editable")
       and boon.get("current") == "Pact Armor" and len(boon.get("options") or []) == 4, boon)
    api3.set_decision(boon["id"], "Pact Spell")
    e4 = next(e for e in api3.ledger["levels"][4] if e.get("slot") == "pact_boon")
    ok("changing the boon flows grants from the catalog and drops the old boon's captured maneuvers",
       e4["pick"] == "Pact Spell" and not e4.get("grants") and not e4.get("granted_maneuvers"),
       (e4.get("grants"), e4.get("granted_maneuvers")))
    # FR-8 slice 1: Runt's L1 Pact Weapon boon is now a clean picker (de-bundled from its weapon text)
    api4 = builder_api.BuilderAPI("runt", CATPATHS)
    l1boon = next((d for d in st(api4)["decisions"]
                   if d.get("slot") == "pact_boon" and d.get("level") == 1), None)
    ok("FR-8 L1 Pact Weapon is a clean editable picker (not fixed text), current Pact Weapon, 4 options",
       bool(l1boon) and l1boon["widget"] == "picker" and l1boon.get("editable")
       and l1boon.get("current") == "Pact Weapon" and len(l1boon.get("options") or []) == 4, l1boon)
    api4.set_decision(l1boon["id"], "Pact Familiar")
    cc4 = next(c for c in api4.ledger["chargen"]["class_choices"] if c["slot"] == "pact_boon")
    ok("changing the L1 boon re-aggregates grants from the catalog (Pact Familiar grants none)",
       cc4["picks"][0] == "Pact Familiar" and not cc4.get("grants"), (cc4.get("picks"), cc4.get("grants")))
    apiR = builder_api.BuilderAPI("runt", CATPATHS)
    mrows = [d for d in st(apiR)["decisions"] if d.get("slot") == "maneuver"]
    boon_man = [d for d in mrows if "#maneuvers#" in str(d.get("id") or "")]
    ok("all maneuver rows are editable pickers and NOT removable (BUG-16: budget slots edit-only)",
       bool(mrows) and all(d["widget"] == "picker" and d.get("editable") for d in mrows)
       and not any(d.get("removable") for d in mrows),
       [(d.get("current"), d.get("widget"), d.get("removable")) for d in mrows])
    ok("grants-only: pact-boon maneuvers are EDITABLE grant-child pickers (Cleave/Pathcarver/Brace/Side Step)",
       {d.get("current") for d in boon_man} == {"Cleave", "Pathcarver", "Brace", "Side Step"},
       [d.get("current") for d in boon_man])
    ok("no new problems introduced by the replace (runt is now fully clean; BUG-7 AD closed)",
       s1["problems"] == [], s1["problems"])
    html = open(os.path.join(REPO, "builds", "builder.html"), encoding="utf-8").read()
    ok("page JS carries the replace-picker furniture",
       "t.replaceable" in html and "&mdash; replace &mdash;" in html
       and 'class="select repl"' in html and "t.was_note" in html
       and "data-dismiss" in html)
    ok("retired reconcile furniture is gone from the page JS (data-expand / t.expandable)",
       "data-expand" not in html and "t.expandable" not in html)


# ---------------------------------------------------------------- (12) Wave 2 UX
def check_wave2():
    print()
    print("## (12) Wave 2 UX: FR-14 recent files + Level A, FR-1 sort, FR-5 guard, "
          "FR-7 refilter, BUG-3 budget messaging")
    # ---- FR-7: a picker hides options already chosen elsewhere (no double-picks) ----
    api = builder_api.BuilderAPI(None, CATPATHS, new_class="commander")  # 2 L1 maneuver slots
    s = st(api)
    man = [d for d in s["decisions"] if (d.get("id") or "").startswith("cg:man:")]
    names = [o["name"] for o in man[0]["options"]]
    A, B = names[0], names[1]
    api.set_decision(man[0]["id"], A)
    s = json.loads(api.set_decision(man[1]["id"], B))
    o0 = [o["name"] for o in find_dec(s, lambda d: d["id"] == man[0]["id"])["options"]]
    o1 = [o["name"] for o in find_dec(s, lambda d: d["id"] == man[1]["id"])["options"]]
    ok("FR-7 maneuver: each picker hides the other's pick, keeps its own",
       B not in o0 and A in o0 and A not in o1 and B in o1, (A, B))
    api = builder_api.BuilderAPI(None, CATPATHS, new_class="druid")  # 4 L1 spell slots
    s = st(api)
    spl = [d for d in s["decisions"] if (d.get("id") or "").startswith("cg:spell:")]
    names = [o["name"] for o in spl[0]["options"]]
    A, B = names[0], names[1]
    api.set_decision(spl[0]["id"], A)
    s = json.loads(api.set_decision(spl[1]["id"], B))
    s0 = [o["name"] for o in find_dec(s, lambda d: d["id"] == spl[0]["id"])["options"]]
    s1 = [o["name"] for o in find_dec(s, lambda d: d["id"] == spl[1]["id"])["options"]]
    ok("FR-7 spell: each picker hides the other's pick, keeps its own",
       B not in s0 and A in s0 and A not in s1 and B in s1, (A, B))
    api = builder_api.BuilderAPI(None, CATPATHS, new_class="spellblade")  # 2 school slots
    s = st(api)
    sch = [d for d in s["decisions"] if (d.get("id") or "").startswith("cg:school:")]
    names = [o["name"] for o in sch[0]["options"]]
    A, B = names[0], names[1]
    api.set_decision(sch[0]["id"], A)
    s = json.loads(api.set_decision(sch[1]["id"], B))
    sc1 = [o["name"] for o in find_dec(s, lambda d: d["id"] == sch[1]["id"])["options"]]
    ok("FR-7 spell_school: the second picker hides the school already chosen",
       A not in sc1 and B in sc1, (A, B, sc1))
    ok("FR-7 filter set = spell/maneuver/talent/spell_school",
       builder_api.FR7_FILTER_SLOTS == {"spell", "maneuver", "talent", "spell_school"},
       builder_api.FR7_FILTER_SLOTS)
    ok("FR-7 leaves ancestry_trait unfiltered (budget/opens machinery, later pass)",
       "ancestry_trait" not in builder_api.FR7_FILTER_SLOTS)

    # ---- BUG-3: symmetric, clear budget verdicts ----
    for c in builder_build.CHARS:
        s = st(builder_api.BuilderAPI(c, CATPATHS))
        blines = [b for b in s["budgets"]
                  if b.startswith(("Skill points", "Trade points", "Language points"))]
        ok("%-10s all three budget lines print an explicit verdict (symmetric)" % c,
           len(blines) == 3 and all(("balanced" in b or "SPARE" in b or "OVER-SPENT" in b)
                                    for b in blines), blines)
        ok("%-10s no budget line still reads the old 'UNDER-SPENT'" % c,
           not any("UNDER-SPENT" in b for b in s["budgets"]), s["budgets"])
    # BUG-8 (2026-07-16) balanced Xanwyn; CH-1 (2026-07-18) filled minimus's skills from
    # his L4 paper sheet, so NO baseline character carries a spare any more. Keep the
    # SPARE-wording coverage with a synthetic: unset one minimus skill in memory (not
    # exported), which frees 1 SP and must read as a legal SPARE advisory, not a problem.
    api = builder_api.BuilderAPI("minimus", CATPATHS)
    api.set_mastery("skills:Acrobatics", "None")
    s = st(api)
    ok("BUG-3 synthetic spare SP (minimus minus one skill) reads SPARE (legal) in advisories",
       any("SPARE" in a and "Skill points" in a for a in s["advisories"])
       and not any("SPARE" in p for p in s["problems"]), (s["advisories"], s["problems"]))
    s = st(builder_api.BuilderAPI("minimus", CATPATHS))
    ok("CH-1 minimus baseline is balanced (no advisories) after the sheet-audit skill fill",
       s["advisories"] == [] and s["problems"] == [], (s["advisories"], s["problems"]))
    s = st(builder_api.BuilderAPI("tanrielle", CATPATHS))
    ok("BUG-3 language line is symmetric (prints -> balanced even when balanced)",
       any(b.startswith("Language points") and "-> balanced" in b for b in s["budgets"]),
       s["budgets"])

    # ---- FR-14 / FR-1 / FR-5: page furniture in the built builder.html ----
    html = open(os.path.join(REPO, "builds", "builder.html"), encoding="utf-8").read()
    ok("FR-14 Level A: the baked party is no longer listed in the default dropdown",
       '<optgroup label="party">' not in html and "CHARS.map(c=>`<option" not in html)
    ok("FR-14 recent-files machinery present (localStorage + build + deeplink auto-add)",
       "RECENT_KEY" in html and '"dc20builder:recent"' in html and "function loadRecents(" in html
       and "function addRecent(" in html and "function buildCharSel(" in html
       and "recent files" in html and "if(mode.char){ addRecent(handle" in html)
    ok("FR-14 party still resolves by deeplink (baked ledgers kept; ?char= reads CHARS)",
       "CHARS.includes(h)" in html and "return {char: h}" in html)
    ok("FR-1 new-from-scratch list is sorted alphabetically", "NEWC.slice().sort()" in html)
    ok("FR-5 unsaved-changes guard on switch (confirm + revert selection)",
       "if(dirty && !confirm(" in html and "Switch anyway" in html
       and "sel.value = currentSelValue(); return;" in html)

    # ---- BUG-9: character-sheet button pinned top-right via a flex header ----
    ok("BUG-9 header is a flex row with the sheet button pinned right",
       ".apphead{display:flex" in html and ".apphead #sheetbtn{margin-left:auto}" in html
       and '<div class="apphead">' in html)

    # ---- BUG-10: picker labels format grants, never print the raw dict ----
    xapi = builder_api.BuilderAPI("xanwyn", CATPATHS)   # spellblade -> disciplines
    dlabels = [o["label"] for o in xapi._options_for("discipline")]
    rapi = builder_api.BuilderAPI("runt", CATPATHS)      # warlock -> pact_boons
    blabels = [o["label"] for o in rapi._options_for("pact_boon")]
    ok("BUG-10 no picker label prints a raw grants dict",
       not any("{'" in l or "':" in l for l in dlabels + blabels), dlabels + blabels)
    ok("BUG-10 discipline/boon labels format grants readably (e.g. '+2 maneuvers')",
       any("maneuver" in l for l in blabels) and any("MP" in l for l in dlabels),
       dlabels + blabels)

    # ---- FR-10: echo EVERY level's grants into that level's section header ----
    # (generalised 2026-07-17 from the old cur+1-only echo to all levels, all chars).
    ok("FR-10 builder bakes the generalised lvlprev echo (CSS + per-level level_grants injection)",
       ".lvlprev{" in html and "s.level_grants && s.level_grants[lvl]" in html
       and "grants: ${parts.join(' &middot; ')}" in html)
    ok("FR-10 the old cur+1-only gate is gone (superseded by level_grants)",
       "s.next && s.next.level===lvl && s.next.summary" not in html)
    # state() carries a grant summary for EVERY rendered level (1..current + planned),
    # including L1 (chargen kit), for every party character - not just Tanrielle's plan.
    for c in builder_build.CHARS:
        s2 = st(builder_api.BuilderAPI(c, CATPATHS))
        want = set(range(1, s2["level"] + 1)) | set(s2["planned"])
        lg = s2["level_grants"]
        got = {int(k) for k in lg}
        ok("FR-10 %s: level_grants covers every rendered level %s (1..current + planned)"
           % (c, sorted(want)), got == want, sorted(got))
        ok("FR-10 %s: every level_grants entry has a non-empty grant summary (incl L1)" % c,
           all(lg[k]["summary"] and "features" in lg[k] for k in lg),
           {k: lg[k]["summary"] for k in lg})
    # Regression: Tanrielle's L5 header still reads the exact documented FR-10 string,
    # now sourced from level_grants rather than the next-level strip.
    ts = st(builder_api.BuilderAPI("tanrielle", CATPATHS))
    l5 = ts["level_grants"]["5"]
    ok("FR-10 tanrielle L5 grant summary unchanged + Class Feature",
       l5["summary"] == "+2 HP, +1 SP, +1 MP, +1 spell, +1 attribute pt, +2 skill pt, +1 trade pt"
       and l5["features"] == ["Class Feature"], l5)
    # A no-plan character (runt) now gets grants on all its levels - the exact case
    # the old gate missed (Tanrielle-L5-only). Its next-level strip stays intact too.
    rs = st(builder_api.BuilderAPI("runt", CATPATHS))
    ok("FR-10 runt (no planned level) now shows grants on all levels 1..current",
       {int(k) for k in rs["level_grants"]} == set(range(1, rs["level"] + 1))
       and all(rs["level_grants"][k]["summary"] for k in rs["level_grants"]),
       sorted(rs["level_grants"]))
    ok("FR-10 the sidebar next-level strip (s.next) still drives the Add-level button",
       rs["next"] and rs["next"]["level"] == rs["level"] + 1 and bool(rs["next"]["summary"]),
       rs["next"])


# ---------------------------------------------------------------- (13) FR-8 slice 2 backbone
def check_slice2():
    UND = "(undecided)"
    print()
    print("## (13) FR-8 slice 2: grants -> typed child picker-slots backbone")
    # BUG-21 (2026-07-27) added `disciplines` (Paladin Lay on Hands grants one). maneuvers/spells stay
    # OFF this map by design: they use the flat pool, with their own constrained-child branches.
    ok("GRANT_CHILD_SLOTS maps pickable grant resources (runes/metamagic/skills/trades/disciplines), excludes maneuvers/spells",
       builder_api.GRANT_CHILD_SLOTS == {"runes": "rune", "metamagic": "metamagic",
                                         "skills": "skill", "trades": "trade",
                                         "disciplines": "discipline"},
       builder_api.GRANT_CHILD_SLOTS)

    # No party ledger grants a pickable resource yet (rune/metamagic catalogs land in slices 3/4),
    # so drive the backbone with a synthetic fixture - same style as the DR-plumbing injection test.

    # ---- (a) a LEVEL grant-bearing parent materialises typed child slots keyed to it ----
    rapi = builder_api.BuilderAPI("runt", CATPATHS)
    rapi.ccat["runes"] = [{"name": "Fire Rune"}, {"name": "Water Rune"}, {"name": "Cloud Rune"}]
    l4 = rapi.ledger["levels"][4]
    pe = next(e for e in l4 if e.get("slot") == "pact_boon")   # a real grant-bearing parent
    pe["grants"] = dict(pe.get("grants") or {}); pe["grants"]["runes"] = 2
    pe["granted_runes"] = ["Fire Rune"]                        # one pre-filled, one should be undecided
    idx = l4.index(pe)
    s = st(rapi)
    kids = [d for d in s["decisions"] if str(d.get("id")).startswith("GC#L4:%d#runes#" % idx)]
    ok("a LEVEL parent's {runes:2} grant materialises 2 typed 'rune' child pickers keyed to it",
       len(kids) == 2 and all(d["slot"] == "rune" and d["widget"] == "picker" and d["editable"] for d in kids),
       [(d["id"], d.get("current")) for d in kids])
    ok("child picks read from the parent's granted_runes (Fire Rune filled, slot 1 undecided), 3 options each",
       kids[0]["current"] == "Fire Rune" and kids[1]["current"] == UND
       and all(len(d["options"]) == 3 for d in kids),
       [(d["current"], len(d["options"])) for d in kids])
    ok("an undecided grant-child surfaces as a builder completeness problem",
       any("rune undecided" in p for p in s["builder_problems"]), s["builder_problems"])
    rapi.set_decision(kids[1]["id"], "Water Rune")
    ok("editing a grant-child writes into the parent's granted_runes list (structural link)",
       rapi.ledger["levels"][4][idx].get("granted_runes") == ["Fire Rune", "Water Rune"],
       rapi.ledger["levels"][4][idx].get("granted_runes"))

    # ---- (b) re-picking a real grant-bearing PARENT rebuilds/clears its child slots (_apply_grants) ----
    bapi = builder_api.BuilderAPI("runt", CATPATHS)
    bapi.ccat["runes"] = [{"name": "Fire Rune"}, {"name": "Water Rune"}]
    next(b for b in bapi.ccat["pact_boons"] if b["name"] == "Pact Spell")["grants"] = {"runes": 2}
    l4boon = next(d for d in st(bapi)["decisions"] if d.get("slot") == "pact_boon" and d.get("level") == 4)
    bapi.set_decision(l4boon["id"], "Pact Spell")             # re-pick to the rune-granting boon
    pe = next(e for e in bapi.ledger["levels"][4] if e.get("slot") == "pact_boon")
    ok("re-picking a boon to a rune-granting option rebuilds granted_runes as 2 undecided slots and clears old granted_maneuvers",
       pe.get("grants") == {"runes": 2} and pe.get("granted_runes") == [UND, UND]
       and not pe.get("granted_maneuvers"),
       (pe.get("grants"), pe.get("granted_runes"), pe.get("granted_maneuvers")))
    kids = [d for d in st(bapi)["decisions"] if "#runes#" in str(d.get("id"))]
    ok("2 rune child pickers now render under the re-picked boon", len(kids) == 2, [d["id"] for d in kids])
    bapi.set_decision(kids[0]["id"], "Fire Rune")
    bapi.set_decision(l4boon["id"], "Pact Armor")             # back to a non-rune boon
    pe = next(e for e in bapi.ledger["levels"][4] if e.get("slot") == "pact_boon")
    ok("re-picking to a non-rune boon drops both the runes grant and the granted_runes children",
       "runes" not in (pe.get("grants") or {}) and not pe.get("granted_runes"),
       (pe.get("grants"), pe.get("granted_runes")))

    # ---- (c) the closed slice-1 gap: the CHARGEN cg:choice re-pick clears stale granted_maneuvers ----
    gapi = builder_api.BuilderAPI("runt", CATPATHS)
    cc = next(c for c in gapi.ledger["chargen"]["class_choices"] if c["slot"] == "pact_boon")
    ok("precondition: Runt's L1 chargen boon carries granted_maneuvers (Cleave/Pathcarver)",
       cc.get("granted_maneuvers") == ["Cleave", "Pathcarver"], cc.get("granted_maneuvers"))
    l1boon = next(d for d in st(gapi)["decisions"] if d.get("slot") == "pact_boon" and d.get("level") == 1)
    gapi.set_decision(l1boon["id"], "Pact Familiar")
    cc = next(c for c in gapi.ledger["chargen"]["class_choices"] if c["slot"] == "pact_boon")
    ok("closed slice-1 gap: re-picking the CHARGEN boon clears the old boon's granted_maneuvers (symmetric with the level path)",
       not cc.get("granted_maneuvers") and not cc.get("grants"),
       (cc.get("granted_maneuvers"), cc.get("grants")))

    # ---- (d) surgical boundary + built-page furniture ----
    # Slice 2 kept plain spells/maneuvers on the flat-pool model (NOT in GRANT_CHILD_SLOTS). Slice 5
    # then added ONE deliberate, opt-in exception: a TAG-CONSTRAINED spell grant (Eldritch's Psychic
    # slot) materialises a single spell child via a separate gated path, without adding 'spells' to
    # GRANT_CHILD_SLOTS. So the structural boundary is intact and Runt has exactly one GC# row.
    base = st(builder_api.BuilderAPI("runt", CATPATHS))
    gc_ids = sorted(str(d.get("id")) for d in base["decisions"] if str(d.get("id")).startswith("GC#"))
    ok("surgical boundary intact: plain 'spells'/'maneuvers' are NOT in GRANT_CHILD_SLOTS (flat-pool model kept)",
       "spells" not in builder_api.GRANT_CHILD_SLOTS and "maneuvers" not in builder_api.GRANT_CHILD_SLOTS,
       dict(builder_api.GRANT_CHILD_SLOTS))
    # grants-only (2026-07-19): pact-boon maneuvers ("N of your choice") ARE editable grant-children
    # via the dedicated pact_boon branch, but flat-pool grants (Martial Expansion {maneuvers:2}, the
    # L2 Slam/Body Block/Throw Creature picks) are NOT - they stay flat. So Runt's GC rows = the
    # slice-5 Psychic spell + his 4 pact-boon maneuvers, and nothing else.
    ok("pact-boon maneuvers are GC children; flat-pool grants (Martial Expansion) stay flat",
       set(gc_ids) == {"GC#L3:0#spells#0", "GC#cg:0#maneuvers#0", "GC#cg:0#maneuvers#1",
                       "GC#L4:1#maneuvers#0", "GC#L4:1#maneuvers#1"},
       gc_ids)
    ok("the page's BuilderAPI glue carries the slice-2 backbone methods (glue is base64-baked; blob==source is checked in section 1)",
       all(hasattr(builder_api.BuilderAPI, m) for m in ("_grant_children", "_apply_grants", "_set_grant_child"))
       and hasattr(builder_api, "GRANT_CHILD_SLOTS"))


# ---------------------------------------------------------------- (14) FR-8 slice 3 Rune Knight
def check_slice3():
    UND = "(undecided)"
    print()
    print("## (14) FR-8 slice 3: Rune Knight subclass grants 2 runes (Xanwyn, real catalog)")

    # ---- (a) the real Spellblade rune catalog populates the 'rune' picker ----
    xapi = builder_api.BuilderAPI("xanwyn", CATPATHS)
    rune_opts = xapi._options_for("rune")
    ok("Spellblade ccat['runes'] populates _options_for('rune') with the 6 canonical runes",
       {o["name"] for o in rune_opts} == {"Earth", "Flame", "Frost", "Lightning", "Water", "Wind"},
       [o["name"] for o in rune_opts])
    ok("Rune Knight carries the runes:2 grant in the catalog subclass_grants side-map",
       (xapi.ccat.get("subclass_grants") or {}).get("Rune Knight", {}).get("grants") == {"runes": 2},
       (xapi.ccat.get("subclass_grants") or {}).get("Rune Knight"))

    # ---- (b) Xanwyn's L3 subclass is now a real editable picker (de-bundled from the name) ----
    s = st(xapi)
    subdec = next(d for d in s["decisions"] if d.get("slot") == "subclass")
    ok("Xanwyn's subclass row is a clean editable picker reading 'Rune Knight' (not fixed composite text)",
       subdec["widget"] == "picker" and subdec["editable"] and subdec["current"] == "Rune Knight"
       and not subdec.get("replaceable"),
       (subdec["widget"], subdec.get("current"), subdec.get("replaceable")))
    subref = str(subdec["id"])   # e.g. 'L3:0'

    # ---- (c) 2 rune child pickers materialise keyed to the subclass, reading Flame + Water ----
    kids = [d for d in s["decisions"] if str(d.get("id")).startswith("GC#%s#runes#" % subref)]
    ok("the {runes:2} subclass grant materialises 2 'rune' child pickers keyed to the subclass row",
       len(kids) == 2 and all(d["slot"] == "rune" and d["widget"] == "picker" and d["editable"] for d in kids),
       [(d["id"], d.get("current")) for d in kids])
    ok("the rune children read Xanwyn's granted_runes [Flame, Water], 6 options each",
       [d["current"] for d in kids] == ["Flame", "Water"] and all(len(d["options"]) == 6 for d in kids),
       [(d["current"], len(d["options"])) for d in kids])
    ok("both runes decided -> no rune completeness problem and Xanwyn's build stays clean",
       not any("rune undecided" in p for p in s["builder_problems"]) and s["catalog_problems"] == [],
       (s["builder_problems"], s["catalog_problems"]))

    # ---- (d) re-picking the subclass rebuilds/clears the rune child-slots (_apply_grants wiring) ----
    xapi.set_decision(subref, "Paladin")                       # a non-rune subclass
    e = next(e for lvl in xapi.ledger["levels"] for e in xapi.ledger["levels"][lvl] if e.get("slot") == "subclass")
    ok("re-picking to a non-rune subclass (Paladin) drops the runes grant and the granted_runes children",
       "runes" not in (e.get("grants") or {}) and not e.get("granted_runes")
       and not any(str(d.get("id")).startswith("GC#%s#runes#" % subref) for d in st(xapi)["decisions"]),
       (e.get("grants"), e.get("granted_runes")))
    xapi.set_decision(subref, "Rune Knight")                   # back to the rune-granting subclass
    e = next(e for lvl in xapi.ledger["levels"] for e in xapi.ledger["levels"][lvl] if e.get("slot") == "subclass")
    ok("re-picking Rune Knight rebuilds 2 undecided rune slots (all UNDECIDED on a real option change)",
       e.get("grants") == {"runes": 2} and e.get("granted_runes") == [UND, UND],
       (e.get("grants"), e.get("granted_runes")))
    s2 = st(xapi)
    kids2 = [d for d in s2["decisions"] if str(d.get("id")).startswith("GC#%s#runes#" % subref)]
    ok("2 fresh rune child pickers render + surface as builder problems until decided",
       len(kids2) == 2 and all(d["current"] == UND for d in kids2)
       and any("rune undecided" in p for p in s2["builder_problems"]),
       ([d["current"] for d in kids2], [p for p in s2["builder_problems"] if "rune" in p]))
    xapi.set_decision(kids2[0]["id"], "Frost")
    e = next(e for lvl in xapi.ledger["levels"] for e in xapi.ledger["levels"][lvl] if e.get("slot") == "subclass")
    ok("editing a rune child writes into the subclass's granted_runes (structural GC# link)",
       e.get("granted_runes") == ["Frost", UND], e.get("granted_runes"))


# ---------------------------------------------------------------- (15) FR-8 slice 4 Meta Magic talent
def check_slice4():
    UND = "(undecided)"
    print()
    print("## (15) FR-8 slice 4: Meta Magic talent grants 2 metamagic (Scaletrix, real cat-level catalog)")

    # ---- (a) the cat-level metamagic catalog populates the 'metamagic' picker (cross-class) ----
    sapi = builder_api.BuilderAPI("scaletrix", CATPATHS)
    mm_opts = sapi._options_for("metamagic")
    ok("cat-level metamagic catalog populates _options_for('metamagic') with the 6 canonical options",
       {o["name"] for o in mm_opts} == {"Careful Spell", "Distant Spell", "Quickened Spell",
                                        "Subtle Spell", "Transmuted Spell", "Vicious Spell"},
       [o["name"] for o in mm_opts])
    _mm_feat = next((t for t in sapi.cat["talents"]["mc_features"] if t["name"] == "Meta Magic"), {})
    ok("Meta Magic carries the metamagic:2 grant in the talents catalog mc_features",
       _mm_feat.get("grants") == {"metamagic": 2}, _mm_feat.get("grants"))

    # ---- (b) Scaletrix's L4 Meta Magic talent is a clean editable picker (de-bundled from the name) ----
    s = st(sapi)
    tdec = next(d for d in s["decisions"] if d.get("slot") == "talent" and d.get("current") == "Meta Magic")
    ok("Scaletrix's Meta Magic talent row is a clean editable picker reading 'Meta Magic' (not fixed composite text)",
       tdec["widget"] == "picker" and tdec["editable"] and tdec["current"] == "Meta Magic"
       and not tdec.get("replaceable"),
       (tdec["widget"], tdec.get("current"), tdec.get("replaceable")))
    tref = str(tdec["id"])   # e.g. 'L4:0'
    _lvl, _idx = int(tref[1:].split(":")[0]), int(tref[1:].split(":")[1])

    # ---- (c) 2 metamagic child pickers materialise keyed to the talent, reading Quickened + Vicious ----
    kids = [d for d in s["decisions"] if str(d.get("id")).startswith("GC#%s#metamagic#" % tref)]
    ok("the {metamagic:2} talent grant materialises 2 'metamagic' child pickers keyed to the talent row",
       len(kids) == 2 and all(d["slot"] == "metamagic" and d["widget"] == "picker" and d["editable"] for d in kids),
       [(d["id"], d.get("current")) for d in kids])
    ok("the metamagic children read Scaletrix's granted_metamagic [Quickened Spell, Vicious Spell], 6 options each",
       [d["current"] for d in kids] == ["Quickened Spell", "Vicious Spell"] and all(len(d["options"]) == 6 for d in kids),
       [(d["current"], len(d["options"])) for d in kids])
    ok("both metamagic decided -> no metamagic completeness problem and Scaletrix's build stays clean",
       not any("metamagic undecided" in p for p in s["builder_problems"]) and s["catalog_problems"] == [],
       (s["builder_problems"], s["catalog_problems"]))

    # ---- (d) re-picking the talent rebuilds/clears the metamagic child-slots (_apply_grants wiring) ----
    sapi.set_decision(tref, "Life Tap")                        # a non-metamagic talent (mc_feature, no grants)
    e = sapi.ledger["levels"][_lvl][_idx]
    ok("re-picking to a non-metamagic talent (Life Tap) drops the metamagic grant and the granted_metamagic children",
       "metamagic" not in (e.get("grants") or {}) and not e.get("granted_metamagic")
       and not any(str(d.get("id")).startswith("GC#%s#metamagic#" % tref) for d in st(sapi)["decisions"]),
       (e.get("grants"), e.get("granted_metamagic")))
    sapi.set_decision(tref, "Meta Magic")                      # back to the metamagic-granting talent
    e = sapi.ledger["levels"][_lvl][_idx]
    ok("re-picking Meta Magic rebuilds 2 undecided metamagic slots (all UNDECIDED on a real option change)",
       e.get("grants") == {"metamagic": 2} and e.get("granted_metamagic") == [UND, UND],
       (e.get("grants"), e.get("granted_metamagic")))
    s2 = st(sapi)
    kids2 = [d for d in s2["decisions"] if str(d.get("id")).startswith("GC#%s#metamagic#" % tref)]
    ok("2 fresh metamagic child pickers render + surface as builder problems until decided",
       len(kids2) == 2 and all(d["current"] == UND for d in kids2)
       and any("metamagic undecided" in p for p in s2["builder_problems"]),
       ([d["current"] for d in kids2], [p for p in s2["builder_problems"] if "metamagic" in p]))
    sapi.set_decision(kids2[0]["id"], "Subtle Spell")
    e = sapi.ledger["levels"][_lvl][_idx]
    ok("editing a metamagic child writes into the talent's granted_metamagic (structural GC# link)",
       e.get("granted_metamagic") == ["Subtle Spell", UND], e.get("granted_metamagic"))


# ---------------------------------------------------------------- (16) FR-8 slice 5 Eldritch Psychic spell
def check_slice5():
    UND = "(undecided)"
    print()
    print("## (16) FR-8 slice 5: Eldritch constrained Psychic-spell grant (Runt; meets FR-13)")

    rapi = builder_api.BuilderAPI("runt", CATPATHS)

    # ---- (a) the constrained picker offers ONLY Psychic-tag spells (tag sourced from subclass_grants) ----
    sub_e = next(e for lvl in rapi.ledger["levels"] for e in rapi.ledger["levels"][lvl]
                if e.get("slot") == "subclass")
    ok("Eldritch's spell grant is tag-constrained: _spell_grant_tag -> 'Psychic' (from subclass_grants spell_access)",
       rapi._spell_grant_tag(sub_e) == "Psychic", rapi._spell_grant_tag(sub_e))
    topts = rapi._options_for("spell_tagged")
    tnames = {o["name"] for o in topts}
    meta = rapi.meta
    ok("the constrained picker offers ONLY Psychic-tag spells",
       topts and all("Psychic" in (meta.get(o["name"]) or {}).get("tags", []) for o in topts),
       [o["name"] for o in topts if "Psychic" not in (meta.get(o["name"]) or {}).get("tags", [])][:5])
    ok("Tendrils from Beyond is offered (Psychic tag; its Conjuration school is NOT chosen)",
       "Tendrils from Beyond" in tnames and "Conjuration" not in (rapi.ledger["chargen"].get("spell_schools") or []),
       ("Tendrils from Beyond" in tnames))
    ok("a non-Psychic accessible spell (Lightning Bolt, chosen Elemental school) is NOT offered in the constrained picker",
       "Lightning Bolt" not in tnames, "Lightning Bolt" in tnames)

    # ---- (b) Runt's L3 subclass row is a clean editable picker ----
    sst = st(rapi)
    subdec = next(d for d in sst["decisions"] if d.get("slot") == "subclass")
    ok("Runt's subclass row is a clean editable picker reading 'Eldritch'",
       subdec["widget"] == "picker" and subdec["editable"] and subdec["current"] == "Eldritch",
       (subdec["widget"], subdec.get("current")))
    subref = str(subdec["id"])   # e.g. 'L3:0'

    # ---- (c) the {spells:1} grant materialises exactly ONE 'spell_tagged' child, reading Tendrils ----
    kids = [d for d in sst["decisions"] if str(d.get("id")).startswith("GC#%s#spells#" % subref)]
    ok("the {spells:1} tag-constrained grant materialises exactly 1 'spell_tagged' child picker keyed to the subclass",
       len(kids) == 1 and kids[0]["slot"] == "spell_tagged" and kids[0]["widget"] == "picker" and kids[0]["editable"],
       [(d["id"], d["slot"], d.get("current")) for d in kids])
    ok("the spell child reads Runt's granted_spells [Tendrils from Beyond] and offers only Psychic spells",
       kids and kids[0]["current"] == "Tendrils from Beyond"
       and all("Psychic" in (meta.get(o["name"]) or {}).get("tags", []) for o in kids[0]["options"]),
       kids[0].get("current") if kids else None)
    ok("both the spell grant is decided -> no 'spell (tag) undecided' problem and Runt's build stays clean",
       not any("spell (tag) undecided" in p for p in sst["builder_problems"]) and sst["catalog_problems"] == [],
       (sst["builder_problems"], sst["catalog_problems"]))

    # ---- (d) consume-not-stack: Tendrils is NOT double-offered in the flat spell pickers (FR-7 dedup) ----
    flat_spell_opts = [d for d in sst["decisions"] if d.get("slot") == "spell" and d["widget"] == "picker"]
    ok("the granted Psychic spell is hidden from the flat spell pickers (no double-pick across slots)",
       flat_spell_opts and all("Tendrils from Beyond" not in {o["name"] for o in d["options"]} for d in flat_spell_opts),
       "hidden")

    # ---- (e) FR-13a boundary: a plain {spells:N} grant (NO spell_access) stays flat-pool; a grant
    #     that carries a spell_access SOURCE now gets source-constrained children (Scaletrix Innate
    #     Power). Tag-constrained subclass grants keep the spell_tagged path (Runt, above).
    #     BUG-30 (2026-07-27) moved bonan OFF this list: his MC Bard talent carries spell_access.any,
    #     so it is now a child-bearing parent too (asserted just below). Tanrielle's MC Warlock Pact
    #     Spell and Xanwyn's Spell School Initiate carry no spell_access and hold the flat boundary.
    for other in ("tanrielle", "xanwyn"):
        oapi = builder_api.BuilderAPI(other, CATPATHS)
        os_ = st(oapi)
        ok("%s's flat {spells:N} grant gets NO spell child slot (no spell_access -> flat-pool model)" % other,
           not any("#spells#" in str(d.get("id")) for d in os_["decisions"]),
           [d.get("id") for d in os_["decisions"] if "#spells#" in str(d.get("id"))])
    # FR-13a positive case: Scaletrix's Innate Power (spell_access source Arcane) materialises 2
    # source-constrained 'spell_sourced' children, Arcane-filtered, reading his granted_spells.
    scapi = builder_api.BuilderAPI("scaletrix", CATPATHS)
    sca = st(scapi)
    scakids = [d for d in sca["decisions"]
               if d.get("slot") == "spell_sourced" and str(d.get("id")).startswith("GC#L2:0#spells#")]
    ok("Scaletrix Innate Power: 2 source-constrained spell_sourced children (Arcane-only), read granted_spells",
       len(scakids) == 2
       and {d.get("current") for d in scakids} == {"Disintegrating Beam", "Gravity Well"}
       and all(d["widget"] == "picker" and d.get("editable") for d in scakids)
       and all(all("Arcane" in (meta.get(o["name"]) or {}).get("sources", []) or o["name"] == d.get("current")
                   for o in d["options"]) for d in scakids),
       [(d.get("current"), len(d.get("options") or [])) for d in scakids])

    # ---- FR-13a SLICE 2 -------------------------------------------------------------------------
    # (a) Command is childed UNDER the Fiendish Magic ancestry trait (Arcane + Elemental/Enchantment
    #     source-constrained), not a flat chargen spell. Its GC# id encodes the ancestry-trait parent
    #     (cgtrait:<i>), and it is NOT in the flat chargen spells list.
    cmdkids = [d for d in sca["decisions"]
               if d.get("slot") == "spell_sourced" and str(d.get("id")).startswith("GC#cgtrait:")]
    ok("slice2(a): Command is an ancestry-trait grant-child (GC#cgtrait:...), source-constrained, not flat",
       len(cmdkids) == 1 and cmdkids[0]["current"] == "Command"
       and cmdkids[0]["widget"] == "picker" and cmdkids[0].get("editable")
       and cmdkids[0].get("current_group") is None  # not resolved via the ancestry-trait alias path
       and all((meta.get(o["name"]) or {}).get("school") in ("Elemental", "Enchantment")
               or o["name"] == "Command" for o in cmdkids[0]["options"])
       and "Command" not in (scapi.ledger["chargen"].get("spells") or []),
       (cmdkids[0]["current"], len(cmdkids[0]["options"])) if cmdkids else None)
    ok("slice2(a): the ancestry-trait Command child writes into the trait's granted_spells (structural GC# link)",
       scapi.ledger["chargen"]["ancestry_traits"][1].get("granted_spells") == ["Command"],
       scapi.ledger["chargen"]["ancestry_traits"][1].get("granted_spells"))

    # (b) the two Spellcaster-path spells (Dispel Magic, Telekinesis) carry a canonical source, so their
    #     flat pickers are Arcane-source-filtered - NO "(current, off-list)" option any more.
    def _offlist(dec):
        return any("off-list" in (o.get("label") or "") for o in (dec.get("options") or []))
    flatarc = {d["current"]: d for d in sca["decisions"]
               if d.get("slot") == "spell" and d.get("current") in ("Dispel Magic", "Telekinesis")}
    ok("slice2(b): Dispel Magic + Telekinesis are source-filtered flat pickers with NO off-list option",
       set(flatarc) == {"Dispel Magic", "Telekinesis"}
       and not any(_offlist(d) for d in flatarc.values())
       and all(all("Arcane" in (meta.get(o["name"]) or {}).get("sources", []) for o in d["options"])
               for d in flatarc.values()),
       {k: (len(d["options"]), _offlist(d)) for k, d in flatarc.items()})
    ok("slice2(b): a FREE-TEXT source (minimus 'Spellcaster path +1 spell') is NOT treated as canonical",
       True in [any(d.get("slot") == "spell" for d in
                    st(builder_api.BuilderAPI("minimus", CATPATHS))["decisions"])],
       "minimus flat spells still render (Commander model none)")
    # regression: no Scaletrix spell picker anywhere still shows an off-list option (all 3 tags cleared)
    ok("slice2: NO Scaletrix spell/spell_sourced picker carries an off-list option (all 3 Arcane tags cleared)",
       not any(_offlist(d) for d in sca["decisions"]
               if d.get("slot") in ("spell", "spell_sourced")),
       [d.get("current") for d in sca["decisions"]
        if d.get("slot") in ("spell", "spell_sourced") and _offlist(d)])

    # (c) the Sorcerous Origin sub-choice is an EXPLICIT editable node (source_choice) whose value
    #     drives the Innate Power children's source filter; re-picking it resets + re-filters them.
    sonode = [d for d in sca["decisions"] if d.get("slot") == "source_choice"]
    ok("slice2(c): explicit Sorcerous Origin node (source_choice), current Arcane, 3 source options",
       len(sonode) == 1 and sonode[0]["current"] == "Arcane"
       and sonode[0]["widget"] == "picker" and sonode[0].get("editable")
       and {o["name"] for o in sonode[0]["options"]} == {"Arcane", "Divine", "Primal"},
       (sonode[0]["current"], [o["name"] for o in sonode[0]["options"]]) if sonode else None)
    scapi.set_decision(sonode[0]["id"], "Primal")
    s3 = st(scapi)
    ip3 = [d for d in s3["decisions"] if str(d.get("id")).startswith("GC#L2:0#spells#")]
    ok("slice2(c): re-picking the origin to Primal RESETS the 2 Innate Power children + re-filters to Primal",
       scapi.ledger["levels"][2][0].get("sorcerous_origin", {}).get("chosen_source") == "Primal"
       and all(d["current"] == UND for d in ip3)
       and all(all("Primal" in (meta.get(o["name"]) or {}).get("sources", []) for o in d["options"]) for d in ip3),
       (scapi.ledger["levels"][2][0].get("sorcerous_origin"), [d["current"] for d in ip3]))

    # ---- (f) re-picking the subclass rebuilds/clears the constrained spell slot (_apply_grants wiring) ----
    rapi.set_decision(subref, "Fey")                            # a non-tag-constrained subclass (no spell_access)
    e = next(e for lvl in rapi.ledger["levels"] for e in rapi.ledger["levels"][lvl] if e.get("slot") == "subclass")
    ok("re-picking to a non-tag subclass (Fey) drops the spells grant and the granted_spells child",
       "spells" not in (e.get("grants") or {}) and not e.get("granted_spells")
       and not any(str(d.get("id")).startswith("GC#%s#spells#" % subref) for d in st(rapi)["decisions"]),
       (e.get("grants"), e.get("granted_spells")))
    rapi.set_decision(subref, "Eldritch")                       # back to the tag-constrained subclass
    e = next(e for lvl in rapi.ledger["levels"] for e in rapi.ledger["levels"][lvl] if e.get("slot") == "subclass")
    ok("re-picking Eldritch rebuilds 1 undecided Psychic-spell slot (UNDECIDED on a real change)",
       e.get("grants") == {"spells": 1} and e.get("granted_spells") == [UND],
       (e.get("grants"), e.get("granted_spells")))
    s2 = st(rapi)
    kids2 = [d for d in s2["decisions"] if str(d.get("id")).startswith("GC#%s#spells#" % subref)]
    ok("1 fresh Psychic-spell child picker renders + surfaces as a builder problem until decided",
       len(kids2) == 1 and kids2[0]["current"] == UND
       and any("spell (tag) undecided" in p for p in s2["builder_problems"]),
       ([d["current"] for d in kids2], [p for p in s2["builder_problems"] if "spell (tag)" in p]))
    rapi.set_decision(kids2[0]["id"], "Psychic Wave")
    e = next(e for lvl in rapi.ledger["levels"] for e in rapi.ledger["levels"][lvl] if e.get("slot") == "subclass")
    ok("editing the Psychic-spell child writes into the subclass's granted_spells (structural GC# link)",
       e.get("granted_spells") == ["Psychic Wave"], e.get("granted_spells"))


def check_fr3():
    print("## (18) FR-3: Add Planned Level for every PC (editable plans, no ledger reshape) + undo")
    # minimus has NO hand-authored plan: the plan button + editable plans must work for it.
    api = builder_api.BuilderAPI("minimus", CATPATHS)
    s = st(api)
    ok("minimus (no plan) can add a planned level: can_plan, plan_level 5, no undo yet",
       s["can_plan"] and s["plan_level"] == 5 and s["undo_level"] is None,
       (s["can_plan"], s["plan_level"], s["undo_level"]))
    ok("minimus is clean at rest before planning", clean(s), probs(s))
    # add a PLANNED level: appends L5 WITHOUT advancing current_level
    s = json.loads(api.add_planned_level())
    ok("add_planned_level appends L5 as a plan and does NOT advance current_level",
       s["level"] == 4 and s["planned"] == [5], (s["level"], s["planned"]))
    ok("the undo link labels the real added level (L5) and does not vanish",
       s["undo_level"] == 5, s["undo_level"])
    ok("planning again is still offered, now at L6", s["can_plan"] and s["plan_level"] == 6,
       (s["can_plan"], s["plan_level"]))
    l5 = [d for d in s["decisions"] if d["level"] == 5]
    ok("the generated L5 rows are all plan rows (dashed group)", l5 and all(d["plan"] for d in l5), len(l5))
    editable = [d for d in l5 if d["editable"] and d["widget"] == "picker"]
    ok("a builder-generated plan is EDITABLE (spine slots are real pickers you can fill in)",
       len(editable) >= 1 and all(d["slot"] in ("attribute", "talent", "path", "subclass",
                                                 "spell", "maneuver", "ancestry_trait",
                                                 "skill", "trade") for d in editable),
       [(d["slot"], d["widget"]) for d in l5])
    # FR-3 slice 2 / FR-17 changed the plan contract for the POINT-BUY carriers (skills AND trades):
    # a plan is engine/catalog clean and raises no OTHER builder problems, but its enforced skill/trade
    # point budgets flag until spent.
    def only_pointbuy(b):
        return all(("planned skill" in p or "planned trade" in p) for p in b)
    e0, c0, b0 = probs(s)
    ok("an added plan is engine/catalog clean and raises only skill/trade point-budget problems",
       not e0 and not c0 and only_pointbuy(b0), probs(s))
    # editing a plan pick writes it and the row stays an editable picker (use a non-point-buy spine row)
    row = [d for d in editable if d["slot"] not in ("skill", "trade")][0]
    val = row["options"][0]["name"]
    s = json.loads(api.set_decision(row["id"], val))
    r2 = find_dec(s, lambda d: d["id"] == row["id"])
    ok("editing a plan pick writes the value and the row stays an editable picker",
       r2 and r2["current"] == val and r2["editable"] and r2["widget"] == "picker",
       (r2 or {}).get("current"))
    e1, c1, b1 = probs(s)
    ok("filling a non-point-buy plan pick keeps engine/catalog clean (only skill/trade budgets remain)",
       not e1 and not c1 and only_pointbuy(b1), probs(s))
    # a second planned level stacks; undo unwinds L6 then L5 (undo link never wrongly gone)
    s = json.loads(api.add_planned_level())
    ok("a second planned level stacks to L6 and the undo link now says L6",
       s["planned"] == [5, 6] and s["undo_level"] == 6, (s["planned"], s["undo_level"]))
    s = json.loads(api.undo_add_level())
    ok("first undo removes L6, undo link falls back to L5 (not gone)",
       s["planned"] == [5] and s["undo_level"] == 5, (s["planned"], s["undo_level"]))
    s = json.loads(api.undo_add_level())
    ok("second undo removes L5, planning is back to the baseline (undo link gone)",
       s["planned"] == [] and s["undo_level"] is None and s["level"] == 4,
       (s["planned"], s["undo_level"], s["level"]))
    # a planned level survives export + reload and stays editable (plan_edit persists)
    api2 = builder_api.BuilderAPI("minimus", CATPATHS)
    api2.add_planned_level()
    y = api2.export_yaml()
    ok("an exported plan carries the plan_edit marker", "plan_edit" in y, None)
    api3 = builder_api.BuilderAPI("minimus-x", CATPATHS, ledger_text=y)
    s3 = st(api3)
    ok("a re-loaded plan is still editable (plan_edit round-trips)",
       any(d["level"] == 5 and d["editable"] for d in s3["decisions"]),
       [(d["slot"], d["editable"]) for d in s3["decisions"] if d["level"] == 5])
    # Tanrielle's HAND-AUTHORED locked plan must stay a read-only preview (the key distinction)
    ta = builder_api.BuilderAPI("tanrielle", CATPATHS)
    s = st(ta)
    tplan = [d for d in s["decisions"] if d["level"] in (5, 6)]
    ok("Tanrielle's hand-authored locked plan L5/L6 stays read-only (no editable rows)",
       bool(tplan) and not any(d["editable"] for d in tplan) and all(d["plan"] for d in tplan),
       [(d["level"], d["slot"], d["editable"]) for d in tplan])
    ok("Tanrielle can still add a plan ABOVE her locked plan (stacks at L7)",
       s["can_plan"] and s["plan_level"] == 7, (s["can_plan"], s["plan_level"]))
    s = json.loads(ta.add_planned_level())
    ok("adding a plan for Tanrielle appends L7 (undo link L7), locked L5/L6 untouched",
       s["planned"] == [5, 6, 7] and s["undo_level"] == 7, (s["planned"], s["undo_level"]))
    # advance vs plan interplay: a planned level can later be PROMOTED, and undo restores it as a plan
    mi = builder_api.BuilderAPI("minimus", CATPATHS)
    mi.add_planned_level()                       # L5 becomes a plan
    s = json.loads(mi.add_level())               # add_level now PROMOTES that plan (new == cur+1 == 5)
    ok("a planned level can be promoted by Add level (current -> 5, plan consumed)",
       s["level"] == 5 and s["planned"] == [], (s["level"], s["planned"]))
    s = json.loads(mi.undo_add_level())
    ok("undo of the promote restores L5 back as a plan (not deleted)",
       s["level"] == 4 and s["planned"] == [5], (s["level"], s["planned"]))
    # the L10 ceiling: no planning past L10
    cap = builder_api.BuilderAPI("minimus", CATPATHS)
    for _ in range(8):
        cap.add_planned_level()
    s = st(cap)
    ok("planning stops at the L10 ceiling (no plan level above 10)",
       max(s["planned"]) == 10 and not s["can_plan"] and s["plan_level"] is None,
       (s["planned"], s["can_plan"], s["plan_level"]))


def check_fr3_slice2():
    print("\n## (19) FR-3 slice 2: planned levels carry their own skill picks "
          "(Hybrid, FR-8 backbone, enforced)")

    def skl(s, level):
        return [d for d in s["decisions"] if d["slot"] == "skill" and d["level"] == level]

    def onames(dec):
        return [o["name"] for o in dec.get("options", [])]

    # (a) the six baselines are byte-identical at rest: no ledger carries a skills carrier, so no
    # granted_skills, so every new code path is a no-op and no character gains a problem.
    allclean = True
    for c in builder_build.CHARS:
        api = builder_api.BuilderAPI(c, CATPATHS)
        s = st(api)
        if any("planned skill" in p for p in s["builder_problems"]) \
                or any("planned skill" in p for p in s["catalog_problems"]) \
                or any(d["slot"] == "skills" for d in s["decisions"]):
            allclean = False
    ok("no ledger has a skills carrier at rest; all six baselines stay clean (Hybrid: no reshape)", allclean)

    # (b) a plan level's spine skill_points materialise N editable skill child-slots on a carrier.
    api = builder_api.BuilderAPI("minimus", CATPATHS)   # Commander L4; L5 grants 2 SP. Aggregate
    # holds 5 Novice skills since the CH-1 sheet fill (2026-07-18), so options mix add-new + raises.
    s = json.loads(api.add_planned_level())
    carrier = [d for d in s["decisions"] if d["slot"] == "skills" and d["level"] == 5]
    sk5 = skl(s, 5)
    ok("the L5 skill-point budget materialises a 'skills' carrier + 2 editable skill child slots",
       len(carrier) == 1 and len(sk5) == 2 and all(d["editable"] and d["widget"] == "picker" for d in sk5),
       (len(carrier), len(sk5)))
    ids = [d["id"] for d in sk5]
    ok("skill child ids are keyed structurally to the carrier parent (GC#L5:...#skills#k)",
       all(i.startswith("GC#L5:") and "#skills#" in i for i in ids), ids)

    # (c) ENFORCE (Darryl's call): unspent planned skill points flag as ONE aggregate problem
    # (points-based since FR-17, because a cap+ pick costs 2 points).
    bp = [p for p in s["builder_problems"] if "planned skill" in p]
    ok("unspent planned skills flag as an aggregate point-budget problem (enforced, not speculative)",
       len(bp) == 1 and "2 of 2" in bp[0] and not s["problems"] and not s["catalog_problems"], probs(s))

    # (d) options against the real aggregate: an unheld skill is offered add-new at Novice; a
    # held Novice skill is offered as a one-step raise to Adept (L5 cap Adept); a held skill is
    # never re-offered at its current tier.
    o0 = onames(sk5[0])
    ok("an unheld skill is offered add-new at Novice ('Stealth: Novice')",
       "Stealth: Novice" in o0, o0[:6])
    ok("a held Novice skill is offered as a one-step raise ('Acrobatics: Adept'), not at Novice",
       "Acrobatics: Adept" in o0 and "Acrobatics: Novice" not in o0,
       [x for x in o0 if x.startswith("Acrobatics")])

    # (e) sibling distinctness: a skill picked in one slot is hidden from the other slot of the level.
    s = json.loads(api.set_decision(sk5[0]["id"], "Stealth: Novice"))
    sk5 = skl(s, 5)
    other = [d for d in sk5 if d["id"] != ids[0]][0]
    ok("a skill chosen in one slot is hidden from the sibling slot (points go to distinct skills)",
       not any(x.startswith("Stealth") for x in onames(other)), onames(other)[:4])
    ok("spending one of two skill points reports '1 of 2 unspent'",
       any("planned skills: 1 of 2" in p for p in s["builder_problems"]), s["builder_problems"])
    s = json.loads(api.set_decision(other["id"], onames(other)[0]))
    ok("filling both planned skills clears the skill budget problem",
       not any("planned skill" in p for p in s["builder_problems"]), probs(s))

    # (f) RAISE + carried Mastery-Limit raise, on Tanrielle. Her Awareness is Adept AND carries a
    # skill_point_purchase limit raise, so the ceiling for Awareness is +1: at L8 (level cap Adept)
    # she can raise Awareness to Expert WITHOUT a new cap+ (the purchase carries). A skill with no
    # carried raise (Athletics, Novice) is capped normally.
    ta = builder_api.BuilderAPI("tanrielle", CATPATHS)
    for _ in range(4):                                  # L7(0 SP), L8(1 SP), L9(0), L10(2 SP)
        ta.add_planned_level()
    s = st(ta)
    o8 = onames(skl(s, 8)[0])
    ok("at L8 a carried Mastery-Limit raise lets Awareness go Adept->Expert (no new cap+ needed)",
       "Awareness: Expert" in o8, [x for x in o8 if x.startswith("Awareness")])
    ok("at L8 (cap Adept) a skill with no carried raise stops at Adept (Athletics: Expert not offered)",
       "Athletics: Adept" in o8 and "Athletics: Expert" not in o8,
       [x for x in o8 if x.startswith("Athletics")])

    # (g) running state chains across plan levels (a lower plan raise feeds a higher level's options).
    s = json.loads(ta.set_decision(skl(s, 8)[0]["id"], "Athletics: Adept"))
    o10b = onames(skl(s, 10)[0])
    ok("a raise at L8 feeds L10's running state (Athletics: Expert now offered, Adept no longer)",
       "Athletics: Expert" in o10b and "Athletics: Adept" not in o10b, [x for x in o10b if x.startswith("Athletics")])

    # (h) Tanrielle's HAND-AUTHORED locked plan skill rows stay read-only (the Hybrid boundary).
    tplan_sk = [d for d in st(builder_api.BuilderAPI("tanrielle", CATPATHS))["decisions"]
                if d["slot"] == "skill" and d["level"] in (5, 6)]
    ok("Tanrielle's hand-authored L5/L6 skill rows stay read-only (locked, not builder-generated)",
       bool(tplan_sk) and not any(d["editable"] for d in tplan_sk),
       [(d["level"], d["editable"]) for d in tplan_sk])

    # (i) export/reload: granted_skills round-trips and the slots stay editable.
    ap = builder_api.BuilderAPI("minimus", CATPATHS)
    ap.add_planned_level()
    ap.set_decision(skl(st(ap), 5)[0]["id"], "Stealth: Novice")
    y = ap.export_yaml()
    ok("an exported plan carries granted_skills", "granted_skills" in y, None)
    ar = builder_api.BuilderAPI("minimus-x", CATPATHS, ledger_text=y)
    sr = st(ar)
    keep = [d for d in skl(sr, 5) if d.get("current") == "Stealth: Novice"]
    ok("a reloaded plan skill persists and stays editable (round-trips)",
       bool(keep) and all(d["editable"] for d in skl(sr, 5)), None)

    # (j) legality DEFENCE: a stale illegal value (2-step jump / over-cap) is caught by catalog_problems.
    dfn = builder_api.BuilderAPI("minimus", CATPATHS)
    dfn.add_planned_level()
    car = [e for e in dfn.ledger["levels"][5] if e.get("slot") == "skills"][0]
    car["granted_skills"] = ["Acrobatics: Expert", "(undecided)"]   # Novice->Expert is 2 steps AND > cap Adept
    sd = st(dfn)
    cp = [p for p in sd["catalog_problems"] if "planned skill" in p]
    ok("a stale illegal planned skill (2-step + over-cap) is flagged by catalog_problems",
       any("single step" in p for p in cp) and any("mastery limit" in p for p in cp), cp)

    # (k) HYBRID surgical boundary: a real advance (add_level) does NOT create a skills carrier;
    # skills stay in the flat aggregate for completed/current levels.
    adv = builder_api.BuilderAPI("minimus", CATPATHS)
    adv.add_level()                                    # advance to L5 (real, not a plan)
    sa = st(adv)
    ok("a REAL advance (add_level) creates no skills carrier - completed levels keep the flat aggregate",
       sa["level"] == 5 and not any(d["slot"] == "skills" for d in sa["decisions"]), sa["level"])


def check_fr17():
    print("\n## (20) FR-17: plan skill/trade cap+ (Mastery-Limit purchase above the level cap) + trades in plans")

    def dsl(s, lvl, slot):
        return [d for d in s["decisions"] if d["slot"] == slot and d["level"] == lvl]

    # --- SKILLS cap+: raise a skill to Expert BELOW L10 via a cap+ purchase. Keep the flat aggregate
    # legal (the engine validates it at current_level): raise Acrobatics Novice->Adept in the L5 plan
    # (within cap), then cap+ it Adept->Expert at L6 (level cap still Adept). Commander L5=2SP, L6=1SP.
    api = builder_api.BuilderAPI("minimus", CATPATHS)
    api.add_planned_level()                                  # L5 (2 SP, cap Adept)
    c5 = [e for e in api.ledger["levels"][5] if e.get("slot") == "skills"][0]
    c5["granted_skills"] = ["Acrobatics: Adept", "Insight: Adept"]   # legal within-cap raises, 2/2
    api.add_planned_level()                                  # L6 (1 SP, cap Adept)
    s = st(api)
    slot6 = dsl(s, 6, "skill")[0]
    o_norm = [o["name"] for o in slot6["options"]]
    ok("plan skill slots carry the cap+ control (plan_pointbuy=='skills', capraise off)",
       slot6.get("plan_pointbuy") == "skills" and slot6.get("capraise") is False, slot6.get("plan_pointbuy"))
    ok("normal mode does NOT offer an above-cap raise (Acrobatics Adept, cap Adept -> no Expert at L6)",
       not any(x.startswith("Acrobatics: Expert") for x in o_norm),
       [x for x in o_norm if x.startswith("Acrobatics")])
    # arm cap+ on the empty slot -> stores CAPARM, options switch to the cap+ set
    s = json.loads(api.set_plan_capraise(slot6["id"], True))
    car6 = [e for e in api.ledger["levels"][6] if e.get("slot") == "skills"][0]
    ok("arming cap+ on an empty slot stores a bare CAPARM sentinel (armed, not yet a pick)",
       (car6.get("granted_skills") or [None])[0] == builder_api.CAPARM, car6.get("granted_skills"))
    slot6 = dsl(s, 6, "skill")[0]
    o_cap = [o["name"] for o in slot6["options"]]
    ok("arming cap+ switches the slot to cap+ options (Acrobatics: Expert (cap+) now offered)",
       slot6["capraise"] is True and "Acrobatics: Expert (cap+)" in o_cap,
       [x for x in o_cap if x.startswith("Acrobatics")])
    # pick the above-cap raise
    s = json.loads(api.set_decision(slot6["id"], "Acrobatics: Expert (cap+)"))
    car6 = [e for e in api.ledger["levels"][6] if e.get("slot") == "skills"][0]
    ok("the cap+ pick is stored with its marker in granted_skills",
       "Acrobatics: Expert (cap+)" in (car6.get("granted_skills") or []), car6.get("granted_skills"))
    ok("a cap+ pick costs 2 points: at a 1-SP level it reports over budget (1 points, 2 spent)",
       any("planned skills over budget" in p and "2 spent" in p for p in s["builder_problems"]),
       [p for p in s["builder_problems"] if "planned skill" in p])
    ok("the cap+ purchase consumes both points in its one slot (no extra empty skill slot renders)",
       len(dsl(s, 6, "skill")) == 1, [d.get("current") for d in dsl(s, 6, "skill")])
    ok("the cap+ pick is engine-clean and catalog-legal (the purchase makes Expert legal below L10)",
       not s["problems"] and not any("planned skill" in p for p in s["catalog_problems"]), probs(s))
    # disarming cap+ strips the marker; without the purchase Expert is over the cap -> catalog flags it
    s = json.loads(api.set_plan_capraise(dsl(s, 6, "skill")[0]["id"], False))
    car6 = [e for e in api.ledger["levels"][6] if e.get("slot") == "skills"][0]
    ok("disarming cap+ strips the marker from the stored pick",
       (car6.get("granted_skills") or [""])[0] == "Acrobatics: Expert", car6.get("granted_skills"))
    ok("without the cap+ purchase, Expert exceeds the cap -> catalog_problems flags it",
       any("mastery limit" in p for p in s["catalog_problems"]), s["catalog_problems"])

    # --- TRADES in plans: a plan level materialises a trade carrier + editable trade pickers ---
    t = builder_api.BuilderAPI("minimus", CATPATHS)
    t.add_planned_level()                                  # L5 also grants trade points
    s = st(t)
    tcar = dsl(s, 5, "trades")
    tsl = dsl(s, 5, "trade")
    ok("a plan level materialises a 'trades' carrier + editable trade child pickers",
       len(tcar) == 1 and len(tsl) >= 1 and all(d["editable"] and d["widget"] == "picker" for d in tsl),
       (len(tcar), len(tsl)))
    ok("trade child ids are keyed to the trade carrier (GC#L5:...#trades#k) and carry the cap+ control",
       all(str(d["id"]).startswith("GC#L5:") and "#trades#" in str(d["id"])
           and d.get("plan_pointbuy") == "trades" for d in tsl), [d["id"] for d in tsl])
    ok("an unfilled trade budget is enforced as a points-based problem",
       any("planned trades:" in p for p in s["builder_problems"]),
       [p for p in s["builder_problems"] if "planned trade" in p])
    topt = [o["name"] for o in tsl[0]["options"]]
    s = json.loads(t.set_decision(tsl[0]["id"], topt[0]))
    tc = [e for e in t.ledger["levels"][5] if e.get("slot") == "trades"][0]
    ok("filling a trade pick writes granted_trades and clears the trade budget problem",
       tc.get("granted_trades") == [topt[0]] and not any("planned trade" in p for p in s["builder_problems"]),
       (tc.get("granted_trades"), [p for p in s["builder_problems"] if "planned trade" in p]))


def check_fr6():
    print("\n## (17) FR-6: rule text on a chosen option (baked corpus + Companion linkify)")
    path = os.path.join(REPO, "builds", "builder.html")
    html = open(path, encoding="utf-8").read()
    m = re.search(r"const RULES_DATA = (\[.*?\]);\n", html, re.S)
    ok("rules corpus baked into builder.html (const RULES_DATA)", bool(m))
    corpus = json.loads(m.group(1)) if m else []
    ok("baked corpus is non-empty and shaped {f,t,h,x}",
       len(corpus) > 100 and all(k in corpus[0] for k in ("f", "t", "h", "x")), len(corpus))
    import rules_corpus
    ok("baked corpus == tools/rules_corpus.build_rules_data(REPO) (single source, no drift)",
       bool(m) and m.group(1) == rules_corpus.corpus_embed(rules_corpus.build_rules_data(REPO)))
    for fn in ("function linkifyTerms", "function _linkable", "function ruleTag",
               "function openRulePanel", "function closeRulePanel"):
        ok("builder JS has %s" % fn, fn in html)
    ok("rule panel + scrim + body markup present",
       'id="rulePanel"' in html and 'id="ruleScrim"' in html and 'id="ruleBody"' in html)
    ok("term sets present (CONDS_SET / DEFINED)",
       "const CONDS_SET=" in html and "const DEFINED=" in html)
    ok("picker branch routes t.current through ruleTag", "ruleTag(t.current)" in html)
    ok("fixed-text branch routes t.pick through ruleTag", "ruleTag(t.pick)" in html)
    ok("rule panel renders rule HTML through linkifyTerms (in-doc cross-links)", "linkifyTerms(sec.h)" in html)
    node = shutil.which("node")
    if not node:
        print("  FR-6 runtime harness: node not available, SKIPPED")
        return
    i = html.index("const RULES_DATA = [")
    j = html.index(">rule</span>';}", i) + len(">rule</span>';}")
    block = html[i:j]
    harness = (
        'var esc=function(s){return String(s);};\n'
        + block + '\n'
        + 'function resolves(q){q=_clean(q);var k=q.toLowerCase(),b=-1;if(CONDS_SET.has(k)){b=_condTarget(k);if(b<0)b=_home(k);}else{b=_home(k);}return b;}\n'
        + 'var R={};\n'
        + 'R.prone_link=_linkable("Prone");R.prone_res=resolves("Prone");\n'
        + 'R.pw_link=_linkable("Pact Weapon");R.pw_res=resolves("Pact Weapon");\n'
        + 'R.tag_known=ruleTag("Pact Weapon");R.tag_junk=ruleTag("Zqxwvthing");R.tag_undec=ruleTag("(undecided)");\n'
        + 'R.tag_comp=ruleTag("Meta Magic (Quickened Spell, Vicious Spell)");\n'
        + 'R.lt_known=linkifyTerms("<p><b>Prone</b> x</p>");R.lt_unknown=linkifyTerms("<p><b>Zqxwvthing</b> x</p>");\n'
        + 'console.log(JSON.stringify(R));\n'
    )
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(harness)
        name = f.name
    r = subprocess.run([node, name], capture_output=True, text=True)
    os.unlink(name)
    ok("FR-6 runtime harness runs on the real baked corpus", r.returncode == 0, r.stderr[:300])
    R = json.loads(r.stdout) if (r.returncode == 0 and r.stdout.strip()) else {}
    ok("known condition 'Prone' is linkable and resolves to a section",
       R.get("prone_link") is True and isinstance(R.get("prone_res"), int) and R.get("prone_res", -1) >= 0, R)
    ok("known term 'Pact Weapon' is linkable and resolves to a section",
       R.get("pw_link") is True and R.get("pw_res", -1) >= 0, R)
    ok("ruleTag builds a clickable rule link for a known term",
       "rlink" in R.get("tag_known", "") and "data-q=" in R.get("tag_known", ""), R.get("tag_known"))
    ok("ruleTag is empty for an unknown pick and for (undecided)",
       R.get("tag_junk") == "" and R.get("tag_undec") == "", (R.get("tag_junk"), R.get("tag_undec")))
    ok("ruleTag cleans a composite pick to its base name",
       'data-q="Meta Magic"' in R.get("tag_comp", ""), R.get("tag_comp"))
    ok("linkifyTerms wraps a known bold term, leaves an unknown one plain",
       "rlink" in R.get("lt_known", "") and "rlink" not in R.get("lt_unknown", ""),
       (R.get("lt_known"), R.get("lt_unknown")))


# ---------------------------------------------------------------- (21) FR-20 picker order
FR20_RANK = {
    'attributes': 0, 'attribute': 0,
    'subclass': 1, 'pact_boon': 1, 'discipline': 1, 'spell_school': 1,
    'talent': 1, 'path': 1, 'class_feature': 1, 'class_features': 1,
    'spellblade_disciplines': 1, 'bound_weapon_options': 1,
    'ancestry_trait': 2, 'ancestry_traits': 2,
    'spell': 3, 'maneuver': 3, 'spell_tagged': 3, 'spells': 3, 'maneuvers': 3,
    'skills': 3, 'trades': 3, 'skill': 3, 'trade': 3, 'rune': 3, 'metamagic': 3,
}


def check_fr20():
    print("\n## (21) FR-20: level pickers render in chargen flow "
          "(attrs -> class/subclass -> ancestry -> resources), children glued")
    from collections import defaultdict

    def rank(slot):
        return FR20_RANK.get(slot, 3)

    for who in builder_build.CHARS:
        api = builder_api.BuilderAPI(who, CATPATHS)
        s = st(api)
        byl = defaultdict(list)
        for d in s["decisions"]:
            byl[d["level"]].append(d)
        for lvl in sorted(byl):
            rows = byl[lvl]
            # (a) top-level (non-child) picker ranks must be non-decreasing within the level
            top = [d for d in rows if not str(d.get("id") or "").startswith("GC#")]
            ranks = [rank(d["slot"]) for d in top]
            ok("%s L%d top-level ranks non-decreasing" % (who, lvl),
               ranks == sorted(ranks), [d["slot"] for d in top])
            # (b) every grant-child row is glued directly under its block: the row above it is
            #     either its parent (a top-level row) or a sibling child with the same parent ref
            for i, d in enumerate(rows):
                did = str(d.get("id") or "")
                if not did.startswith("GC#"):
                    continue
                ref = did.split("#")[1]
                prev = rows[i - 1] if i > 0 else None
                pid = str((prev or {}).get("id") or "")
                glued = prev is not None and (
                    (pid.startswith("GC#") and pid.split("#")[1] == ref)   # sibling child
                    or not pid.startswith("GC#"))                          # its parent row
                ok("%s L%d GC child %s glued under its parent block" % (who, lvl, did), glued, pid)

    # (c) the two cross-category glue cases are the strongest evidence: a class-rank parent
    #     with resource-flavoured children keeps its children directly under it, NOT migrated
    #     to the resources section (Xanwyn Rune Knight -> 2 runes; Scaletrix Meta Magic -> 2 metamagic)
    def slot_seq(who, lvl):
        s = st(builder_api.BuilderAPI(who, CATPATHS))
        return [d["slot"] for d in s["decisions"] if d["level"] == lvl]
    ok("Xanwyn L3 = attribute, subclass, its 2 runes, then resources (spell, maneuver)",
       slot_seq("xanwyn", 3) == ["attribute", "subclass", "rune", "rune", "spell", "maneuver"],
       slot_seq("xanwyn", 3))
    ok("Scaletrix L4 = talent, its 2 metamagic, path, ancestry, then resources (the FR-13a path spell)",
       slot_seq("scaletrix", 4) == ["talent", "metamagic", "metamagic", "path", "ancestry_trait", "spell"],
       slot_seq("scaletrix", 4))
    # grants-only (2026-07-19): the 2 Pact Weapon maneuvers ("of your choice") are editable
    # grant-children glued directly under the L1 pact_boon (class rank), so they render right after
    # the boon and before ancestry; the 4 free chargen spells stay in the resources tail.
    ok("Runt L1 = attributes -> class (schools + boon + its 2 maneuvers) -> ancestry -> resources (spells)",
       slot_seq("runt", 1) == ["attributes", "spell_school", "spell_school", "spell_school", "pact_boon",
                               "maneuver", "maneuver"] + ["ancestry_trait"] * 7 + ["spell"] * 4,
       slot_seq("runt", 1))


# ---------------------------------------------------------------- (22) FR-9 ancestry slots/budget
def check_fr9():
    print("\n## (22) FR-9: ancestry-trait budget readout + auto ready-slot (polish + lock)")
    # (a) all six canon ledgers are at budget -> anc_spent == anc_budget, no ancestry-point
    #     problem. BUG-17: a canon PC that already has its one free Minor (0-cost) Trait shows
    #     no auto slot; one still MISSING its minor (Scaletrix, Xanwyn) shows a single L1
    #     minor-allowance ready slot (a legal free pick), still with no ancestry-point problem.
    for who in builder_build.CHARS:
        api0 = builder_api.BuilderAPI(who, CATPATHS)
        s = st(api0)
        autos = [d for d in s["decisions"] if d.get("auto") and d.get("slot") == "ancestry_trait"]
        anc_probs = [p for p in s["problems"] if "Ancestry point" in p]
        minor_ct = sum(1 for t in (api0.ledger["chargen"].get("ancestry_traits") or [])
                       if str(t.get("name")) != "(undecided)" and int(t.get("cost", 0) or 0) == 0)
        base_ok = s["anc_spent"] == s["anc_budget"] and not anc_probs
        if minor_ct >= 1:
            ok("%s at budget (has minor): no auto slot, no ancestry problem" % who,
               base_ok and not autos, (s["anc_spent"], s["anc_budget"], len(autos), anc_probs))
        else:
            ok("%s at budget (no minor): one L1 minor ready slot, no ancestry problem" % who,
               base_ok and len(autos) == 1 and autos[0]["level"] == 1,
               (s["anc_spent"], s["anc_budget"], len(autos), anc_probs))
    # (b) under budget -> exactly one auto ready-slot, full options, ancestry problem raised
    api = builder_api.BuilderAPI("runt", CATPATHS)
    del api.ledger["chargen"]["ancestry_traits"][1]   # drop Brute (cost 1): 7 -> 6 spent vs 7
    s = st(api)
    autos = [d for d in s["decisions"] if d.get("auto")]
    ok("under budget: exactly one auto ready-slot", len(autos) == 1, len(autos))
    # BUG-18: Runt is L4 and under budget, so the ready slot is placed at the level that most
    # recently granted ancestry points (L4) -> id "L4:trait:+", not the chargen "cg:trait:+".
    ok("auto slot is an ancestry_trait picker (BUG-18 level-placed id L4:trait:+, undecided, full options)",
       autos and autos[0]["id"] == "L4:trait:+" and autos[0]["slot"] == "ancestry_trait"
       and autos[0]["level"] == 4 and autos[0]["current"] == "(undecided)"
       and len(autos[0].get("options") or []) > 10, autos[:1])
    ok("under budget: readout numbers (6 of 7) + engine ancestry problem raised",
       s["anc_spent"] == 6 and s["anc_budget"] == 7
       and any("Ancestry points: 6 spent vs 7 budget" in p for p in s["problems"]), s["anc_spent"])
    # (c) picking via the auto slot materialises a real trait; back at budget -> no auto slot
    opt = next(o["name"] for o in autos[0]["options"] if 0 < o.get("cost", 0) <= 1)
    s2 = json.loads(api.set_decision(autos[0]["id"], opt))
    ok("picking the auto slot materialises a real trait and rebalances the budget",
       s2["anc_spent"] == 7 and not [p for p in s2["problems"] if "Ancestry point" in p]
       and not [d for d in s2["decisions"] if d.get("auto")], (s2["anc_spent"],))
    ok("the materialised trait is now a real editable ancestry_trait row (not auto)",
       any(d["slot"] == "ancestry_trait" and d.get("current") == opt and not d.get("auto")
           for d in s2["decisions"]), opt)
    # (d) guard: an existing UNDECIDED real slot suppresses the auto slot (this is what keeps
    #     the trips/scratch harness safe: they add a real undecided slot before reading)
    api3 = builder_api.BuilderAPI("runt", CATPATHS)
    del api3.ledger["chargen"]["ancestry_traits"][1]
    s3 = json.loads(api3.add_trait(1))
    ok("an existing undecided slot suppresses the auto slot (never two open slots)",
       not [d for d in s3["decisions"] if d.get("auto")]
       and any(d["slot"] == "ancestry_trait" and d["current"] == "(undecided)" for d in s3["decisions"]))
    # (e) page furniture: readout element, undecAt skips auto rows, sentinel handled
    html = open(os.path.join(REPO, "builds", "builder.html"), encoding="utf-8").read()
    ok("builder.html has the ancestry readout element (#ancpts) + 'Ancestry points:' label",
       'id="ancpts"' in html and "Ancestry points:" in html)
    ok("undecAt counter skips auto rows (&& !t.auto)", "&& !t.auto)" in html)
    # the sentinel + budget helper live in API_PY (base64-baked into the page; check_page's
    # "api blob == builder_build.API_PY" already proves the bake matches this source)
    ok("auto-slot sentinels handled in set_decision (chargen cg:trait:+ + BUG-18 level :trait:+)",
       "cg:trait:+" in builder_build.API_PY and "':trait:+'" in builder_build.API_PY
       and "_anc_budget" in builder_build.API_PY and "_anc_ready_level" in builder_build.API_PY)


# ---------------------------------------------------------------- (23) BUG-16 maneuver/spell edit-only
def check_bug16():
    print("\n## (23) BUG-16: maneuver/spell budget slots are edit-only (not removable, no dead-end)")
    for who in builder_build.CHARS:
        s = st(builder_api.BuilderAPI(who, CATPATHS))
        bad = [(d.get("level"), d.get("slot"), d.get("current")) for d in s["decisions"]
               if d.get("slot") in ("maneuver", "spell") and d.get("removable")]
        ok("%s: NO maneuver/spell row is removable (was the unrecoverable-delete bug)" % who,
           not bad, bad)
    # ancestry-trait removability is deliberately unchanged: a builder-added trait stays removable
    # because ancestry DOES self-heal (FR-9 auto ready-slot + the "+ ancestry trait" button re-add
    # against the point budget), so removing one is never a dead-end.
    api = builder_api.BuilderAPI("runt", CATPATHS)
    del api.ledger["chargen"]["ancestry_traits"][1]
    s = st(api)
    auto = [d for d in s["decisions"] if d.get("auto") and d.get("slot") == "ancestry_trait"][0]
    owned = {d.get("current") for d in s["decisions"] if d["slot"] == "ancestry_trait"}
    opt = next(o["name"] for o in auto["options"]
               if 0 < o.get("cost", 0) <= 1 and o["name"] not in owned and "Attribute" not in o["name"])
    s2 = json.loads(api.set_decision(auto["id"], opt))
    added = next(d for d in s2["decisions"] if d["slot"] == "ancestry_trait" and d.get("current") == opt)
    ok("ancestry removability unchanged: a builder-added trait is still removable (safe, self-heals)",
       added.get("removable") is True, added.get("removable"))


# ---------------------------------------------------------------- (24) FR-36 category left accent
def check_fr36():
    print("\n## (24) FR-36: decision rows carry a category rank + a coloured left accent (not amber)")
    # (a) every decision row has a cat in {0,1,2,3}; a top-level (non-child) row's cat equals
    #     its FR20 slot rank; a GC child inherits its parent block's cat (so a block is one colour)
    for who in builder_build.CHARS:
        s = st(builder_api.BuilderAPI(who, CATPATHS))
        rows = s["decisions"]
        ok("%s: every row has cat in {0,1,2,3}" % who,
           all(d.get("cat") in (0, 1, 2, 3) for d in rows),
           [(d["slot"], d.get("cat")) for d in rows if d.get("cat") not in (0, 1, 2, 3)][:3])
        top_bad = [(d["slot"], d.get("cat")) for d in rows
                   if not str(d.get("id") or "").startswith("GC#")
                   and d.get("cat") != FR20_RANK.get(d["slot"], 3)]
        ok("%s: top-level rows' cat == FR20 slot rank" % who, not top_bad, top_bad[:3])
        for i, d in enumerate(rows):
            if not str(d.get("id") or "").startswith("GC#"):
                continue
            # the child's cat matches the nearest preceding non-child row (its parent block)
            parent = next((rows[j] for j in range(i - 1, -1, -1)
                           if not str(rows[j].get("id") or "").startswith("GC#")), None)
            ok("%s: GC child %s inherits parent block cat" % (who, d.get("id")),
               parent is not None and d.get("cat") == parent.get("cat"),
               (d.get("cat"), (parent or {}).get("cat")))
    # (b) the built page carries the four category accent rules and NO longer the amber .newlvl
    html = open(os.path.join(REPO, "builds", "builder.html"), encoding="utf-8").read()
    for cls, col in (("cat0", "#185FA5"), ("cat1", "#C2410C"), ("cat2", "#1D9E75"), ("cat3", "#BA7517")):
        ok("builder.html has .dec.%s left accent %s" % (cls, col),
           ".dec.%s{border-left:4px solid %s}" % (cls, col) in html)
    ok("the old amber .dec.newlvl border rule is gone (replaced by category colour)",
       "newlvl" not in html)
    # (c) rowHTML tags the row with its category class, and the builder-touched note now rides
    #     the amber note text in the editable branch (its old signal was only the amber border)
    ok('rowHTML adds the category class (" cat" + t.cat)', '" cat" + (t.cat==null?3:t.cat)' in html)
    # FR-36 declutter (Darryl live-verify 2026-07-18): editable pickers must NOT dump the ledger
    # notes (they were dev bookkeeping - "Added in builder", "ASK PHIL", catalog-model prose - and
    # cluttered every picker). The old amber border is gone; the builder-touched cue is simply not
    # surfaced. Guard: Runt has editable rows that carry notes, and the editable branch does not
    # render t.note (only the fixed/else branch does).
    ed_noted = [(d.get("level"), d.get("slot")) for d in st(builder_api.BuilderAPI("runt", CATPATHS))["decisions"]
                if d.get("editable") and d.get("note")]
    ok("Runt has editable rows carrying (now-hidden) ledger notes", len(ed_noted) >= 5, len(ed_noted))
    ok("editable pickers do NOT dump ledger notes (declutter; the reverted note-span is gone)",
       "(!t.was_note && t.note) ?" not in html)


# ---------------------------------------------------------------- (25) FR-21 category sub-headers
def check_fr21():
    print("\n## (25) FR-21: long level sections group under light category sub-headers (no nesting)")
    html = open(os.path.join(REPO, "builds", "builder.html"), encoding="utf-8").read()
    ok("builder.html has the .deccat sub-header style", ".deccat{" in html)
    ok("render loop groups levels with >=5 rows under category sub-headers",
       "dl.length >= 5" in html and 'class="deccat"' in html
       and "Attributes" in html and "Resources" in html)
    # behavioural: Runt L1 is the long level (>=5 rows) and spans multiple categories, so it
    # renders sub-headers; a typical level-up level is short (<5 rows) and renders flat.
    from collections import defaultdict
    s = st(builder_api.BuilderAPI("runt", CATPATHS))
    byl = defaultdict(list)
    for d in s["decisions"]:
        byl[d["level"]].append(d)
    l1 = byl[1]
    ok("Runt L1 is a long level (>=5 rows) spanning multiple categories -> sub-headers fire",
       len(l1) >= 5 and len({d.get("cat") for d in l1}) >= 2,
       (len(l1), sorted({d.get("cat") for d in l1})))
    # each category is a single contiguous run (FR-20 sorted), so one sub-header per category
    cats_in_order = [d.get("cat") for d in l1]
    runs = [c for i, c in enumerate(cats_in_order) if i == 0 or c != cats_in_order[i - 1]]
    ok("Runt L1 categories are contiguous (one sub-header per category, not repeated)",
       len(runs) == len(set(runs)), runs)
    short = next((lv for lv, ds in byl.items() if len(ds) < 5), None)
    ok("at least one short level-up level renders flat (no sub-headers, <5 rows)",
       short is not None, {lv: len(ds) for lv, ds in byl.items()})


# ---------------------------------------------------------------- (26) FR-4 display-name rename
def check_fr4():
    print("\n## (26) FR-4: canon/loaded characters get a display-name rename (set_meta 'character')")
    # (a) behavioural: renaming a canon PC updates the display name but not the stable handle,
    #     and touches nothing engine-derived (set_meta whitelists character/player/background).
    api = builder_api.BuilderAPI("runt", CATPATHS)
    before = st(api)
    api.set_meta("character", "Runt the Renamed")
    after = st(api)
    ok("set_meta('character') renames the display name",
       after["character"] == "Runt the Renamed", after["character"])
    ok("rename leaves the stable handle untouched",
       after["handle"] == before["handle"] == "runt", (before["handle"], after["handle"]))
    ok("rename does not disturb the derived build (stats unchanged)",
       after["stats"] == before["stats"], "stats changed under a rename")
    # (b) the built page renders a name input wired to set_meta('character') for non-scratch chars,
    #     with the display-name label + the handle/deeplink-unchanged scope note.
    html = open(os.path.join(REPO, "builds", "builder.html"), encoding="utf-8").read()
    ok("builder.html wires the rename input to set_meta('character')",
       "api.set_meta('character', $('m-character').value)" in html)
    ok("the rename card carries the display-name label + scope note",
       "display name</span>" in html and "Renames the display name only" in html)


# ---------------------------------------------------------------- (27) FR-23 Stamina Regen
def check_fr23():
    print("\n## (27) FR-23: Stamina Regen trigger(s) on the character sheet, catalog-driven")
    expect_labels = {
        "tanrielle": ["Spellblade"], "xanwyn": ["Spellblade"],
        "minimus": ["Commander"], "bonan": ["Barbarian"],
        "runt": ["Spellcaster", "Monk"], "scaletrix": [],
    }
    for who, exp in expect_labels.items():
        sh = json.loads(builder_api.BuilderAPI(who, CATPATHS).sheet())
        got = [t["label"] for t in sh.get("stamina_regen", [])]
        ok("%-10s sheet stamina_regen -> %s" % (who, got or ["None"]), got == exp, (got, exp))
    # Spellblade shows the errata wording, not the classes.md l.2829 'Spell Attack' text.
    ttxt = json.loads(builder_api.BuilderAPI("tanrielle", CATPATHS).sheet())["stamina_regen"][0]["text"]
    ok("Spellblade trigger uses the errata (Bound Weapon / Weapon tag) wording",
       "Bound Weapon" in ttxt and "Weapon tag" in ttxt and "Spell Attack" not in ttxt, ttxt)
    # the built page renders the sheet row + the multi-trigger 1-benefit/round cue.
    html = open(os.path.join(REPO, "builds", "builder.html"), encoding="utf-8").read()
    ok("builder.html renders a Stamina Regen sheet row", "Stamina Regen</span>" in html)
    ok("builder.html carries the 1-benefit/round note for multi-trigger PCs",
       "Only 1 Stamina Regen benefit per Round." in html)


def check_grants_only():
    print("\n## (28) grants-only unification + maneuver/spell auto-heal (BUG-16 full fix)")
    UND = "(undecided)"
    # (a) every canon ledger is internally consistent: named flat picks + fixed grants == the
    #     engine budget. FR-13a (2026-07-19): Scaletrix's 4 Arcane spells are now recorded from
    #     Darryl's sheet, so every canon ledger is fully consistent (no maneuver/spell gaps anywhere).
    for who in builder_build.CHARS:
        s = st(builder_api.BuilderAPI(who, CATPATHS))
        gap_m = s["man_budget"] - s["man_have"]
        gap_s = s["spell_budget"] - s["spell_have"]
        exp = (0, 0)
        ok("%-10s no maneuver/spell over-fill; gaps == expected %s" % (who, exp),
           gap_m >= 0 and gap_s >= 0 and (gap_m, gap_s) == exp, (gap_m, gap_s))
    # (b) Runt: the 4 pact-boon maneuvers are "of your choice" (classes.md l.3244/3269), so they
    #     are EDITABLE grant-child pickers tied to the boon (not read-only, not duplicated into the
    #     flat pool); the flat free maneuvers stay editable too, and no name is duplicated.
    sr = st(builder_api.BuilderAPI("runt", CATPATHS))
    mrows = [d for d in sr["decisions"] if d.get("slot") == "maneuver"]
    boon_man = [d for d in mrows if "#maneuvers#" in str(d.get("id") or "")]
    flat_man = [d for d in mrows if not str(d.get("id") or "").startswith("GC#")]
    ok("Runt: pact-boon maneuvers are EDITABLE grant-child pickers (Cleave/Pathcarver/Brace/Side Step), not locked",
       {d.get("current") for d in boon_man} == {"Cleave", "Pathcarver", "Brace", "Side Step"}
       and all(d["widget"] == "picker" and d.get("editable") and not d.get("removable") for d in boon_man),
       [(d.get("current"), d.get("widget"), d.get("editable")) for d in boon_man])
    ok("Runt: every maneuver row is an editable picker; no maneuver name is duplicated",
       bool(flat_man) and all(d["widget"] == "picker" and d.get("editable") for d in mrows)
       and len(mrows) == len({d.get("current") for d in mrows}), [d.get("current") for d in mrows])
    # the boon constrains maneuver TYPE (Pact Weapon = Attack, Pact Armor = Defense, l.3244/3269):
    # each grant-child picker offers only that type (plus its own current pick).
    import yaml as _yaml
    _mc = _yaml.safe_load(open(os.path.join(REPO, "builds", "catalog", "maneuvers.yaml")))["maneuvers"]
    _mtype = {m: t for t, lst in _mc.items() for m in lst}
    pw = [d for d in boon_man if d.get("current") in ("Cleave", "Pathcarver")]
    pa = [d for d in boon_man if d.get("current") in ("Brace", "Side Step")]
    ok("Pact Weapon maneuver pickers offer ATTACK maneuvers only (+ current)",
       bool(pw) and all(all(_mtype.get(o["name"]) == "Attack" or o["name"] == d.get("current")
                            for o in d["options"]) for d in pw),
       [(d.get("current"), sorted({_mtype.get(o["name"], "?") for o in d["options"]})) for d in pw])
    ok("Pact Armor maneuver pickers offer DEFENSE maneuvers only (+ current)",
       bool(pa) and all(all(_mtype.get(o["name"]) == "Defense" or o["name"] == d.get("current")
                            for o in d["options"]) for d in pa),
       [(d.get("current"), sorted({_mtype.get(o["name"], "?") for o in d["options"]})) for d in pa])
    # off-list current value stays selectable: a picker's <select> must contain its own current
    # value or the browser renders it blank (Scaletrix's inferred "Dispel Magic" is not in his
    # school-filtered list, so it is prepended as an off-list option).
    ss = st(builder_api.BuilderAPI("scaletrix", CATPATHS))
    dm = next((d for d in ss["decisions"] if d.get("slot") == "spell" and d.get("current") == "Dispel Magic"), None)
    ok("off-list current value kept in its picker options (Scaletrix Dispel Magic renders, not blank)",
       bool(dm) and any(o.get("name") == "Dispel Magic" for o in (dm.get("options") or [])),
       dm and dm.get("current"))
    # (c) FR-13a: Scaletrix is now fully recorded - NO auto spell slot, 10 of 10, no problems.
    api = builder_api.BuilderAPI("scaletrix", CATPATHS)
    s = st(api)
    ok("Scaletrix: fully recorded now (10 of 10 spells, no auto spell slot, no problems)",
       s["spell_have"] == 10 and s["spell_budget"] == 10
       and not [d for d in s["decisions"] if d.get("auto") and d.get("slot") == "spell"]
       and not s["builder_problems"] and not s["catalog_problems"],
       (s["spell_have"], s["builder_problems"]))
    # (d) the auto-heal chaining MECHANISM (BUG-16) still works: synthesise a 2-spell gap by
    #     dropping two recorded chargen spells and confirm ONE ready-slot surfaces at a time,
    #     picking it materialises a real editable spell + re-derives, chaining until the gap closes.
    apg = builder_api.BuilderAPI("scaletrix", CATPATHS)
    apg.ledger["chargen"]["spells"] = apg.ledger["chargen"]["spells"][:-2]  # drop 2 -> gap of 2
    sg = st(apg)
    sp_autos = [d for d in sg["decisions"] if d.get("auto") and d.get("slot") == "spell"]
    ok("synthetic gap: exactly one auto spell ready-slot (id cg:spell:+, undecided, has options)",
       len(sp_autos) == 1 and sp_autos[0]["id"] == "cg:spell:+"
       and sp_autos[0]["current"] == UND and len(sp_autos[0].get("options") or []) > 5, sp_autos[:1])
    ok("synthetic gap: readout reports 8 of 10; no maneuver auto-slot; no problems",
       sg["spell_have"] == 8 and sg["spell_budget"] == 10
       and not [d for d in sg["decisions"] if d.get("auto") and d.get("slot") == "maneuver"]
       and not sg["builder_problems"] and not sg["catalog_problems"], (sg["spell_have"],))
    pick = next(o["name"] for o in sp_autos[0]["options"] if o["name"] != UND)
    s2 = json.loads(apg.set_decision("cg:spell:+", pick))
    ok("picking the auto slot materialises a real editable spell and re-derives (9 of 10)",
       s2["spell_have"] == 9
       and any(d["slot"] == "spell" and d.get("current") == pick and not d.get("auto")
               for d in s2["decisions"])
       and len([d for d in s2["decisions"] if d.get("auto") and d.get("slot") == "spell"]) == 1,
       s2["spell_have"])
    a = [d for d in json.loads(apg.state())["decisions"] if d.get("auto") and d.get("slot") == "spell"]
    apg.set_decision("cg:spell:+", next(o["name"] for o in a[0]["options"] if o["name"] != UND))
    sf = json.loads(apg.state())
    ok("after filling both, the gap closes (10 of 10, no auto spell slot, still no problem)",
       sf["spell_have"] == 10
       and not [d for d in sf["decisions"] if d.get("auto") and d.get("slot") == "spell"]
       and not sf["builder_problems"], (sf["spell_have"],))
    # (e) an existing undecided flat slot suppresses the auto slot (one ready slot at a time)
    api2 = builder_api.BuilderAPI("scaletrix", CATPATHS)
    api2.ledger["chargen"].setdefault("spells", []).append(UND)
    s3 = st(api2)
    ok("an existing undecided spell slot suppresses the auto slot (never two open at once)",
       not [d for d in s3["decisions"] if d.get("auto") and d.get("slot") == "spell"], None)
    # (f) page furniture: the readout element + the retired-reconcile absence
    html = open(os.path.join(REPO, "builds", "builder.html"), encoding="utf-8").read()
    ok("builder.html has the maneuver/spell readout element (#resreadout) + sentinels in API_PY",
       'id="resreadout"' in html and "cg:spell:+" in builder_build.API_PY
       and "cg:man:+" in builder_build.API_PY and "_res_have" in builder_build.API_PY)
    ok("expand_composite is gone from API_PY (reconcile retired)",
       "def expand_composite" not in builder_build.API_PY)



# --------------------------------------------- option-effects (scratch-mode grants)
def check_option_effects():
    """2026-07-25 option-effects layer: a scratch-mode ancestry pick must APPLY its catalog
    effect, not just its cost. Numeric ancestry grants (mp/hp/jump/jump_from) flow from the
    catalog onto the ledger entry via _set_trait, and a re-pick clears them.
    2026-07-27: extended to CHOICE spell grants (BUG-25, Fiendish Magic / Celestial Magic ->
    source-filtered child pickers) and to ready-slot level placement (BUG-23, a level's granted
    spells/maneuvers spawn their ready slot AT that level and record a level entry)."""
    print("## (OE) Option-effects: scratch ancestry grants apply + clear; spell grants; slot level")

    def stat(s, n):
        v = next(r[1] for r in s["stats"] if r[0] == n)
        return int(str(v).split()[0])

    def last_trait_slot(s):
        return [d for d in s["decisions"] if d["slot"] == "ancestry_trait"][-1]

    def fresh(cls, anc):
        a = builder_api.BuilderAPI(None, CATPATHS, new_class=cls)
        a.set_attr("might", 3); a.set_attr("agility", 1)
        a.set_attr("charisma", 0); a.set_attr("intelligence", 0)
        a.set_ancestry(anc, "-")
        return a

    # Mana Increase -> +1 MP (BUG-27)
    a = fresh("druid", "Dragonborn"); mp0 = stat(st(a), "MP")
    d = last_trait_slot(json.loads(a.add_trait(1)))
    s1 = json.loads(a.set_decision(d["id"], "Mana Increase"))
    ok("scratch Dragonborn Mana Increase grants +1 MP (BUG-27)",
       stat(s1, "MP") == mp0 + 1, "%d->%d" % (mp0, stat(s1, "MP")))
    # re-pick to a no-numeric-grant trait clears the MP grant
    s2 = json.loads(a.set_decision(d["id"], "Darkvision"))
    ok("scratch Mana Increase -> Darkvision clears the MP grant",
       stat(s2, "MP") == mp0, "%d (base %d)" % (stat(s2, "MP"), mp0))

    # Tough -> +1 HP ; Jumper -> +2 Jump Distance
    a = fresh("barbarian", "Beastborn"); s0 = st(a)
    hp0, j0 = stat(s0, "HP"), stat(s0, "Jump Distance")
    d = last_trait_slot(json.loads(a.add_trait(1)))
    sh = json.loads(a.set_decision(d["id"], "Tough"))
    ok("scratch Beastborn Tough grants +1 HP",
       stat(sh, "HP") == hp0 + 1, "%d->%d" % (hp0, stat(sh, "HP")))
    d = last_trait_slot(json.loads(a.add_trait(1)))
    sj = json.loads(a.set_decision(d["id"], "Jumper"))
    ok("scratch Beastborn Jumper grants +2 Jump Distance",
       stat(sj, "Jump Distance") == j0 + 2, "%d->%d" % (j0, stat(sj, "Jump Distance")))

    # BUG-24: per-ancestry Origin picker appears once a trait of that ancestry is taken, records
    # the choice, and is engine-neutral; canon Scaletrix loads with both origins seeded.
    def origins(s):
        return [d for d in s["decisions"] if d["slot"] == "ancestry_origin"]
    a = fresh("druid", "Dragonborn")
    ok("no Draconic Origin node before any Dragonborn trait", len(origins(st(a))) == 0)
    d = last_trait_slot(json.loads(a.add_trait(1)))
    s = json.loads(a.set_decision(d["id"], "Draconic Breath Weapon"))
    od = origins(s)
    ok("Draconic Origin node appears after a Dragonborn trait", len(od) == 1,
       [x["slot"] for x in od])
    if od:
        opts = {o["name"] for o in od[0]["options"]}
        ok("Draconic Origin offers the 8 rules damage types",
           opts == {"Cold", "Corrosion", "Fire", "Lightning", "Poison", "Psychic", "Radiant", "Umbral"},
           sorted(opts))
        mp_before = stat(s, "MP")
        s2 = json.loads(a.set_decision(od[0]["id"], "Fire"))
        ok("picking a Draconic Origin records it", origins(s2)[0]["current"] == "Fire",
           origins(s2)[0]["current"])
        ok("Draconic Origin pick is engine-neutral (MP unchanged)",
           stat(s2, "MP") == mp_before, (mp_before, stat(s2, "MP")))
    a2 = builder_api.BuilderAPI("scaletrix", CATPATHS)
    od2 = origins(st(a2))
    ok("canon Scaletrix loads both origins seeded to Fire (no undecided)",
       len(od2) == 2 and all(x["current"] == "Fire" for x in od2),
       [(x.get("slotlabel"), x["current"]) for x in od2])

    # ---- BUG-25 (2026-07-27): a CHOICE spell grant flows from the catalog too, so the two
    # spell-granting ancestry traits render source-filtered child pickers in scratch mode.
    UND = "(undecided)"

    def gchild(s):
        return [d for d in s["decisions"] if (d.get("id") or "").startswith("GC#cgtrait:")]
    a = fresh("druid", "Fiendborn"); b0 = st(a)["spell_budget"]
    d = last_trait_slot(json.loads(a.add_trait(1)))
    s = json.loads(a.set_decision(d["id"], "Fiendish Magic"))
    kids = gchild(s)
    ok("scratch Fiendborn Fiendish Magic grants +1 spell (BUG-25)",
       s["spell_budget"] == b0 + 1, "%d->%d" % (b0, s["spell_budget"]))
    ok("Fiendish Magic renders ONE source-constrained spell child under the trait",
       len(kids) == 1 and kids[0]["slot"] == "spell_sourced" and kids[0]["current"] == UND,
       [(k["id"], k["slot"]) for k in kids])
    ok("its options are Arcane, narrowed to Elemental/Enchantment (ancestries.md l.718-726)",
       bool(kids) and {o["group"] for o in kids[0]["options"]} == {"Elemental", "Enchantment"}
       and len(kids[0]["options"]) > 10,
       sorted({o["group"] for o in kids[0]["options"]}) if kids else None)
    pick = kids[0]["options"][0]["name"]
    sp = json.loads(a.set_decision(kids[0]["id"], pick))
    ok("picking the child records it as the trait's granted spell and fills the budget",
       a.ledger["chargen"]["ancestry_traits"][-1].get("granted_spells") == [pick]
       and sp["spell_have"] == 1,
       (a.ledger["chargen"]["ancestry_traits"][-1].get("granted_spells"), sp["spell_have"]))
    sr = json.loads(a.set_decision(d["id"], "Darkvision"))
    t_after = a.ledger["chargen"]["ancestry_traits"][-1]
    ok("re-picking the trait clears the spell grant, access AND provenance",
       sr["spell_budget"] == b0 and not t_after.get("grants")
       and "spell_access" not in t_after and "granted_spells" not in t_after,
       (sr["spell_budget"], t_after))
    # the Angelborn sibling: Divine, any school (l.654-658), so no school narrowing
    a = fresh("druid", "Angelborn")
    d = last_trait_slot(json.loads(a.add_trait(1)))
    s = json.loads(a.set_decision(d["id"], "Celestial Magic"))
    kids = gchild(s)
    ok("Angelborn Celestial Magic renders a Divine child with no school narrowing",
       len(kids) == 1 and len({o["group"] for o in kids[0]["options"]}) > 2,
       sorted({o["group"] for o in kids[0]["options"]}) if kids else None)
    # canon regression: Scaletrix's hand-authored "Arcane Spell" entry is untouched by the copy
    sc = st(builder_api.BuilderAPI("scaletrix", CATPATHS))
    ok("canon Scaletrix still resolves 10 of 10 spells with Command childed under the trait",
       sc["spell_have"] == 10 and sc["spell_budget"] == 10
       and any(k.get("current") == "Command" for k in gchild(sc)),
       (sc["spell_have"], [k.get("current") for k in gchild(sc)]))

    # ---- BUG-23 (2026-07-27): the maneuver/spell ready slot renders at the level that granted
    # the budget, not always at chargen (the BUG-18 treatment), and materialises a LEVEL entry.
    # Vehicle = Spellcasting Expansion, a general talent granting {spells: 3} with NO spell_access, so
    # its spells use the flat pool. (The original repro used MC Bard Remarkable Repertoire, which BUG-30
    # later moved onto its own any-list child-slots, so it no longer exercises the flat ready slot.)
    a = drive_fresh("barbarian")
    s = json.loads(a.add_level())
    tal = [d for d in s["decisions"] if d.get("id") and d["slot"] == "talent"][0]
    a.set_decision(tal["id"], "Spellcasting Expansion")   # general talent: 3 flat-pool spells
    s = json.loads(a.set_decision("L2:2", "Spellcaster"))  # path rider: +1 spell -> budget 4
    ok("Barbarian + Spellcasting Expansion at L2 budgets 4 spells (BUG-23 root)",
       s["spell_budget"] == 4 and s["spell_have"] == 0, (s["spell_have"], s["spell_budget"]))
    rider0 = [d for d in s["decisions"] if d["slot"] == "spell" and d["level"] == 2]
    a.set_decision(rider0[0]["id"], rider0[0]["options"][0]["name"])   # fill the path-rider slot
    s = json.loads(a.state())
    autos = [d for d in s["decisions"] if d.get("auto") and d["slot"] == "spell"]
    ok("the ready spell slot renders AT L2, the level that granted it (not cg:spell:+)",
       len(autos) == 1 and autos[0]["id"] == "L2:spell:+" and autos[0]["level"] == 2,
       [(x["id"], x["level"]) for x in autos])
    for _ in range(3):
        au = [d for d in json.loads(a.state())["decisions"]
              if d.get("auto") and d["slot"] == "spell"]
        if au:
            a.set_decision(au[0]["id"], next(o["name"] for o in au[0]["options"]
                                             if o["name"] not in
                                             {e.get("pick") for e in a.ledger["levels"][2]}))
    s = json.loads(a.state())
    l2 = [e for e in a.ledger["levels"][2] if e.get("slot") == "spell"]
    ok("chaining fills 4 of 4 and every pick is recorded as an L2 entry",
       s["spell_have"] == 4 and s["spell_budget"] == 4 and len(l2) == 4
       and not [d for d in s["decisions"] if d.get("auto") and d["slot"] == "spell"],
       (s["spell_have"], [e.get("pick") for e in l2]))
    rt = yaml.safe_load(a.export_yaml())
    ok("the L2 spells round-trip through export",
       len([e for e in rt["levels"][2] if e.get("slot") == "spell"]) == 4,
       [e.get("pick") for e in rt["levels"][2] if e.get("slot") == "spell"])
    ok("both level sentinels are wired in API_PY",
       ":spell:+" in builder_build.API_PY and ":man:+" in builder_build.API_PY
       and "_res_ready_level" in builder_build.API_PY)

    # ---- BUG-28 (2026-07-27): re-picking a grant-bearing entry away must not leave the picks it
    # funded behind, and an over-recorded count must never be silent.
    s = json.loads(a.set_decision(tal["id"], "Wild Form"))   # MC Druid: no spell grant
    l2 = [e for e in a.ledger["levels"][2] if e.get("slot") == "spell"]
    ok("swapping the talent away prunes the spells it funded (4 of 4 -> 1 of 1)",
       s["spell_have"] == 1 and s["spell_budget"] == 1 and len(l2) == 1
       and not s["builder_problems"],
       (s["spell_have"], s["spell_budget"], [e.get("pick") for e in l2], s["builder_problems"]))
    ok("the path-rider spell survives the prune (its path is still chosen)",
       bool(l2) and str(l2[0].get("source", "")).startswith("path rider"),
       l2[0].get("source") if l2 else None)
    s = json.loads(a.set_decision(tal["id"], "Spellcasting Expansion"))
    au = [d for d in s["decisions"] if d.get("auto") and d["slot"] == "spell"]
    ok("swapping the talent back re-opens the ready slot at L2 (1 of 4)",
       s["spell_have"] == 1 and s["spell_budget"] == 4
       and len(au) == 1 and au[0]["id"] == "L2:spell:+",
       (s["spell_have"], s["spell_budget"], [x["id"] for x in au]))
    # hand-authored rows are NEVER pruned (only builder-added ones are), so a canon ledger that ends up
    # over-recorded raises the advisory instead of losing data. Synthesised on a canon ledger: two extra
    # flat spells at L2 that no grant pays for.
    c = builder_api.BuilderAPI("bonan", CATPATHS)
    sc0 = st(c)
    c.ledger["levels"][2] += [{"slot": "spell", "pick": "Fire Bolt"},
                              {"slot": "spell", "pick": "Gust"}]
    sc = st(c)
    kept = [e.get("pick") for e in c.ledger["levels"][2] if e.get("slot") == "spell"]
    ok("canon Bonan starts clean at 3 of 3 (2 childed under the talent + 1 flat)",
       sc0["spell_have"] == 3 and sc0["spell_budget"] == 3 and clean(sc0),
       (sc0["spell_have"], sc0["spell_budget"]))
    ok("hand-authored over-recording keeps every row (nothing pruned)",
       len(kept) == 3, kept)
    ok("...and flags the overflow instead of going silent (BUG-28)",
       any("5 spells recorded but only 3 granted" in p for p in sc["builder_problems"]),
       sc["builder_problems"])
    ok("the readout renders the over-budget branch too (not just under)",
       "recorded, only ${budget} granted" in builder_build.TEMPLATE
       and "var(--bad)" in builder_build.TEMPLATE)

    # ---- BUG-29 (2026-07-27): ready-slot suppression is per level, so a short level still gets its
    # slot while another level has an open one of its own.
    b = builder_api.BuilderAPI(None, CATPATHS, new_class="spellblade")
    b.set_attr("might", 3); b.set_attr("agility", 1)
    b.set_attr("charisma", 0); b.set_attr("intelligence", 0)
    b.set_ancestry("Human", "-")
    sb = json.loads(b.add_level())
    tsb = find_dec(sb, lambda d: d["slot"] == "talent" and d["level"] == 2)
    sb = json.loads(b.set_decision(tsb["id"], "Spellcasting Expansion"))   # 3 flat-pool spells at L2
    aub = [d for d in sb["decisions"] if d.get("auto") and d["slot"] == "spell"]
    ok("Spellblade L2 talent spells get a ready slot at L2 while L1 spells are undecided (BUG-29)",
       sb["spell_budget"] == 5 and len(aub) == 1 and aub[0]["id"] == "L2:spell:+",
       (sb["spell_budget"], [(x["id"], x["level"]) for x in aub]))
    # ...but a level whose OWN slot is open gets no second slot (one ready slot per level)
    b2 = drive_fresh("barbarian")
    s2b = json.loads(b2.add_level())
    t2b = find_dec(s2b, lambda d: d["slot"] == "talent" and d["level"] == 2)
    b2.set_decision(t2b["id"], "Spellcasting Expansion")
    s2b = json.loads(b2.set_decision("L2:2", "Spellcaster"))   # path rider leaves an undecided L2 spell
    ok("a short level with its own open slot gets no extra ready slot",
       not [d for d in s2b["decisions"] if d.get("auto") and d["slot"] == "spell"],
       [d["id"] for d in s2b["decisions"] if d.get("auto")])

    # ---- BUG-30 (2026-07-27): an any-list grant (MC Bard Magical Secrets, "any 2 Spells from any Spell
    # List") is NOT bound by the character's own schools, so it renders its own unfiltered child-slots
    # under the granting talent. Everything else stays filtered: widening the shared flat pool was the
    # first attempt and it leaked off-list options into every other picker (Darryl's live-verify).
    b3 = builder_api.BuilderAPI(None, CATPATHS, new_class="spellblade")
    b3.set_attr("might", 3); b3.set_attr("agility", 1)
    b3.set_attr("charisma", 0); b3.set_attr("intelligence", 0)
    b3.set_ancestry("Human", "-")
    b3.set_decision("cg:school:0", "Invocation")
    b3.set_decision("cg:school:1", "Divination")
    s3b = st(b3)
    native_n = len(find_dec(s3b, lambda d: d["id"] == "cg:spell:0")["options"])
    ok("Spellblade without an any-list grant holds 0 any-list slots", b3._any_list_slots() == 0)
    s3b = json.loads(b3.add_level())
    t3b = find_dec(s3b, lambda d: d["slot"] == "talent" and d["level"] == 2)
    s3b = json.loads(b3.set_decision(t3b["id"], "Remarkable Repertoire"))
    kids = [d for d in s3b["decisions"] if (d.get("id") or "").startswith("GC#L2:")]
    d3b = find_dec(s3b, lambda d: d["id"] == "cg:spell:0")
    ok("Remarkable Repertoire declares 2 any-list slots from the catalog (BUG-30)",
       b3._any_list_slots() == 2, b3._any_list_slots())
    ok("it renders 2 spell_any children glued under the talent, offering EVERY spell",
       len(kids) == 2 and all(k["slot"] == "spell_any" for k in kids)
       and all(len(k["options"]) == len(builder_build.extract_spell_meta(
           os.path.join(REPO, "rules", "spells.md"))) for k in kids),
       [(k["id"], k["slot"], len(k["options"])) for k in kids])
    ok("the OTHER pickers stay filtered to the character's own lists (no leak)",
       len(find_dec(st(b3), lambda d: d["id"] == "cg:spell:0")["options"]) == native_n
       and not any(o["group"] == "any Spell List" for o in d3b["options"]),
       (native_n, len(d3b["options"])))
    off = next(o["name"] for o in kids[0]["options"]
               if o["name"] not in {x["name"] for x in d3b["options"]})
    s3b = json.loads(b3.set_decision(kids[0]["id"], off))
    ok("an off-school spell picked in the child is legal and fills the budget",
       s3b["catalog_problems"] == [] and s3b["spell_have"] == 1
       and b3.ledger["levels"][2][1]["granted_spells"][0] == off,
       (off, s3b["catalog_problems"], s3b["spell_have"]))
    s3b = json.loads(b3.set_decision(t3b["id"], "Wild Form"))
    ok("swapping the talent away removes the children and their budget",
       not [d for d in s3b["decisions"] if (d.get("id") or "").startswith("GC#L2:")]
       and s3b["spell_budget"] == 2 and not s3b["catalog_problems"],
       (s3b["spell_budget"], s3b["catalog_problems"]))
    # canon Bonan: his 2 Magical Secrets spells are childed under the long-form talent name
    ab = builder_api.BuilderAPI("bonan", CATPATHS)
    sb2 = st(ab)
    bkids = [d for d in sb2["decisions"] if (d.get("id") or "").startswith("GC#L2:")]
    ok("canon Bonan: long-form 'MC Bard: Remarkable Repertoire' resolves to 2 any-list slots",
       ab._any_list_slots() == 2, ab._any_list_slots())
    ok("canon Bonan: Command + Charm render as his talent's children, Frost Bolt stays flat, 3 of 3",
       [k.get("current") for k in bkids] == ["Command", "Charm"]
       and any(d["slot"] == "spell" and d.get("current") == "Frost Bolt" for d in sb2["decisions"])
       and sb2["spell_have"] == 3 and sb2["spell_budget"] == 3 and clean(sb2),
       ([k.get("current") for k in bkids], sb2["spell_have"]))
    # the flat-pool tolerance survives for received files that left such spells flat (Bonan's old shape)
    ab2 = builder_api.BuilderAPI("bonan", CATPATHS)
    tal_e = [e for e in ab2.ledger["levels"][2] if e.get("slot") == "talent"][0]
    tal_e.pop("granted_spells", None)
    ab2.ledger["levels"][2] += [{"slot": "spell", "pick": "Command"}, {"slot": "spell", "pick": "Charm"}]
    ok("a received file with those spells left FLAT is tolerated up to the slot count",
       not [p for p in ab2.catalog_problems() if "any-list" in p], ab2.catalog_problems())
    ok("the readout also reports a MET count (no more vanishing when complete)",
       "of ${budget} recorded</b>`);" in builder_build.TEMPLATE
       and "var(--ok)" in builder_build.TEMPLATE)


# --------------------------------------------- class features (BUG-19 / BUG-21 / BUG-22)
def check_class_features():
    """2026-07-27: the class-feature trio. `class_features.yaml` names what each class actually gains
    per level (the class table only prints "Class Feature") and carries the numeric effects, so a
    scratch build shows its L1 features and gets their bonuses (BUG-19 + BUG-22); the Paladin subclass
    grants the Acolyte Discipline, or a free pick when it is already held (BUG-21)."""
    print("## (CF) Class features: named L1/L2 rows, Berserker effects, Paladin's discipline")
    UND = "(undecided)"

    def stat(s, n):
        v = next((r[1] for r in s["stats"] if r[0] == n), None)
        return int(str(v).split()[0]) if v is not None else None

    def cf_rows(s, lvl=None):
        return [d for d in s["decisions"] if str(d["slot"]).startswith("class_feature")
                and (lvl is None or d["level"] == lvl)]

    def val(d):   # a read-only class-feature row carries its value in `pick`, not `current`
        return str(d.get("current") or d.get("pick") or "")

    # BUG-19: a fresh build shows its real L1 features by name (it showed none at all before)
    a = builder_api.BuilderAPI(None, CATPATHS, new_class="barbarian")
    s = st(a)
    rows = cf_rows(s, 1)
    ok("fresh barbarian L1 lists its real class features by name (BUG-19)",
       len(rows) == 1 and rows[0]["slot"] == "class_features"
       and "Rage" in val(rows[0]) and "Berserker" in val(rows[0]),
       val(rows[0]) if rows else None)
    # BUG-22: Berserker = +1 Speed, Jump from Might, +2 AD while unarmoured
    base_ad = 8 + 1 + (-2) + (-2)      # 8 + CM + Might + Charisma, all attributes at -2
    ok("Berserker grants +1 Speed / Jump-from-Might / +2 AD unarmoured (BUG-22)",
       stat(s, "Move Speed") == 6 and stat(s, "AD") == base_ad + 2 and stat(s, "Jump Distance") == 1,
       (stat(s, "Move Speed"), stat(s, "AD"), stat(s, "Jump Distance")))
    ok("the L1 entry records the grants + an unarmoured caveat in its note",
       (a.ledger["chargen"]["class_choices"][0].get("grants") or {}).get("ad") == 2
       and "unarmoured" in a.ledger["chargen"]["class_choices"][0].get("note", ""),
       a.ledger["chargen"]["class_choices"][0].get("grants"))
    # armour suppresses the unarmoured-only half (documented name heuristic)
    b = builder_api.BuilderAPI(None, CATPATHS, new_class="barbarian")
    b.ledger["equipment"] = [{"name": "Plate Armor", "pd": 2}]
    sb = json.loads(b.add_level())
    ok("the same feature at a level notes the unarmoured bonus is NOT applied when armour is worn",
       any("NOT applied" in str(d.get("note")) for d in cf_rows(sb))
       or all(val(d) != "Berserker" for d in cf_rows(sb, 2)),
       [(val(d), d.get("note")) for d in cf_rows(sb)])
    # BUG-19 second half: a generated level row is NAMED, not a bare "Class Feature"
    s2 = json.loads(a.add_level())
    l2 = cf_rows(s2, 2)
    ok("the L2 class-feature row reads Battlecry, not a bare \"Class Feature\" (BUG-19)",
       len(l2) == 1 and val(l2[0]) == "Battlecry", [val(d) for d in l2])
    # every walked class has curated L1 + L2 names
    for cls, l1, l2n in (("commander", "Inspiring Presence", "Commanding Aura"),
                         ("druid", "Druid Domain", "Nature's Torrent"),
                         ("spellblade", "Bound Weapon", "Spellstrike"),
                         ("warlock", "Warlock Contract", "Life Tap")):
        api = builder_api.BuilderAPI(None, CATPATHS, new_class=cls)
        s3 = st(api)
        s4 = json.loads(api.add_level())
        ok("%-10s L1 names %s and L2 names %s" % (cls, l1, l2n),
           l1 in val((cf_rows(s3, 1) or [{}])[0])
           and any(val(d) == l2n for d in cf_rows(s4, 2)),
           [(d["level"], val(d)) for d in cf_rows(s4)])

    # BUG-21: Paladin (Spellblade L3) grants the Acolyte Discipline, pre-filled
    c = builder_api.BuilderAPI(None, CATPATHS, new_class="spellblade")
    for _ in range(2):
        c.add_level()
    sc = json.loads(c.add_level())
    sub = find_dec(sc, lambda d: d["slot"] == "subclass")
    sc = json.loads(c.set_decision(sub["id"], "Paladin"))
    kids = [d for d in sc["decisions"] if d["slot"] == "discipline"
            and str(d.get("id")).startswith("GC#")]
    ok("Paladin grants 1 Discipline, pre-filled with Acolyte (BUG-21)",
       len(kids) == 1 and kids[0].get("current") == "Acolyte", [k.get("current") for k in kids])
    ok("...and it is recorded on the subclass entry as granted_disciplines",
       [e for e in c.ledger["levels"][3]
        if e.get("slot") == "subclass"][0].get("granted_disciplines") == ["Acolyte"],
       c.ledger["levels"][3])
    # ...but if Acolyte is already held it becomes a free pick, with Acolyte filtered out
    d2 = builder_api.BuilderAPI(None, CATPATHS, new_class="spellblade")
    disc = find_dec(st(d2), lambda x: x["slot"] == "discipline" and str(x["id"]).startswith("cg:choice"))
    d2.set_decision(disc["id"], "Acolyte")
    for _ in range(2):
        d2.add_level()
    sd = json.loads(d2.add_level())
    sub2 = find_dec(sd, lambda x: x["slot"] == "subclass")
    sd = json.loads(d2.set_decision(sub2["id"], "Paladin"))
    kids2 = [x for x in sd["decisions"] if x["slot"] == "discipline"
             and str(x.get("id")).startswith("GC#")]
    ok("already holding Acolyte: the grant is an open pick with Acolyte filtered out (BUG-21)",
       len(kids2) == 1 and kids2[0].get("current") == UND
       and not any(o["name"] == "Acolyte" for o in kids2[0]["options"]),
       (kids2[0].get("current"), len(kids2[0]["options"])) if kids2 else None)
    # Rune Knight is unaffected (no prefer key) and canon Xanwyn still resolves
    x = st(builder_api.BuilderAPI("xanwyn", CATPATHS))
    # BUG-31: the harness built CATPATHS from CATALOG while the PAGE carried a hand-written literal,
    # so a newly added catalog file passed every test here and did nothing in the browser (that is
    # exactly how class_features shipped inert). Assert the page's map covers CATALOG, in the page.
    import re as _re
    html_cp = open(os.path.join(REPO, "builds", "builder.html"), encoding="utf-8").read()
    m_cp = _re.search(r"CATPATHS = (\{[^}]*\})", html_cp)
    page_cp = eval(m_cp.group(1)) if m_cp else {}
    want_cp = {c for c in builder_build.CATALOG if c not in builder_build.CATPATHS_EXCLUDE}
    ok("the PAGE's CATPATHS covers every BuilderAPI catalog in CATALOG (BUG-31)",
       bool(m_cp) and set(page_cp) == want_cp
       and all(page_cp[c] == c + ".yaml" for c in want_cp),
       sorted(want_cp - set(page_cp)) or sorted(set(page_cp) - want_cp))
    ok("...and class_features in particular reaches the API (the bug that shipped inert)",
       page_cp.get("class_features") == "class_features.yaml", page_cp.get("class_features"))

    ok("canon Xanwyn (Rune Knight) unaffected: no discipline grant-child, still clean",
       not [d for d in x["decisions"] if d["slot"] == "discipline"
            and str(d.get("id")).startswith("GC#")] and clean(x),
       (x["problems"], x["catalog_problems"], x["builder_problems"]))


# --------------------------------------------- sheet ability groups + build stamp (BUG-32 / FR-43)
def check_sheet_groups():
    """2026-07-27: the sheet's Features & Abilities list is emitted BY THE API (SHEET_GROUPS), not
    assembled from a list held in the page JS. That literal had silently dropped Xanwyn's runes,
    Runt's pact boons, Scaletrix's metamagic + origin nodes and the BUG-19 class-features row. Also
    checks the FR-43 build stamp is present."""
    print("## (SG) Sheet ability groups emitted by the API + build stamp")
    covered = {sl for sl, _ in builder_api.SHEET_GROUPS} | builder_api.SHEET_SLOT_SKIP
    uncovered = {}
    got = {}
    for h in list(builder_build.CHARS) + ["new:" + c for c in builder_build.NEWCLASSES]:
        api = (builder_api.BuilderAPI(h, CATPATHS) if not h.startswith("new:")
               else builder_api.BuilderAPI(None, CATPATHS, new_class=h[4:]))
        sh = json.loads(api.sheet())
        got[h] = {g["label"]: len(g["items"]) for g in sh["ability_groups"]}
        for k in sh["abilities"]:
            if k not in covered:
                uncovered.setdefault(k, []).append(h)
    ok("every slot a real sheet emits is covered by SHEET_GROUPS (BUG-32)", not uncovered, uncovered)
    # the four that were invisible before, on the characters that own them
    ok("Xanwyn's 2 Runes reach the sheet", got["xanwyn"].get("Runes") == 2, got["xanwyn"])
    ok("Runt's 2 Pact boons reach the sheet", got["runt"].get("Pact boons") == 2, got["runt"])
    ok("Scaletrix's 2 Meta Magic reach the sheet", got["scaletrix"].get("Meta Magic") == 2,
       got["scaletrix"])
    ok("Scaletrix's Origin + Spell source nodes reach the sheet",
       got["scaletrix"].get("Origin") == 1 and got["scaletrix"].get("Spell source") == 1,
       got["scaletrix"])
    ok("a fresh barbarian's class features reach the sheet (the BUG-19 row, plural slot aliased)",
       got["new:barbarian"].get("Class features") == 1, got["new:barbarian"])
    ok("canon rows still land: Xanwyn keeps Disciplines / Bound weapon / Ancestry",
       all(got["xanwyn"].get(k) for k in ("Disciplines", "Bound weapon", "Ancestry")), got["xanwyn"])
    # page side: renders what it is given, holds no label list of its own, and carries a stamp
    html = open(os.path.join(REPO, "builds", "builder.html"), encoding="utf-8").read()
    ok("the page renders d.ability_groups and no longer holds a catLabels literal (BUG-32)",
       "d.ability_groups" in html and "catLabels" not in html)
    import re as _re2
    m_st = _re2.search(r'class="stamp">Build: ([^<]+)<', html)
    ok("FR-43: the page carries a build stamp (date + short SHA, like the Companion's)",
       bool(m_st) and bool(_re2.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2} \S+ . \S+$", m_st.group(1))),
       m_st.group(1) if m_st else None)


def _fresh_at(cls, anc, levels=0):
    """A scratch character of `cls`/`anc`, point-buy filled, optionally advanced `levels` times.
    Deliberately minimal: these checks only read derived stats and decision shapes."""
    api = builder_api.BuilderAPI(None, CATPATHS, new_class=cls)
    api.set_attr("might", 3); api.set_attr("agility", 1)
    api.set_attr("charisma", 0); api.set_attr("intelligence", 0)
    api.set_ancestry(anc, "-")
    for _ in range(levels):
        api.add_level()
    return api


def _pick_trait(api, name):
    s = json.loads(api.add_trait(1))
    d = [x for x in s["decisions"] if x["slot"] == "ancestry_trait"][-1]
    assert name in [o["name"] for o in d["options"]], "%s not offered" % name
    return json.loads(api.set_decision(d["id"], name))


def _stat(s, key):
    row = [r for r in s["stats"] if r[0] == key]
    return row[0][1] if row else None


def check_ch5_burndown():
    """CH-5 Tier-1 (2026-07-27): the seven ancestry traits that were priced but inert now MOVE the
    derived stat they are supposed to move. Four are plain `grants` (the BUG-27 copy path); three are
    `grants_unarmored`, the conditional-defence shape class features already used (BUG-22), now also
    honoured on ancestry traits. Asserting the DERIVED STAT, not the catalog row, is the point: the
    whole bug family was 'the data says it, nothing applies it'."""
    print("## (CH5) option-effects burn-down, Tier-1 ancestry traits")
    cases = [("Elf", "Frail", "HP", -2),
             ("Elf", "Brittle", "AD", -1),
             ("Elf", "Quick Reactions", "PD", 1),
             ("Dwarf", "Thick-Skinned", "AD", 1),
             ("Beastborn", "Reckless", "PD", -1)]
    for anc, trait, stat, want in cases:
        before = _stat(json.loads(_fresh_at("barbarian", anc).state()), stat)
        after = _stat(_pick_trait(_fresh_at("barbarian", anc), trait), stat)
        got = int(after) - int(before)
        ok("%-9s %-16s %s %+d" % (anc, trait, stat, want), got == want,
           "%s -> %s (delta %s)" % (before, after, got))
    # Hard Shell is the pair case: unconditional {speed:-1} PLUS unarmoured-only {ad:+1}, and it
    # requires Thick-Skinned, so measure it against a Thick-Skinned-only baseline.
    base = _pick_trait(_fresh_at("barbarian", "Beastborn"), "Thick-Skinned")
    api = _fresh_at("barbarian", "Beastborn")
    _pick_trait(api, "Thick-Skinned")
    after = _pick_trait(api, "Hard Shell")
    ok("Beastborn Hard Shell AD +1 (unarmoured) and Move Speed -1, over a Thick-Skinned baseline",
       int(_stat(after, "AD")) - int(_stat(base, "AD")) == 1
       and int(_stat(after, "Move Speed")) - int(_stat(base, "Move Speed")) == -1,
       "AD %s->%s  Speed %s->%s" % (_stat(base, "AD"), _stat(after, "AD"),
                                    _stat(base, "Move Speed"), _stat(after, "Move Speed")))
    # armour worn => the unarmoured half must NOT apply (the documented name-match heuristic)
    api = _fresh_at("barbarian", "Dwarf")
    api.ledger.setdefault("equipment", []).append({"name": "Half Plate Armor"})
    s = _pick_trait(api, "Thick-Skinned")
    armoured_ad = int(_stat(s, "AD"))
    api2 = _fresh_at("barbarian", "Dwarf")
    api2.ledger.setdefault("equipment", []).append({"name": "Half Plate Armor"})
    plain_ad = int(_stat(json.loads(api2.state()), "AD"))
    ok("Thick-Skinned's unarmoured-only +1 AD does NOT apply while armour is worn",
       armoured_ad == plain_ad, "%s vs %s" % (armoured_ad, plain_ad))
    trait = [t for t in api.ledger["chargen"]["ancestry_traits"]
             if str(t.get("name")).startswith("Thick-Skinned")][0]
    ok("...and the row says so in its note",
       "NOT applied" in str(trait.get("note", "")), trait.get("note"))

    # ---- Tier-2 (2026-07-28): the engine slice. Move Speed and the per-attribute deltas are
    # DATA now, not two name-matches in build_engine.py. Six options closed, and the assertion
    # is still the derived stat: the three that already worked by name-match must keep working
    # (a refactor that changes what a player sees is a regression, not a refactor), and the
    # four that were inert must start working.
    print("## (CH5b) option-effects burn-down, Tier-2: speed + per-attribute grants")
    for anc, trait, want in (("Elf", "Speed Increase", 1),
                             ("Beastborn", "Speed Increase", 1),
                             ("Dwarf", "Short-Legged", -1),
                             ("Halfling", "Short-Legged", -1)):
        before = _stat(json.loads(_fresh_at("druid", anc).state()), "Move Speed")
        after = _stat(_pick_trait(_fresh_at("druid", anc), trait), "Move Speed")
        ok("%-9s %-16s Move Speed %+d (was an engine name-match)" % (anc, trait, want),
           int(after) - int(before) == want, "%s -> %s" % (before, after))
    # fixed-target decreases: inert before Tier-2, and each names its own attribute
    for anc, trait, attr in (("Elf", "Might Attribute Decrease", "might"),
                             ("Dwarf", "Charisma Attribute Decrease", "charisma"),
                             ("Halfling", "Intelligence Attribute Decrease", "intelligence"),
                             ("Giantborn", "Intelligence Attribute Decrease", "intelligence")):
        b = _rt_attr_val(_rt_stats(json.loads(_fresh_at("druid", anc).state())), attr)
        a = _rt_attr_val(_rt_stats(_pick_trait(_fresh_at("druid", anc), trait)), attr)
        ok("%-9s %-32s %s %+d" % (anc, trait, attr.title(), -1), a - b == -1, "%s -> %s" % (b, a))
    # the two TARGETED options: the picker offers per-attribute variants and the chosen target
    # is the one that moves, which is the half a fixed-target row cannot prove
    for trait, want in (("Attribute Increase", 1), ("Attribute Decrease", -1)):
        for attr in ("charisma", "intelligence"):
            pick = "%s (%s)" % (trait, attr)
            other = "might" if attr != "might" else "agility"
            base = _rt_stats(json.loads(_fresh_at("druid", "Human").state()))
            got = _rt_stats(_pick_trait(_fresh_at("druid", "Human"), pick))
            ok("Human    %-32s %s %+d, and %s does not move"
               % (pick, attr.title(), want, other.title()),
               _rt_attr_val(got, attr) - _rt_attr_val(base, attr) == want
               and _rt_attr_val(got, other) == _rt_attr_val(base, other),
               "%s %s->%s  %s %s->%s" % (attr, _rt_attr_val(base, attr), _rt_attr_val(got, attr),
                                         other, _rt_attr_val(base, other),
                                         _rt_attr_val(got, other)))
    # the rules floor: "to a minimum of -2" (ancestries.md l.352). A decrease at the floor is a
    # legal pick that correctly moves nothing, so this is the one case where "it did not move"
    # is the PASS, and it is asserted explicitly rather than left as an untested branch.
    api = _fresh_at("druid", "Human")
    api.set_attr("charisma", -2)
    floor_before = _rt_attr_val(_rt_stats(json.loads(api.state())), "charisma")
    floor_after = _rt_attr_val(_rt_stats(_pick_trait(api, "Attribute Decrease (charisma)")),
                               "charisma")
    # "it did not move" is the PASS here, which is also what a BROKEN pick looks like, so the same
    # pick is driven on an unclamped probe in the same breath. Only the pair distinguishes a
    # working clamp from target resolution having silently stopped working.
    api2 = _fresh_at("druid", "Human")
    api2.set_attr("charisma", 0)
    unclamped = _rt_attr_val(_rt_stats(_pick_trait(api2, "Attribute Decrease (charisma)")),
                             "charisma")
    ok("Human    Attribute Decrease clamps at -2 while the same pick still moves 0 -> -1",
       floor_before == -2 and floor_after == -2 and unclamped == -1,
       "floor %s -> %s, unclamped 0 -> %s" % (floor_before, floor_after, unclamped))
    # an ancestry trait taken AT A LEVEL moves the attribute too. The name-match this replaced
    # read only the chargen list, so this case was silently inert; sum_grants walks both.
    eng = builder_api.eng
    led = {"chargen": {}, "levels": {2: [{"slot": "ancestry_trait",
                                          "pick": "Attribute Increase (might)",
                                          "grants": {"attr_might": 1}}]}}
    ok("a level-taken attribute grant is counted (the name-match read chargen only)",
       eng.attribute_deltas(led, 2)["might"] == 1 and eng.attribute_deltas(led, 1)["might"] == 0,
       "L2=%s L1=%s" % (eng.attribute_deltas(led, 2), eng.attribute_deltas(led, 1)))
    # an unresolved placeholder must be LOUD, not inert: that failure mode is the entire
    # BUG-19/22/24/25/27/30/36 family, so the engine reports it instead of ignoring it.
    stray = {"chargen": {"ancestry_traits": [{"name": "Attribute Increase",
                                              "grants": {"attribute": 1}}]}, "levels": {}}
    ok("an unresolved `attribute` grant is reported, not silently dropped",
       eng.unresolved_attribute_grants(stray, 1) == 1,
       eng.unresolved_attribute_grants(stray, 1))
    # Tanrielle is the atomic-change guard: she holds Speed Increase (L4) AND Attribute
    # Increase (Might) (chargen), so a half-landed CH-5 shows up as Move Speed 5 / Might 1.
    tan = yaml.safe_load(open(os.path.join(REPO, "builds", "tanrielle.yaml"), encoding="utf-8"))
    trep = builder_api.eng.replay(tan, 4)
    ok("tanrielle canon: Move Speed 6 and Might 2 both still derive (CH-5 atomicity)",
       trep.derived.get("move") == 6 and builder_api.eng.attribute_deltas(tan, 4)["might"] == 1,
       "move=%s attr_might delta=%s" % (trep.derived.get("move"),
                                        builder_api.eng.attribute_deltas(tan, 4)["might"]))


def check_bug33_class_talents():
    """BUG-33 (2026-07-27): _talent_options OFFERED class_talents but both talent lookups read only
    general + mc_features, so every class talent that carries an effect applied nothing. Same
    duplicate-list root cause as BUG-31/32, so the guard is the anti-mirror one: every name the
    picker offers must resolve in the row list the pick path uses."""
    print("## (CT) class talents: offered rows resolve and apply their grants (BUG-33)")
    for cls in ("barbarian", "spellblade", "warlock", "commander", "druid"):
        api = _fresh_at(cls, "Human")
        offered = {o["name"] for o in api._talent_options()}
        rows = {r["name"] for r in api._talent_rows()}
        ok("%-11s every offered talent resolves in _talent_rows" % cls,
           offered <= rows, sorted(offered - rows)[:5])
    # and the effects actually land, one per shape: a flat numeric grant and a child-slot grant
    api = _fresh_at("barbarian", "Human", levels=3)
    s = json.loads(api.state())
    d = [x for x in s["decisions"] if x["slot"] == "talent"
         and "Unfathomable Strength" in [o["name"] for o in x["options"]]][-1]
    before = _stat(s, "Jump Distance")
    after = _stat(json.loads(api.set_decision(d["id"], "Unfathomable Strength")), "Jump Distance")
    ok("Barbarian Unfathomable Strength grants +1 Jump Distance (Titanic Leap)",
       int(after) - int(before) == 1, "%s -> %s" % (before, after))
    api = _fresh_at("spellblade", "Human", levels=3)
    s = json.loads(api.state())
    d = [x for x in s["decisions"] if x["slot"] == "talent"
         and "Expanded Disciplines" in [o["name"] for o in x["options"]]][-1]
    n_before = len([x for x in s["decisions"] if x["slot"] == "discipline"])
    s2 = json.loads(api.set_decision(d["id"], "Expanded Disciplines"))
    n_after = len([x for x in s2["decisions"] if x["slot"] == "discipline"])
    ok("Spellblade Expanded Disciplines spawns 2 discipline child-pickers",
       n_after - n_before == 2, "%d -> %d" % (n_before, n_after))
    api = _fresh_at("warlock", "Human", levels=3)
    s = json.loads(api.state())
    d = [x for x in s["decisions"] if x["slot"] == "talent"
         and "Pact Bane" in [o["name"] for o in x["options"]]][-1]
    before = _stat(s, "Spells known")
    after = _stat(json.loads(api.set_decision(d["id"], "Pact Bane")), "Spells known")
    ok("Warlock Pact Bane raises Spells known by 1",
       int(after) - int(before) == 1, "%s -> %s" % (before, after))


def _earned_tp(s):
    """Trade points EARNED, read off the budgets readout (the surface a player actually sees)."""
    for b in s["budgets"]:
        if b.startswith("Trade points"):
            return int(re.search(r"earned (\d+)", b).group(1))
    return None


def _sub_pick(api, name):
    s = json.loads(api.state())
    d = [x for x in s["decisions"] if x["slot"] == "subclass"][-1]
    return d, json.loads(api.set_decision(d["id"], name))


def check_bug35_paragon():
    """BUG-35 (2026-07-27): Paragon is the one UNIVERSAL subclass and it granted NOTHING on any of
    the five classes. RAW (character-creation.md l.757-780): Novice Paragon at L3 = a Class Talent
    of your choice FROM YOUR CLASS, plus Jack of one Trade = 1 Trade Point; Expert (L7) and Master
    (L10) each grant another Class Talent.

    The Class Talent is a REAL sibling entry, not a grant-child, because a class talent carries its
    own grants and a grant-child is treated as a leaf (BUG-34). So the checks below assert the two
    halves that matter: the picker is narrowed to this class's class talents, and a talent picked
    through it moves the derived stat. Plus the artifact (trap 3): it must reach the sheet."""
    print("## (PG) Paragon subclass: class-talent rider + Trade Point, all five classes (BUG-35)")
    UND = "(undecided)"
    for cls in ("barbarian", "spellblade", "warlock", "commander", "druid"):
        api = _fresh_at(cls, "Human", levels=2)      # -> current level 3, where Subclass is chosen
        s0 = json.loads(api.state())
        d, s = _sub_pick(api, "Paragon")
        riders = [x for x in s["decisions"] if x.get("restrict") == "class_talents"]
        want = [r["name"] for r in
                (api.cat["talents"].get("class_talents") or {}).get(api.cls, [])]
        ok("%-11s Paragon spawns exactly 1 class-talent picker at L3" % cls,
           len(riders) == 1 and riders[0]["level"] == 3,
           [(x["level"], x["slot"]) for x in riders])
        ok("%-11s ...offering this class's class talents and nothing else" % cls,
           bool(want) and riders and [o["name"] for o in riders[0]["options"]] == want,
           riders and [o["name"] for o in riders[0]["options"]])
        ok("%-11s ...and Jack of one Trade adds 1 Trade Point" % cls,
           _earned_tp(s) - _earned_tp(s0) == 1,
           "%s -> %s" % (_earned_tp(s0), _earned_tp(s)))
        # re-picking a DIFFERENT subclass takes the rider and the trade point with it
        other = [o["name"] for o in d["options"] if o["name"] != "Paragon"][0]
        s2 = json.loads(api.set_decision(d["id"], other))
        ok("%-11s ...both are withdrawn when the subclass changes (-> %s)" % (cls, other),
           not [x for x in s2["decisions"] if x.get("restrict")]
           and _earned_tp(s2) == _earned_tp(s0),
           "%d rider(s), TP %s" % (len([x for x in s2["decisions"] if x.get("restrict")]),
                                   _earned_tp(s2)))
    # the granted talent APPLIES its grants (the whole point of it being a real entry, not a child)
    api = _fresh_at("barbarian", "Human", levels=2)
    before = _stat(json.loads(api.state()), "Jump Distance")
    _, s = _sub_pick(api, "Paragon")
    r = [x for x in s["decisions"] if x.get("restrict")][0]
    s = json.loads(api.set_decision(r["id"], "Unfathomable Strength"))
    ok("a Paragon-granted class talent applies its grant (+1 Jump Distance)",
       int(_stat(s, "Jump Distance")) - int(before) == 1,
       "%s -> %s" % (before, _stat(s, "Jump Distance")))
    sh = json.loads(api.sheet())
    ok("...and reaches the character sheet's talent group",
       any(t.get("pick") == "Unfathomable Strength"
           for t in (sh.get("abilities") or {}).get("talent") or []),
       (sh.get("abilities") or {}).get("talent"))
    # a child-slot grant still spawns its children through the rider (Spellblade)
    api = _fresh_at("spellblade", "Human", levels=2)
    _, s = _sub_pick(api, "Paragon")
    n0 = len([x for x in s["decisions"] if x["slot"] == "discipline"])
    r = [x for x in s["decisions"] if x.get("restrict")][0]
    s = json.loads(api.set_decision(r["id"], "Expanded Disciplines"))
    ok("a Paragon-granted Expanded Disciplines still spawns its 2 discipline child-pickers",
       len([x for x in s["decisions"] if x["slot"] == "discipline"]) - n0 == 2,
       "%d -> %d" % (n0, len([x for x in s["decisions"] if x["slot"] == "discipline"])))
    # L7 / L10: the next Class Talent arrives with the level, and the L3 pick survives the re-sync
    api = _fresh_at("spellblade", "Human", levels=2)
    _, s = _sub_pick(api, "Paragon")
    r = [x for x in s["decisions"] if x.get("restrict")][0]
    json.loads(api.set_decision(r["id"], "Sling-Blade"))
    for _ in range(4):                                  # L3 -> L7
        s = json.loads(api.add_level())
    got = sorted((x["level"], x["pick"]) for x in s["decisions"] if x.get("restrict"))
    ok("Expert Paragon adds a second class-talent picker at L7, L3's pick untouched",
       got == [(3, "Sling-Blade"), (7, UND)], got)
    for _ in range(3):                                  # L7 -> L10
        s = json.loads(api.add_level())
    got = sorted((x["level"], x["pick"]) for x in s["decisions"] if x.get("restrict"))
    ok("Master Paragon adds a third at L10, earlier picks untouched",
       got == [(3, "Sling-Blade"), (7, UND), (10, UND)], got)
    # a PLANNED L7 gets its rider too, and it is fillable (FR-3)
    api = _fresh_at("commander", "Human", levels=2)
    _sub_pick(api, "Paragon")
    for _ in range(4):
        s = json.loads(api.add_planned_level())
    plan = [x for x in s["decisions"] if x.get("restrict") and x["level"] == 7]
    ok("a planned L7 carries the Expert Paragon picker and it is editable",
       len(plan) == 1 and plan[0]["plan"] and plan[0]["editable"], plan)


def check_bug34_grant_child_effects():
    """BUG-34 (2026-07-27, Darryl in Chrome; shape (a), his call). The FR-8 child machinery assumed
    every grant-child is a LEAF, so a grant-bearing child applied nothing: a Magus picked under
    Expanded Disciplines moved neither MP nor Spells, while the same Magus picked first-class moved
    both. The fix keeps the DECLARED grant (`grants: {disciplines: 2}`) and the DERIVED total
    (`granted_effects`) in separate keys and sums both in the engine.

    The checks below deliberately measure the FIRST-CLASS pick and the CHILD pick against each
    other: the whole bug was the two paths disagreeing, so equality is the property worth asserting,
    not a hard-coded number that would drift with the catalog."""
    print("## (GE) grant-bearing grant-children apply their own effects (BUG-34)")
    STATS = ("MP", "Spells known", "Maneuvers known")

    def snap(s):
        return tuple(int(_stat(s, k)) for k in STATS)

    # first-class reference: a chargen discipline pick, the path that always worked
    ref = _fresh_at("spellblade", "Human")
    s0 = json.loads(ref.state())
    ch = [x for x in s0["decisions"] if x["slot"] == "discipline"]
    base = snap(s0)
    magus_first = snap(json.loads(ref.set_decision(ch[0]["id"], "Magus")))
    warrior_first = snap(json.loads(ref.set_decision(ch[1]["id"], "Warrior")))
    ok("reference: a first-class Magus moves MP and Spells",
       tuple(a - b for a, b in zip(magus_first, base)) == (1, 1, 0),
       "%s -> %s" % (base, magus_first))
    # the same two disciplines, this time as grant-children of Expanded Disciplines
    api = _fresh_at("spellblade", "Human", levels=2)
    s = json.loads(api.state())
    d = [x for x in s["decisions"] if x["slot"] == "subclass"][-1]
    s = json.loads(api.set_decision(d["id"], "Paragon"))
    r = [x for x in s["decisions"] if x.get("restrict")][0]
    s = json.loads(api.set_decision(r["id"], "Expanded Disciplines"))
    kids = [x for x in s["decisions"]
            if x["slot"] == "discipline" and str(x["id"]).startswith("GC#")]
    ok("Expanded Disciplines spawns 2 grant-children", len(kids) == 2, [k["id"] for k in kids])
    cbase = snap(s)
    s = json.loads(api.set_decision(kids[0]["id"], "Magus"))
    ok("a GRANTED Magus applies its own +1 MP / +1 spell, same as first-class",
       tuple(a - b for a, b in zip(snap(s), cbase))
       == tuple(a - b for a, b in zip(magus_first, base)),
       "%s -> %s" % (cbase, snap(s)))
    mid = snap(s)
    s = json.loads(api.set_decision(kids[1]["id"], "Warrior"))
    ok("a GRANTED Warrior applies its own +1 maneuver, same as first-class",
       tuple(a - b for a, b in zip(snap(s), mid))
       == tuple(a - b for a, b in zip(warrior_first, magus_first)),
       "%s -> %s" % (mid, snap(s)))
    parent = [e for lv in api.ledger["levels"] for e in api.ledger["levels"][lv]
              if e.get("granted_disciplines")][0]
    ok("the DECLARED grant is left alone; the derived total lives in granted_effects",
       parent.get("grants") == {"disciplines": 2}
       and parent.get("granted_effects") == {"mp": 1, "spells": 1, "maneuvers": 1},
       (parent.get("grants"), parent.get("granted_effects")))
    # re-picking a child REBUILDS the derived dict rather than accumulating into it
    s = json.loads(api.set_decision(kids[0]["id"], "Acolyte"))   # Acolyte is no_effect
    ok("re-picking a child rebuilds granted_effects (Magus -> Acolyte drops its half)",
       parent.get("granted_effects") == {"maneuvers": 1}
       and tuple(a - b for a, b in zip(snap(s), cbase)) == (0, 0, 1),
       (parent.get("granted_effects"), cbase, snap(s)))
    # combat training: the non-numeric half, on BOTH paths, and it must reach the sheet
    ok("a granted Warrior brings its combat training to the sheet",
       json.loads(api.sheet()).get("combat_training") == ["Heavy Armor", "Heavy Shield"],
       json.loads(api.sheet()).get("combat_training"))
    ok("...and so does a first-class Warrior (the gap was on every path)",
       json.loads(ref.sheet()).get("combat_training") == ["Heavy Armor", "Heavy Shield"],
       json.loads(ref.sheet()).get("combat_training"))
    canon = builder_api.BuilderAPI("xanwyn", CATPATHS)
    # FR-48 guard: with nothing granted and no base list, the sheet must render NO training row
    # rather than "None recorded", which would read as "trained in nothing" on a scratch build.
    bare = _fresh_at("spellblade", "Human")
    ok("a scratch build with no granted training reports an empty list (row hidden, not 'None')",
       json.loads(bare.sheet()).get("combat_training") == [],
       json.loads(bare.sheet()).get("combat_training"))
    page = open(os.path.join(REPO, "builds", "builder.html"), encoding="utf-8").read()
    ok("...and the GENERATED page emits that row conditionally (ctRow), never a bare placeholder",
       "const ctRow=ct.length" in page and "Combat Training</span>" in page,
       "ctRow guard missing from the generated sheet renderer")
    ok("a canon ledger still shows its hand-authored combat training, unchanged",
       json.loads(canon.sheet()).get("combat_training")
       == ["Weapons", "Spell Focuses", "Light Armor", "Light Shields"],
       json.loads(canon.sheet()).get("combat_training"))
    # the BUG-21 sibling path: a SUBCLASS that grants a discipline routes through the same code
    api = _fresh_at("spellblade", "Human", levels=2)
    s = json.loads(api.state())
    d = [x for x in s["decisions"] if x["slot"] == "subclass"][-1]
    s = json.loads(api.set_decision(d["id"], "Paladin"))   # grants 1 discipline, pre-filled Acolyte
    kid = [x for x in s["decisions"]
           if x["slot"] == "discipline" and str(x["id"]).startswith("GC#")]
    pbase = snap(s)
    ok("Paladin's granted discipline slot exists and pre-fills Acolyte (BUG-21 intact)",
       len(kid) == 1 and kid[0]["pick"] == "Acolyte", kid and kid[0]["pick"])
    if kid:
        s = json.loads(api.set_decision(kid[0]["id"], "Magus"))
        ok("...and swapping it to Magus applies +1 MP / +1 spell through the subclass path too",
           tuple(a - b for a, b in zip(snap(s), pbase)) == (1, 1, 0),
           "%s -> %s" % (pbase, snap(s)))
    # all six canon ledgers are untouched by the load-time resync (the PARTY_DERIVED guarantee)
    for h in ("tanrielle", "runt", "minimus", "bonan", "scaletrix", "xanwyn"):
        a = builder_api.BuilderAPI(h, CATPATHS)
        found = [e for e in _all_grant_bearers(a.ledger) if e.get("granted_effects")]
        ok("%-10s load-time resync adds no granted_effects (PARTY_DERIVED safe)" % h,
           not found, found[:2])


# ------------------------------------------- (RT) FR-46 exhaustive option round-trip
# FR-44 built the option-coverage ledger: every one of the catalog's pickable options
# DECLARES what it does (`modelled` with a real effect, `no_effect: <category>`, or `todo`).
# Nothing executed that declaration, so the gap between "declared" and "actually arrives in
# the model" stayed invisible, and it is exactly where BUG-19/22/24/25/27/30/33 all lived.
#
# This section makes the ledger EXECUTABLE. For every option declared `modelled` it drives a
# scratch build, PICKS the option, and asserts the declared effect materialises in the state
# the page renders from. It is exhaustive rather than exemplary: the guards we write by hand
# cover the case we just fixed, this covers the ones nobody has thought about yet.
#
# Three properties are what make it a structural answer rather than another narrow guard:
#
#   1. The option list is DISCOVERED (coverage.walk_options), never hand-kept, so a new
#      catalog option enters this check automatically.
#   2. Every modelled option must be REACHABLE by the probe fleet. An option the fleet cannot
#      reach is a FAILURE, not a silent skip, unless it is in RT_UNREACHABLE with a reason,
#      and every RT_UNREACHABLE entry is itself asserted to still be unreachable.
#   3. Every grant KEY the catalog uses must appear in exactly one assertion table below.
#      An unrecognised key FAILS. That is what stops a new grant key shipping unasserted,
#      which is the trap-2 "never hand-maintain a list that mirrors another list" rule
#      applied to this harness itself.
#
# A note on observability, learned while building this: a probe whose BASELINE already carries
# the effect proves nothing. Mighty Leap (`jump_from: might`) looks inert on a Barbarian because
# Berserker already re-keyed jump to Might at L1. So the ancestry probes run on a Druid, and the
# flag assertion explicitly requires the baseline NOT to carry the flag already.

# grant key -> the derived-stat row it must move by the granted amount
RT_STAT = {"hp": "HP", "mp": "MP", "pd": "PD", "ad": "AD",
           "speed": "Move Speed", "jump": "Jump Distance"}
# grant key -> the state() budget field it must raise by the granted amount
RT_BUDGET = {"spells": "spell_budget", "maneuvers": "man_budget"}
# grant key -> the state()['budgets'] point readout whose "earned" must rise
RT_POINTS = {"skill_points": "Skill points", "trade_points": "Trade points"}
# grant key -> it must spawn that many `attribute` rider decisions
RT_ATTR_SLOTS = {"attribute_points"}
# grant key -> it must raise the ancestry-point budget
RT_ANC_POINTS = {"ancestry_points"}
# NON-numeric flag grants: key -> the derived stat that must re-key when the flag lands
RT_FLAG = {"jump_from": "Jump Distance"}

# Modelled options the probe fleet legitimately cannot reach, each with the reason. Asserted
# in BOTH directions: a stale entry (the option became reachable) fails loudly, so these get
# retired when a fifth class or the BUG-26 multiclass route arrives.
RT_UNREACHABLE = {
    "Expanded Meta Magic":
        "Sorcerer class talent; Sorcerer is not one of the five playable classes and no "
        "MC feature unlocks another class's talent list (see BUG-26)",
    "Greater Innate Power":
        "Sorcerer class talent; as above",
    "Expanded Spell School":
        "Wizard class talent; Wizard is not a playable class",
}

# Modelled options that are FIXED class features rather than picks: they carry an effect but
# there is no picker to drive, so the round-trip asserts the effect on a plain scratch build
# of the class. Value is the class that gets it at L1.
RT_FIXED = {"Berserker": "barbarian",
            "Spellblade Disciplines": "spellblade",
            "Pact Boon": "warlock"}

# Declared `modelled` but the effect does NOT arrive: a real open bug, filed, so the check
# records the failure without turning the suite red. Same discipline as builder_smoke.py's
# KNOWN_FAIL registry: if one of these starts PASSING, that is a FAILURE, so the entry is
# retired with the fix instead of rotting.
# EMPTY is the goal state, not a bug in this file. BUG-36 ("Ancestry Increase") was the only
# entry and was retired 2026-07-28 when the fix landed; the option is now asserted for real by
# _rt_assert_grants via RT_ANC_POINTS. Re-populate this only with a filed bug ID.
RT_KNOWN_FAIL = {}

# RT_NAME_MATCHED / RT_VARIANT_MATCHED were RETIRED by CH-5 (2026-07-28), which is what those
# registries existed for. Speed Increase and Short-Legged now declare {speed: +/-1} and flow
# through RT_STAT like any other grant; Attribute Increase / Attribute Decrease declare a
# targeted grant and are driven through _rt_variant_pick below. Every remaining `todo` option is
# asserted INERT, so _rt_check_todos no longer needs an exception list at all.

# The target used when driving a `targets: attributes` option. CHARISMA on purpose: the probe
# fleet buys cha 0, so it is clear of BOTH the ATTR_FLOOR (-2, where a decrease would correctly
# fail to move) and the L1 attribute limit (3, where an increase would trip a problem line). A
# probe whose baseline sits on a boundary proves nothing, which is the same lesson as Mighty Leap.
RT_ATTR_TARGET = "charisma"


def _rt_attr_keys():
    """{grant key -> attribute} for the per-attribute keys, DERIVED from the engine's own tuple.

    Never a hand-kept copy: if the engine gains or renames an attribute this follows it, which
    is the trap-2 rule applied to this harness (BUG-31/32/33 were all mirrored lists)."""
    eng = builder_api.eng
    return {eng.ATTR_GRANT_PREFIX + a: a for a in eng.ATTRIBUTES}


def _rt_attrs(stats):
    """Parse the derived "Attributes" row ("Mig 3 / Agi 1 / Cha 0 / Int 0") into {attr: value}.

    Asserting against the RENDERED row rather than the engine's internal dict is deliberate
    (trap 3: assert the artifact). This row is what the page and the sheet show."""
    out = {}
    for part in str(stats.get("Attributes", "")).split("/"):
        bits = part.split()
        if len(bits) == 2:
            out[bits[0].lower()] = int(bits[1])
    return out


def _rt_attr_val(stats, attr):
    return _rt_attrs(stats).get(str(attr)[:3].lower())


def _rt_variant_pick(row, name, grants):
    """(pick_name, resolved_grants) for a `targets: attributes` option, else (name, grants).

    The picker offers decorated variants ("Attribute Decrease (charisma)") because a target-less
    pick means nothing to the engine, and the builder rewrites the placeholder `attribute` grant
    key to attr_<target> on pick. The round-trip therefore has to drive the variant and expect
    the resolved key, both derived from the catalog row rather than listed by name here."""
    if row.get("targets") != "attributes" or "attribute" not in (grants or {}):
        return name, grants
    resolved = dict(grants)
    resolved[builder_api.eng.ATTR_GRANT_PREFIX + RT_ATTR_TARGET] = resolved.pop("attribute")
    return "%s (%s)" % (name, RT_ATTR_TARGET), resolved

# Option names that produced at least one real assertion this run. Populated by _rt_ok and
# checked at the end: a modelled option that asserts nothing is a FAILURE, not a pass.
RT_ASSERTED = set()


def _rt_ok(option_name, label, cond, detail=""):
    """ok() that also records the option as having been genuinely asserted."""
    RT_ASSERTED.add(option_name)
    ok(label, cond, detail)


def _rt_stats(s):
    return {r[0]: r[1] for r in s["stats"]}


def _rt_num(v):
    """First integer in a stat cell ('12', '6', 'Mig 3 / ...' -> 3 is not wanted, so callers
    only use this on single-number rows)."""
    try:
        return int(str(v).split()[0])
    except (ValueError, IndexError):
        return None


def _rt_earned(s, label):
    """The 'earned N' number out of the state()['budgets'] readout line for `label`."""
    for line in s["budgets"]:
        if line.startswith(label):
            m = re.search(r"earned (\d+)", line)
            if m:
                return int(m.group(1))
    return None


def _rt_snap(api):
    """Everything the assertions can look at, in one shot."""
    s = json.loads(api.state())
    return {
        "s": s,
        "stats": _rt_stats(s),
        "spell_budget": s["spell_budget"], "man_budget": s["man_budget"],
        "anc_budget": s["anc_budget"],
        "skill_earned": _rt_earned(s, "Skill points"),
        "trade_earned": _rt_earned(s, "Trade points"),
        "decs": [(str(d.get("id")), d["slot"]) for d in s["decisions"]],
    }


def _rt_new_decs(before, after, slot=None, prefix=None):
    new = [d for d in after["decs"] if d not in before["decs"]]
    if slot is not None:
        new = [d for d in new if d[1] == slot]
    if prefix is not None:
        new = [d for d in new if d[0].startswith(prefix)]
    return new


def _rt_probe_ancestry(anc):
    """Druid, so no Berserker jump_from/speed grant masks an ancestry one."""
    return _fresh_at("druid", anc)


def _rt_open_trait(api):
    """Open a fresh ancestry-trait slot and return (state, decision-id, offered-names)."""
    s = json.loads(api.add_trait(1))
    d = [x for x in s["decisions"] if x["slot"] == "ancestry_trait"][-1]
    return s, d["id"], {o["name"] for o in d["options"]}


def _rt_probe_talent(cls, lvl=2):
    """A scratch `cls` advanced to `lvl` with its talent slot located."""
    api = _fresh_at(cls, "Human", levels=lvl - 1)
    s = json.loads(api.state())
    tal = [d for d in s["decisions"] if d["slot"] == "talent" and d.get("level") == lvl]
    return api, (tal[0] if tal else None)


def _rt_fleet():
    """The probe fleet, and the reachability index it produces.

    Deliberately small and shaped by what actually gates an option: ancestry traits are
    gated by ancestry, talents by class, chargen choices by class. It does NOT need to be
    the full cross-product, because the reachability assertion below PROVES the fleet
    covers every modelled option rather than assuming it.

    Returns {option name -> [(probe label, slot)]}.
    """
    index = {}

    def note(name, label, slot):
        index.setdefault(name, []).append((label, slot))

    _anccat = yaml.safe_load(open(CATPATHS["ancestries"], encoding="utf-8"))["ancestries"]
    _targeted = {r["name"] for rows in _anccat.values() if isinstance(rows, list)
                 for r in rows if isinstance(r, dict) and r.get("targets") == "attributes"}
    ancestries = sorted(_anccat)
    for anc in ancestries:
        api = _rt_probe_ancestry(anc)
        _, _, offered = _rt_open_trait(api)
        for name in offered:
            note(name, "druid/%s L1" % anc, "ancestry_trait")
            # CH-5: a `targets: attributes` row is only ever OFFERED as decorated variants
            # ("Attribute Decrease (charisma)"), so also register the catalog name the coverage
            # ledger knows it by, or the reachability check would call it unreachable. Gated on
            # the row really being targeted: registering every base name would hand a free
            # "reachable" to the next option that happens to carry a parenthetical, which could
            # wrongly retire an RT_UNREACHABLE entry.
            base = builder_api.base_name(name)
            if base != name and base in _targeted:
                note(base, "druid/%s L1" % anc, "ancestry_trait")

    for cls in sorted(builder_api.CLASS_NAMES):
        # chargen choices (disciplines, pact boons, spell schools) at L1
        s = json.loads(_fresh_at(cls, "Human").state())
        for d in s["decisions"]:
            for o in (d.get("options") or []):
                note(o["name"], "%s L1" % cls, d["slot"])
        # talents at L2
        api, tal = _rt_probe_talent(cls, 2)
        if tal:
            for o in tal["options"]:
                note(o["name"], "%s L2" % cls, "talent")
    return index


def check_fr46_round_trip():
    print("## (RT) FR-46: exhaustive option round-trip (every declared effect must ARRIVE)")
    import coverage                                    # noqa: PLC0415  (repo-local, tools/)
    options, _ = coverage.walk_options()
    modelled = [o for o in options if o.kind == "modelled"]
    todos = [o for o in options if o.kind == "todo"]

    # ---- 0. the ledger this section executes is the one catalog_verify reports
    ok("the coverage ledger walks the whole option surface (231+ options, 44 modelled)",
       len(options) >= 231 and len(modelled) >= 44,
       "%d options, %d modelled" % (len(options), len(modelled)))

    # ---- 1a. every modelled option's catalog row must RESOLVE, and must still carry the
    # effect keys coverage.py classified it by. Without this the section can pass vacuously:
    # an unresolvable row yields {}, which asserts nothing at all and prints nothing either.
    unresolved = []
    for o in modelled:
        row = _rt_catalog_row(o)
        if not row or not (coverage.EFFECT_KEYS & set(row)):
            unresolved.append("%s/%s/%s" % (o.filename, o.path, o.name))
    ok("every modelled option's catalog row resolves and still carries its effect keys",
       not unresolved, unresolved)

    # ---- 1b. every grant KEY in the catalog is covered by an assertion table above.
    # An unknown key fails here rather than passing silently downstream, which is the whole
    # point: a new grant key cannot ship unasserted.
    # `attribute` is the placeholder key a `targets: attributes` row declares; it is asserted
    # through _rt_variant_pick, which resolves it to the attr_<target> key the engine reads.
    known = (set(RT_STAT) | set(RT_BUDGET) | set(RT_POINTS) | RT_ATTR_SLOTS
             | RT_ANC_POINTS | set(RT_FLAG) | set(builder_api.GRANT_CHILD_SLOTS)
             | set(_rt_attr_keys()) | {"attribute"})
    used = set()
    for o in modelled:
        row = _rt_catalog_row(o)
        for key in ("grants", "grants_unarmored"):
            used |= set((row.get(key) or {}))
    ok("every grant key the catalog uses has an assertion table (unknown key = FAIL)",
       used <= known, "unasserted keys: %s" % sorted(used - known))

    # ---- 2. reachability: the fleet must reach every modelled option
    index = _rt_fleet()
    unreached = sorted({o.name for o in modelled
                        if o.name not in index and o.name not in RT_FIXED})
    ok("the probe fleet reaches every modelled option it is supposed to",
       set(unreached) == set(RT_UNREACHABLE), "unreached=%s expected=%s"
       % (unreached, sorted(RT_UNREACHABLE)))
    for name, why in sorted(RT_UNREACHABLE.items()):
        # a stale entry (it became reachable) must fail, so these get retired not rotted
        ok("RT_UNREACHABLE %-22s still genuinely unreachable" % name,
           name not in index, "now reachable via %s - retire the entry (%s)"
           % (index.get(name), why))
    for name in sorted(RT_FIXED):
        ok("RT_FIXED %-24s is a fixed class feature, so no picker offers it" % name,
           name not in index, "now offered as a pick via %s" % (index.get(name),))

    # ---- 3. the round-trip itself, per modelled option
    RT_ASSERTED.clear()
    for o in sorted(modelled, key=lambda x: (x.filename, x.path, x.name)):
        _rt_check_option(o, index)

    # ---- 4. the fixed class features: effect applied without a pick
    _rt_check_fixed(modelled)

    # ---- 4b. no modelled option may pass by asserting NOTHING. This is the guard against the
    # failure mode this section itself shipped with on the first run: the three fixed class
    # features resolved to an empty catalog row, so the dispatch below ran zero assertions for
    # them and the section still printed PASS. Silence is now a failure.
    want = {o.name for o in modelled} - set(RT_UNREACHABLE)
    silent = sorted(want - set(RT_ASSERTED))
    ok("every reachable modelled option produced at least one assertion (silence = FAIL)",
       not silent, "asserted nothing: %s" % silent)

    # ---- 5. the todo burn-down: which of the 11 are genuinely inert?
    _rt_check_todos(todos)


def _rt_catalog_row(o):
    """The raw catalog dict behind a coverage Option (re-read, so nothing is mirrored).

    Returns {} when the row cannot be resolved, which is a BUG in this harness rather than in
    the catalog, so check_fr46_round_trip asserts every modelled option resolves. That check
    exists because the first cut of this function walked the path with string keys only, and
    class_features.yaml keys its levels as INTEGERS (`classes.Barbarian.1`). All three fixed
    class features silently resolved to {} and their assertions vanished without a failure:
    the empty-list-passes-vacuously trap, inside the very section meant to catch it.
    """
    data = yaml.safe_load(open(CATPATHS[o.filename[:-5]], encoding="utf-8"))
    node = data
    for part in o.path.split("."):
        if not isinstance(node, dict):
            return {}
        if part in node:
            node = node[part]
        else:
            try:                                  # class_features.yaml keys levels as ints
                node = node[int(part)]
            except (ValueError, KeyError):
                return {}
    if isinstance(node, list):
        for row in node:
            if isinstance(row, dict) and row.get("name") == o.name:
                return row
    return {}


def _rt_assert_grants(name, label, before, after, grants, unarmored=False):
    """The assertion table applied: every key in `grants` must be observable."""
    for key, amount in sorted(grants.items()):
        tag = "%s %s%s" % (label, key, " (unarmored)" if unarmored else "")
        _rt = lambda lbl, cond, det="": _rt_ok(name, lbl, cond, det)   # noqa: E731
        if key in RT_FLAG:
            # A non-numeric flag (jump_from: might) re-keys which attribute feeds the stat, so
            # the assertion is "the stat changed", and it is only meaningful on a probe whose
            # baseline does NOT already carry the flag. That is why the ancestry probes are
            # Druids: on a Barbarian, Berserker has already re-keyed jump at L1 and Mighty Leap
            # looks inert. If this ever fails, check the probe before the engine.
            stat = RT_FLAG[key]
            _rt("%-64s re-keys %s (baseline must not already carry it)" % (tag, stat),
               after["stats"].get(stat) != before["stats"].get(stat),
               "%s unchanged at %r - is the flag already granted on this probe?"
               % (stat, before["stats"].get(stat)))
        elif key in RT_STAT:
            stat = RT_STAT[key]
            b, a = _rt_num(before["stats"].get(stat)), _rt_num(after["stats"].get(stat))
            _rt("%-64s moves %s by %+d" % (tag, stat, amount),
               b is not None and a is not None and a - b == amount, "%s -> %s" % (b, a))
        elif key in RT_BUDGET:
            fld = RT_BUDGET[key]
            _rt("%-64s raises %s by %+d" % (tag, fld, amount),
               after[fld] - before[fld] == amount,
               "%s -> %s" % (before[fld], after[fld]))
        elif key in RT_POINTS:
            fld = "skill_earned" if key == "skill_points" else "trade_earned"
            _rt("%-64s raises %s earned by %+d" % (tag, RT_POINTS[key], amount),
               (after[fld] or 0) - (before[fld] or 0) == amount,
               "%s -> %s" % (before[fld], after[fld]))
        elif key in _rt_attr_keys():
            attr = _rt_attr_keys()[key]
            b, a = (_rt_attr_val(before["stats"], attr), _rt_attr_val(after["stats"], attr))
            _rt("%-64s moves %s by %+d" % (tag, attr.title(), amount),
               b is not None and a is not None and a - b == amount, "%s -> %s" % (b, a))
        elif key in RT_ATTR_SLOTS:
            new = _rt_new_decs(before, after, slot="attribute")
            _rt("%-64s spawns %d attribute rider(s)" % (tag, amount),
               len(new) == amount, [d[0] for d in new])
        elif key in RT_ANC_POINTS:
            _rt("%-64s raises the ancestry-point budget by %+d" % (tag, amount),
               after["anc_budget"] - before["anc_budget"] == amount,
               "%s -> %s" % (before["anc_budget"], after["anc_budget"]))
        elif key in builder_api.GRANT_CHILD_SLOTS:
            slot = builder_api.GRANT_CHILD_SLOTS[key]
            new = _rt_new_decs(before, after, slot=slot, prefix="GC#")
            _rt("%-64s spawns %d %s child picker(s)" % (tag, amount, slot),
               len(new) == amount, [d[0] for d in new])
        else:
            _rt("%-64s has an assertion table entry" % tag, False,
               "unknown grant key %r" % key)


def _rt_check_option(o, index):
    """Drive one modelled option and assert its declared effect arrives."""
    name = o.name
    if name in RT_FIXED or name in RT_UNREACHABLE:
        return                                    # handled by _rt_check_fixed / reachability
    row = _rt_catalog_row(o)
    grants = row.get("grants") or {}
    grants_un = row.get("grants_unarmored") or {}
    pick, grants = _rt_variant_pick(row, name, grants)   # CH-5 targeted options
    where = "%s/%s" % (o.filename[:-5], o.path.split(".")[-1])
    label = "%s %s" % (where, name)
    known_bug = RT_KNOWN_FAIL.get(name)

    # --- build the right probe and pick the option
    if o.filename == "ancestries.yaml":
        anc = o.path.split(".")[-1]
        api = _rt_probe_ancestry(anc)
        before = _rt_snap(api)
        _, did, offered = _rt_open_trait(api)
        if pick not in offered:
            _rt_ok(name, "%-64s is offered on %s" % (label, anc), False, sorted(offered))
            return
        api.set_decision(did, pick)
    elif o.filename == "talents.yaml":
        cls = _rt_class_offering(name, index)
        if not cls:
            _rt_ok(name, "%-64s is offered by some class at L2" % label, False,
                   "no class offers it")
            return
        api, tal = _rt_probe_talent(cls, 2)
        before = _rt_snap(api)
        api.set_decision(tal["id"], name)
    else:
        # chargen choice children: disciplines (spellblade), pact boons (warlock)
        cls, slot = _rt_chargen_slot(name, index)
        if not cls:
            _rt_ok(name, "%-64s is offered in a chargen choice" % label, False,
                   "not found in the fleet")
            return
        api = _fresh_at(cls, "Human")
        before = _rt_snap(api)
        s = json.loads(api.state())
        d = [x for x in s["decisions"] if x["slot"] == slot
             and name in {o2["name"] for o2 in (x.get("options") or [])}][0]
        api.set_decision(d["id"], name)

    after = _rt_snap(api)

    # --- assert the declared effect
    if known_bug:
        # KNOWN_FAIL: record it, and fail if it starts working so the entry gets retired
        moved = _rt_any_movement(before, after, grants)
        _rt_ok(name, "%-64s KNOWN %s (declared effect does not arrive)" % (label, known_bug),
               not moved, "it now WORKS - retire the RT_KNOWN_FAIL entry for %s" % name)
    else:
        if grants:
            _rt_assert_grants(name, label, before, after, grants)
        if grants_un:
            _rt_assert_grants(name, label, before, after, grants_un, unarmored=True)

    if "spell_access" in row:
        _rt_assert_spell_access(name, label, before, after, row["spell_access"])
    if "choice" in row:
        _rt_assert_choice(name, label, before, after, row["choice"])
    if "opens" in row:
        _rt_assert_opens(name, label, api, row["opens"])
    if "training" in row:
        _rt_ok(name, "%-64s brings its combat training to the sheet" % label,
               set(row["training"]) <= set(json.loads(api.sheet()).get("combat_training") or []),
               json.loads(api.sheet()).get("combat_training"))


def _rt_any_movement(before, after, grants):
    """Did ANY observable the grant claims to move actually move?"""
    for key, amount in (grants or {}).items():
        if key in _rt_attr_keys():
            attr = _rt_attr_keys()[key]
            if _rt_attr_val(after["stats"], attr) != _rt_attr_val(before["stats"], attr):
                return True
        elif key in RT_STAT:
            if _rt_num(after["stats"].get(RT_STAT[key])) != _rt_num(before["stats"].get(RT_STAT[key])):
                return True
        elif key in RT_BUDGET and after[RT_BUDGET[key]] != before[RT_BUDGET[key]]:
            return True
        elif key in RT_ANC_POINTS and after["anc_budget"] != before["anc_budget"]:
            return True
        elif key in RT_POINTS:
            fld = "skill_earned" if key == "skill_points" else "trade_earned"
            if after[fld] != before[fld]:
                return True
    return False


def _rt_class_offering(name, index):
    for label, slot in index.get(name, []):
        if slot == "talent":
            return label.split()[0]
    return None


def _rt_chargen_slot(name, index):
    for label, slot in index.get(name, []):
        if "L1" in label:
            return label.split()[0], slot
    return None, None


def _rt_assert_spell_access(name, label, before, after, access):
    """A spell_access declaration must render a CONSTRAINED spell child, not a flat pool one."""
    kids = [d for d in _rt_new_decs(before, after, prefix="GC#")
            if d[1] in ("spell_sourced", "spell_any", "spell_tagged")]
    _rt_ok(name, "%-64s renders a constrained spell child (%s)"
       % (label, "any" if access.get("any") else access.get("source")),
       bool(kids), [d for d in _rt_new_decs(before, after, prefix="GC#")])
    if not kids:
        return
    want_any = bool(access.get("any"))
    _rt_ok(name, "%-64s child is %s" % (label, "an any-list slot" if want_any else "source-filtered"),
       (kids[0][1] == "spell_any") == want_any, kids[0])
    if access.get("schools"):
        dec = [d for d in after["s"]["decisions"] if str(d.get("id")) == kids[0][0]][0]
        groups = {o.get("group") for o in (dec.get("options") or [])}
        _rt_ok(name, "%-64s narrows to the declared schools %s" % (label, access["schools"]),
           groups == set(access["schools"]), sorted(groups))


def _rt_assert_choice(name, label, before, after, choice):
    """A `choice` declaration must spawn its named picker(s)."""
    slot = builder_api.SHEET_SLOT_ALIAS.get(choice, choice)
    new = [d for d in _rt_new_decs(before, after) if d[1] == slot]
    _rt_ok(name, "%-64s spawns its %r picker" % (label, slot), bool(new),
       "new decisions: %s" % _rt_new_decs(before, after))


def _rt_assert_opens(name, label, api, opened):
    """An `opens` declaration must make the named ancestry's traits offerable."""
    _, _, offered = _rt_open_trait(api)
    data = yaml.safe_load(open(CATPATHS["ancestries"], encoding="utf-8"))["ancestries"]
    want = {r["name"] for r in (data.get(opened) or []) if isinstance(r, dict)}
    _rt_ok(name, "%-64s opens the %s trait list" % (label, opened),
       bool(want & offered), "none of %d %s traits offered" % (len(want), opened))


def _rt_check_fixed(options):
    """The modelled options that are FIXED class features: there is no picker to drive, so the
    effect has to be observed a different way.

    For numeric grants the only available baseline is a class that does NOT get the feature,
    which makes this a cross-class comparison rather than a true before/after. That is weaker
    than the picked-option round-trip and it is deliberately limited to the specific stats the
    catalog row declares, so an unrelated class-table difference cannot make it pass.
    For `choice` features the assertion is exact: the declared picker must exist at L1.
    """
    by_name = {o.name: o for o in options}
    ref_cls = "druid"                     # gets none of the three
    ref = _rt_stats(json.loads(_fresh_at(ref_cls, "Human").state()))
    for name, cls in sorted(RT_FIXED.items()):
        o = by_name.get(name)
        if o is None:
            _rt_ok(name, "fixed/%-58s is still in the coverage ledger" % name, False,
                   "not found - retire the RT_FIXED entry")
            continue
        row = _rt_catalog_row(o)
        cur = _rt_stats(json.loads(_fresh_at(cls, "Human").state()))
        for key, amount in sorted((row.get("grants") or {}).items()):
            if key in RT_STAT:
                stat = RT_STAT[key]
                _rt_ok(name, "fixed/%-24s %-32s %s is %+d vs a %s"
                   % (name, key, stat, amount, ref_cls),
                   _rt_num(cur[stat]) - _rt_num(ref[stat]) == amount,
                   "%s %s vs %s %s" % (cls, cur[stat], ref_cls, ref[stat]))
            elif key in RT_FLAG:
                stat = RT_FLAG[key]
                _rt_ok(name, "fixed/%-24s %-32s re-keys %s vs a %s" % (name, key, stat, ref_cls),
                   _rt_num(cur[stat]) != _rt_num(ref[stat]),
                   "%s %s vs %s %s" % (cls, cur[stat], ref_cls, ref[stat]))
        if "choice" in row:
            slot = builder_api.SHEET_SLOT_ALIAS.get(row["choice"], row["choice"])
            s = json.loads(_fresh_at(cls, "Human").state())
            got = [d for d in s["decisions"] if d["slot"] == slot]
            _rt_ok(name, "fixed/%-24s spawns its %r picker(s) at L1 without a pick" % (name, slot),
               bool(got), sorted({d["slot"] for d in s["decisions"]}))


def _rt_check_todos(todos):
    """The CH-5 burn-down, answered: a `todo` declares an effect that is NOT modelled, so the
    expectation is that nothing moves, and an option that DOES move must be re-declared
    `modelled`. The two name-matched exceptions this used to carry were retired by CH-5
    (2026-07-28) when Speed Increase, Short-Legged and the Attribute Increase / Decrease
    variants became ordinary data, so there is no exception list here any more."""
    by_name = {}
    for o in todos:
        by_name.setdefault(o.name, []).append(o)
    for name in sorted(by_name):
        rows = [r for r in by_name[name] if r.filename == "ancestries.yaml"]
        if not rows:
            continue                              # non-ancestry todos have no trait probe
        anc = rows[0].path.split(".")[-1]
        pick = name
        api = _rt_probe_ancestry(anc)
        before = _rt_snap(api)
        _, did, offered = _rt_open_trait(api)
        if pick not in offered:
            ok("todo/%-26s is offered on %s" % (name, anc), False, sorted(offered))
            continue
        api.set_decision(did, pick)
        after = _rt_snap(api)
        moved = [k for k in ("spell_budget", "man_budget", "anc_budget")
                 if before[k] != after[k]]
        moved += ["stat " + k for k in before["stats"]
                  if before["stats"][k] != after["stats"].get(k)]
        ok("todo/%-26s is INERT, so the burn-down row is a real gap" % name,
           not moved, "it moves %s - re-declare it `modelled`" % moved)


def _all_grant_bearers(ledger):
    cg = ledger.get("chargen") or {}
    out = list(cg.get("class_choices") or []) + list(cg.get("ancestry_traits") or [])
    for lvl in (ledger.get("levels") or {}):
        out += list(ledger["levels"][lvl] or [])
    return out


def main():
    global CATPATHS, builder_api
    # --only <name>[,<name>...] runs just the named section(s), matched as a substring of the
    # check function name (so `--only fr46` runs check_fr46_round_trip). The full pass is ~45s,
    # which does not fit the Claude sandbox's background-process budget, so mutation-testing a
    # single section needs a way to run it alone. CI always runs the whole suite: --only is a
    # development convenience, never a way to make a red build green.
    only = []
    for i, a in enumerate(sys.argv):
        if a == "--only" and i + 1 < len(sys.argv):
            only = [x.strip() for x in sys.argv[i + 1].split(",") if x.strip()]

    def want(fn):
        return not only or any(o in fn.__name__ for o in only)

    def run(fn):
        if want(fn):
            fn()

    if want(check_page):
        check_page()
    if want(check_fr6):
        check_fr6()
    tmp = stage()
    old = os.getcwd()
    os.chdir(tmp)
    sys.path.insert(0, tmp)
    import importlib
    import builder_api as _ba
    globals()["builder_api"] = importlib.reload(_ba)
    CATPATHS = {c: c + ".yaml" for c in builder_build.CATALOG}
    try:
        for _fn in (check_baseline, check_trips, check_scratch, check_addlevel,
                    check_received, check_comments, check_new_features, check_sheet,
                    check_newstats, check_replace_hatch, check_wave2, check_slice2,
                    check_slice3, check_slice4, check_slice5, check_fr3,
                    check_fr3_slice2, check_fr17, check_fr20, check_fr9, check_bug16,
                    check_fr36, check_fr21, check_fr4, check_fr23, check_grants_only,
                    check_option_effects, check_class_features, check_sheet_groups,
                    check_ch5_burndown, check_bug33_class_talents, check_bug35_paragon,
                    check_bug34_grant_child_effects, check_fr46_round_trip):
            run(_fn)
    finally:
        os.chdir(old)
        shutil.rmtree(tmp, ignore_errors=True)
    print("=" * 62)
    if FAILS:
        print("FAIL - %d check(s) failed, %d passed:" % (len(FAILS), PASSES))
        for f in FAILS:
            print("  - " + f)
        sys.exit(1)
    if only:
        print("PASS - %d check(s); sections matching %s only (NOT a full pass)" % (PASSES, only))
        sys.exit(0)
    if QUIET:
        # CH-8: the pass summary banner is ~30 lines of feature narration that restates what the
        # section names already say. Under --quiet the verdict is the check count and nothing else.
        print("PASS - %d check(s), 0 failures (full suite, --quiet)" % PASSES)
        return
    _print_pass_summary()
    sys.exit(0)


def _print_pass_summary():
    print("PASS - builder page, six baselines, widget trips, fresh-L1 x5,")
    print("       add-a-level (promote + generate + undo), received-file safety,")
    print("       comment-preserving export, round-2 bug fixes, character sheet,")
    print("       new derived stats (saves/move/jump/spend-limit/DR) vs oracle,")
    print("       composite re-pick escape hatch,")
    print("       Wave 2 UX (recent files + Level A, sort, unsaved guard, refilter, budget messaging),")
    print("       FR-8 slice 2 grants -> typed child picker-slots backbone,")
    print("       FR-8 slice 3 Rune Knight subclass grants 2 runes (Xanwyn, real catalog)")
    print("       FR-8 slice 4 Meta Magic talent grants 2 metamagic (Scaletrix, real cat-level catalog)")
    print("       FR-8 slice 5 Eldritch constrained Psychic-spell grant (Runt; meets FR-13)")
    print("       FR-6 rule text on a chosen option (baked corpus + linkify + rule panel)")
    print("       FR-3 Add Planned Level for every PC (editable plans, no ledger reshape) + undo")
    print("       FR-3 slice 2 planned levels carry their own skill picks (Hybrid, FR-8 backbone, enforced)")
    print("       FR-20 level pickers reorder to chargen flow (attrs->class->ancestry->resources, children glued)")
    print("       FR-9 ancestry-point readout + auto ready-slot (budget-gated, sentinel materialise)")
    print("       BUG-16 maneuver/spell budget slots edit-only (not removable into an unrecoverable shortfall)")
    print("       FR-4 display-name rename for canon/loaded characters (set_meta, handle/deeplink unchanged)")
    print("       FR-23 Stamina Regen trigger(s) on the sheet, catalog-driven (errata Spellblade; Runt two triggers)")
    print("       grants-only unification + maneuver/spell auto-heal (read-only fixed grants; ready-slot chaining; reconcile retired)")
    print("       CH-5 Tier-1 seven ancestry traits move their derived stat (incl. grants_unarmored on traits)")
    print("       BUG-33 class talents resolve in the pick path and apply their grants (anti-mirror guard)")
    print("       BUG-35 Paragon grants a class-talent picker + 1 Trade Point on all five classes (L3/L7/L10)")
    print("       BUG-34 a grant-bearing grant-child applies its own effects (derived granted_effects + training)")
    print("       FR-46 exhaustive option round-trip: every DECLARED effect arrives in the model")


if __name__ == "__main__":
    main()
