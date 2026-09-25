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
      + Weapon/Ward tags (Spell School Initiate teaches 2 childed spells, no widening); Warlock: 3 chosen schools + Eldritch
      Psychic-tag grant; Druid: Primal source + Arcane grant slots; Commander/Barbarian:
      existence + path-rider note); every maneuver is a real 0.10.5 maneuver (Bonan's "Recovery" was a typo for Recover,
      placeholder whitelisted); every talent resolves to a catalog talent or multiclass feature;
      disciplines / pact boons / subclasses exist and their grants match the ledgers.
  (4) The option-coverage ledger (tools/coverage.py) - every pickable option must DECLARE
      its effect (modelled / no_effect+category / todo+note); undeclared is a failure, and
      no walked ledger may depend on an option whose effect is still an open todo.
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
from build_engine import replay, load_class_tables, class_feature_rider_grants  # noqa: E402
from build_engine import OVERLAY_MISMATCH_LABELS  # noqa: E402  (CH-14 A18)
from build_engine import class_roster  # noqa: E402  (CH-10 A14: the one class roster)
import coverage  # noqa: E402  (the option-coverage ledger: one walker, no mirrored lists)

# FR-12.0: the class spines are authored data now, read by the engine AND catalog_build.
CLASS_SPINES = load_class_tables(os.path.join(ROOT, "builds", "catalog", "class_spines.yaml"))

KNOWN_OPEN = set()  # retired 2026-07-16: runt's trade over-spend was the phantom Deep Speech LP
                    # (BUG-2, now a free Eldritch grant); scaletrix's was fixed 2026-07-12 (Draconic Limited).
# Ledger entries that are placeholders for known-missing/known-invalid data, not real picks:
PLACEHOLDER_MARKERS = ("not itemised", "does NOT exist")
# CH-13: grant keys that buy a further PICK rather than move a stat, resource -> the ledger
# slot name that pick lands under. Mirrors GRANT_CHILD_SLOTS in tools/builder_api.py; keep
# the two in step (CH-14 is the row that proposes naming shared constants once).
CHILD_SLOTS = {"runes": "rune", "metamagic": "metamagic", "skills": "skill",
               "trades": "trade", "disciplines": "discipline"}

fails = []
checks = 0   # CH-17: every expect() call, so the banner can report a real number


def load(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as f:
        return yaml.safe_load(f)


def read(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as f:
        return f.read()


def expect(cond, msg):
    # CH-17: count every assertion. The PASS banner used to print a hard-coded "90/90", so the
    # figure quoted as this harness's regression baseline could not move and could not fail:
    # BUG-52 added 14 real checks on 2026-08-15 and it still read 90/90. Same defect class as
    # BUG-37's mirrored cap, a number that looks like evidence and is not.
    global checks
    checks += 1
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
    _MM = OVERLAY_MISMATCH_LABELS
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
CLASS_ROSTER = class_roster()   # exits on an empty spine (trap 4)
CLASS_CAT = {c: load(f"builds/catalog/{c.lower()}.yaml")
             for c in CLASS_ROSTER}   # CH-10 A14: derived from class_spines.yaml
schools_cat = load("builds/catalog/spell_schools.yaml")
sources_cat = load("builds/catalog/spell_sources.yaml")
anc = load("builds/catalog/ancestries.yaml")
maneuvers_cat = load("builds/catalog/maneuvers.yaml")
talents_cat = load("builds/catalog/talents.yaml")
metamagic_cat = load("builds/catalog/metamagic.yaml")
class_features_cat = load("builds/catalog/class_features.yaml")   # BUG-39/BUG-47: was never loaded here

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

# 2026-09-23 (FR-48 thread): each SCRIPTED class file must equal what catalog_build.py generates.
# spellblade.yaml carried a hand edit (BUG-43's rune grants) past its "do not hand-edit" header,
# so the next regenerate would have silently reverted it. Compared as parsed YAML, so formatting
# is free but content is not. Also FR-48: every class carries a non-empty base Combat Training.
import catalog_build as _cb   # noqa: E402
for _cls in _cb.CLASS_CONFIG:
    _gen = _cb.build(_cls)
    expect(_gen == CLASS_CAT[_cls],
           f"{_cls.lower()}.yaml differs from catalog_build.py output (hand edit, or a stale regenerate): "
           f"keys {sorted(k for k in set(_gen) | set(CLASS_CAT[_cls]) if _gen.get(k) != CLASS_CAT[_cls].get(k))}")
    expect(bool(CLASS_CAT[_cls].get("combat_training")),
           f"{_cls} has no base combat_training (FR-48)")
expect(len(_cb.CLASS_CONFIG) == len(CLASS_CAT) >= 5, f"generator/catalog class sets differ: {sorted(CLASS_CAT)}")
print(f"  {len(_cb.CLASS_CONFIG)} scripted class files equal catalog_build.py output; base Combat Training present")

# FR-8 slice 3: Spellblade rune catalog + Rune Knight grant (feeds the slice-2 child-slot backbone)
_sb = CLASS_CAT["Spellblade"]
expect({r["name"] for r in _sb.get("runes", [])} == {"Earth", "Flame", "Frost", "Lightning", "Water", "Wind"},
       f"Spellblade runes drift (classes.md l.3081-3116): {[r.get('name') for r in _sb.get('runes', [])]}")
expect((_sb.get("subclass_grants") or {}).get("Rune Knight", {}).get("grants") == {"runes": 2},
       f"Spellblade Rune Knight must grant runes: 2, got {(_sb.get('subclass_grants') or {}).get('Rune Knight')}")
print("  Spellblade rune catalog (6 runes) present + Rune Knight grants runes: 2 OK")

# BUG-43 (2026-08-21): the runes that carry a NUMERIC grant must carry the number the prose gives.
# Lightning's Quickness (+1 Speed) and Wind's Wind Swept (+3 Jump Distance) sat as
# `no_effect: situational` for weeks even though `speed` and `jump` are first-class engine grant
# keys, so a scratch Rune Knight who picked either was permanently short. The expected value is
# PARSED out of classes.md rather than restated here, because a literal in the check is the same
# defect one layer up: it can only ever agree with the catalog it is checking.
_clstext = read("rules/classes.md")
RUNE_PROSE = {"speed": r"Your Speed increases by (\d+)",      # Lightning, Quickness
              "jump": r"\+(\d+) Jump Distance"}              # Wind, Wind Swept
for _r in _sb.get("runes", []):
    _g = _r.get("grants") or {}
    if not _g:
        continue
    _m = re.search(r"^%s Rune$" % re.escape(_r["name"]), _clstext, re.M)
    expect(bool(_m), f"Spellblade rune {_r['name']}: no '{_r['name']} Rune' heading in classes.md")
    if not _m:
        continue
    _nxt = re.search(r"^\w+ Rune$|^Rune Expert", _clstext[_m.end():], re.M)
    _block = _clstext[_m.end(): _m.end() + (_nxt.start() if _nxt else 400)]
    for _k, _v in _g.items():
        _pat = RUNE_PROSE.get(_k)
        expect(_pat is not None,
               f"Spellblade rune {_r['name']}: grant {_k!r} has no prose pattern to check it against")
        if not _pat:
            continue
        _pm = re.search(_pat, _block)
        expect(bool(_pm) and int(_pm.group(1)) == _v,
               f"Spellblade rune {_r['name']}: catalog {_k}={_v} vs classes.md "
               f"{_pm.group(1) if _pm else None}")
        print(f"  rune {_r['name']}: {_k} +{_v} matches its classes.md sentence")

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
    for t in led["chargen"].get("ancestry_traits") or []:    # FR-13a: spells childed under an ancestry trait
        if isinstance(t, dict):                               # (e.g. Scaletrix's Command via Fiendish Magic)
            for x in t.get("granted_spells") or []:
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


def origin_opt(e, row):
    # BUG-26: the option a ledger entry chose on its catalog row's sub_choice node (by `choice.pick`).
    decl = (row or {}).get("sub_choice") or {}
    pick = (e.get("choice") or {}).get("pick")
    return next((o for o in decl.get("options") or [] if o["name"] == pick), None)


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
    subs = [(lvl, e) for lvl, es in (led.get("levels") or {}).items()
            for e in es or [] if e.get("slot") == "subclass"]
    for _lvl, e in subs:
        b = base_name(e["pick"])
        expect(b in cat["subclasses"], f"{who}: subclass {b} not in {cls} catalog {cat['subclasses']}")
        sg = (cat.get("subclass_grants") or {}).get(b)
        # CH-13: unconditional, but split by the KIND of grant key, because the two kinds fail
        # differently. An EFFECT key moves a derived stat and the engine reads effects off the
        # LEDGER ENTRY, never off the pick name, so an omitted effect key is silently wrong and
        # must be compared outright. A PICK-BUDGET key (GRANT_CHILD_SLOTS in builder_api) buys a
        # further pick instead of a stat, and a hand-authored ledger may record that pick either
        # as a grant-CHILD (granted_<res>, Xanwyn's runes) or as a sibling entry at the same
        # level (Tanrielle's L3 Magus). Either is accounted for; neither is not. C5 of CH-10.
        if sg:
            _cat_eff = {k: v for k, v in sg["grants"].items() if k not in CHILD_SLOTS}
            _led_eff = {k: v for k, v in (e.get("grants") or {}).items() if k not in CHILD_SLOTS}
            expect(_led_eff == _cat_eff,
                   f"{who}: subclass {b} effect grants {_led_eff} vs catalog {_cat_eff}")
            for _res, _n in sg["grants"].items():
                if _res not in CHILD_SLOTS:
                    continue
                _kids = len(e.get(f"granted_{_res}") or [])
                _sibs = sum(1 for _s in (led.get("levels") or {}).get(_lvl) or []
                            if _s.get("slot") == CHILD_SLOTS[_res])
                expect(_kids + _sibs >= int(_n),
                       f"{who}: subclass {b} grants {_n} {_res} but the ledger records "
                       f"{_kids} granted_{_res} and {_sibs} L{_lvl} {CHILD_SLOTS[_res]} entr(ies)")
                print(f"    subclass {b} {_res} budget {_n} accounted "
                      f"({_kids} child, {_sibs} sibling at L{_lvl}) OK")
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
                # CH-13: unconditional. `or {}` only so an all-situational pair (catalog sum {})
                # matches a ledger that records no grants; a NON-empty sum still fails on omission.
                expect((c.get("grants") or {}) == gsum,
                       f"{who}: L1 discipline grants {c.get('grants')} vs catalog sum {gsum}")
                print(f"    disciplines L1 {c['picks']} OK (grants {gsum} match)")
        for lvl, es in (led.get("levels") or {}).items():
            for e in es or []:
                if e.get("slot") == "discipline":
                    expect(base_name(e["pick"]) in cat_disc, f"{who}: discipline {e['pick']} missing from catalog")
                    expect(e.get("grants") == cat_disc[base_name(e["pick"])].get("grants"),  # CH-13
                           f"{who}: discipline {e['pick']} grants {e.get('grants')} vs catalog")
                    print(f"    discipline L{lvl} {e['pick']} OK")
                # CH-13/C5: a discipline can also be a grant-CHILD of the entry that grants it
                # (Paladin -> 1 discipline, GRANT_CHILD_SLOTS). Check those the same way, or
                # childing a pick would move it out of every check above.
                for _gd in (e.get("granted_disciplines") or []):
                    expect(base_name(_gd) in cat_disc, f"{who}: granted discipline {_gd} missing from catalog")
                    print(f"    granted discipline L{lvl} {_gd} (child of {e.get('pick')}) OK")
                if e.get("granted_disciplines"):
                    expect(len(e["granted_disciplines"]) == int((e.get("grants") or {}).get("disciplines", 0)),
                           f"{who}: {len(e['granted_disciplines'])} granted_disciplines vs grant "
                           f"{(e.get('grants') or {}).get('disciplines')}")
    if "pact_boons" in cat:
        cat_boon = {b["name"]: b for b in cat["pact_boons"]}
        for c in led["chargen"].get("class_choices") or []:
            if c["slot"] == "pact_boon":
                for p in c["picks"]:
                    b = norm(p).split(":")[0].strip()
                    expect(b in cat_boon, f"{who}: pact boon {b} not in catalog")
                    expect(c.get("grants") == cat_boon[b].get("grants"),   # CH-13: unconditional
                           f"{who}: pact boon {b} grants {c.get('grants')} vs catalog {cat_boon[b].get('grants')}")
                    print(f"    pact boon {b} OK (grants {c.get('grants')} match)")
        for lvl, es in (led.get("levels") or {}).items():
            for e in es or []:
                if e.get("slot") == "pact_boon":
                    b = norm(e["pick"]).split(":")[0].strip()
                    expect(b in cat_boon, f"{who}: pact boon {b} (L{lvl}) not in catalog")
                    expect(e.get("grants") == cat_boon[b].get("grants"),   # CH-13: unconditional
                           f"{who}: pact boon {b} (L{lvl}) grants {e.get('grants')} vs catalog {cat_boon[b].get('grants')}")
                    print(f"    pact boon L{lvl} {b} OK (grants match)")

    # talents
    for lvl, e in talent_picks(led):
        via = resolve_talent(e["pick"])
        expect(via is not None, f"{who}: talent unresolved by catalog: {e['pick']!r}")
        if via:
            b = base_name(norm(e["pick"]).split(":")[-1] if str(e["pick"]).startswith("MC") else str(e["pick"]).split(":")[0])
            known = MC_FEATURES.get(b) or next((t for t in talents_cat["general"] if t["name"] == b), None)
            if known and known.get("grants"):   # BUG-26: + the chosen sub_choice option's grants (was a CH-13 exemption)
                want = dict(known["grants"])
                for k, v in (origin_opt(e, known) or {}).get("grants", {}).items():
                    want[k] = want.get(k, 0) + v
                expect(e.get("grants") == want,
                       f"{who}: talent {b} grants {e.get('grants')} vs catalog {want}")
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
        # FR-12 Phase 3: Spell School Initiate no longer widens the Spell List (the school is a node
        # answer and teaches 2 childed spells, it does not add the school; the name parse is retired).
        # subclass tag grants (Eldritch: Psychic)
        grant_tags = {sg["spell_access"]["tag"] for b, sg in (cat.get("subclass_grants") or {}).items()
                      if any(base_name(e["pick"]) == b for _l, e in subs) and "spell_access" in sg}
        for s in picks:
            meta = spell_meta[s]
            legal_school = meta["school"] in chosen
            legal_tag = bool(set(meta["tags"]) & tags) or bool(set(meta["tags"]) & grant_tags)
            expect(legal_school or legal_tag,
                   f"{who}: spell {s} illegal: school {meta['school']} not in {chosen}, tags {meta['tags']}")
            if meta["school"] in chosen:
                expect(s in schools_cat["schools"].get(meta["school"], []),
                       f"{who}: {s} (school {meta['school']}) missing from spell_schools.yaml")
            # name EVERY route, so a spell legal twice never reads as depending on one (the 2026-09-24
            # misread: Umbral Imbued looked Transmutation-only while its Weapon tag also made it legal)
            why = " + ".join(([f"school {meta['school']}"] if legal_school else [])
                             + ([f"tag {sorted(set(meta['tags']) & (tags | grant_tags))}"] if legal_tag else []))
            print(f"    spell {s:18} legal via {why}")
    elif model == "source":
        src = cat["spellcasting"]["source"]
        primal_flat = {sp for sch in sources_cat["sources"][src].values() for sp in sch}
        # Arcane grant slots the walked ledger carries (Scaletrix): Intuitive Magic (2, any
        # from the MC'd Sorcerer's chosen Source - Arcane per ledger) + Fiendish Magic (1)
        # + each Spellcaster-path rank (1 spell drawn from the MC'd class Source; Scaletrix
        # MC'd Sorcerer = Arcane, so his 2 path ranks are 2 more Arcane slots). FR-13a.
        grant_slots = 0
        for _, e in talent_picks(led):
            if str(e["pick"]).startswith("MC"):   # BUG-26: the Sorcerous Origin answer, not the pick name
                _b = base_name(norm(e["pick"]).split(":")[-1])
                grant_slots += int(((origin_opt(e, MC_FEATURES.get(_b)) or {}).get("grants") or {}).get("spells", 0))
        for t in iter_traits(led):
            if base_name(t["name"]) in ("Fiendish Magic", "Arcane Spell"):
                grant_slots += 1
        for _, e in ((lvl, e) for lvl, ents in (led.get("levels") or {}).items()
                     for e in ents or []):
            if e.get("slot") == "path" and base_name(e.get("pick", "")) == "Spellcaster":
                grant_slots += 1   # MC'd source is Arcane for the one walked case (Sorcerer)
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


# ---- (2b) ledger class-feature rows vs class_features.yaml -----------------
# BUG-39 + BUG-47 (2026-08-21). CH-10 row C1: NOTHING reconciled a ledger's class-feature rows
# against the catalog, and this file did not even load class_features.yaml. What that allowed, on a
# live character: bonan.yaml's L1 row named `Battlecry` (a LEVEL 2 feature), named `Shouts` (which
# occurs zero times in classes.md: they are Battlecry's three options, not a feature), omitted
# `Shattering Force`, and hand-copied Berserker Defense as a flat `grants: {ad: 2}` when the catalog
# declares it `grants_unarmored`, so equipping armour kept the +2 AND added the armour's AD.
#
# What is asserted: every name a ledger claims is a real feature of THAT class at THAT level, and
# the entry's grants equal the catalog's, with the conditional half compared as `grants_unarmored`
# rather than merged, so a re-frozen conditional fails here. Expected values come from the catalog;
# the catalog's own agreement with classes.md is section (3)'s job.
print("\n## (2b) Ledger class-feature rows vs class_features.yaml (BUG-39)")
_cf_classes = class_features_cat["classes"]
_cf_rows = _cf_uncurated = _cf_missing = 0
for fname, led in LEDGERS.items():
    cls = led.get("class")
    per_class = _cf_classes.get(cls)
    if per_class is None:
        continue
    entries = [(1, e) for e in ((led.get("chargen") or {}).get("class_choices") or [])
               if str(e.get("slot", "")).startswith("class_feature")]
    entries += [(int(lvl), e) for lvl, es in (led.get("levels") or {}).items() for e in (es or [])
                if str(e.get("slot", "")).startswith("class_feature")]
    for lvl, e in entries:
        who = f"{fname} L{lvl}"
        rows = per_class.get(lvl)
        if rows is None:                     # outside the curated L1-L6 range (CH-4)
            _cf_uncurated += 1
            print(f"  {who}: {e.get('pick') or e.get('picks')} - L{lvl} not curated yet (CH-4), skipped")
            continue
        by_name = {r["name"]: r for r in rows}
        picks = e.get("picks") or ([e["pick"]] if e.get("pick") else [])
        for name in picks:
            expect(name in by_name,
                   f"{who}: {name!r} is not a {cls} L{lvl} class feature "
                   f"(class_features.yaml has {sorted(by_name)})")
        if e.get("slot") == "class_features":          # the plural carrier: the class grants ALL of them
            expect(set(picks) == set(by_name),
                   f"{who}: lists {sorted(picks)} but {cls} L{lvl} grants {sorted(by_name)}")
        # grants: the catalog is the spec, and the conditional half must STAY conditional
        want, want_un = {}, {}
        for name in picks:
            r = by_name.get(name) or {}
            if r.get("choice"):
                continue                              # its effects live in that picker
            want.update(r.get("grants") or {})
            for _k, _v in class_feature_rider_grants(r, led).items():   # Expert Warlock boon riders
                want[_k] = want.get(_k, 0) + _v
            want_un.update(r.get("grants_unarmored") or {})
        expect((e.get("grants") or {}) == want,
               f"{who}: ledger grants {e.get('grants')} vs catalog {want or None}")
        expect((e.get("grants_unarmored") or {}) == want_un,
               f"{who}: ledger grants_unarmored {e.get('grants_unarmored')} vs catalog "
               f"{want_un or None} (a conditional grant flattened into `grants` is BUG-39)")
        _cf_rows += 1
        print(f"  {who}: {picks} reconcile with class_features.yaml"
              + (f", grants {want}" if want else "")
              + (f" + unarmoured {want_un}" if want_un else ""))
    # completeness, reported not asserted: a curated level whose features are absent from the ledger
    have = {lvl for lvl, _e in entries}
    for lvl, rows in sorted(per_class.items()):
        if rows and lvl not in have and lvl <= (led.get("current_level") or 1):
            _cf_missing += 1
            print(f"  {fname}: L{lvl} class features {[r['name'] for r in rows]} are NOT on the ledger"
                  f" (display gap only: none of them carries a numeric grant, see the note below)")
print(f"  => {_cf_rows} ledger class-feature row(s) reconcile, {_cf_uncurated} outside the curated"
      f" range, {_cf_missing} curated level(s) with no row at all")

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


# BUG-44 (2026-08-21): a prerequisite can be stated as a SENTENCE ABOVE A BULLETED LIST rather than
# inline in the trait name. ancestries.md l.927 reads "The following Traits require the Natural Weapon
# Trait:" and then bullets six Beastborn traits. The old parser only read an inline "(requires X)", so
# md_req came back None for all six, the six catalog rows carried no `requires`, and the reconcile
# below agreed with the omission: a scratch Beastborn could buy Rend with no Natural Weapon and the
# build reported clean. `requires` IS enforced by the builder, so this was a live legality hole.
#
# Scope of a sentence-stated prerequisite: it applies to the BULLET rows that follow it, and ends at
# the first non-bullet trait row (in ancestries.md the six bullets are followed by "(2) Fast
# Reflexes", the first Miscellaneous trait). Verified as the only occurrence of the sentence in the
# file, so this stays a narrow rule rather than a guess about layout.
LIST_REQ_RE = re.compile(r"The following Traits require the (.+?) Trait:", re.I)


def parse_ancestry(md, heading):
    body = ancestry_region(md, heading)
    out, reqs = {}, {}
    pending = None                       # a sentence-stated prerequisite awaiting its bullets
    for mm in re.finditer(r"^(?:(-)\s*)?\((-?\d+)\)\s+(.+?):|^(The following Traits require .+?:)$",
                          body, re.MULTILINE):
        if mm.group(4):                                            # the sentence itself
            pending = re.sub(r"\s+", " ", norm(LIST_REQ_RE.search(mm.group(4)).group(1))).strip()
            continue
        bullet, raw = mm.group(1), mm.group(3)
        rq = re.search(r"\(requires ([^)]*)\)", raw)              # "(requires X)" inside the name
        if not rq:
            after = body[mm.end():mm.end() + 60]                   # or just after the colon
            rq = re.match(r"\s*\(requires ([^)]*)\)", after)
        name = base_name(re.sub(r"\s*\(requires[^)]*\)", "", norm(raw)))
        out[name] = int(mm.group(2))
        if rq:
            reqs[name] = re.sub(r"\s+", " ", norm(rq.group(1))).strip()
        elif pending and bullet:
            reqs[name] = pending
        if not bullet:
            pending = None                                         # the bulleted list has ended
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

# origins (BUG-24): the per-ancestry Origin damage-type lists must match ancestries.md.
def parse_origin_types(md, heading, label):
    body = ancestry_region(md, heading)
    m = re.search(label + r"(.*?)(?:Default Traits|Fiendborn Redemption)", body, re.S)
    seg = m.group(1) if m else ""
    # damage types are Capitalised words in the list sentence(s); collect unique, dedup, sort.
    types = sorted(set(re.findall(r"\b(Cold|Corrosion|Fire|Lightning|Poison|Psychic|Radiant|Umbral)\b", seg)))
    return types

for a in (anc.get("origins") or {}):
    heading = a
    label = "Draconic Origin" if a == "Dragonborn" else "Fiendish Origin"
    md_types = parse_origin_types(anctext, heading, label)
    cat_types = sorted(set(anc["origins"][a]))
    expect(cat_types == md_types,
           f"{a} origin list: catalog {cat_types} vs ancestries.md {md_types}")
    print(f"  {a} origin: {len(cat_types)} damage types match ancestries.md")

# spell-granting ancestry traits (BUG-25): a def carrying `grants: {spells: N}` must also carry the
# spell_access constraint that turns it into N source-filtered child pickers, its rules line must
# actually say it teaches a Spell, and the source + any schools must be real names. Guards against a
# grant that silently reaches the whole spell list.
SPELL_SOURCES = {"Arcane", "Divine", "Primal"}
n_spellgrant = 0
for a in anc["ancestries"]:
    body = ancestry_region(anctext, a)
    for row in anc["ancestries"][a]:
        if int((row.get("grants") or {}).get("spells", 0) or 0) <= 0:
            expect(not row.get("spell_access"),
                   f"{a}/{row['name']}: spell_access without a spells grant")
            continue
        sa = row.get("spell_access") or {}
        expect(bool(sa.get("source")),
               f"{a}/{row['name']}: spells grant with no spell_access.source")
        expect(sa.get("source") in SPELL_SOURCES,
               f"{a}/{row['name']}: spell_access.source {sa.get('source')!r} is not a real Source")
        # oracle for school names = every School appearing in spells.md (spell_schools.yaml only
        # curates the five the six PCs use, and these grants reach outside them).
        for sch in (sa.get("schools") or []):
            expect(sch in {m["school"] for m in spell_meta.values()},
                   f"{a}/{row['name']}: spell_access school {sch!r} is not a real School")
        m = re.search(re.escape(row["name"]) + r":\s*You learn 1 Spell", body)
        expect(bool(m), f"{a}/{row['name']}: ancestries.md does not say it teaches 1 Spell")
        expect(f"{sa['source']} Spell List" in body[m.start():m.start() + 400] if m else False,
               f"{a}/{row['name']}: ancestries.md does not name the {sa.get('source')} Spell List")
        n_spellgrant += 1
        print(f"  {a}/{row['name']}: grants 1 {sa['source']} spell"
              + (f" ({'/'.join(sa['schools'])} only)" if sa.get("schools") else " (any school)")
              + " - matches ancestries.md")
expect(n_spellgrant == 2,
       f"expected 2 spell-granting ancestry traits (Fiendish Magic, Celestial Magic), found {n_spellgrant}")

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
                expect(_ad["cap_stat"] in ("sp", "mp", "spend_limit"),
                       f"damage_addons: {_id} cap_stat must be sp|mp|spend_limit")
# rules grounding for the two computed patterns + the UI hit-grade/crit constants
expect("2 AP worth of AP Enhancements" in _combat_md,
       "damage_addons: the MP-on-AP-Enhancement rule (1 MP = 2 AP worth) not found in combat.md")
# BUG-37: the cap is the Mana Spend Limit, which is CM and rises with level, so it must be
# DERIVED per character. Asserting a literal here only ever mirrored the literal in the catalog.
expect(_defs["mp_to_damage"]["per"] == 2 and _defs["mp_to_damage"].get("cap_stat") == "spend_limit"
       and "cap" not in _defs["mp_to_damage"],
       "damage_addons: mp_to_damage should be +2 per MP, capped at the derived Mana Spend Limit")
# Smite = +1 Bound damage per SP; the single free Damage enhancement is a SEPARATE one-shot
# toggle (smite_free), NOT +1 per SP (Darryl ruling 2026-07-19).
# Darryl 2026-08-14: Smite is capped by the STAMINA SPEND LIMIT, not by max SP. 09's dev-intent
# section says "capped only by the Stamina Spend Limit", so max SP over-reported it (3 vs 2 at L4).
expect(_defs["smite"]["per"] == 1 and _defs["smite"].get("cap_stat") == "spend_limit",
       "damage_addons: smite should be +1 Bound dmg per SP, capped at the Stamina Spend Limit")
expect(_defs["smite_free"]["type"] == "toggle" and _defs["smite_free"]["amount"] == 1,
       "damage_addons: smite_free should be a one-shot +1 toggle (the single free enhancement)")
# generic Damage enhancement is single-target, capped at the derived Stamina Spend Limit (BUG-37).
expect(_defs["gen_damage"]["per"] == 1 and _defs["gen_damage"].get("cap_stat") == "spend_limit"
       and "cap" not in _defs["gen_damage"],
       "damage_addons: gen_damage should be +1 per AP/SP, capped at the derived Stamina Spend Limit")
for _kw in ("Heavy Hit", "Brutal Hit", "bypasses Damage Reduction"):
    expect(_kw in _core_md, f"damage_addons: hit-grade/crit grounding {_kw!r} missing from core-rules.md")
# per-character assignment (single-target v1)
_EXPECT_DMG = {
    "tan":   {"smite", "smite_free", "mp_to_damage", "deaths_toll", "spellstrike", "impact"},
    "xan":   {"smite", "smite_free", "imbue", "mp_to_damage", "spellstrike", "impact"},
    "runt":  {"mp_to_damage", "imbue", "impact"},
    "min":   {"gen_damage", "battlefield", "impact"},
    "bonan": {"rage", "gen_damage", "impact"},
    "scale": {"mp_to_damage", "powerful", "impact"},
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

# ---- BUG-52: the Impact weapon property ----------------------------------------------
# The property itself, cited rather than assumed, and the reason the gate is >= Heavy
# rather than == Heavy (Brutal and Beyond are Heavy Hits for trigger purposes).
_gen_md = read("rules/general-rules.md")
expect("Impact: The Weapon deals +1 damage on Heavy Hits" in _gen_md,
       "damage_addons: the Impact property text not found in general-rules.md")
expect("Brutal Hits are considered Heavy Hits" in _core_md,
       "damage_addons: the Brutal-counts-as-Heavy rule not found in core-rules.md; the "
       "impact gate is grade >= Heavy and depends on it")
expect(_defs["impact"]["type"] == "toggle" and _defs["impact"]["amount"] == 1
       and _defs["impact"].get("when") == "heavy",
       "damage_addons: impact should be a +1 toggle gated on when: heavy")
# All six carry an Impact weapon. Darryl spotted 2026-08-15 that Tanrielle had been left out
# on the filed row's say-so; the Weapon Table settles it, so read the table rather than a
# hand-authored gear card. The table is one cell per line: name, then damage, then properties.
_WEAPON_TABLE_LINES = _gen_md.split("\n")


def _weapon_props(name):
    """The Weapon Table row for a stock weapon, as its property string ('' if absent)."""
    for _i, _l in enumerate(_WEAPON_TABLE_LINES):
        if _l.strip() == name and _i + 2 < len(_WEAPON_TABLE_LINES):
            return _WEAPON_TABLE_LINES[_i + 2].strip()
    return ""


expect("Impact" in _weapon_props("Greatsword"),
       "damage_addons: the Weapon Table no longer lists Greatsword as Impact; Tan's impact "
       f"add-on rests on it (row reads {_weapon_props('Greatsword')!r})")
expect("Impact" not in _weapon_props("Light Crossbow"),
       "damage_addons: the Weapon Table now lists Light Crossbow as Impact; Minimus's base is "
       "an Arcane light crossbow and his impact toggle ships OFF on the strength of that")
expect("impact" in _resolved["tan"],
       "damage_addons: Tan's Greatsword IS an Impact weapon (Weapon Table); she must carry it")
# Every impact assignment names the weapon it comes from, and its default_on is DERIVED
# from that name against the character's base_note rather than trusted. Impact rides a
# WEAPON, the calculator's base is per-character, so the toggle may only ship ON where the
# Impact weapon IS the stated base attack. Renaming a base_note breaks the pairing here
# instead of silently over-reporting at the table.
_STOP = {"of", "the", "and", "with"}
for _h in sorted(_resolved):
    if "impact" not in _resolved[_h]:
        continue
    _imp = next(a for a in _dmg_addons(_h, _dmg)["addons"] if a["id"] == "impact")
    _wpn = _imp.get("weapon")
    expect(isinstance(_wpn, str) and _wpn,
           f"damage_addons: {_h} impact must name the weapon it comes from")
    expect(isinstance(_imp.get("default_on"), bool),
           f"damage_addons: {_h} impact needs an explicit boolean default_on")
    _note = _dmg["characters"][_h].get("base_note", "")
    _base_is_impact = any(w in _note for w in
                          (x for x in re.findall(r"[A-Za-z]{4,}", _wpn or "") if x.lower() not in _STOP))
    expect(_imp["default_on"] == _base_is_impact,
           f"damage_addons: {_h} impact default_on={_imp['default_on']} but base_note "
           f"{_note!r} {'names' if _base_is_impact else 'does not name'} {_wpn!r}")
    print(f"  {_h:6} impact -> {_wpn} (default {'ON' if _imp['default_on'] else 'off'})")

# ---- FR-52: the three roll-section modifiers, all cited ------------------------------
expect("gain a +2 bonus to Hit using it" in _gen_md,
       "FR-52: the Versatile +2 (2-handed grip) text not found in general-rules.md")
expect("additional +2 to your Melee Attack" in _gen_md,
       "FR-52: the Flanking +2 text not found in general-rules.md; it is MELEE only")
expect("Multiple Help Penalty" in _combat_md and "(d8 > d6 > d4)" in _combat_md,
       "FR-52: the Multiple Help Penalty decay chain not found in combat.md")
print(f"  {len(_resolved)} characters resolve; defs + rules grounding reconcile")

# ---- (5b) Rest Point hooks catalog (FR-55) ---------------------------------
# Every hook's cited line range must contain its own name and "Rest Point", so the text the
# Companion shows is anchored in rules/ (trap: intake claims are not evidence). The expected set of
# holders is derived by the engine from the ledgers, and asserted NON-EMPTY (trap 4).
print("\n## (5b) Rest Point hooks catalog (FR-55)")
from build_engine import rest_point_hooks as _rp_hooks  # noqa: E402
_rp = load("builds/catalog/rest_points.yaml")
_rp_list = _rp.get("hooks") or []
expect(len(_rp_list) >= 3, f"rest_points: expected at least 3 hooks, found {len(_rp_list)}")
expect("Rest Points equal to your" in read("rules/general-rules.md"),
       "FR-55: the 'Rest Points equal to your HP maximum' rule is no longer in general-rules.md")
for _h in _rp_list:
    _f, _a, _b = _h["cite"]
    _lines = read("rules/" + _f).splitlines()[_a - 1:_b]
    _blk = " ".join(_lines)
    expect(_h["name"] in _blk, f"rest_points: {_h['name']!r} not in {_f} l.{_a}-{_b}")
    expect("Rest Point" in _blk, f"rest_points: {_f} l.{_a}-{_b} does not mention Rest Points")
    expect(bool(_h.get("spend")) != bool(_h.get("gain")),
           f"rest_points: {_h['name']} must declare exactly one of spend / gain")
    expect(_h["kind"] in ("spell", "maneuver", "rune", "talent"), f"rest_points: bad kind {_h['kind']}")
_rp_held = {f: [x["name"] for x in _rp_hooks(led, _rp)] for f, led in LEDGERS.items()}
expect(any(_rp_held.values()), "rest_points: no ledger holds any hook (an empty set proves nothing)")
print(f"  {len(_rp_list)} hooks cite-checked; held: " + ", ".join(
    f"{f.split('.')[0]}={v}" for f, v in _rp_held.items() if v))

# ---- (4) option-coverage ledger -------------------------------------------
# Every pickable catalog option must DECLARE its effect: modelled, no_effect with a
# category, or todo with a note. BARE (undeclared) is a failure. See tools/coverage.py
# for why: through July 2026 the largest single bug family was "option X does not apply
# its effect", arriving one player at a time because nothing distinguished "correctly
# needs nothing" from "we forgot". The todo count below is the burn-down, and it should
# only ever go DOWN.
print("\n[4] option-coverage ledger")
_cov_opts, (_used_files, _used_paths) = coverage.walk_options()
_cov_totals, _cov_per_file = coverage.summarise(_cov_opts)
for _fn in sorted(_cov_per_file):
    _b = _cov_per_file[_fn]
    print("  %-24s %s" % (_fn, " ".join("%s=%d" % (k, _b[k]) for k in sorted(_b))))
print("  TOTAL %s" % "  ".join("%s=%d" % (k, _cov_totals[k]) for k in sorted(_cov_totals)))

_bare = [o for o in _cov_opts if o.kind == "BARE"]
expect(not _bare,
       "coverage: %d option(s) declare no effect disposition (add grants / no_effect / todo): %s"
       % (len(_bare), ", ".join("%s:%s" % (o.filename, o.name) for o in _bare[:8])))
_badcat = [o for o in _cov_opts if o.kind == "bad_category"]
expect(not _badcat,
       "coverage: %d option(s) use an unknown no_effect category (allowed: %s): %s"
       % (len(_badcat), ", ".join(sorted(coverage.NO_EFFECT_CATEGORIES)),
          ", ".join("%s:%s=%s" % (o.filename, o.name, o.detail) for o in _badcat[:8])))
# A stale exclusion is a silent hole, so it fails too (the anti-mirror rule: the only
# hand-kept lists in coverage.py are the two EXCLUDE sets, and both are checked here).
for _fn in coverage.EXCLUDE_FILES:
    expect(_fn in _used_files,
           f"coverage: EXCLUDE_FILES names {_fn!r} but no such catalog file exists (stale exclusion)")
for _key in coverage.EXCLUDE_PATHS:
    expect(_key in _used_paths,
           f"coverage: EXCLUDE_PATHS names {_key} but that list was not found (stale exclusion)")
# Every todo must actually say what is missing, or it is not a burn-down item.
for _o in _cov_opts:
    if _o.kind == "todo":
        expect(len(_o.detail.strip()) > 10,
               f"coverage: {_o.filename}:{_o.name} todo needs a note saying what it should grant")
_todo_names = sorted({o.name for o in _cov_opts if o.kind == "todo"})
print("  %d options; burn-down = %d rows / %d distinct: %s"
      % (len(_cov_opts), _cov_totals.get("todo", 0), len(_todo_names), ", ".join(_todo_names[:6]) + " ..."))
# Canon safety net: no walked ledger may DEPEND on a todo option, because a todo option is
# by definition not applying its effect. There is NO allowance any more: BUG-20 (2026-09-23)
# modelled Skill/Trade Expertise and retired `_TODO_CANON_OK`, the last one (Tanrielle's
# hand-authored Herbalism cap). Do not reintroduce an allowance set; model the option instead.
#
# BUG-49: the todo set is keyed on (ancestry list, name), not the bare name. Keyed on the name,
# modelling Human's Trade Expertise while Elf's stayed a todo left the name in the set, so an
# allowance for it stayed green while the effect was applied twice (once by the model, once by
# a hand-written ledger cap). A pick matches a todo only in ITS list (the entry's `source:`);
# a pick with no source is checked against every list carrying that name, the strict reading.
_todo_keys = set()
for o in _cov_opts:
    if o.kind == "todo":
        _todo_keys.add((o.path.split(".")[-1] if o.filename == "ancestries.yaml" else o.filename,
                        o.name))
expect(all(isinstance(k, tuple) and len(k) == 2 for k in _todo_keys),
       "coverage: todo keys must be (list, name) pairs (BUG-49)")
for _lf in sorted(glob.glob(os.path.join(LEDGER_DIR, "*.yaml"))):
    _led = yaml.safe_load(open(_lf, encoding="utf-8"))
    if not isinstance(_led, dict):
        continue
    _picks = [(t.get("name", ""), t.get("source")) for t in
              (_led.get("chargen") or {}).get("ancestry_traits", []) or []]
    for _lvl, _ents in (_led.get("levels") or {}).items():
        for _e in _ents or []:
            if _e.get("slot") == "ancestry_trait":
                _picks.append((_e.get("pick", ""), _e.get("source")))
    for _p, _src in _picks:
        _bn = base_name(norm(_p))
        _hit = [k for k in _todo_keys if k[1] == _bn and (_src is None or k[0] == _src)]
        expect(not _hit,
               f"coverage: {os.path.basename(_lf)} picks {_p!r} ({_src or 'no source'}), whose "
               f"effect is an open todo {_hit} (so its derived stats are wrong)")
print("  no walked ledger depends on an un-modelled option (todo set keyed on (list, name), no allowances)")

# ---- Skill / Trade Expertise (BUG-20, 2026-09-23) --------------------------------------------
print("\n## (2e) Skill / Trade Expertise: categories, rows and ledger entries (BUG-20)")
_st = load("builds/catalog/skills_trades.yaml")
_trades = list(_st["trades"])
_cats = dict(_st.get("trade_categories") or {})
_cats_all = dict(_cats, Knowledge=list(_st["knowledge_trades"]))
# The five categories must PARTITION the trade list: every trade in exactly one group.
_seen = [t for grp in _cats_all.values() for t in grp]
expect(sorted(_seen) == sorted(_trades) and len(_seen) == len(set(_seen)),
       f"skills_trades: trade_categories + knowledge_trades must partition trades exactly "
       f"(missing {sorted(set(_trades) - set(_seen))}, dup/extra {sorted(set(t for t in _seen if _seen.count(t) > 1) | (set(_seen) - set(_trades)))})")
# ...and each group must match its "#### <Category>" heading in the rules text (derive, do not
# trust the hand copy). A trade belongs to the heading section its own entry line sits under.
_core = open(os.path.join(ROOT, "rules", "core-rules.md"), encoding="utf-8").read().split("\n")
_hd = [(i, ln[5:].strip()) for i, ln in enumerate(_core) if ln.startswith("#### ")]
def _section_of(trade):
    for i, ln in enumerate(_core):
        if ln.strip() == trade:
            prev = [h for j, h in _hd if j < i]
            if prev and prev[-1] in _cats_all:
                return prev[-1]
    return None
_bad_cat = {t: (c, _section_of(t)) for c, grp in _cats_all.items() for t in grp if _section_of(t) != c}
expect(not _bad_cat, f"skills_trades: category membership disagrees with core-rules.md headings: {_bad_cat}")
expect(len(_cats_all) == 5, f"expected 5 trade categories, got {sorted(_cats_all)}")
# Every catalog Expertise row: a valid kind, valid categories, and a real skill/trade list behind it.
_ex_rows = [(lst, r) for lst, rows in anc["ancestries"].items() if isinstance(rows, list)
            for r in rows if isinstance(r, dict) and "expertise" in r]
expect(len(_ex_rows) >= 5, f"expected the Human Skill Expertise + 4 Trade Expertise rows, got {len(_ex_rows)}")
_skills_all = [n for grp in _st["skills"].values() for n in grp]
def _ex_targets(r):
    if r["expertise"] == "skills":
        return list(_skills_all)
    allowed = set(t for c in (r.get("trade_categories") or _cats_all) for t in _cats_all.get(c, []))
    return [t for t in _trades if t in allowed]
for lst, r in _ex_rows:
    expect(r["expertise"] in ("skills", "trades"), f"ancestries: {lst} {r['name']} expertise kind {r['expertise']!r}")
    expect(set(r.get("trade_categories") or []) <= set(_cats_all),
           f"ancestries: {lst} {r['name']} unknown trade_categories {r.get('trade_categories')}")
    expect(bool(_ex_targets(r)), f"ancestries: {lst} {r['name']} has no legal targets")
_dw = next((r for lst, r in _ex_rows if lst == "Dwarf"), None)
expect(_dw is not None and sorted(_ex_targets(_dw)) == sorted(_cats["Crafting"] + _cats["Services"]),
       "ancestries: Dwarf Trade Expertise must be limited to Crafting or Services (ancestries.md l.406)")
# Every LEDGER entry naming an Expertise row carries the target as data, the name agrees with
# the data (the rename guard), the target is legal for its row, and it has a mastery row. A
# mastery row may carry only a point-purchase limit_raise: the engine flags anything else, and
# this pass counts what it walked so an empty walk cannot pass (trap 4).
_ex_walked = 0
for _fn, _led in sorted(LEDGERS.items()):
    _ents = [("name", t) for t in (_led.get("chargen") or {}).get("ancestry_traits", []) or []]
    _ents += [("pick", e) for L, es in (_led.get("levels") or {}).items() for e in es or []
              if e.get("slot") == "ancestry_trait"]
    for _k, _e in _ents:
        _nm = str(_e.get(_k, ""))
        _row = next((r for lst, r in _ex_rows if r["name"] == base_name(norm(_nm))
                     and (_e.get("source") in (None, lst))), None)
        if _row is None:
            expect("expertise" not in _e, f"{_fn}: {_nm!r} carries expertise but is not an Expertise trait")
            continue
        _ex_walked += 1
        _ex = _e.get("expertise") or {}
        _m = re.search(r"\(([^)]+)\)\s*$", _nm)
        expect(_ex.get("kind") == _row["expertise"], f"{_fn}: {_nm!r} expertise kind {_ex.get('kind')!r} != {_row['expertise']!r}")
        expect(_m is not None and _m.group(1).strip() == _ex.get("target"),
               f"{_fn}: {_nm!r} names a target that its expertise data ({_ex.get('target')!r}) does not carry")
        expect(_ex.get("target") in _ex_targets(_row), f"{_fn}: {_nm!r} target is not legal for its row")
        expect(_ex.get("target") in ((_led.get(_ex.get("kind")) or {}).get("masteries") or {}),
               f"{_fn}: {_nm!r} target has no mastery row")
    for _kind in ("skills", "trades"):
        for _mn, _mm in ((_led.get(_kind) or {}).get("masteries") or {}).items():
            _lr = _mm.get("limit_raise")
            expect(_lr in (None, "skill_point_purchase", "trade_point_purchase"),
                   f"{_fn}: {_kind} {_mn} carries a hand-written limit_raise {_lr!r} (BUG-49: an Expertise raise lives on its trait)")
expect(_ex_walked >= 1, "no ledger Expertise entry walked (Tanrielle's Trade Expertise (Herbalism) should be one)")
print(f"  5 trade categories partition {len(_trades)} trades and match core-rules.md; "
      f"{len(_ex_rows)} Expertise rows; {_ex_walked} ledger Expertise entr{'y' if _ex_walked == 1 else 'ies'} reconcile")

# ---- ledger entry grants must agree with the catalog row they name (CH-5, 2026-07-28) --------
# The engine reads EFFECTS off the ledger entry, never off the pick name. That is the point of
# CH-5, and it moves a burden onto the hand-authored canon ledgers: an entry whose catalog row
# declares an effect must carry that effect, or the trait is priced and inert. Before CH-5 the
# engine name-matched two of these, so the ledgers could get away with omitting them.
#
# The sharp case is a RENAME. `Attribute Increase (Might)` carries `grants: {attr_might: 1}`;
# editing the name to `(Agility)` and forgetting the key leaves it granting Might, silently and
# forever, because nothing else in the pipeline looks at that parenthetical again. So the target
# encoded in the NAME is asserted against the target encoded in the KEY.
#
# `grants_unarmored` is deliberately excluded: it is equipment-conditional, resolved at pick time
# against the character's armour, so a hand-authored ledger legitimately may not carry it.
_ANCROWS = {}
for _lst, _rr in anc["ancestries"].items():
    for _r in _rr or []:
        _ANCROWS.setdefault(_r["name"], _r)
        for _al in (_r.get("aliases") or []):
            _ANCROWS.setdefault(_al, _r)
_recon = 0
for _lf in sorted(glob.glob(os.path.join(LEDGER_DIR, "*.yaml"))):
    _led = yaml.safe_load(open(_lf, encoding="utf-8"))
    if not isinstance(_led, dict):
        continue
    _ents = [(0, t.get("name"), t) for t in (_led.get("chargen") or {}).get("ancestry_traits") or []]
    for _lvl, _rows in (_led.get("levels") or {}).items():
        _ents += [(_lvl, _e.get("pick"), _e) for _e in _rows or []
                  if _e.get("slot") == "ancestry_trait"]
    for _lvl, _nm, _ent in _ents:
        _row = _ANCROWS.get(base_name(norm(_nm)))
        if _row is None:
            continue                                    # off-catalog picks are caught elsewhere
        _want = {_k: _v for _k, _v in (_row.get("grants") or {}).items()
                 if isinstance(_v, (int, float))}
        if _row.get("targets") == "attributes" and "attribute" in _want:
            _amt = _want.pop("attribute")
            _m = re.search(r"\(([^)]+)\)", str(_nm))
            expect(_m is not None,
                   f"{os.path.basename(_lf)} L{_lvl} picks {_nm!r}, a targeted trait, with no "
                   f"(target) in the name, so nothing says which attribute it moves")
            if _m:
                _want["attr_" + _m.group(1).strip().lower()] = _amt
        _have = _ent.get("grants") or {}
        for _k, _v in _want.items():
            expect(_have.get(_k) == _v,
                   f"{os.path.basename(_lf)} L{_lvl} {_nm!r}: catalog declares "
                   f"grants {{{_k}: {_v}}} but the ledger entry has {_have or '{}'}, so the "
                   f"trait is priced and inert (the engine reads the entry, not the name)")
            _recon += 1
print(f"  {_recon} ledger ancestry-trait grants reconcile with their catalog rows (name target == key target)")

# ---- FR-42 / FR-48: talent training riders and the choice node, against the rules text ----------
print("\n## (2f) Talent Combat Training riders and choice nodes (FR-42, FR-48)")
_cc = read("rules/character-creation.md")
_nt = 0
for _t in talents_cat["general"]:
    if not _t.get("training"):
        continue
    _i = _cc.find("\n" + _t["name"] + "\nGeneral Talent")
    expect(_i >= 0, f"talent {_t['name']!r} carries training but has no rules block")
    _blk = _cc[_i:_i + 700]
    _m = re.search(r"Combat Training: You gain Combat Training with\s+(.+?)\.", _blk, re.S)
    expect(_m is not None, f"{_t['name']}: no Combat Training bullet in its rules block")
    if _m:
        _want = [w.strip() for w in re.split(r",|\band\b", " ".join(_m.group(1).split())) if w.strip()]
        _want = [w[0].upper() + w[1:] for w in _want]
        expect(_t["training"] == _want, f"{_t['name']} training {_t['training']} vs rules {_want}")
        _nt += 1
expect(_nt >= 2, f"expected at least 2 talents with a training rider, found {_nt}")
_schools = set(load("builds/catalog/spell_schools.yaml")["schools"])
_nc = 0
for _t in talents_cat["general"] + [r for rows in (talents_cat.get("class_talents") or {}).values() for r in rows]:
    _c = _t.get("sub_choice")
    if not _c:
        continue
    _nc += 1
    if _c.get("kind") == "school_magic":   # FR-12 Phase 3: checked with its twins in (2g) below
        continue
    expect(_c.get("kind") == "spell_list", f"{_t['name']}: unknown choice kind {_c.get('kind')!r}")
    for _o in _c.get("options") or []:
        _src = (_o.get("adds") or {}).get("source")
        expect(_src is None or _src in {"Arcane", "Divine", "Primal"}, f"{_t['name']} option {_o['name']}: bad source {_src}")
        _th = _o.get("then") or {}
        expect(not _th or (_th.get("slot") == "spell_school" and int(_th.get("n", 0)) > 0),
               f"{_t['name']} option {_o['name']}: bad then {_th}")
        expect(bool(_src) != bool(_th), f"{_t['name']} option {_o['name']}: needs exactly one of adds.source / then")
    expect(len(_c.get("options") or []) == 4, f"{_t['name']}: Spellcasting Expansion offers 3 Sources + Schools")
expect(_nc >= 1, "no choice node declared (FR-42)")
# BUG-26: Innate Power's Sorcerous Origin node matches the rules block (classes.md l.2541-2560): the three
# named origins, and only Intuitive Magic grants spells (2) and opens the Sorcerer Source pick.
_ip = MC_FEATURES.get("Innate Power") or {}
_so = _ip.get("sub_choice") or {}
_cls_md = read("rules/classes.md")
_m = re.search(r"Choose a Sorcerous Origin that grants you a benefit:\s+(.+?)\.", _cls_md, re.S)
expect(_so.get("kind") == "sorcerous_origin", f"Innate Power: sub_choice kind {_so.get('kind')!r}")
if _m:
    _names = [w.strip() for w in re.split(r",|\bor\b", " ".join(_m.group(1).split())) if w.strip()]
    expect([o["name"] for o in _so.get("options") or []] == _names, f"Sorcerous Origins {_so.get('options')} vs rules {_names}")
else:
    expect(False, "classes.md: Innate Power 'Choose a Sorcerous Origin' line not found")
_ms = re.search(r"Intuitive Magic: You learn (\d+) Spells", _cls_md)
for _o in _so.get("options") or []:
    _sp = int((_o.get("grants") or {}).get("spells", 0))
    if _o["name"] == "Intuitive Magic":
        expect(_ms and _sp == int(_ms.group(1)) and _o.get("source_pick"), f"Intuitive Magic {_o} vs rules")
    else:
        expect(not _o.get("grants") and not _o.get("source_pick") and _o.get("no_effect"), f"{_o['name']} must be no_effect")
expect(len(_schools) == 8, f"spell_schools.yaml has {len(_schools)} schools")
print(f"  {_nt} talent training riders match their rules bullet; {_nc} choice node(s) well-formed")

# ---- (FR12-3) class coverage: spines vs the rules tables, sources, MC twins ----
# FR-12 Phase 3 (2026-09-24). Three guards the Sorcerer needed and nothing asserted:
#  a. every roster class's spine equals its rules/tables.md Class Table, row by row (no check
#     compared class_spines.yaml with the rules at all; Phase 0 only proved engine byte-identity).
#  b. every Spell Source a roster class draws from has a spell_sources.yaml block (the Sorcerer
#     chooses Arcane/Divine/Primal; the file held Primal only).
#  c. an mc_features row and its base-class twin in class_features.yaml agree (trap 2: Innate
#     Power and Meta Magic now live in both).
print("\n## (FR12-3) class spines vs tables.md; class sources; MC-feature twins")
_tbl = read("rules/tables.md")
_COL = {"Health": "hp", "Attribute": "attr", "Skill": "skill", "Trade": "trade", "Stamina": "sp",
        "Maneuvers": "man", "Mana": "mp", "Spells": "spells"}
_FEAT = {"Path Progression": "Path", "Subclass Feature": "Subclass",
         "Subclass Expert Feature": "Subclass Expert", "Class Capstone Feature": "Class Capstone",
         "Subclass Capstone Feature": "Subclass Capstone"}
_spines = load_class_tables()
expect(len(CLASS_ROSTER) > 0, "class roster empty")
for _c in CLASS_ROSTER:
    _m = re.search(r"### %s Class Table\n\n(\|.*?)\n\n" % re.escape(_c), _tbl + "\n\n", re.S)
    expect(_m is not None, f"tables.md has no {_c} Class Table")
    if _m is None:
        continue
    _rows = [[x.strip() for x in r.strip().strip("|").split("|")] for r in _m.group(1).splitlines()]
    _hdr = [h.split()[0] for h in _rows[0]]
    _body = [r for r in _rows[2:] if r and r[0].isdigit()]
    expect(len(_body) == 10, f"{_c} table has {len(_body)} level rows")
    for _r in _body:
        _lvl = int(_r[0])
        _want = {}
        for _h, _v in zip(_hdr[1:], _r[1:]):
            if _h == "Features":
                _want["features"] = [_FEAT.get(f.strip(), f.strip()) for f in _v.split(",") if f.strip()]
            elif _h in _COL and _v:
                _want[_COL[_h]] = int(_v.lstrip("+"))
        _have = dict(_spines[_c].get(_lvl) or {})
        expect(_have == _want, f"{_c} L{_lvl} spine {_have} != tables.md {_want}")
    print(f"  {_c}: spine matches tables.md, {len(_body)} levels")
for _c in CLASS_ROSTER:
    _sc = CLASS_CAT[_c].get("spellcasting") or {}
    for _src in ([_sc["source"]] if _sc.get("source") else []) + list(_sc.get("source_choice") or []):
        expect(bool(sources_cat["sources"].get(_src)), f"{_c} draws from {_src}: no spell_sources.yaml block")
_cfc = class_features_cat["classes"]
_twins = 0
for _t in talents_cat["mc_features"]:
    _rows_c = _cfc.get(_t["class"])
    if not _rows_c:
        continue   # the class is not walked yet: nothing to agree with
    _twin = next((r for r in _rows_c.get(_t["feature_level"]) or [] if r["name"] == _t["name"]), None)
    if _t["name"] == "Pact Spell":   # a Pact Boon option, not a class-feature row
        continue
    expect(_twin is not None, f"mc_features {_t['name']} has no {_t['class']} L{_t['feature_level']} class_features twin")
    if _twin is None:
        continue
    _twins += 1
    expect((_t.get("grants") or {}) == (_twin.get("grants") or {}),
           f"{_t['name']}: MC grants {_t.get('grants')} != class feature {_twin.get('grants')}")
    _a, _b = _t.get("sub_choice"), _twin.get("sub_choice")
    expect(bool(_a) == bool(_b), f"{_t['name']}: sub_choice on one twin only")
    if _a and _b:
        # FR-12 Phase 3: a node may DERIVE its options (options_from); then the twins must agree on
        # the derivation and on the spell children instead of on a literal list
        expect(_a["kind"] == _b["kind"] and [(o["name"], o.get("grants")) for o in _a.get("options") or []]
               == [(o["name"], o.get("grants")) for o in _b.get("options") or []]
               and _a.get("options_from") == _b.get("options_from")
               and _a.get("child_spells") == _b.get("child_spells")
               and bool(_a.get("options") or _a.get("options_from")),
               f"{_t['name']}: MC and base-class sub_choice options disagree")
expect(_twins > 0, "no MC-feature twin was compared (trap 4)")
# FR-12 Phase 3: every school_magic node (Spell School Initiate twins, Expanded Spell School) derives
# its options from a real spell_sources.yaml block, childs to a real Source, and its row grants the
# spell count the rules print ("You learn 2 Arcane Spells from this Spell School").
_sm = [r for rows in _cfc.values() for lv in rows.values() for r in lv or []] + list(talents_cat["mc_features"]) \
    + [r for rows in (talents_cat.get("class_talents") or {}).values() for r in rows]
_sm = [r for r in _sm if (r.get("sub_choice") or {}).get("kind") == "school_magic"]
expect(len(_sm) >= 3, f"expected 3 school_magic rows (SSI twins + Expanded Spell School), found {len(_sm)} (trap 4)")
_rtxt = read("rules/classes.md") + read("rules/character-creation.md")
for _r in _sm:
    _c = _r["sub_choice"]
    _src = (_c.get("options_from") or {}).get("source_schools")
    expect(len((sources_cat["sources"].get(_src) or {})) == 8, f"{_r['name']}: options_from {_src} is not an 8-school Source")
    expect((_c.get("child_spells") or {}).get("source") in sources_cat["sources"], f"{_r['name']}: child_spells source")
    _blk = _rtxt[_rtxt.find("\n" + _r["name"] + "\n"):][:600]
    _m = re.search(r"You learn (\d) Arcane Spells\s+from this Spell\s+School", " ".join(_blk.split()))
    expect(_m is not None and int(_m.group(1)) == int((_r.get("grants") or {}).get("spells", 0)),
           f"{_r['name']}: grants {_r.get('grants')} vs rules {_m.group(0) if _m else 'no School Magic line'}")
print(f"  {len(_sm)} school_magic nodes derive 8 Arcane schools and grant the rules' spell count")
print(f"  {len(CLASS_ROSTER)} class sources covered; {_twins} MC-feature twins agree with class_features.yaml")

# ---- FR-12 Phase 3 Cleric (2026-09-25) -----------------------------------------------------------
# damage_types.yaml is catalog_build's parse of core-rules.md; re-read the rules INDEPENDENTLY here
# (each type must sit on its category's "Includes" line) so a parser drift cannot pass unseen.
_dt = load("builds/catalog/damage_types.yaml")["categories"]
_core = " ".join(read("rules/core-rules.md").split())
for _cat in ("Physical", "Elemental", "Mystical"):
    _m = re.search(_cat + r" Damage: Includes ([^.]+)\.", _core)
    expect(_m is not None and bool(_dt.get(_cat)), f"damage_types {_cat}: no rules line or empty (trap 4)")
    if _m:
        _words = set(re.findall(r"[A-Z][a-z]+", _m.group(1)))
        expect(set(_dt[_cat]) == _words, f"damage_types {_cat} {_dt[_cat]} != core-rules.md {sorted(_words)}")
# the Divine Domains: 15 of them, each a standalone line (or heading, the Knowledge / Divination
# extraction quirk) inside the Cleric Order block. Magic, and only Magic, says it repeats.
_cl = load("builds/catalog/cleric.yaml")
_doms = {r["name"]: r for r in _cl.get("domains") or []}
_ctxt = read("rules/classes.md")
_blk = _ctxt[_ctxt.index("\nCleric Order\n"):_ctxt.index("\nDivine Blessing\n")]
_lines = [ln.strip().lstrip("#").strip() for ln in _blk.splitlines()]
expect(len(_doms) == 15, f"cleric.yaml carries {len(_doms)} Divine Domains, rules list 15 (trap 4)")
for _n in _doms:
    expect(_n in _lines, f"Divine Domain {_n} is not a line in the Cleric Order block (name drift?)")
_rep_txt = "You can choose this Divine Domain multiple times"
for _n, _r in _doms.items():
    _i = _blk.find("\n" + _n + "\n") if ("\n" + _n + "\n") in _blk else _blk.find("#### " + _n + "\n")
    _seg = " ".join(_blk[_i:_i + 200].split())
    expect(bool(_r.get("repeatable")) == (_rep_txt in _seg), f"Divine Domain {_n}: repeatable flag vs rules text")
    if _r.get("maneuver_type"):
        expect(_r["maneuver_type"] in load("builds/catalog/maneuvers.yaml")["maneuvers"]
               and f"1 {_r['maneuver_type']} Maneuver" in _seg, f"Divine Domain {_n}: maneuver_type vs rules")
    if _r.get("limit_raise"):
        expect(_r["limit_raise"]["group"] in load("builds/catalog/skills_trades.yaml"), f"Divine Domain {_n}: limit_raise group unknown")
# the domain counts the rules print: Cleric Order 2, Expert Cleric 1, Expanded Order 2
_cf = {r["name"]: r for lv in _cfc["Cleric"].values() for r in lv or []}
_eo = next(r for r in talents_cat["class_talents"]["Cleric"] if r["name"] == "Expanded Order")
for _n, _r, _want in (("Cleric Order", _cf["Cleric Order"], 2), ("Expert Cleric", _cf["Expert Cleric"], 1),
                      ("Expanded Order", _eo, 2)):
    expect((_r.get("grants") or {}).get("disciplines") == _want, f"{_n}: grants {_r.get('grants')} != {_want} domains")
_dd = (_cf["Cleric Order"].get("sub_choice") or {}).get("options_from") or {}
expect(_dd.get("damage_categories") == ["Elemental", "Mystical"], f"Cleric Order Divine Damage options_from {_dd}")
print(f"  damage_types.yaml matches core-rules.md; {len(_doms)} Divine Domains match the Cleric Order block")

# ---- verdict --------------------------------------------------------------
print("\n" + "=" * 62)
if fails:
    print(f"FAIL - {len(fails)} of {checks} check(s) failed:")
    for f in fails:
        print("  -", f)
    sys.exit(1)
# CH-17. Two numbers, and the distinction is the whole point of the item. The banner used to
# print a hard-coded "90/90" copied out of section (1), which made a REAL figure look like a
# claim about the whole harness. 90/90 is the derived-stat oracle only, and it is asserted at
# line 120. The total below is every expect() call; it is DATA-DEPENDENT (adding a catalog row
# or a character moves it), so treat a change in it as a prompt to look, not as a regression.
print(f"PASS - {checks} check(s), 0 failures. Engine oracle {total_ok}/{total_ok + total_mismatch}\n"
      "       derived-stat checks (all item/feature effects modelled, BUG-7 runt AD closed);\n"
      "       catalog reconciles with all six ledgers and rules/*.md")
