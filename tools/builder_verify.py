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


KNOWN = {"runt": ["Trade points over-spent"], "scaletrix": ["Trade points over-spent"]}
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
        e, cat, b = probs(s)
        ok("%-10s stats %d OK / 0 MISMATCH" % (c, marks.count("OK")),
           marks and all(m == "OK" for m in marks), marks)
        ok("%-10s engine problems == known whitelist" % c,
           e == KNOWN.get(c, []), e)
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
       not s["problems"] and any("UNDER-SPENT" in a for a in s["advisories"]), s["advisories"])
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


def main():
    global CATPATHS, builder_api
    check_page()
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
    print("       comment-preserving export")
    sys.exit(0)


if __name__ == "__main__":
    main()
