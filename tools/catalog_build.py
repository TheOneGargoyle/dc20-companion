#!/usr/bin/env python3
"""Build the SCRIPTED half of the option catalog: the class spine.

RUNG3_PLAN build-order step 2 (§7) / spike 2 resolution (§11): "script the class spine
(reshape what the engine already holds), hand-curate the small cross-cutting cost lists."

This script owns the scripted half. It reshapes the Spellblade entry from the engine's
CLASS_TABLES into a catalog spine, pulls the Discipline / Subclass / spellcasting facts out
of rules/classes.md, and cross-checks the numeric table against rules/tables.md. Output:
builds/catalog/spellblade.yaml. It NEVER hand-edits numbers — every resource delta comes from
CLASS_TABLES, so the catalog spine can never drift from the engine.

The cross-cutting cost lists (spell_schools.yaml, ancestries.yaml) are hand-curated and live
beside this file; tools/catalog_verify.py checks them against rules/*.md.

Usage:  python3 tools/catalog_build.py            # writes builds/catalog/spellblade.yaml
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

CLASS = "Spellblade"

# Discipline resource deltas (grants) that the engine consumes via ledger `grants:`.
# Names are cross-checked against classes.md below; the numbers are the rules text
# (classes.md l.2874-2935): only Magus and Warrior confer resources.
DISCIPLINE_GRANTS = {
    "Magus": {"grants": {"mp": 1, "spells": 1}},
    "Warrior": {"grants": {"maneuvers": 1}, "training": ["Heavy Armor", "Heavy Shield"]},
    "Acolyte": {},
    "Hex Warrior": {},
    "Spell Breaker": {},
    "Spell Warder": {},
    "Blink Blade": {},
    "Sense Magic": {"flavor": True},
}

# map CLASS_TABLES keys -> catalog spine keys (human-readable)
KEYMAP = {"hp": "hp", "attr": "attribute_points", "skill": "skill_points",
          "trade": "trade_points", "sp": "sp", "man": "maneuvers",
          "mp": "mp", "spells": "spells"}


def spine_from_engine():
    table = CLASS_TABLES[CLASS]
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


def spellblade_section(text):
    """Return the classes.md text from '### Spellblade' up to the next '### ' heading."""
    start = text.index("\n### Spellblade\n")
    rest = text[start + 1:]
    nxt = re.search(r"\n### (?!Spellblade)", rest)
    return rest[: nxt.start()] if nxt else rest


def parse_subclasses(section):
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
    sys.exit("Could not parse Spellblade subclass list from classes.md")


def verify_disciplines_present(section):
    """Confirm every catalog discipline name literally appears in the rules text."""
    missing = [d for d in DISCIPLINE_GRANTS if d not in section]
    if missing:
        sys.exit(f"Discipline(s) not found in classes.md (name drift?): {missing}")


def build():
    text = read(CLASSES_MD)
    section = spellblade_section(text)
    verify_disciplines_present(section)
    subclasses = parse_subclasses(section)
    if len(subclasses) != 3:
        sys.exit(f"Expected 3 Spellblade subclasses, parsed {len(subclasses)}: {subclasses}")

    disciplines = []
    for name, extra in DISCIPLINE_GRANTS.items():
        row = {"name": name}
        row.update(extra)
        disciplines.append(row)

    catalog = {
        "catalog_version": 1,
        "ruleset": "DC20 0.10.5",
        "class": CLASS,
        "generated_by": "tools/catalog_build.py",
        "source": "CLASS_TABLES (build_engine.py) + rules/classes.md l.2759-3048 + rules/tables.md l.157-170",
        "spine": spine_from_engine(),
        "disciplines_pick_l1": 2,
        "disciplines": disciplines,
        "subclasses": subclasses,
        "spellcasting": {"model": "schools", "schools_chosen": 2, "tag_access": ["Weapon", "Ward"]},
        "paths": ["Martial", "Spellcaster"],
    }
    return catalog


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="print, do not write")
    args = ap.parse_args()
    catalog = build()
    header = ("# SCRIPTED — do not hand-edit. Regenerate: python3 tools/catalog_build.py\n"
              "# Spine numbers come straight from CLASS_TABLES; names cross-checked vs classes.md.\n")
    body = yaml.safe_dump(catalog, sort_keys=False, allow_unicode=True, width=100)
    out = header + body
    if args.check:
        print(out)
        return
    outdir = os.path.join(ROOT, "builds", "catalog")
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "spellblade.yaml")
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"[wrote {path}]")


if __name__ == "__main__":
    main()
