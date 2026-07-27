#!/usr/bin/env python3
"""The option-coverage ledger: every pickable catalog option must DECLARE its effect.

Why this exists
---------------
Through July 2026 a steady stream of player-reported bugs all said the same sentence:
"option X does not apply its effect" (BUG-19, BUG-20, BUG-22, BUG-24, BUG-25, BUG-27).
They were not independent defects. They were one systemic gap surfacing one player at a
time: the catalog priced an option (cost, prerequisites, legality) but said nothing about
what it DOES, and nothing distinguished "correctly needs nothing" (Discerning Sight is
ADV on a Check, invisible to the engine) from "we forgot" (Mana Increase is +1 MP).

So the arrival rate of that bug family was set by which options players happened to click,
not by code quality, and the only discovery mechanism was a player getting a wrong sheet.

The ledger closes that by making the disposition EXPLICIT and machine-checkable. Every
option resolves to exactly one of:

  modelled   - carries a real effect the builder/engine consumes: grants, grants_unarmored,
               spell_access, limit_raise, opens, choice, languages, training
  no_effect  - deliberately has no build-time effect, with a CATEGORY saying why
               (see NO_EFFECT_CATEGORIES). `flavor: true` is a legacy alias for narrative.
  todo       - a real unmodelled effect, with a note saying what it should grant. This is
               the burn-down list, and it is a NUMBER THAT ONLY GOES DOWN.
  BARE       - undeclared. Illegal: tools/catalog_verify.py fails on it.

Anti-mirror discipline (the 2026-07-27 lesson)
----------------------------------------------
Two bugs shipped completely inert that day because a hand-maintained list mirrored a
build-time list. So this module does NOT keep a list of option families. It DISCOVERS
them: any list of dicts that all carry a `name` key, anywhere in a catalog file, is an
option list. Add a new catalog file or a new option list and it enters the ledger
automatically and fails closed until its options declare themselves.

The only hand-kept lists here are the two EXCLUDE sets, and catalog_verify asserts that
every exclusion still matches something, so a stale exclusion is a failure rather than a
silent hole.

Usage:  python3 tools/coverage.py        # print the ledger + the burn-down list
"""
import os
import sys
import glob

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG_DIR = os.path.join(ROOT, "builds", "catalog")

# Keys that ARE a modelled effect (the builder copies these onto the ledger entry on pick,
# and the engine consumes the numeric ones via sum_grants / grant_flag).
EFFECT_KEYS = {"grants", "grants_unarmored", "spell_access", "limit_raise", "opens",
               "choice", "languages", "training"}

# Declared-neutral categories. Deliberately coarse: the point is to record WHY an option
# has no build-time delta, not to model the effect in prose.
NO_EFFECT_CATEGORIES = {
    "situational",    # conditional / per-rest / AP-spend ability used in play
    "adv",            # ADV or DisADV on Checks or Saves
    "resistance",     # damage resistance, vulnerability, condition immunity
    "sense",          # darkvision, tremorsense, blindsight and friends
    "movement_mode",  # climb / swim / burrow / glide / flight, or terrain rules
    "size",           # size category only
    "training",       # combat training only (no derived-stat delta today)
    "narrative",      # flavour, roleplay, or table-side only
    "delegated",      # the effect belongs to a sub-choice this option unlocks
}

# Catalog files whose named lists are NOT pickable options with build-time effects.
# Each entry carries the reason; catalog_verify checks each one still matches a real file.
EXCLUDE_FILES = {
    "spell_schools.yaml":  "spell lists: a spell's effect is cast at the table, not derived",
    "spell_sources.yaml":  "spell lists: as above, plus source->school mapping data",
    "maneuvers.yaml":      "maneuver names: spent in play, no build-time resource delta",
    "skills_trades.yaml":  "allocator inventory, not options: effects are the mastery numbers",
    "languages.yaml":      "allocator inventory, not options",
    "damage_addons.yaml":  "EV-model inputs for tools/ev_model.py, not builder options",
    "stamina_regen.yaml":  "trigger descriptions surfaced on the sheet (FR-23), not options",
    "class_spines.yaml":   "the per-level class table itself; the engine reads it directly",
}

# Named lists inside an INCLUDED file that are data rather than pickable options.
EXCLUDE_PATHS = {
    ("warlock.yaml", "subclass_grants.Eldritch.languages"):
        "a language grant the subclass confers, not an option the player picks",
}


class Option(object):
    """One pickable catalog option and its declared disposition."""

    def __init__(self, filename, path, name, kind, detail):
        self.filename = filename
        self.path = path
        self.name = name
        self.kind = kind        # modelled | no_effect | todo | BARE | bad_category
        self.detail = detail

    def __repr__(self):
        return "<%s %s/%s %s>" % (self.kind, self.filename, self.name, self.detail)


def _classify(row):
    """Resolve one option dict to (kind, detail). Order matters: a real effect wins."""
    keys = set(row)
    if EFFECT_KEYS & keys:
        return "modelled", ",".join(sorted(EFFECT_KEYS & keys))
    if "todo" in row:
        return "todo", str(row["todo"])
    if row.get("flavor") is True:          # legacy alias, predates the ledger
        return "no_effect", "narrative"
    if "no_effect" in row:
        cat = row["no_effect"]
        if cat not in NO_EFFECT_CATEGORIES:
            return "bad_category", str(cat)
        return "no_effect", cat
    return "BARE", ""


def _discover(node, path, found):
    """Recursively find every list-of-named-dicts. No hand-kept family list (see module doc)."""
    if isinstance(node, dict):
        for key, val in node.items():
            _discover(val, path + [str(key)], found)
    elif isinstance(node, list):
        if node and all(isinstance(x, dict) and "name" in x for x in node):
            found.append((".".join(path), node))
        else:
            for item in node:
                _discover(item, path, found)


def walk_options(catalog_dir=CATALOG_DIR):
    """Return (options, used_exclusions) for every pickable option in the catalog."""
    options = []
    used_files = set()
    used_paths = set()
    for filepath in sorted(glob.glob(os.path.join(catalog_dir, "*.yaml"))):
        filename = os.path.basename(filepath)
        if filename in EXCLUDE_FILES:
            used_files.add(filename)
            continue
        found = []
        _discover(yaml.safe_load(open(filepath, encoding="utf-8")), [], found)
        for path, rows in found:
            if (filename, path) in EXCLUDE_PATHS:
                used_paths.add((filename, path))
                continue
            for row in rows:
                kind, detail = _classify(row)
                options.append(Option(filename, path, str(row.get("name")), kind, detail))
    return options, (used_files, used_paths)


def summarise(options):
    """Counts by kind, plus per-file counts."""
    totals = {}
    per_file = {}
    for opt in options:
        totals[opt.kind] = totals.get(opt.kind, 0) + 1
        bucket = per_file.setdefault(opt.filename, {})
        bucket[opt.kind] = bucket.get(opt.kind, 0) + 1
    return totals, per_file


def main():
    options, _ = walk_options()
    totals, per_file = summarise(options)
    print("Option-coverage ledger (%d pickable options)\n" % len(options))
    for filename in sorted(per_file):
        bucket = per_file[filename]
        bits = " ".join("%s=%d" % (k, bucket[k]) for k in sorted(bucket))
        print("  %-24s %s" % (filename, bits))
    print("\n  TOTAL  " + "  ".join("%s=%d" % (k, totals[k]) for k in sorted(totals)))

    todos = [o for o in options if o.kind == "todo"]
    seen = set()
    print("\nBurn-down list (%d rows, %d distinct options):"
          % (len(todos), len({o.name for o in todos})))
    for opt in sorted(todos, key=lambda o: o.name):
        if opt.name in seen:
            continue
        seen.add(opt.name)
        print("  %-32s %s" % (opt.name, opt.detail))

    bare = [o for o in options if o.kind in ("BARE", "bad_category")]
    if bare:
        print("\nUNDECLARED (%d) - catalog_verify treats these as failures:" % len(bare))
        for opt in bare:
            print("  %s %s/%s %s" % (opt.kind, opt.filename, opt.name, opt.detail))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
