#!/usr/bin/env python3
"""Oracle harness for the option catalog (RUNG3_PLAN build-order step 2 verification).

Three checks, in order:
  (1) The 66/66 oracle — re-run every builds/*.yaml ledger through the engine; all derived-stat
      checks must pass. (The two "Trade points over-spent" flags on runt/scaletrix are the KNOWN
      1-TP language over-spends recorded in _SESSION_LOG, not stat-check failures — whitelisted.)
  (2) Catalog vs tanrielle.yaml — the pilot build's picks must all be legal and priced by the
      catalog: spine == CLASS_TABLES, every ancestry-trait cost matches, every spell is legal
      (chosen school OR Weapon/Ward tag), disciplines/subclass exist, Magus grant matches.
  (3) Curated lists vs rules/*.md — the hand-curated ancestry costs and spell-school lists must
      match their source in ancestries.md / spells.md (catches transcription drift).

Usage:  python3 tools/catalog_verify.py      # exit 0 = PASS, 1 = FAIL
"""
import os
import re
import sys
import glob

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER_DIR = os.path.join(ROOT, "builds")
sys.path.insert(0, os.path.join(ROOT, "tools"))
from build_engine import replay, CLASS_TABLES  # noqa: E402

KNOWN_OPEN = {"Trade points over-spent"}  # runt/scaletrix 1-TP language over-spends (session log)

fails = []


def load(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as f:
        return yaml.safe_load(f)


def read(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as f:
        return f.read()


def expect(cond, msg):
    if not cond:
        fails.append(msg)


# ---- (1) the 66/66 oracle -------------------------------------------------
print("## (1) Engine oracle - re-run every ledger (derived-stat checks)")
total_ok = total_mismatch = 0
for path in sorted(glob.glob(os.path.join(LEDGER_DIR, "*.yaml"))):
    led = yaml.safe_load(open(path, encoding="utf-8"))
    lvl = led["current_level"]
    rep = replay(led, lvl)
    ok = sum(1 for ln in rep.lines if ln.endswith("| OK |"))
    mm = sum(1 for ln in rep.lines if ln.endswith("| MISMATCH |"))
    total_ok += ok
    total_mismatch += mm
    unexpected = [p for p in rep.problems if p not in KNOWN_OPEN]
    tag = "OK" if not unexpected else f"UNEXPECTED: {unexpected}"
    known = " (+known open: Trade over-spend)" if set(rep.problems) & KNOWN_OPEN else ""
    print(f"  {os.path.basename(path):16} L{lvl}  {ok:2} stat-checks OK, {mm} mismatch  {tag}{known}")
    expect(not unexpected, f"{os.path.basename(path)} unexpected problems: {unexpected}")
print(f"  => TOTAL {total_ok}/{total_ok + total_mismatch} derived-stat checks passed\n")
expect(total_mismatch == 0, f"{total_mismatch} mismatched checks")
expect(total_ok == 66, f"expected 66 passing checks, got {total_ok}")

# ---- load the catalog -----------------------------------------------------
sb = load("builds/catalog/spellblade.yaml")
schools = load("builds/catalog/spell_schools.yaml")
anc = load("builds/catalog/ancestries.yaml")
tan = load("builds/tanrielle.yaml")

# ---- (2a) spine matches the engine (no drift) -----------------------------
print("## (2) Catalog vs tanrielle.yaml")
KEY = {"hp": "hp", "attr": "attribute_points", "skill": "skill_points", "trade": "trade_points",
       "sp": "sp", "man": "maneuvers", "mp": "mp", "spells": "spells"}
for lvl, deltas in CLASS_TABLES["Spellblade"].items():
    row = sb["spine"][lvl]
    for src, dst in KEY.items():
        expect(row.get(dst, 0) == deltas.get(src, 0),
               f"spine L{lvl} {dst}: catalog {row.get(dst, 0)} vs engine {deltas.get(src, 0)}")
    expect(row.get("features") == list(deltas.get("features", [])), f"spine L{lvl} features drift")
print("  spine matches CLASS_TABLES across all 10 levels")


# ---- (2b) ancestry-trait costs --------------------------------------------
def anc_cost(source, name):
    for row in anc["ancestries"].get(source, []):
        if row["name"] == name:
            return row["cost"]
    return None


def base_trait(pick):
    return re.sub(r"\s*\(.*\)$", "", pick).strip()


traits = list(tan["chargen"]["ancestry_traits"])
for lvl, entries in tan.get("levels", {}).items():
    for e in entries:
        if e.get("slot") == "ancestry_trait":
            traits.append({"name": e["pick"], "source": e.get("source"), "cost": e.get("cost")})
for t in traits:
    nm, src, led_cost = base_trait(t["name"]), t.get("source"), t.get("cost", 0)
    cat = anc_cost(src, nm)
    expect(cat is not None, f"ancestry trait not in catalog: {src}/{nm}")
    expect(cat == led_cost, f"ancestry cost {src}/{nm}: catalog {cat} vs ledger {led_cost}")
    print(f"  ancestry {src + '/' + nm:32} cost {led_cost} == catalog {cat}")

# ---- (2c) spells legal via chosen schools OR tag access -------------------
spelltext = read("rules/spells.md")
lines = spelltext.splitlines()
spell_meta = {}
for i, ln in enumerate(lines):
    if ln.startswith("School:") and i >= 2 and lines[i - 1].startswith("Source:"):
        name = lines[i - 2].strip()
        school = ln.split(":", 1)[1].strip()
        tags = []
        if i + 1 < len(lines) and lines[i + 1].startswith("Tags:"):
            tags = [t.strip() for t in lines[i + 1].split(":", 1)[1].split(",")]
        spell_meta[name] = {"school": school, "tags": tags}
chosen = tan["chargen"]["spell_schools"]
tag_access = set(schools["tag_access"])
all_spells = list(tan["chargen"].get("spells", []))
for lvl, entries in tan.get("levels", {}).items():
    for e in entries:
        if e.get("slot") == "spell":
            all_spells.append(e["pick"])
for sp_name in all_spells:
    meta = spell_meta.get(sp_name)
    expect(meta is not None, f"spell not found in spells.md: {sp_name}")
    if not meta:
        continue
    in_school = meta["school"] in chosen
    via_tag = bool(set(meta["tags"]) & tag_access)
    if in_school:
        expect(sp_name in schools["schools"].get(meta["school"], []),
               f"{sp_name} School {meta['school']} but missing from catalog list")
    expect(in_school or via_tag,
           f"spell {sp_name} illegal: school {meta['school']} not in {chosen}, tags {meta['tags']}")
    why = f"school {meta['school']}" if in_school else f"tag {set(meta['tags']) & tag_access}"
    print(f"  spell {sp_name:16} legal via {why}")

# ---- (2d) disciplines / subclass / magus grant ----------------------------
cat_disc = {d["name"] for d in sb["disciplines"]}
for c in tan["chargen"].get("class_choices", []):
    if "disciplin" in c["slot"]:
        for p in c["picks"]:
            expect(p in cat_disc, f"L1 discipline {p} not in catalog")
for lvl, entries in tan.get("levels", {}).items():
    for e in entries:
        if e.get("slot") == "discipline":
            expect(e["pick"] in cat_disc, f"discipline {e['pick']} missing from catalog")
        if e.get("slot") == "subclass":
            expect(e["pick"] in sb["subclasses"], f"subclass {e['pick']} missing from catalog")
magus_cat = next(d for d in sb["disciplines"] if d["name"] == "Magus")["grants"]
magus_led = next(e["grants"] for lvl, es in tan["levels"].items() for e in es
                 if e.get("slot") == "discipline" and e["pick"] == "Magus")
expect(magus_cat == magus_led, f"Magus grant catalog {magus_cat} vs ledger {magus_led}")
print(f"  disciplines/subclass present; Magus grant {magus_cat} == ledger {magus_led}")

# ---- (3) curated files vs rules source ------------------------------------
print("\n## (3) Curated lists vs rules/*.md")
anctext = read("rules/ancestries.md")


def parse_ancestry(md, heading):
    m = re.search(rf"#### {heading}\n(.*?)(?=\n#### )", md, re.DOTALL)
    body = m.group(1)
    return {mm.group(2).strip(): int(mm.group(1))
            for mm in re.finditer(r"^\((-?\d+)\)\s+([^:]+):", body, re.MULTILINE)}


for a in ("Human", "Elf"):
    src_costs = parse_ancestry(anctext, a)
    for row in anc["ancestries"][a]:
        expect(row["name"] in src_costs, f"{a}/{row['name']} not in ancestries.md")
        if row["name"] in src_costs:
            expect(src_costs[row["name"]] == row["cost"],
                   f"{a}/{row['name']}: catalog {row['cost']} vs md {src_costs[row['name']]}")
    print(f"  {a}: all {len(anc['ancestries'][a])} curated costs match ancestries.md")

# spell-school lists: slice the 'Spells sorted by Schools' block, then read each school's bullets
start = spelltext.index("#### Spells sorted by Schools")
end = spelltext.index("Astromancy is the magic", start)   # start of the full descriptions
sec = spelltext[start:end]


def school_list(sec, school):
    for b in sec.split("#### "):
        if b.startswith(school + "\n"):
            return [ln[2:].strip() for ln in b.splitlines() if ln.startswith("- ")]
    return None


for school in ("Invocation", "Divination"):
    src = school_list(sec, school)
    expect(schools["schools"][school] == src,
           f"{school}: catalog != md\n    catalog={schools['schools'][school]}\n    md={src}")
    print(f"  {school}: {len(src)} spells match spells.md exactly")

# ---- verdict --------------------------------------------------------------
print("\n" + "=" * 62)
if fails:
    print(f"FAIL - {len(fails)} problem(s):")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("PASS - 66/66 oracle holds; catalog reconciles with tanrielle.yaml and rules/*.md")
