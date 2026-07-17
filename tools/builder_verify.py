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


def ok(label, cond, detail=""):
    if cond:
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

    # (item 1) ancestry-trait prerequisites: dropping xanwyn's Climb Speed makes her
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
    # expand = character-wide reconcile: every granting level (incl. L1 chargen) gets its slots
    api2 = precon()
    comp = find(st(api2), "maneuver", 2)
    ok("multi-item composite is expandable; expand_n = total maneuvers granted (8)",
       comp.get("expandable") is True and comp.get("expand_n") == 8, (comp.get("expandable"), comp.get("expand_n")))
    api2.expand_composite(comp["id"])
    L1 = api2.ledger["chargen"]["maneuvers"]
    L2 = [e["pick"] for e in api2.ledger["levels"][2] if e.get("slot") == "maneuver"]
    L4 = [e["pick"] for e in api2.ledger["levels"][4] if e.get("slot") == "maneuver"]
    ok("reconcile sizes each level to its grant (L1=2, L2=3, L4=3)",
       len(L1) == 2 and len(L2) == 3 and len(L4) == 3, (L1, L2, L4))
    ok("captured boon names pre-fill the slots (L1 Cleave/Pathcarver, L4 has Brace/Side Step) - no blanks",
       L1 == ["Cleave", "Pathcarver"] and L2 == ["Slam", "Body Block", "Throw Creature"]
       and set(L4) == {"Heroic Intimidate", "Brace", "Side Step"} and UND not in (L1 + L2 + L4),
       (L1, L2, L4))
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
    mrows = [d for d in st(api2)["decisions"] if d.get("slot") == "maneuver"]
    ok("all generated maneuver rows are editable pickers (level slots removable)",
       all(d["widget"] == "picker" and d.get("editable") for d in mrows)
       and all(d.get("removable") for d in mrows if (d.get("level") or 1) > 1),
       [(d.get("level"), d.get("current")) for d in mrows])
    ok("no new problems introduced by the replace (runt is now fully clean; BUG-7 AD closed)",
       s1["problems"] == [], s1["problems"])
    html = open(os.path.join(REPO, "builds", "builder.html"), encoding="utf-8").read()
    ok("page JS carries the replace-picker furniture",
       "t.replaceable" in html and "&mdash; replace &mdash;" in html
       and 'class="select repl"' in html and "t.was_note" in html
       and "data-dismiss" in html and "data-expand" in html and "t.expandable" in html
       and "!t.expandable" in html)   # replace dropdown suppressed on expandable rows


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
    # BUG-8 (2026-07-16) added Xanwyn's missing History trade, so his trade budget now
    # balances; the "legal SPARE" example moves to minimus (6 unspent skill points).
    s = st(builder_api.BuilderAPI("minimus", CATPATHS))
    ok("BUG-3 minimus spare SP reads SPARE (legal) in advisories, not a problem",
       any("SPARE" in a and "Skill points" in a for a in s["advisories"])
       and not any("SPARE" in p for p in s["problems"]), (s["advisories"], s["problems"]))
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
    ok("GRANT_CHILD_SLOTS maps pickable grant resources (runes/metamagic), excludes maneuvers/spells",
       builder_api.GRANT_CHILD_SLOTS == {"runes": "rune", "metamagic": "metamagic"},
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
    ok("Runt's flat maneuvers/spells do NOT become GC child slots; his ONLY GC row is the slice-5 tag-constrained Psychic spell",
       not any("#maneuvers#" in i for i in gc_ids) and gc_ids == ["GC#L3:0#spells#0"],
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

    # ---- (e) surgical boundary intact: plain {spells:N} grants do NOT get a spell_tagged child ----
    for other in ("scaletrix", "tanrielle", "bonan", "xanwyn"):
        oapi = builder_api.BuilderAPI(other, CATPATHS)
        os_ = st(oapi)
        ok("%s's flat {spells:N} grant gets NO spell child slot (spells stay on the flat-pool model)" % other,
           not any("#spells#" in str(d.get("id")) for d in os_["decisions"]),
           [d.get("id") for d in os_["decisions"] if "#spells#" in str(d.get("id"))])

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
                                                 "spell", "maneuver", "ancestry_trait") for d in editable),
       [(d["slot"], d["widget"]) for d in l5])
    ok("an added plan raises NO builder_problems and leaves the engine/catalog clean (a plan is speculative)",
       clean(s), probs(s))
    # editing a plan pick writes it and the row stays an editable picker
    row = editable[0]
    val = row["options"][0]["name"]
    s = json.loads(api.set_decision(row["id"], val))
    r2 = find_dec(s, lambda d: d["id"] == row["id"])
    ok("editing a plan pick writes the value and the row stays an editable picker",
       r2 and r2["current"] == val and r2["editable"] and r2["widget"] == "picker",
       (r2 or {}).get("current"))
    ok("filling a plan pick still raises no engine/catalog/builder problems", clean(s), probs(s))
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


def main():
    global CATPATHS, builder_api
    check_page()
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
        check_baseline()
        check_trips()
        check_scratch()
        check_addlevel()
        check_received()
        check_comments()
        check_new_features()
        check_sheet()
        check_newstats()
        check_replace_hatch()
        check_wave2()
        check_slice2()
        check_slice3()
        check_slice4()
        check_slice5()
        check_fr3()
    finally:
        os.chdir(old)
        shutil.rmtree(tmp, ignore_errors=True)
    print("=" * 62)
    if FAILS:
        print("FAIL - %d check(s) failed:" % len(FAILS))
        for f in FAILS:
            print("  - " + f)
        sys.exit(1)
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
    sys.exit(0)


if __name__ == "__main__":
    main()
