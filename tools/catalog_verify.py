#!/usr/bin/env python3
"""Oracle harness for the option catalog (RUNG3_PLAN build-order steps 2+4 verification).

Three checks, in order:
  (1) The engine oracle - re-run every builds/*.yaml ledger through the engine; derived-stat
      checks must pass. (The two "Trade points over-spent" flags on runt/scaletrix are the KNOWN
      1-TP language over-spends recorded in _SESSION_LOG, not stat-check failures - whitelisted.)
  (2) Catalog vs ALL SIX ledgers - every walked pick must be legal and priced by the catalog:
      each class spine == CLASS_TABLES; every ancestry-trait cost matches (with source aliases,
      trait aliases, and the Redeemed Fiendborn->Angelborn fallback); every named spell exists in
      spells.md and is legal for that character's spell-access model (Spellblade: chosen schools
      + Weapon/Ward tags + Spell School Initiate school; Warlock: 3 chosen schools + Eldritch
      Psychic-tag grant; Druid: Primal source + Arcane grant slots; Commander/Barbarian:
      existence + path-rider note); every maneuver is a real 0.10.5 maneuver (Bonan's "Recovery"
      placeholder whitelisted); every talent resolves to a catalog talent or multiclass feature;
      disciplines / pact boons / subclasses exist and their grants match the ledgers.
  (3) Curated lists vs rules/*.md - the hand-curated ancestry costs, spell-school lists,
      spell-SOURCE lists (parent-source headings, the SS11 wrinkle), maneuver names and talent
      names must match their source text (catches transcription drift).

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
# Ledger entries that are placeholders for known-missing/known-invalid data, not real picks:
PLACEHOLDER_MARKERS = ("not itemised", "does NOT exist")

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


def norm(s):
    return str(s).replace("’", "'").strip()


def base_name(pick):
    """Strip trailing parenthetical(s) and whitespace: 'Keen Sense (Vision)' -> 'Keen Sense'."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", norm(pick)).strip()


def split_names(pick):
    """'Command, Charm, Frost Bolt (order unknown)' -> ['Command','Charm','Frost Bolt'];
    'Death Bolt + Regenerate (...)' -> ['Death Bolt','Regenerate']."""
    s = re.sub(r"\s*\([^)]*\)", "", norm(pick)).strip().rstrip(".")
    parts = re.split(r",\s*|\s\+\s", s)
    return [p.strip() for p in parts if p.strip()]


# ---- (1) the 66/66 oracle -------------------------------------------------
print("## (1) Engine oracle - re-run every ledger (derived-stat checks)")
LEDGERS = {}
total_ok = total_mismatch = 0
for path in sorted(glob.glob(os.path.join(LEDGER_DIR, "*.yaml"))):
    led = yaml.safe_load(open(path, encoding="utf-8"))
    LEDGERS[os.path.basename(path)] = led
    lvl = led["current_level"]
    rep = replay(led, lvl)
    ok = sum(1 for ln in rep.lines if ln.endswith("| OK |"))
    mm = sum(1 for ln in rep.lines if ln.endswith("| MISMATCH |"))
    total_ok += ok
    total_mismatch += mm
    # scaletrix Saves / bonan Move-Jump mismatch the sheet reference BY DESIGN
    # (item/feature overlays the RAW engine does not model - shown red, whitelisted).
    _MM = ("Saves", "Move Speed", "Jump Distance")
    unexpected = [p for p in rep.problems
                  if p not in KNOWN_OPEN and p.split(":")[0] not in _MM]
    tag = "OK" if not unexpected else f"UNEXPECTED: {unexpected}"
    known = " (+known open: Trade over-spend)" if set(rep.problems) & KNOWN_OPEN else ""
    print(f"  {os.path.basename(path):16} L{lvl}  {ok:2} stat-checks OK, {mm} mismatch  {tag}{known}")
    expect(not unexpected, f"{os.path.basename(path)} unexpected problems: {unexpected}")
print(f"  => TOTAL {total_ok}/{total_ok + total_mismatch} derived-stat checks passed\n")
expect(total_mismatch == 3,
       f"expected 3 known-delta mismatches (scaletrix Saves, bonan Move/Jump), got {total_mismatch}")
expect(total_ok == 87, f"expected 87 passing checks (66 + 24 new stat rows - 3 known-delta mismatches), got {total_ok}")

# ---- load the catalog -----------------------------------------------------
CLASS_CAT = {c: load(f"builds/catalog/{c.lower()}.yaml")
             for c in ("Spellblade", "Warlock", "Commander", "Barbarian", "Druid")}
schools_cat = load("builds/catalog/spell_schools.yaml")
sources_cat = load("builds/catalog/spell_sources.yaml")
anc = load("builds/catalog/ancestries.yaml")
maneuvers_cat = load("builds/catalog/maneuvers.yaml")
talents_cat = load("builds/catalog/talents.yaml")

ALL_MANEUVERS = {m for lst in maneuvers_cat["maneuvers"].values() for m in lst}
TALENT_NAMES = ({t["name"] for t in talents_cat["general"]}
                | {t["name"] for t in talents_cat["multiclass"]}
                | {t["name"] for lst in talents_cat["class_talents"].values() for t in lst})
MC_FEATURES = {t["name"]: t for t in talents_cat["mc_features"]}
SRC_ALIASES = anc.get("source_aliases", {})

# ---- spells.md metadata (name -> source/school/tags) ----------------------
spelltext = read("rules/spells.md")
slines = spelltext.splitlines()
spell_meta = {}
for i, ln in enumerate(slines):
    if ln.startswith("School:") and i >= 2 and slines[i - 1].startswith("Source:"):
        name = slines[i - 2].strip()
        srcs = [s.strip() for s in slines[i - 1].split(":", 1)[1].split(",")]
        school = ln.split(":", 1)[1].strip()
        tags = []
        if i + 1 < len(slines) and slines[i + 1].startswith("Tags:"):
            tags = [t.strip() for t in slines[i + 1].split(":", 1)[1].split(",")]
        spell_meta[name] = {"sources": srcs, "school": school, "tags": tags}


# ---- (2) catalog vs the six ledgers ---------------------------------------
print("## (2) Catalog vs the six ledgers")

# (2a) each class spine matches the engine (no drift)
KEY = {"hp": "hp", "attr": "attribute_points", "skill": "skill_points", "trade": "trade_points",
       "sp": "sp", "man": "maneuvers", "mp": "mp", "spells": "spells"}
for cls, cat in CLASS_CAT.items():
    for lvl, deltas in CLASS_TABLES[cls].items():
        row = cat["spine"][lvl]
        for src, dst in KEY.items():
            expect(row.get(dst, 0) == deltas.get(src, 0),
                   f"{cls} spine L{lvl} {dst}: catalog {row.get(dst, 0)} vs engine {deltas.get(src, 0)}")
        expect(row.get("features") == list(deltas.get("features", [])), f"{cls} spine L{lvl} features drift")
print("  spines match CLASS_TABLES across all 10 levels x 5 classes")


def anc_lookup(source, name):
    """Resolve (source, trait-name) -> (cost, resolved-list). Tries the named list (via
    source_aliases), trait aliases, then every curated list (Redeemed / unsourced entries)."""
    name = base_name(name)
    ordered = []
    if source:
        ordered.append(SRC_ALIASES.get(source, source))
    ordered += [a for a in anc["ancestries"] if a not in ordered]
    for lst in ordered:
        for row in anc["ancestries"].get(lst, []):
            if row["name"] == name or name in (row.get("aliases") or []):
                return row["cost"], lst, row["name"]
    return None, None, None


def iter_traits(led):
    for t in led["chargen"].get("ancestry_traits") or []:
        yield t
    for lvl, entries in (led.get("levels") or {}).items():
        for e in entries or []:
            if e.get("slot") == "ancestry_trait":
                yield {"name": e["pick"], "source": e.get("source"), "cost": e.get("cost", 0)}


def spell_picks(led):
    names = []
    for s in led["chargen"].get("spells") or []:
        names += split_names(s)
    for lvl, entries in (led.get("levels") or {}).items():
        for e in entries or []:
            if e.get("slot") == "spell":
                names += split_names(e["pick"])
    return names


def maneuver_picks(led):
    names = []
    for m in led["chargen"].get("maneuvers") or []:
        names += split_names(m)
    for lvl, entries in (led.get("levels") or {}).items():
        for e in entries or []:
            if e.get("slot") == "maneuver":
                if any(mk in str(e.get("pick")) for mk in PLACEHOLDER_MARKERS):
                    print(f"    maneuver placeholder whitelisted (known audit item): {e['pick']!r}")
                    continue
                names += split_names(e["pick"])
    return [n for n in names if not any(mk in n for mk in PLACEHOLDER_MARKERS)]


def talent_picks(led):
    for lvl, entries in (led.get("levels") or {}).items():
        for e in entries or []:
            if e.get("slot") == "talent":
                yield lvl, e


def resolve_talent(pick):
    """Resolve a ledger talent pick to a catalog row. Returns a 'via' string or None."""
    s = norm(pick)
    m = re.match(r"MC (\w+)(?: \((Novice|Adept|Expert|Master)\))?:\s*(.*)", s)
    if m:
        klass, tier, feat = m.group(1), m.group(2), base_name(m.group(3).split(":")[0])
        if feat in MC_FEATURES:
            return f"{MC_FEATURES[feat]['via']} -> {klass} feature {feat}"
        if tier in ("Expert", "Master"):
            return f"{tier} Multiclass ({klass})"   # feature text, not a name (e.g. '+2 any-source spells')
        return None
    b = base_name(s.split(":")[0])
    if b in TALENT_NAMES:
        return f"talent {b}"
    if b in MC_FEATURES:
        return f"{MC_FEATURES[b]['via']} -> {MC_FEATURES[b]['class']} feature {b}"
    return None


def school_of(name):
    return spell_meta[name]["school"] if name in spell_meta else None


def check_ledger(fname, led):
    cls = led["class"]
    cat = CLASS_CAT[cls]
    who = fname.replace(".yaml", "")
    print(f"  --- {who} ({cls})")

    # subclass
    subs = [e for lvl, es in (led.get("levels") or {}).items() for e in es or [] if e.get("slot") == "subclass"]
    for e in subs:
        b = base_name(e["pick"])
        expect(b in cat["subclasses"], f"{who}: subclass {b} not in {cls} catalog {cat['subclasses']}")
        sg = (cat.get("subclass_grants") or {}).get(b)
        if e.get("grants") and sg:
            expect(e["grants"] == sg["grants"],
                   f"{who}: subclass {b} grants {e['grants']} vs catalog {sg['grants']}")
        print(f"    subclass {b} OK" + (f" (grants {sg['grants']} match)" if sg and e.get('grants') else ""))

    # ancestry traits
    for t in iter_traits(led):
        nm = str(t.get("name", ""))
        if any(mk in nm for mk in PLACEHOLDER_MARKERS):
            print(f"    ancestry placeholder whitelisted (known open item): {nm!r} (cost {t.get('cost')})")
            continue
        cost, lst, resolved = anc_lookup(t.get("source"), nm)
        expect(cost is not None, f"{who}: ancestry trait not in catalog: {t.get('source')}/{nm}")
        if cost is None:
            continue
        expect(cost == t.get("cost", 0),
               f"{who}: ancestry cost {lst}/{resolved}: catalog {cost} vs ledger {t.get('cost', 0)}")
        via = "" if lst == SRC_ALIASES.get(t.get("source"), t.get("source")) else f"  [resolved via {lst}]"
        print(f"    ancestry {str(t.get('source')) + '/' + base_name(nm):34} cost {t.get('cost',0)} == catalog {cost}{via}")

    # disciplines / pact boons (class_choices + level entries)
    if "disciplines" in cat:
        cat_disc = {d["name"]: d for d in cat["disciplines"]}
        for c in led["chargen"].get("class_choices") or []:
            if "disciplin" in c["slot"]:
                gsum = {}
                for p in c["picks"]:
                    expect(p in cat_disc, f"{who}: L1 discipline {p} not in catalog")
                    for k, v in (cat_disc.get(p, {}).get("grants") or {}).items():
                        gsum[k] = gsum.get(k, 0) + v
                if c.get("grants"):
                    expect(c["grants"] == gsum,
                           f"{who}: L1 discipline grants {c['grants']} vs catalog sum {gsum}")
                print(f"    disciplines L1 {c['picks']} OK" + (f" (grants {gsum} match)" if c.get('grants') else ""))
        for lvl, es in (led.get("levels") or {}).items():
            for e in es or []:
                if e.get("slot") == "discipline":
                    expect(base_name(e["pick"]) in cat_disc, f"{who}: discipline {e['pick']} missing from catalog")
                    if e.get("grants"):
                        expect(e["grants"] == cat_disc[base_name(e["pick"])].get("grants"),
                               f"{who}: discipline {e['pick']} grants {e['grants']} vs catalog")
                    print(f"    discipline L{lvl} {e['pick']} OK")
    if "pact_boons" in cat:
        cat_boon = {b["name"]: b for b in cat["pact_boons"]}
        for c in led["chargen"].get("class_choices") or []:
            if c["slot"] == "pact_boon":
                for p in c["picks"]:
                    b = norm(p).split(":")[0].strip()
                    expect(b in cat_boon, f"{who}: pact boon {b} not in catalog")
                    if c.get("grants"):
                        expect(c["grants"] == cat_boon[b].get("grants"),
                               f"{who}: pact boon {b} grants {c['grants']} vs catalog {cat_boon[b].get('grants')}")
                    print(f"    pact boon {b} OK" + (f" (grants {c['grants']} match)" if c.get('grants') else ""))

    # talents
    for lvl, e in talent_picks(led):
        via = resolve_talent(e["pick"])
        expect(via is not None, f"{who}: talent unresolved by catalog: {e['pick']!r}")
        if via:
            b = base_name(norm(e["pick"]).split(":")[-1] if str(e["pick"]).startswith("MC") else str(e["pick"]).split(":")[0])
            known = MC_FEATURES.get(b) or next((t for t in talents_cat["general"] if t["name"] == b), None)
            if e.get("grants") and known and known.get("grants") and "Innate Power" not in b:
                expect(e["grants"] == known["grants"],
                       f"{who}: talent {b} grants {e['grants']} vs catalog {known['grants']}")
            print(f"    talent L{lvl} {str(e['pick'])[:44]:46} -> {via}")

    # maneuvers
    mp = maneuver_picks(led)
    for m in mp:
        expect(m in ALL_MANEUVERS, f"{who}: maneuver {m!r} not a 0.10.5 maneuver (catalog)")
    if mp:
        print(f"    maneuvers {mp} all in catalog")

    # spells (per-class access model)
    model = cat["spellcasting"]["model"]
    picks = spell_picks(led)
    for s in picks:
        expect(s in spell_meta, f"{who}: spell not found in spells.md: {s}")
    picks = [s for s in picks if s in spell_meta]
    if model == "schools":
        chosen = led["chargen"].get("spell_schools") or []
        expect(len(chosen) == cat["spellcasting"]["schools_chosen"],
               f"{who}: {len(chosen)} schools chosen vs {cat['spellcasting']['schools_chosen']} allowed")
        tags = set(cat["spellcasting"].get("tag_access") or []) if cls == "Spellblade" else set()
        # talent-granted school access (Spell School Initiate: <School>)
        extra_schools = [norm(e["pick"]).split(":")[1].strip()
                         for _, e in talent_picks(led) if str(e["pick"]).startswith("Spell School Initiate:")]
        # subclass tag grants (Eldritch: Psychic)
        grant_tags = {sg["spell_access"]["tag"] for b, sg in (cat.get("subclass_grants") or {}).items()
                      if any(base_name(e["pick"]) == b for e in subs) and "spell_access" in sg}
        for s in picks:
            meta = spell_meta[s]
            legal_school = meta["school"] in chosen or meta["school"] in extra_schools
            legal_tag = bool(set(meta["tags"]) & tags) or bool(set(meta["tags"]) & grant_tags)
            expect(legal_school or legal_tag,
                   f"{who}: spell {s} illegal: school {meta['school']} not in {chosen}+{extra_schools}, tags {meta['tags']}")
            if meta["school"] in chosen:
                expect(s in schools_cat["schools"].get(meta["school"], []),
                       f"{who}: {s} (school {meta['school']}) missing from spell_schools.yaml")
                why = f"school {meta['school']}"
            elif meta["school"] in extra_schools:
                why = f"school {meta['school']} (Spell School Initiate)"
            else:
                why = f"tag {set(meta['tags']) & (tags | grant_tags)}"
            print(f"    spell {s:18} legal via {why}")
    elif model == "source":
        src = cat["spellcasting"]["source"]
        primal_flat = {sp for sch in sources_cat["sources"][src].values() for sp in sch}
        # Arcane grant slots the walked ledger carries (Scaletrix): Intuitive Magic (2, any
        # from the MC'd Sorcerer's chosen Source - Arcane per ledger) + Fiendish Magic (1).
        grant_slots = 0
        for _, e in talent_picks(led):
            if "Innate Power" in str(e["pick"]) and "Intuitive" in str(e["pick"]):
                grant_slots += 2
        for t in iter_traits(led):
            if base_name(t["name"]) in ("Fiendish Magic", "Arcane Spell"):
                grant_slots += 1
        off_source = []
        for s in picks:
            meta = spell_meta[s]
            if src in meta["sources"]:
                expect(s in primal_flat,
                       f"{who}: {s} (Source {src}) missing from spell_sources.yaml {src} block")
                print(f"    spell {s:18} legal via {src} source (school {meta['school']})")
            else:
                off_source.append(s)
                expect("Arcane" in meta["sources"],
                       f"{who}: spell {s} neither {src} nor Arcane (sources {meta['sources']})")
                print(f"    spell {s:18} off-source ({'/'.join(meta['sources'])}) -> needs an Arcane grant slot")
        expect(len(off_source) <= grant_slots,
               f"{who}: {len(off_source)} off-source spells vs {grant_slots} Arcane grant slots")
        if picks:
            print(f"    off-source count {len(off_source)} <= {grant_slots} Arcane grant slots OK")
    else:  # model == none (Commander / Barbarian): spells only via path rider / MC talents
        if picks:
            covering = [nm for nm, flat in
                        [("Primal source", {sp for sch in sources_cat['sources']['Primal'].values() for sp in sch})]
                        if all(("Primal" in spell_meta[s]["sources"]) for s in picks)]
            note = (f"consistent with a single {covering[0]} list pick" if covering
                    else "covered by any-list grants (MC Bard Magical Secrets / path list unpinned)")
            print(f"    spells {picks} exist in spells.md; access = path-rider list choice "
                  f"(unrecorded) - {note}")


for fname, led in LEDGERS.items():
    check_ledger(fname, led)

# ---- (3) curated files vs rules source ------------------------------------
print("\n## (3) Curated lists vs rules/*.md")
anctext = read("rules/ancestries.md")
ANCESTRY_HEADINGS = ["Human", "Elf", "Dwarf", "Halfling", "Gnome", "Orc", "Dragonborn",
                     "Giantborn", "Angelborn", "Fiendborn", "Beastborn"]


def ancestry_region(md, heading):
    start = md.index(f"#### {heading}\n")
    ends = [md.index(f"#### {h}\n", start + 1) for h in ANCESTRY_HEADINGS
            if f"#### {h}\n" in md[start + 1:] and md.index(f"#### {h}\n", start + 1) > start]
    return md[start: min(ends)] if ends else md[start:]


def parse_ancestry(md, heading):
    body = ancestry_region(md, heading)
    out, reqs = {}, {}
    for mm in re.finditer(r"^(?:-\s*)?\((-?\d+)\)\s+(.+?):", body, re.MULTILINE):
        raw = mm.group(2)
        rq = re.search(r"\(requires ([^)]*)\)", raw)              # "(requires X)" inside the name
        if not rq:
            after = body[mm.end():mm.end() + 60]                   # or just after the colon
            rq = re.match(r"\s*\(requires ([^)]*)\)", after)
        name = base_name(re.sub(r"\s*\(requires[^)]*\)", "", norm(raw)))
        out[name] = int(mm.group(1))
        if rq:
            reqs[name] = re.sub(r"\s+", " ", norm(rq.group(1))).strip()
    return out, reqs


for a in anc["ancestries"]:
    src_costs, src_reqs = parse_ancestry(anctext, a)
    nreq = 0
    for row in anc["ancestries"][a]:
        expect(row["name"] in src_costs, f"{a}/{row['name']} not in ancestries.md")
        if row["name"] in src_costs:
            expect(src_costs[row["name"]] == row["cost"],
                   f"{a}/{row['name']}: catalog {row['cost']} vs md {src_costs[row['name']]}")
        cat_req = norm(row["requires"]) if row.get("requires") else None
        md_req = src_reqs.get(row["name"])
        expect(cat_req == md_req,
               f"{a}/{row['name']}: catalog requires {cat_req!r} vs md {md_req!r}")
        if cat_req:
            nreq += 1
    print(f"  {a}: all {len(anc['ancestries'][a])} curated costs"
          + (f" + {nreq} prerequisites" if nreq else "") + " match ancestries.md")

# spell-school lists: slice the 'Spells sorted by Schools' block, read each school's bullets
start = spelltext.index("#### Spells sorted by Schools")
end = spelltext.index("Astromancy is the magic", start)   # start of the full descriptions
sec = spelltext[start:end]


def school_list(sec, school):
    for b in sec.split("#### "):
        if b.startswith(school + "\n"):
            return [ln[2:].strip() for ln in b.splitlines() if ln.startswith("- ")]
    return None


for school in schools_cat["schools"]:
    src = school_list(sec, school)
    expect(schools_cat["schools"][school] == src,
           f"{school}: catalog != md\n    catalog={schools_cat['schools'][school]}\n    md={src}")
    print(f"  school {school}: {len(src)} spells match spells.md exactly")

# spell-SOURCE lists: parse the by-Sources block TRACKING PARENT SOURCE HEADINGS (SS11 wrinkle)
s_start = spelltext.index("#### Spells sorted by Sources")
s_end = spelltext.index("#### Spells sorted by Schools")
by_src = {}
cur_src = cur_school = None
for ln in spelltext[s_start:s_end].splitlines():
    t = ln.strip()
    if t in ("Arcane", "Divine", "Primal"):
        cur_src = t
        by_src[t] = {}
    elif t.startswith("#### ") and cur_src:
        cur_school = t[5:].strip()
        by_src[cur_src][cur_school] = []
    elif t.startswith("- ") and cur_src and cur_school:
        by_src[cur_src][cur_school].append(t[2:].strip())
for src_name, sch_map in sources_cat["sources"].items():
    for sch, lst in sch_map.items():
        expect(by_src.get(src_name, {}).get(sch) == lst,
               f"sources {src_name}/{sch}: catalog != md\n    catalog={lst}\n    md={by_src.get(src_name, {}).get(sch)}")
    print(f"  source {src_name}: {len(sch_map)} school lists match spells.md (parent-source tracked)")

# maneuver names: every curated name appears as a standalone line in the Maneuvers chapter
combat = read("rules/combat.md").splitlines()
m_region = {ln.strip() for ln in combat[967:1684]}
for typ, lst in maneuvers_cat["maneuvers"].items():
    for m in lst:
        expect(m in m_region, f"maneuver {m} ({typ}) not found in combat.md maneuvers chapter")
    print(f"  maneuvers {typ}: {len(lst)} names found in combat.md")

# talent names: general/multiclass/class talents in character-creation.md; mc_features in classes.md
cc = read("rules/character-creation.md")
classes = read("rules/classes.md")
for t in talents_cat["general"] + talents_cat["multiclass"]:
    expect(t["name"] in cc, f"talent {t['name']} not in character-creation.md")
for klass, lst in talents_cat["class_talents"].items():
    for t in lst:
        expect(norm(t["name"]) in cc.replace("’", "'"), f"class talent {t['name']} not in character-creation.md")
for t in talents_cat["mc_features"]:
    expect(t["name"] in classes, f"mc_feature {t['name']} not in classes.md")
print(f"  talents: {len(talents_cat['general'])} general + {len(talents_cat['multiclass'])} multiclass + "
      f"{sum(len(v) for v in talents_cat['class_talents'].values())} class + "
      f"{len(talents_cat['mc_features'])} MC features all found in rules text")

# skill/trade name lists: every curated name appears in core-rules.md's own lists
core = read("rules/core-rules.md")
st_cat = load("builds/catalog/skills_trades.yaml")
sk_region = core.split("### Skills", 1)[1].split("### Trades", 1)[0]
tr_region = core.split("### Trades", 1)[1].split("### Languages", 1)[0]
n_sk = 0
for attr, lst in st_cat["skills"].items():
    for s in lst:
        expect(("- %s" % s) in sk_region, f"skill {s} ({attr}) not in core-rules.md Skill List")
        n_sk += 1
for t in st_cat["trades"]:
    expect(("- %s" % t) in tr_region, f"trade {t} not in core-rules.md Trades List")
for k in st_cat["knowledge_trades"]:
    expect(k in st_cat["trades"], f"knowledge trade {k} missing from the trades list")
    expect(("\n%s\n" % k) in tr_region.split("#### Knowledge", 1)[1].split("####", 1)[0],
           f"{k} not under core-rules.md #### Knowledge")
print(f"  skills/trades: {n_sk} skills + {len(st_cat['trades'])} trades "
      f"({len(st_cat['knowledge_trades'])} knowledge) match core-rules.md")

# language name list: every curated language appears in core-rules.md's Languages List
lang_cat = load("builds/catalog/languages.yaml")
lang_region = core.split("Languages List", 1)[1].split("#### Mortal Languages", 1)[0]
n_lang = 0
for grp, lst in lang_cat["languages"].items():
    for l in lst:
        expect(("- %s" % l) in lang_region, f"language {l} ({grp}) not in core-rules.md Languages List")
        n_lang += 1
print(f"  languages: {n_lang} curated names (Mortal/Exotic/Divine/Outer) match core-rules.md")

# ---- verdict --------------------------------------------------------------
print("\n" + "=" * 62)
if fails:
    print(f"FAIL - {len(fails)} problem(s):")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("PASS - engine oracle holds (87/90 checks; 3 by-design sheet-vs-RAW deltas:\n       scaletrix Saves +1 amulet, bonan Move/Jump); catalog reconciles with\n       all six ledgers and rules/*.md")
