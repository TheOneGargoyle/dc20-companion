#!/usr/bin/env python3
"""Build the SCRIPTED half of the option catalog: the class spines.

RUNG3_PLAN build-order step 2 (Spellblade pilot) + step 4 (fan-out to the other five PCs'
classes) / spike 2 resolution (SS11): "script the class spine (reshape what the engine already
holds), hand-curate the small cross-cutting cost lists."

This script owns the scripted half for ALL FIVE walked classes (Spellblade, Warlock,
Commander, Barbarian, Druid). For each class it reshapes the engine's CLASS_TABLES into a
catalog spine, pulls the class-choice facts (Disciplines / Pact Boons / Subclasses /
spellcasting model) out of rules/classes.md, and cross-checks every curated name against the
rules text. Output: builds/catalog/<class>.yaml. It NEVER hand-edits numbers - every resource
delta comes from CLASS_TABLES, so the catalog spines can never drift from the engine.

The cross-cutting cost lists (spell_schools.yaml, spell_sources.yaml, ancestries.yaml,
maneuvers.yaml, talents.yaml) are hand-curated and live beside the output;
tools/catalog_verify.py checks them against rules/*.md.

Usage:  python3 tools/catalog_build.py            # writes builds/catalog/<class>.yaml x5
        python3 tools/catalog_build.py --check     # build in memory, print, don't write
"""
import argparse
import os
import re
import sys

import yaml

# import the single source of truth for the numbers
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_engine import CLASS_TABLES  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLASSES_MD = os.path.join(ROOT, "rules", "classes.md")

# ---------------------------------------------------------------------------
# Per-class curated facts. Names are cross-checked against classes.md below;
# resource `grants:` mirror the ledger convention (SCHEMA.md) so a builder can
# look an option up and know its deltas without the engine special-casing it.
# ---------------------------------------------------------------------------

# Spellblade Discipline resource deltas (classes.md l.2874-2935): only Magus and
# Warrior confer resources.
SPELLBLADE_DISCIPLINES = {
    "Magus": {"grants": {"mp": 1, "spells": 1}},
    "Warrior": {"grants": {"maneuvers": 1}, "training": ["Heavy Armor", "Heavy Shield"]},
    "Acolyte": {},
    "Hex Warrior": {},
    "Spell Breaker": {},
    "Spell Warder": {},
    "Blink Blade": {},
    "Sense Magic": {"flavor": True},
}

# Warlock Pact Boon options (classes.md "Pact Boon ... Weapon, Armor, Spell, or Familiar").
# Pact Weapon: "You learn 2 Attack Maneuvers of your choice"; Pact Armor: "You learn 2
# Defensive Maneuvers of your choice" (+1 AD & MDR are conditional, worn-only - not a grant).
WARLOCK_PACT_BOONS = {
    "Pact Weapon": {"grants": {"maneuvers": 2}, "note": "2 Attack Maneuvers; Weapon Training; Spell Focus property"},
    "Pact Armor": {"grants": {"maneuvers": 2}, "note": "2 Defensive Maneuvers; Armor Training; +1 AD & MDR while worn (contextual, not a grant)"},
    "Pact Spell": {"note": "an existing known Spell becomes the Pact Spell (no resource delta)"},
    "Pact Familiar": {"note": "summons a familiar (no resource delta)"},
}

# Spellblade Rune Knight runes (classes.md l.3080-3116): "You learn 2 Runes from the following
# list." Six runes; short names (the ledger's convention). None confer a resource delta (their
# effects are passive / on-Smite riders), so no `grants:` - they are pure picks that flow from the
# Rune Knight subclass grant (runes: 2) via the FR-8 slice-2 child-slot backbone.
RUNES = {
    "Earth": {},
    "Flame": {},
    "Frost": {},
    "Lightning": {},
    "Water": {},
    "Wind": {},
}

# Subclass resource grants the walked ledgers record (cross-checked below):
# Eldritch Otherworldly Gift - Psychic Spellcasting: "You learn 1 Spell of your choice with
# the Psychic Spell Tag. When you learn a new Spell, you can choose any Spell that has the
# Psychic Spell Tag." (classes.md l.3414-17)
# Eldritch also grants Fluent Deep Speech for free (classes.md l.3432) - modelled as a
# `languages` grant so the builder can flow it and the engine zero-costs it (BUG-2).
# Spellblade Rune Knight learns 2 Runes (classes.md l.3080) - a pickable grant that materialises
# 2 rune child-slots via the FR-8 slice-2 backbone (FR-8 slice 3).
SUBCLASS_GRANTS = {
    "Warlock": {"Eldritch": {"grants": {"spells": 1}, "spell_access": {"tag": "Psychic"},
                             "languages": [{"name": "Deep Speech", "fluency": "Fluent"}]}},
    "Spellblade": {"Rune Knight": {"grants": {"runes": 2}}},
}

CLASS_CONFIG = {
    "Spellblade": {
        "source_note": "CLASS_TABLES (build_engine.py) + rules/classes.md l.2759-3048 + rules/tables.md l.157-170",
        "extras": {
            "disciplines_pick_l1": 2,
            "disciplines": SPELLBLADE_DISCIPLINES,
            "runes": RUNES,
        },
        "spellcasting": {"model": "schools", "schools_chosen": 2, "tag_access": ["Weapon", "Ward"]},
    },
    "Warlock": {
        "source_note": "CLASS_TABLES (build_engine.py) + rules/classes.md l.3145-3465 + rules/tables.md l.172-186",
        "extras": {
            "pact_boons_pick_l1": 1,
            "pact_boons": WARLOCK_PACT_BOONS,
        },
        # classes.md l.3204: "Spell List: Choose 3 Spell Schools. When you learn a new Spell,
        # you can choose any Spell from the chosen Spell Schools." -> schools model, NOT a
        # Source draw (the SS11 source-heading wrinkle does not bite the Warlock).
        "spellcasting": {"model": "schools", "schools_chosen": 3},
    },
    "Commander": {
        "source_note": "CLASS_TABLES (build_engine.py) + rules/classes.md l.1059-1269 + rules/tables.md l.67-81",
        "extras": {},
        # Martial class: no Spell List of its own. Spells arrive only via the Spellcaster
        # Path first-time rider: "A Class that starts without a Spell List gains a Spell List
        # of their choice from any Class" (character-creation.md l.753-756).
        "spellcasting": {"model": "none", "path_rider": "spell list of choice from any class (character-creation.md l.753-756)"},
    },
    "Barbarian": {
        "source_note": "CLASS_TABLES (build_engine.py) + rules/classes.md l.34-274 + rules/tables.md l.7-21",
        "extras": {},
        "spellcasting": {"model": "none", "path_rider": "spell list of choice from any class (character-creation.md l.753-756)"},
    },
    "Druid": {
        "source_note": "CLASS_TABLES (build_engine.py) + rules/classes.md l.1270-1684 + rules/tables.md l.82-96",
        "extras": {},
        # classes.md l.1315-16: "When you learn a new Spell, you can choose any Spell on the
        # Primal Spell Source." -> source model; THIS is where the SS11 parent-source-heading
        # wrinkle bites (see spell_sources.yaml).
        "spellcasting": {"model": "source", "source": "Primal"},
    },
}

# map CLASS_TABLES keys -> catalog spine keys (human-readable)
KEYMAP = {"hp": "hp", "attr": "attribute_points", "skill": "skill_points",
          "trade": "trade_points", "sp": "sp", "man": "maneuvers",
          "mp": "mp", "spells": "spells"}


def spine_from_engine(cls):
    table = CLASS_TABLES[cls]
    spine = {}
    for level, deltas in sorted(table.items()):
        row = {}
        for src, dst in KEYMAP.items():
            if deltas.get(src):
                row[dst] = deltas[src]
        row["features"] = list(deltas.get("features", []))
        spine[level] = row
    return spine


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def class_section(text, cls):
    """Return the classes.md text from '### <cls>' up to the next '### ' heading."""
    start = text.index(f"\n### {cls}\n")
    rest = text[start + 1:]
    nxt = re.search(rf"\n### (?!{re.escape(cls)})", rest)
    return rest[: nxt.start()] if nxt else rest


def parse_subclasses(section, cls):
    """The 3 subclasses are the bullet list under 'Level 3 Class Features -> Subclass'."""
    lines = section.splitlines()
    for i, ln in enumerate(lines):
        if ln.strip().startswith("Choose one of the following options"):
            subs = []
            for ln2 in lines[i + 1:]:
                s = ln2.strip()
                if s.startswith("- "):
                    subs.append(s[2:].strip())
                elif subs:
                    break
            if subs:
                return subs
    sys.exit(f"Could not parse {cls} subclass list from classes.md")


def verify_names_present(section, names, what, cls):
    """Confirm every curated name literally appears in the class's rules text."""
    missing = [n for n in names if n not in section]
    if missing:
        sys.exit(f"{cls} {what} not found in classes.md (name drift?): {missing}")


def build(cls):
    cfg = CLASS_CONFIG[cls]
    text = read(CLASSES_MD)
    section = class_section(text, cls)
    subclasses = parse_subclasses(section, cls)
    if len(subclasses) != 3:
        sys.exit(f"Expected 3 {cls} subclasses, parsed {len(subclasses)}: {subclasses}")

    catalog = {
        "catalog_version": 1,
        "ruleset": "DC20 0.10.5",
        "class": cls,
        "generated_by": "tools/catalog_build.py",
        "source": cfg["source_note"],
        "spine": spine_from_engine(cls),
    }

    extras = cfg["extras"]
    if "disciplines" in extras:
        verify_names_present(section, extras["disciplines"], "discipline(s)", cls)
        catalog["disciplines_pick_l1"] = extras["disciplines_pick_l1"]
        catalog["disciplines"] = [dict({"name": n}, **v) for n, v in extras["disciplines"].items()]
    if "pact_boons" in extras:
        verify_names_present(section, extras["pact_boons"], "pact boon(s)", cls)
        catalog["pact_boons_pick_l1"] = extras["pact_boons_pick_l1"]
        catalog["pact_boons"] = [dict({"name": n}, **v) for n, v in extras["pact_boons"].items()]
    if "runes" in extras:
        # FR-8 slice 3: Rune Knight learns 2 Runes; same shape as disciplines/pact_boons so the
        # builder can look one up. Short names (ledger convention) appear in classes.md as "<X> Rune".
        verify_names_present(section, extras["runes"], "rune(s)", cls)
        catalog["runes"] = [dict({"name": n}, **v) for n, v in extras["runes"].items()]

    catalog["subclasses"] = subclasses
    sg = SUBCLASS_GRANTS.get(cls, {})
    if sg:
        for name in sg:
            if name not in subclasses:
                sys.exit(f"{cls} subclass-grant name drift: {name} not in {subclasses}")
        catalog["subclass_grants"] = sg
    catalog["spellcasting"] = cfg["spellcasting"]
    catalog["paths"] = ["Martial", "Spellcaster"]
    return catalog


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="print, do not write")
    args = ap.parse_args()
    header = ("# SCRIPTED — do not hand-edit. Regenerate: python3 tools/catalog_build.py\n"
              "# Spine numbers come straight from CLASS_TABLES; names cross-checked vs classes.md.\n")
    for cls in CLASS_CONFIG:
        catalog = build(cls)
        body = yaml.safe_dump(catalog, sort_keys=False, allow_unicode=True, width=100)
        out = header + body
        if args.check:
            print(out)
            continue
        outdir = os.path.join(ROOT, "builds", "catalog")
        os.makedirs(outdir, exist_ok=True)
        path = os.path.join(outdir, cls.lower() + ".yaml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"[wrote {path}]")


if __name__ == "__main__":
    main()
