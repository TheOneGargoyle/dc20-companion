#!/usr/bin/env python3
"""Oracle harness for the option catalog (RUNG3_PLAN build-order steps 2+4 verification).

Three checks, in order:
  (1) The engine oracle - re-run every builds/*.yaml ledger through the engine; derived-stat
      checks must pass. All 90 rows now check OK - BUG-7 (runt AD 12 vs 14) was CLOSED
      2026-07-16: confirmed with Phil the armour is Deflecting Heavy (+2 PD / +0 AD) and Pact
      Armor's +1 is AD not PD, so RAW AD = 13 = the sheet. The old "Trade points over-spent"
      whitelist is also retired (BUG-2: Deep Speech is a free Eldritch grant).
  (2) Catalog vs ALL SIX ledgers - every walked pick must be legal and priced by the catalog:
      each class spine == class_spines.yaml (authored data); every ancestry-trait cost matches (with source aliases,
      trait aliases, and the Redeemed Fiendborn->Angelborn fallback); every named spell exists in
      spells.md and is legal for that character's spell-access model (Spellblade: chosen schools
      + Weapon/Ward tags + Spell School Initiate school; Warlock: 3 chosen schools + Eldritch
      Psychic-tag grant; Druid: Primal source + Arcane grant slots; Commander/Barbarian:
      existence + path-rider note); every maneuver is a real 0.10.5 maneuver (Bonan's "Recovery" was a typo for Recover,
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
from build_engine import replay, load_class_tables  # noqa: E402

# FR-12.0: the class spines are authored data now, read by the engine AND catalog_build.
CLASS_SPINES = load_class_tables(os.path.join(ROOT, "builds", "catalog", "class_spines.yaml"))

KNOWN_OPEN = set()  # retired 2026-07-16: runt's trade over-spend was the phantom Deep Speech LP
                    # (BUG-2, now a free Eldritch grant); scaletrix's was fixed 2026-07-12 (Draconic Limited).
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
    # Historical overlay slots (Saves/Move/Jump/AD): all currently modelled, none tripping.
    # BUG-7 (runt AD) closed 2026-07-16, so there are no documented deltas left.
    _MM = ("Saves", "Move Speed", "Jump Distance", "AD")
    unexpected = [p for p in rep.problems
                  if p not in KNOWN_OPEN and p.split(":")[0] not in _MM]
    tag = "OK" if not unexpected else f"UNEXPECTED: {unexpected}"
    known = " (+known open: Trade over-spend)" if set(rep.problems) & KNOWN_OPEN else ""
    print(f"  {os.path.basename(path):16} L{lvl}  {ok:2} stat-checks OK, {mm} mismatch  {tag}{known}")
    expect(not unexpected, f"{os.path.basename(path)} unexpected problems: {unexpected}")
print(f"  => TOTAL {total_ok}/{total_ok + total_mismatch} derived-stat checks passed\n")
expect(total_mismatch == 0, f"expected 0 documented deltas (BUG-7 runt AD closed 2026-07-16), got {total_mismatch}")
expect(total_ok == 90, f"expected 90 passing checks (all rows OK; BUG-7 closed), got {total_ok}")

# ---- load the catalog -----------------------------------------------------
CLASS_CAT = {c: load(f"builds/catalog/{c.lower()}.yaml")
             for c in ("Spellblade", "Warlock", "Commander", "Barbarian", "Druid")}
schools_cat = load("builds/catalog/spell_schools.yaml")
sources_cat = load("builds/catalog/spell_sources.yaml")
anc = load("builds/catalog/ancestries.yaml")
maneuvers_cat = load("builds/catalog/maneuvers.yaml")
talents_cat = load("builds/catalog/talents.yaml")
metamagic_cat = load("builds/catalog/metamagic.yaml")

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

# (2a) each generated class spine matches the authored data (no drift)
KEY = {"hp": "hp", "attr": "attribute_points", "skill": "skill_points", "trade": "trade_points",
       "sp": "sp", "man": "maneuvers", "mp": "mp", "spells": "spells"}
for cls, cat in CLASS_CAT.items():
    for lvl, deltas in CLASS_SPINES[cls].items():
        row = cat["spine"][lvl]
        for src, dst in KEY.items():
            expect(row.get(dst, 0) == deltas.get(src, 0),
                   f"{cls} spine L{lvl} {dst}: catalog {row.get(dst, 0)} vs data {deltas.get(src, 0)}")
        expect(row.get("features") == list(deltas.get("features", [])), f"{cls} spine L{lvl} features drift")
print("  spines match class_spines.yaml across all 10 levels x 5 classes")

# FR-8 slice 3: Spellblade rune catalog + Rune Knight grant (feeds the slice-2 child-slot backbone)
_sb = CLASS_CAT["Spellblade"]
expect({r["name"] for r in _sb.get("runes", [])} == {"Earth", "Flame", "Frost", "Lightning", "Water", "Wind"},
       f"Spellblade runes drift (classes.md l.3081-3116): {[r.get('name') for r in _sb.get('runes', [])]}")
expect((_sb.get("subclass_grants") or {}).get("Rune Knight", {}).get("grants") == {"runes": 2},
       f"Spellblade Rune Knight must grant runes: 2, got {(_sb.get('subclass_grants') or {}).get('Rune Knight')}")
print("  Spellblade rune catalog (6 runes) present + Rune Knight grants runes: 2 OK")

# FR-8 slice 4: cat-level metamagic catalog + Meta Magic talent grant (feeds the slice-2 child-slot backbone).
# Cross-class (reached via the Sorcerer 'Meta Magic' MC feature), so it lives at catalog level, not in a class file.
METAMAGIC_NAMES = {o["name"] for o in metamagic_cat.get("options", [])}
expect(METAMAGIC_NAMES == {"Careful Spell", "Distant Spell", "Quickened Spell",
                           "Subtle Spell", "Transmuted Spell", "Vicious Spell"},
       f"metamagic option drift (classes.md l.2618-2639): {sorted(METAMAGIC_NAMES)}")
_mm_classes = read("rules/classes.md")
for _mm in METAMAGIC_NAMES:
    expect(_mm in _mm_classes, f"metamagic option {_mm!r} not found in classes.md")
expect((MC_FEATURES.get("Meta Magic") or {}).get("grants") == {"metamagic": 2},
       f"Meta Magic mc_feature must grant metamagic: 2, got {(MC_FEATURES.get('Meta Magic') or {}).get('grants')}")
print("  metamagic catalog (6 options) present in classes.md + Meta Magic talent grants metamagic: 2 OK")


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
    for c in led["chargen"].get("class_choices") or []:      # FR-8 slice 5: granted spells (tag-constrained)
        for x in c.get("granted_spells") or []:
            names += split_names(x)
    for lvl, entries in (led.get("levels") or {}).items():
        for e in entries or []:
            if e.get("slot") == "spell":
                names += split_names(e["pick"])
            for x in e.get("granted_spells") or []:          # FR-8 slice 5: granted spells (tag-constrained)
                names += split_names(x)
    return names


def maneuver_picks(led):
    names = []
    for m in led["chargen"].get("maneuvers") or []:
        names += split_names(m)
    for c in led["chargen"].get("class_choices") or []:
        names += list(c.get("granted_maneuvers") or [])
    for lvl, entries in (led.get("levels") or {}).items():
        for e in entries or []:
            names += list(e.get("granted_maneuvers") or [])
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
        # BUG-2: a subclass that grants languages (e.g. Eldritch -> Fluent Deep Speech) must
        # have each recorded in the ledger as a free (granted / cost 0) language.
        for gl in (sg or {}).get("languages", []) if sg else []:
            led_lang = next((L for L in (led.get("languages") or [])
                             if norm(L.get("name")) == norm(gl["name"])), None)
            expect(led_lang is not None,
                   f"{who}: subclass {b} grants language {gl['name']} but the ledger does not record it")
            if led_lang is not None:
                expect(led_lang.get("granted") is True and led_lang.get("cost", 0) == 0,
                       f"{who}: granted language {gl['name']} must be granted:true cost:0, got "
                       f"granted={led_lang.get('granted')} cost={led_lang.get('cost')}")
                print(f"    subclass {b} grants language {gl['name']} (Fluent, free) OK")
        # FR-8 slice 3: a rune-granting subclass (Rune Knight) records its picks in granted_runes;
        # each must be a real catalog rune (short name).
        cat_runes = {r["name"] for r in (cat.get("runes") or [])}
        for r in (e.get("granted_runes") or []):
            expect(r in cat_runes,
                   f"{who}: granted rune {r!r} not in {cls} catalog runes {sorted(cat_runes)}")
        if e.get("granted_runes"):
            expect(sg and len(e["granted_runes"]) == sg["grants"].get("runes", 0),
                   f"{who}: {len(e['granted_runes'])} granted_runes vs grant {sg and sg.get('grants')}")
            print(f"    subclass {b} granted_runes {e['granted_runes']} all in catalog OK")
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
        for lvl, es in (led.get("levels") or {}).items():
            for e in es or []:
                if e.get("slot") == "pact_boon":
                    b = norm(e["pick"]).split(":")[0].strip()
                    expect(b in cat_boon, f"{who}: pact boon {b} (L{lvl}) not in catalog")
                    if e.get("grants"):
                        expect(e["grants"] == cat_boon[b].get("grants"),
                               f"{who}: pact boon {b} (L{lvl}) grants {e['grants']} vs catalog {cat_boon[b].get('grants')}")
                    print(f"    pact boon L{lvl} {b} OK" + (f" (grants match)" if e.get('grants') else ""))

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
        # FR-8 slice 4: a metamagic-granting talent (Meta Magic) records its picks in granted_metamagic;
        # each must be a real catalog metamagic option, and the count must match the grant.
        for mm in (e.get("granted_metamagic") or []):
            expect(mm in METAMAGIC_NAMES,
                   f"{who}: granted metamagic {mm!r} not in catalog {sorted(METAMAGIC_NAMES)}")
        if e.get("granted_metamagic"):
            expect((e.get("grants") or {}).get("metamagic") == len(e["granted_metamagic"]),
                   f"{who}: {len(e['granted_metamagic'])} granted_metamagic vs grant {e.get('grants')}")
            print(f"    talent {base_name(e['pick'])} granted_metamagic {e['granted_metamagic']} all in catalog OK")

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

# grants-only (2026-07-19): a pact boon that grants maneuvers constrains their TYPE
# (Pact Weapon = Attack of your choice l.3244, Pact Armor = Defensive of your choice l.3269),
# so the builder can offer a type-filtered picker. Assert the catalog carries a valid maneuver_type.
_wl = load("builds/catalog/warlock.yaml")
_man_types = set(maneuvers_cat["maneuvers"].keys())
_boon_type = {"Pact Weapon": "Attack", "Pact Armor": "Defense"}
for _b in _wl.get("pact_boons", []):
    if (_b.get("grants") or {}).get("maneuvers"):
        mt = _b.get("maneuver_type")
        expect(mt in _man_types,
               f"pact boon {_b['name']} grants maneuvers but maneuver_type {mt!r} is not a catalog type")
        expect(_boon_type.get(_b["name"]) == mt,
               f"pact boon {_b['name']} maneuver_type {mt!r} != expected {_boon_type.get(_b['name'])!r}")
        print(f"  pact boon {_b['name']} maneuver_type {mt} OK")

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

# ---- (4) Stamina Regen catalog (FR-23) ------------------------------------
print("\n## (4) Stamina Regen catalog (FR-23)")
from build_engine import stamina_regen as _stam_regen  # noqa: E402
_regen = load("builds/catalog/stamina_regen.yaml")
_classes_md = read("rules/classes.md")
_cc_md = read("rules/character-creation.md")
_index_md = read("rules/_INDEX.md")
# native class triggers: a distinctive phrase from each must appear in its rules source AND
# survive into the catalog trigger text (catches transcription drift).
_REGEN_KEYS = {
    "Barbarian": ("Heavy or Critical Hit", _classes_md),
    "Champion": ("perform a Maneuver", _classes_md),
    "Commander": ("grant a creature a Help Die", _classes_md),
    "Monk": ("Acrobatics", _classes_md),
    "Spellblade": ("Bound Weapon", _index_md),  # errata source (_INDEX.md), NOT classes.md
}
for _cls, (_kw, _src) in _REGEN_KEYS.items():
    expect(_cls in _regen["classes"], f"stamina_regen: {_cls} missing from catalog")
    expect(_kw in _src, f"stamina_regen: {_cls} keyword {_kw!r} not found in its rules source")
    expect(_kw in _regen["classes"].get(_cls, ""),
           f"stamina_regen: {_cls} catalog trigger lost its {_kw!r} phrase")
# Spellblade must carry the errata wording (Weapon tag), not the superseded classes.md l.2829 text.
expect("Weapon tag" in _regen["classes"]["Spellblade"],
       "stamina_regen: Spellblade must use the errata (Weapon-tag) wording")
expect("Spell Attack" not in _regen["classes"]["Spellblade"],
       "stamina_regen: Spellblade should not carry the superseded 'Spell Attack' wording")
expect("Spell Enhancement" in _regen["spellcaster"],
       "stamina_regen: Spellcaster trigger must mention Spell Enhancement")
expect("Spell Enhancement" in _cc_md,
       "stamina_regen: Spellcaster trigger keyword not in character-creation.md")
print(f"  {len(_regen['classes'])} native triggers + Spellcaster fallback reconcile with "
      f"classes.md / _INDEX.md / character-creation.md")
# reconcile the six ledgers -> expected trigger labels (the shared engine helper)
_EXPECT_REGEN = {
    "tanrielle.yaml": ["Spellblade"], "xanwyn.yaml": ["Spellblade"],
    "minimus.yaml": ["Commander"], "bonan.yaml": ["Barbarian"],
    "runt.yaml": ["Spellcaster", "Monk"], "scaletrix.yaml": [],
}
for _fn, _exp in _EXPECT_REGEN.items():
    _got = [t["label"] for t in _stam_regen(LEDGERS[_fn], _regen)]
    expect(_got == _exp, f"stamina_regen: {_fn} triggers {_got} != expected {_exp}")
    print(f"  {_fn:16} regen -> {_got or ['None']}")

# ---- (5) Damage add-ons catalog (FR-25) -----------------------------------
print("\n## (5) Damage add-ons catalog (FR-25)")
from build_engine import damage_addons as _dmg_addons  # noqa: E402
_dmg = load("builds/catalog/damage_addons.yaml")
_defs = _dmg.get("defs", {}) or {}
_combat_md = read("rules/combat.md")
_core_md = read("rules/core-rules.md")
# every character's add-on ids resolve to a def; steppers have per + a cap source, toggles have amount
_resolved = {}
for _cid, _ent in (_dmg.get("characters", {}) or {}).items():
    expect(isinstance(_ent.get("base"), int), f"damage_addons: {_cid} base must be an int")
    _cfg = _dmg_addons(_cid, _dmg)
    _resolved[_cid] = {a.get("id") for a in _cfg["addons"]}
    for _ad in _cfg["addons"]:
        _id = _ad.get("id")
        expect(_id in _defs, f"damage_addons: {_cid} references unknown add-on {_id!r}")
        _ty = _ad.get("type")
        expect(_ty in ("toggle", "stepper"), f"damage_addons: {_id} bad type {_ty!r}")
        if _ty == "toggle":
            expect(isinstance(_ad.get("amount"), int), f"damage_addons: {_id} toggle needs int amount")
        else:
            expect(isinstance(_ad.get("per"), int), f"damage_addons: {_id} stepper needs int per")
            expect(("cap" in _ad) or ("cap_stat" in _ad),
                   f"damage_addons: {_id} stepper needs cap or cap_stat")
            if "cap_stat" in _ad:
                expect(_ad["cap_stat"] in ("sp", "mp"), f"damage_addons: {_id} cap_stat must be sp|mp")
# rules grounding for the two computed patterns + the UI hit-grade/crit constants
expect("2 AP worth of AP Enhancements" in _combat_md,
       "damage_addons: the MP-on-AP-Enhancement rule (1 MP = 2 AP worth) not found in combat.md")
expect(_defs["mp_to_damage"]["per"] == 2 and _defs["mp_to_damage"]["cap"] == 2,
       "damage_addons: mp_to_damage should be +2 per MP, cap 2 (Mana Spend Limit at L4)")
# Smite = +1 Bound damage per SP; the single free Damage enhancement is a SEPARATE one-shot
# toggle (smite_free), NOT +1 per SP (Darryl ruling 2026-07-19).
expect(_defs["smite"]["per"] == 1 and _defs["smite"].get("cap_stat") == "sp",
       "damage_addons: smite should be +1 Bound dmg per SP, capped at SP")
expect(_defs["smite_free"]["type"] == "toggle" and _defs["smite_free"]["amount"] == 1,
       "damage_addons: smite_free should be a one-shot +1 toggle (the single free enhancement)")
# generic Damage enhancement is single-target, capped at the Stamina Spend Limit (2 at L4).
expect(_defs["gen_damage"]["per"] == 1 and _defs["gen_damage"]["cap"] == 2,
       "damage_addons: gen_damage should be +1 per AP/SP, cap 2 (Stamina Spend Limit at L4)")
for _kw in ("Heavy Hit", "Brutal Hit", "bypasses Damage Reduction"):
    expect(_kw in _core_md, f"damage_addons: hit-grade/crit grounding {_kw!r} missing from core-rules.md")
# per-character assignment (single-target v1)
_EXPECT_DMG = {
    "tan":   {"smite", "smite_free", "mp_to_damage", "deaths_toll", "spellstrike"},
    "xan":   {"smite", "smite_free", "imbue", "mp_to_damage", "spellstrike"},
    "runt":  {"mp_to_damage", "imbue"},
    "min":   {"gen_damage", "battlefield"},
    "bonan": {"rage", "gen_damage"},
    "scale": {"mp_to_damage", "powerful"},
}
for _h, _exp in _EXPECT_DMG.items():
    expect(_resolved.get(_h) == _exp, f"damage_addons: {_h} add-ons {_resolved.get(_h)} != expected {_exp}")
    print(f"  {_h:6} dmg add-ons -> {sorted(_resolved.get(_h, []))}")
# Smite / smite_free / Spellstrike are Spellblade-only; Rage is Barbarian(bonan)-only.
for _sb in ("smite", "smite_free", "spellstrike"):
    expect(_sb in _resolved["tan"] and _sb in _resolved["xan"],
           f"damage_addons: both Spellblades must carry {_sb}")
    expect(not any(_sb in _resolved[_h] for _h in ("runt", "min", "bonan", "scale")),
           f"damage_addons: {_sb} is Spellblade-only")
expect("rage" in _resolved["bonan"] and not any("rage" in _resolved[_h] for _h in _resolved if _h != "bonan"),
       "damage_addons: Rage is Barbarian(bonan)-only")
# Spellstrike bolt damage: Tan's Radiant Bolt = 2 (incl. Powerful focus), Xan's Umbral Bolt = 1.
_tan_ss = next(a for a in _dmg_addons("tan", _dmg)["addons"] if a["id"] == "spellstrike")
_xan_ss = next(a for a in _dmg_addons("xan", _dmg)["addons"] if a["id"] == "spellstrike")
expect(_tan_ss["amount"] == 2, "damage_addons: Tan Spellstrike (Radiant Bolt) should be +2")
expect(_xan_ss["amount"] == 1, "damage_addons: Xan Spellstrike (Umbral Bolt) should be +1")
# base-damage defaults Darryl corrected 2026-07-19
expect(_dmg["characters"]["min"]["base"] == 3, "damage_addons: Minimus crossbow base should be 3")
expect(_dmg["characters"]["runt"]["base"] == 2, "damage_addons: Runt Lightning Bolt base should be 2 (incl. Powerful)")
print(f"  {len(_resolved)} characters resolve; defs + rules grounding reconcile")

# ---- verdict --------------------------------------------------------------
print("\n" + "=" * 62)
if fails:
    print(f"FAIL - {len(fails)} problem(s):")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("PASS - engine oracle holds (90/90 checks; all item/feature effects modelled, BUG-7 runt AD closed);\n       catalog reconciles with all six ledgers and rules/*.md")
