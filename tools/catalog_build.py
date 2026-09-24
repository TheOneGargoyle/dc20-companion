#!/usr/bin/env python3
"""Build the SCRIPTED half of the option catalog: the class spines.

RUNG3_PLAN build-order step 2 (Spellblade pilot) + step 4 (fan-out to the other five PCs'
classes) / spike 2 resolution (SS11): "script the class spine (reshape what the engine already
holds), hand-curate the small cross-cutting cost lists."

This script owns the scripted half for EVERY class in the roster (build_engine.class_roster(),
i.e. class_spines.yaml; CH-10 A14). For each class it reshapes the authored class spine from
builds/catalog/class_spines.yaml into a catalog spine, pulls the class-choice facts
(Disciplines / Pact Boons / Subclasses / spellcasting model) out of rules/classes.md, and
cross-checks every curated name against the rules text. Output: builds/catalog/<class>.yaml.
It NEVER hand-edits numbers - every resource delta comes from class_spines.yaml, which the
engine reads too (FR-12.0), so the catalog spines can never drift from the engine.

The cross-cutting cost lists (spell_schools.yaml, spell_sources.yaml, ancestries.yaml,
maneuvers.yaml, talents.yaml) are hand-curated and live beside the output;
tools/catalog_verify.py checks them against rules/*.md.

Usage:  python3 tools/catalog_build.py            # writes builds/catalog/<class>.yaml per roster class
        python3 tools/catalog_build.py --check     # build in memory, print, don't write
"""
import argparse
import copy
import os
import re
import sys

import yaml

# the single source of truth for the numbers is now DATA (FR-12.0): the engine and this
# generator both read builds/catalog/class_spines.yaml, so the spines can never drift.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_engine import load_class_tables, class_roster  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLASS_SPINES = load_class_tables(os.path.join(ROOT, "builds", "catalog", "class_spines.yaml"))
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
    "Acolyte": {"no_effect": "situational"},
    "Hex Warrior": {"no_effect": "situational"},
    "Spell Breaker": {"no_effect": "situational"},
    "Spell Warder": {"no_effect": "situational"},
    "Blink Blade": {"no_effect": "situational"},
    "Sense Magic": {"flavor": True},
}

# Warlock Pact Boon options (classes.md "Pact Boon ... Weapon, Armor, Spell, or Familiar").
# Pact Weapon: "You learn 2 Attack Maneuvers of your choice"; Pact Armor: "You learn 2
# Defensive Maneuvers of your choice" (+1 AD & MDR are conditional, worn-only - not a grant).
WARLOCK_PACT_BOONS = {
    "Pact Weapon": {"grants": {"maneuvers": 2}, "maneuver_type": "Attack", "note": "2 Attack Maneuvers of your choice (classes.md l.3244); Weapon Training; Spell Focus property"},
    "Pact Armor": {"grants": {"maneuvers": 2}, "maneuver_type": "Defense", "note": "2 Defensive Maneuvers of your choice (classes.md l.3269); Armor Training; +1 AD & MDR while worn (contextual, not a grant)"},
    "Pact Spell": {"no_effect": "situational",
                   "note": "an existing known Spell becomes the Pact Spell (no resource delta)"},
    "Pact Familiar": {"no_effect": "situational",
                      "note": "summons a familiar (no resource delta)"},
}

# Spellblade Rune Knight runes (classes.md l.3080-3116): "You learn 2 Runes from the following
# list." Six runes; short names (the ledger's convention). None confer a resource delta (their
# effects are passive / on-Smite riders), so no `grants:` - they are pure picks that flow from the
# Rune Knight subclass grant (runes: 2) via the FR-8 slice-2 child-slot backbone.
RUNES = {
    "Earth": {"no_effect": "situational"},
    "Flame": {"no_effect": "situational"},
    "Frost": {"no_effect": "situational"},
    # BUG-43 (2026-08-21) was hand-applied to spellblade.yaml; carried here so a regenerate keeps it.
    "Lightning": {"grants": {"speed": 1},
                  "note": "Quickness: +1 Speed (classes.md l.3103). Charged (Stunned 1 on a failed Save when you Smite) stays situational."},
    "Water": {"no_effect": "situational"},
    "Wind": {"grants": {"jump": 3},
             "note": "Wind Swept: +3 Jump Distance (classes.md l.3114-3116). The 'no longer halved on a Stand Jump' half and Hurricane (push 1 Space) stay situational."},
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
    # BUG-21: Paladin's Lay on Hands "You gain the Acolyte Discipline. If you already know that
    # Discipline, you gain another one of your choice" (classes.md l.3041-3045). So it is a 1-discipline
    # grant whose DEFAULT is fixed (Acolyte) and which becomes a free pick when Acolyte is already
    # held - `prefer` carries that, and the builder auto-fills it only when it is still available.
    # FR-12 Phase 3: each Sorcerer Spark names a Meta Magic option ("choose another Meta Magic
    # option if you already know it"), the same prefer shape as Paladin -> Acolyte.
    # classes.md l.2708-2710 (Celestial Protection), l.2745-2748 (Draconic Transmutation). NOT
    # modelled: the 2 Ancestry Points restricted to Angelborn / Dragonborn traits.
    "Sorcerer": {"Angelic": {"grants": {"metamagic": 1}, "prefer": {"metamagic": "Careful Spell"}},
                 "Draconic": {"grants": {"metamagic": 1}, "prefer": {"metamagic": "Transmuted Spell"}}},
    "Spellblade": {"Rune Knight": {"grants": {"runes": 2}},
                   "Paladin": {"grants": {"disciplines": 1}, "prefer": {"disciplines": "Acolyte"}}},
}

# BUG-35: Paragon is the one UNIVERSAL subclass (every class's list ends with it) and it granted
# nothing at all. character-creation.md l.757-780: Novice Paragon at L3 = "a Class Talent of your
# choice from your Class" plus Jack of one Trade = 1 Trade Point; Expert Paragon (L7) and Master
# Paragon (L10) each grant another Class Talent.
#
# Two shapes, deliberately different:
#   * the Trade Point is an ordinary numeric grant (`trade_points`, which is the key the engine's
#     sum_grants adds to earned_tp - NOT `trades`, which is the FR-3/FR-17 plan point-buy carrier).
#   * the Class Talents are `level_riders`: REAL sibling talent entries spawned at the named level,
#     not grant-children. A grant-child is written as a bare name string and the engine assumes it
#     is a leaf, so a grant-bearing child applies nothing (that is BUG-34); a class talent is very
#     much grant-bearing (Unfathomable Strength {jump:1}, Expanded Disciplines {disciplines:2}).
#     As a real entry it goes down the ordinary talent path, which applies grants (BUG-33) and
#     runs the talent rider, for free.
#   `restrict: class_talents` narrows the picker to THIS class's class_talents, which is what RAW
#   says and what the general talent picker cannot express.
PARAGON = {
    "grants": {"trade_points": 1},
    "level_riders": {3: [{"slot": "talent", "restrict": "class_talents"}],
                     7: [{"slot": "talent", "restrict": "class_talents"}],
                     10: [{"slot": "talent", "restrict": "class_talents"}]},
    "source": "character-creation.md l.757-780 (Novice / Expert / Master Paragon)",
}

CLASS_CONFIG = {
    "Spellblade": {
        "source_note": "builds/catalog/class_spines.yaml + rules/classes.md l.2759-3048 + rules/tables.md l.157-170",
        "extras": {
            "disciplines_pick_l1": 2,
            "disciplines": SPELLBLADE_DISCIPLINES,
            "runes": RUNES,
        },
        "spellcasting": {"model": "schools", "schools_chosen": 2, "tag_access": ["Weapon", "Ward"]},
    },
    "Warlock": {
        "source_note": "builds/catalog/class_spines.yaml + rules/classes.md l.3145-3465 + rules/tables.md l.172-186",
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
        "source_note": "builds/catalog/class_spines.yaml + rules/classes.md l.1059-1269 + rules/tables.md l.67-81",
        "extras": {},
        # Martial class: no Spell List of its own. Spells arrive only via the Spellcaster
        # Path first-time rider: "A Class that starts without a Spell List gains a Spell List
        # of their choice from any Class" (character-creation.md l.753-756).
        "spellcasting": {"model": "none", "path_rider": "spell list of choice from any class (character-creation.md l.753-756)"},
    },
    "Barbarian": {
        "source_note": "builds/catalog/class_spines.yaml + rules/classes.md l.34-274 + rules/tables.md l.7-21",
        "extras": {},
        "spellcasting": {"model": "none", "path_rider": "spell list of choice from any class (character-creation.md l.753-756)"},
    },
    "Druid": {
        "source_note": "builds/catalog/class_spines.yaml + rules/classes.md l.1270-1684 + rules/tables.md l.82-96",
        "extras": {},
        # classes.md l.1315-16: "When you learn a new Spell, you can choose any Spell on the
        # Primal Spell Source." -> source model; THIS is where the SS11 parent-source-heading
        # wrinkle bites (see spell_sources.yaml).
        "spellcasting": {"model": "source", "source": "Primal"},
    },
    "Sorcerer": {
        "source_note": "builds/catalog/class_spines.yaml + rules/classes.md l.2482-2758 + rules/tables.md l.142-155",
        "extras": {},
        # classes.md l.2528-2530: "Spell List: You choose 1 Spell Source (Arcane, Divine, or Primal).
        # When you learn a new Spell, you can choose any Spell from the chosen Spell Source." ->
        # the source model with the source CHOSEN at chargen (FR-12 Phase 3): the ledger carries
        # chargen.spell_source, and there is no fixed `source` key.
        "spellcasting": {"model": "source", "source_choice": ["Arcane", "Divine", "Primal"]},
    },
}

# BUG-35: Paragon is offered by EVERY class, so its grants are attached to every class rather
# than hand-listed five times (a hand-kept mirror of CLASS_CONFIG is exactly the duplicate-list
# trap behind BUG-31/32/33). A fresh copy per class so the YAML dump never emits an alias, and
# so a future per-class tweak cannot leak sideways. The name is still checked against the parsed
# subclass list in build(), so this fails loudly if a class ever stops offering Paragon.
# CH-10 A14: the roster is class_spines.yaml (via the engine). CLASS_CONFIG holds the per-class
# facts the spine cannot (spellcasting model, extras), so it must cover the roster exactly: a class
# added to the spine without its config, or a config for a class the spine lacks, fails loudly here.
ROSTER = class_roster(CLASS_SPINES)
if set(CLASS_CONFIG) != set(ROSTER):
    sys.exit("CLASS_CONFIG does not match the class_spines.yaml roster: missing %s, extra %s"
             % (sorted(set(ROSTER) - set(CLASS_CONFIG)), sorted(set(CLASS_CONFIG) - set(ROSTER))))

for _cls in ROSTER:
    SUBCLASS_GRANTS.setdefault(_cls, {})["Paragon"] = copy.deepcopy(PARAGON)

# map CLASS_TABLES keys -> catalog spine keys (human-readable)
KEYMAP = {"hp": "hp", "attr": "attribute_points", "skill": "skill_points",
          "trade": "trade_points", "sp": "sp", "man": "maneuvers",
          "mp": "mp", "spells": "spells"}


def spine_from_data(cls):
    table = CLASS_SPINES[cls]
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


def parse_combat_training(block, what):
    """FR-48: the first 'Combat Training: a, b, c' line in `block`, joined across a trailing-comma
    wrap (Spellblade's line wraps mid-list). Returned verbatim from the rules text, in order."""
    lines = block.splitlines()
    for i, ln in enumerate(lines):
        if ln.strip().startswith("Combat Training:"):
            txt = ln.strip()[len("Combat Training:"):].strip()
            j = i
            while txt.endswith(",") and j + 1 < len(lines):
                j += 1
                txt += " " + lines[j].strip()
            out = [t.strip() for t in txt.split(",") if t.strip()]
            if out:
                return out
    sys.exit(f"Could not parse a Combat Training line for {what}")


def path_training():
    """FR-48: the Martial / Spellcaster Path riders (character-creation.md '#### <X> Path')."""
    text = read(os.path.join(ROOT, "rules", "character-creation.md"))
    out = {}
    for p in ("Martial", "Spellcaster"):
        start = text.index(f"\n#### {p} Path\n")
        out[p] = parse_combat_training(text[start + 1:start + 600], f"the {p} Path")
    return out


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
        "spine": spine_from_data(cls),
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
    # FR-48: the class's own base Combat Training, parsed from its class section, and the Path
    # riders. Seeded into a scratch ledger (blank_ledger) and onto a picked Path entry.
    catalog["combat_training"] = parse_combat_training(section, cls)
    catalog["path_training"] = path_training()
    return catalog


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="print, do not write")
    args = ap.parse_args()
    header = ("# SCRIPTED - do not hand-edit. Regenerate: python3 tools/catalog_build.py\n"
              "# Spine numbers come from builds/catalog/class_spines.yaml; names cross-checked vs classes.md.\n")
    for cls in ROSTER:
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
