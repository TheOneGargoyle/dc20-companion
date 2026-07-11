#!/usr/bin/env python3
"""DC20 build-ledger replay engine (v1). Ruleset: DC20 Beta 0.10.5.

Replays a builds/<pc>.yaml ledger (schema v1, see builds/SCHEMA.md), derives the
character's numbers at a target level, checks legality budgets, and reports
discrepancies vs the sheet ("expected" block).

Usage:
  python3 tools/build_engine.py builds/tanrielle.yaml            # at current_level
  python3 tools/build_engine.py builds/tanrielle.yaml --level 6  # replay a plan level
  python3 tools/build_engine.py builds/tanrielle.yaml --report   # also write builds/reports/

Scope (v1): resource totals, formulas, point budgets (attributes, ancestry,
skills/trades/languages incl. conversions). NOT yet: PD/AD derivation (armor
stacking), per-skill die bonuses, spell/maneuver legality vs school lists.
"""
import argparse
import math
import os
import sys

import yaml

# ---------------------------------------------------------------- rules data
# Class tables from rules/tables.md (0.10.5). Per level: deltas.
# Keys: hp, attr, skill, trade, sp, man (maneuvers), mp, spells, features.
CLASS_TABLES = {
    "Spellblade": {  # tables.md l.157-170
        1: dict(hp=8, sp=1, man=1, mp=3, spells=2, features=["Class Features"]),
        2: dict(hp=1, features=["Class Feature", "Talent", "Path"]),
        3: dict(hp=2, attr=1, skill=1, trade=1, man=1, mp=2, features=["Subclass"]),
        4: dict(hp=1, features=["Talent", "2 Ancestry Points", "Path"]),
        5: dict(hp=2, attr=1, skill=2, trade=1, sp=1, mp=1, spells=1, features=["Class Feature"]),
        6: dict(hp=1, skill=1, features=["Talent", "Path"]),
        7: dict(hp=2, man=1, mp=2, features=["Subclass Expert"]),
        8: dict(hp=1, attr=1, skill=1, trade=1, features=["Talent", "2 Ancestry Points", "Path"]),
        9: dict(hp=2, sp=1, mp=1, spells=1, features=["Class Capstone"]),
        10: dict(hp=1, attr=1, skill=2, trade=1, man=1, mp=2, features=["Subclass Capstone"]),
    },
    "Warlock": {  # tables.md l.172-186
        1: dict(hp=8, mp=6, spells=4, features=["Class Features"]),
        2: dict(hp=1, features=["Class Feature", "Talent", "Path"]),
        3: dict(hp=2, attr=1, skill=1, trade=1, mp=3, spells=1, features=["Subclass"]),
        4: dict(hp=1, features=["Talent", "2 Ancestry Points", "Path"]),
        5: dict(hp=2, attr=1, skill=2, trade=1, mp=3, spells=1, features=["Class Feature"]),
        6: dict(hp=1, skill=1, features=["Talent", "Path"]),
        7: dict(hp=2, mp=3, spells=1, features=["Subclass Expert"]),
        8: dict(hp=1, attr=1, skill=1, trade=1, features=["Talent", "2 Ancestry Points", "Path"]),
        9: dict(hp=2, mp=3, spells=1, features=["Class Capstone"]),
        10: dict(hp=1, attr=1, skill=2, trade=1, mp=3, spells=1, features=["Subclass Capstone"]),
    },
    "Commander": {  # tables.md l.67-81 (Minimus; a.k.a. the Warlord-flavoured class)
        1: dict(hp=8, sp=2, man=2, features=["Class Features"]),
        2: dict(hp=2, features=["Class Feature", "Talent", "Path"]),
        3: dict(hp=2, attr=1, skill=1, trade=1, sp=1, man=1, features=["Subclass"]),
        4: dict(hp=2, features=["Talent", "2 Ancestry Points", "Path"]),
        5: dict(hp=2, attr=1, skill=2, trade=1, man=1, features=["Class Feature"]),
        6: dict(hp=2, skill=1, features=["Talent", "Path"]),
        7: dict(hp=2, sp=1, man=1, features=["Subclass Expert"]),
        8: dict(hp=2, attr=1, skill=1, trade=1, features=["Talent", "2 Ancestry Points", "Path"]),
        9: dict(hp=2, sp=1, man=1, features=["Class Capstone"]),
        10: dict(hp=2, attr=1, skill=2, trade=1, sp=1, man=1, features=["Subclass Capstone"]),
    },
    "Barbarian": {  # tables.md l.7-21
        1: dict(hp=8, sp=2, man=2, features=["Class Features"]),
        2: dict(hp=2, features=["Class Feature", "Talent", "Path"]),
        3: dict(hp=2, attr=1, skill=1, trade=1, sp=1, man=1, features=["Subclass"]),
        4: dict(hp=2, features=["Talent", "2 Ancestry Points", "Path"]),
        5: dict(hp=2, attr=1, skill=2, trade=1, man=1, features=["Class Expert Feature"]),
        6: dict(hp=2, skill=1, features=["Talent", "Path"]),
        7: dict(hp=2, sp=1, man=1, features=["Subclass Expert"]),
        8: dict(hp=2, attr=1, skill=1, trade=1, features=["Talent", "2 Ancestry Points", "Path"]),
        9: dict(hp=2, sp=1, man=1, features=["Class Capstone"]),
        10: dict(hp=2, attr=1, skill=2, trade=1, sp=1, man=1, features=["Subclass Capstone"]),
    },
    "Druid": {  # tables.md l.82-96
        1: dict(hp=7, mp=6, spells=4, features=["Class Features"]),
        2: dict(hp=1, features=["Class Feature", "Talent", "Path"]),
        3: dict(hp=1, attr=1, skill=1, trade=1, mp=3, spells=1, features=["Subclass"]),
        4: dict(hp=1, features=["Talent", "2 Ancestry Points", "Path"]),
        5: dict(hp=1, attr=1, skill=2, trade=1, mp=3, spells=1, features=["Class Feature"]),
        6: dict(hp=1, skill=1, features=["Talent", "Path"]),
        7: dict(hp=1, mp=3, spells=1, features=["Subclass Expert"]),
        8: dict(hp=1, attr=1, skill=1, trade=1, features=["Talent", "2 Ancestry Points", "Path"]),
        9: dict(hp=1, mp=3, spells=1, features=["Class Capstone"]),
        10: dict(hp=1, attr=1, skill=2, trade=1, mp=3, spells=1, features=["Subclass Capstone"]),
    },
}

POINT_BUY_POINTS = 12          # from -2 base in all four attributes
ATTR_BASE_SUM = -8
ANCESTRY_POINTS_L1 = 5         # +2 at L4 and L8 via class tables ("2 Ancestry Points")
BACKGROUND_SKILL = 5           # + Intelligence
BACKGROUND_TRADE = 3
BACKGROUND_LANG = 2            # Common is free
PATH_LEVELS = [2, 4, 6, 8]

MASTERY_STEPS = {None: 0, "Novice": 1, "Adept": 2, "Expert": 3, "Master": 4, "Grandmaster": 5}


def attribute_limit(level: int) -> int:
    return 3 + sum(1 for l in (5, 10, 15, 20) if level >= l)


def mastery_limit(level: int) -> str:
    if level >= 20: return "Grandmaster"
    if level >= 15: return "Master"
    if level >= 10: return "Expert"
    if level >= 5: return "Adept"
    return "Novice"


def cm(level: int) -> int:
    return math.ceil(level / 2)


# ---------------------------------------------------------------- replay
class Report:
    def __init__(self):
        self.lines, self.problems = [], []
        self.derived = {}  # label -> derived value (machine-readable mirror of the check table)

    def add(self, s=""):
        self.lines.append(s)

    def check(self, label, derived, expected=None):
        self.derived[label] = derived
        if expected is None:
            self.add(f"| {label} | {derived} | - | |")
            return
        ok = derived == expected
        mark = "OK" if ok else "MISMATCH"
        self.add(f"| {label} | {derived} | {expected} | {mark} |")
        if not ok:
            self.problems.append(f"{label}: derived {derived} vs sheet {expected}")

    def problem(self, s):
        self.problems.append(s)


def cumulative(table, level, key):
    return sum(table.get(l, {}).get(key, 0) for l in range(1, level + 1))


def entries_for(ledger, level):
    return ledger.get("levels", {}).get(level, []) or []


def all_entries(ledger, level):
    for l in range(2, level + 1):
        for e in entries_for(ledger, l):
            yield l, e


def sum_grants(ledger, level, key):
    total = 0
    cg = ledger.get("chargen", {})
    for c in (cg.get("class_choices") or []):
        total += (c.get("grants") or {}).get(key, 0)
    for t in (cg.get("ancestry_traits") or []):
        total += (t.get("grants") or {}).get(key, 0)
    for _, e in all_entries(ledger, level):
        total += (e.get("grants") or {}).get(key, 0)
    return total


def replay(ledger, level):
    rep = Report()
    cls = ledger["class"]
    table = CLASS_TABLES.get(cls)
    if table is None:
        sys.exit(f"Class '{cls}' not yet encoded in CLASS_TABLES.")
    cg = ledger["chargen"]
    cur = ledger.get("current_level", level)
    plan = level > cur

    rep.add(f"# Build replay: {ledger['character']} at Level {level}"
            + (" (PLAN)" if plan else ""))
    rep.add(f"Class {cls} ({ledger.get('subclass', '?')}) | {ledger.get('ancestry', '')} | "
            f"ruleset {ledger.get('ruleset', '?')}")
    rep.add()

    # --- attributes -------------------------------------------------------
    attrs = dict(cg["attributes"])
    buy_cost = sum(v + 2 for v in attrs.values())
    if cg.get("attribute_method") == "point_buy" and buy_cost != POINT_BUY_POINTS:
        rep.problem(f"Point buy spends {buy_cost}, not {POINT_BUY_POINTS}")
    for t in cg.get("ancestry_traits", []):
        name = t["name"]
        if name.startswith("Attribute Increase"):
            target = name.split("(")[1].rstrip(")").strip().lower()
            attrs[target] = attrs.get(target, 0) + 1
    attr_picks = [(l, e) for l, e in all_entries(ledger, level) if e.get("slot") == "attribute"]
    for l, e in attr_picks:
        pick = str(e.get("pick", "")).lower()
        if pick in attrs:
            attrs[pick] += 1
            if attrs[pick] > attribute_limit(l):
                rep.problem(f"L{l}: {pick} raised to {attrs[pick]} above limit {attribute_limit(l)}")
    attr_budget = cumulative(table, level, "attr")
    if len(attr_picks) != attr_budget:
        rep.problem(f"Attribute points: {len(attr_picks)} spent vs {attr_budget} granted by class table")
    for a, v in attrs.items():
        if v > attribute_limit(level):
            rep.problem(f"Attribute {a} = {v} exceeds limit {attribute_limit(level)}")

    prime = max(attrs.values())
    might, agi, cha = attrs.get("might", 0), attrs.get("agility", 0), attrs.get("charisma", 0)

    # --- ancestry points --------------------------------------------------
    anc_spent = sum(t.get("cost", 0) for t in cg.get("ancestry_traits", []))
    anc_spent += sum(e.get("cost", 0) for _, e in all_entries(ledger, level)
                     if e.get("slot") == "ancestry_trait")
    anc_budget = ANCESTRY_POINTS_L1 + 2 * sum(
        1 for l in range(2, level + 1) if "2 Ancestry Points" in table.get(l, {}).get("features", []))
    if anc_spent != anc_budget:
        rep.problem(f"Ancestry points: {anc_spent} spent vs {anc_budget} budget")

    # --- paths / talents / subclass ---------------------------------------
    paths = [e.get("pick") for _, e in all_entries(ledger, level) if e.get("slot") == "path"]
    path_slots = sum(1 for l in PATH_LEVELS if l <= level)
    if len(paths) != path_slots:
        rep.problem(f"Paths chosen {len(paths)} vs {path_slots} slots (L2/4/6/8)")
    martial = sum(1 for p in paths if str(p).startswith("Martial"))
    caster = sum(1 for p in paths if str(p).startswith("Spellcaster"))
    talents = sum(1 for _, e in all_entries(ledger, level) if e.get("slot") == "talent")
    talent_slots = sum(1 for l in range(2, level + 1)
                       if "Talent" in table.get(l, {}).get("features", []))
    if talents != talent_slots:
        rep.problem(f"Talents chosen {talents} vs {talent_slots} slots")
    if level >= 3 and not any(e.get("slot") == "subclass" for _, e in all_entries(ledger, level)):
        rep.problem("No subclass entry at L3+")

    # --- resources ---------------------------------------------------------
    hp = cumulative(table, level, "hp") + might + sum_grants(ledger, level, "hp")
    sp = cumulative(table, level, "sp") + martial + sum_grants(ledger, level, "sp")
    mp = cumulative(table, level, "mp") + 3 * caster + sum_grants(ledger, level, "mp")
    spells = (cumulative(table, level, "spells") + caster
              + sum_grants(ledger, level, "spells"))
    maneuvers = (cumulative(table, level, "man") + martial
                 + sum_grants(ledger, level, "maneuvers"))
    pd_items = sum(e.get("pd", 0) for e in (ledger.get("equipment") or []))
    ad_items = sum(e.get("ad", 0) for e in (ledger.get("equipment") or []))
    pd = (8 + cm(level) + agi + attrs.get("intelligence", 0)
          + pd_items + sum_grants(ledger, level, "pd"))
    ad = 8 + cm(level) + might + cha + ad_items + sum_grants(ledger, level, "ad")

    # --- skills / trades / languages (validated at current_level only) -----
    if not plan:
        sk = ledger.get("skills", {})
        earned_sp = (BACKGROUND_SKILL + attrs.get("intelligence", 0)
                     + cumulative(table, level, "skill")
                     + sum_grants(ledger, level, "skill_points"))
        spent_sp = 0
        for name, m in (sk.get("masteries") or {}).items():
            steps = MASTERY_STEPS[m.get("mastery")]
            spent_sp += steps
            if m.get("limit_raise") == "skill_point_purchase":
                spent_sp += 1
            elif MASTERY_STEPS[m.get("mastery")] > MASTERY_STEPS[mastery_limit(level)] \
                    and not m.get("limit_raise"):
                rep.problem(f"Skill {name} at {m.get('mastery')} above L{level} limit with no limit_raise")
        tr = ledger.get("trades", {})
        earned_tp = (BACKGROUND_TRADE + cumulative(table, level, "trade")
                     + sum_grants(ledger, level, "trade_points"))
        spent_tp = 0
        for name, m in (tr.get("masteries") or {}).items():
            steps = MASTERY_STEPS[m.get("mastery")]
            if m.get("limit_raise") == "trade_point_purchase":
                steps += 1  # 1 TP spent to raise the Mastery Limit itself
            elif m.get("limit_raise") and "Expertise" in str(m.get("limit_raise")):
                steps -= 1  # Trade/Skill Expertise: Cap AND Level +1 = one free step
            spent_tp += steps
        langs = ledger.get("languages", []) or []
        spent_lp = sum(l.get("cost", 0) for l in langs)
        # conversions: TP deficit funded by SP (1->2), LP deficit funded by TP (1->2)
        tp_deficit = max(0, spent_tp - earned_tp)
        conv_sp = math.ceil(tp_deficit / 2)
        lp_deficit = max(0, spent_lp - BACKGROUND_LANG)
        conv_tp = math.ceil(lp_deficit / 2)
        total_sp = spent_sp + conv_sp
        total_tp_ok = spent_tp + conv_tp <= earned_tp + conv_sp * 2
        rep.add("## Point budgets")
        rep.add()
        rep.add(f"- Skill points: earned {earned_sp}, spent {spent_sp}"
                + (f" + {conv_sp} converted to {conv_sp*2} TP" if conv_sp else "")
                + f" = {total_sp} -> " + ("balanced" if total_sp == earned_sp else
                  ("UNDER-SPENT" if total_sp < earned_sp else "OVER-SPENT")))
        if total_sp > earned_sp:
            rep.problem(f"Skill points over-spent: {total_sp} vs {earned_sp}")
        tp_total, tp_avail = spent_tp + conv_tp, earned_tp + conv_sp * 2
        rep.add(f"- Trade points: earned {earned_tp} (+{conv_sp*2} via conversion), spent {spent_tp}"
                + (f" + {conv_tp} converted to LP" if conv_tp else "")
                + f" -> " + ("balanced" if tp_total == tp_avail else
                  ("UNDER-SPENT" if tp_total < tp_avail else "OVER-SPENT")))
        if not total_tp_ok:
            rep.problem("Trade points over-spent")
        lp_avail = BACKGROUND_LANG + conv_tp * 2
        rep.add(f"- Language points: {BACKGROUND_LANG} free, spent {spent_lp}"
                + (f" ({conv_tp} TP converted)" if conv_tp else "")
                + (" -> UNDER-SPENT" if spent_lp < lp_avail else ""))
        rep.add()

    # --- derived table ------------------------------------------------------
    exp = (ledger.get("expected") or {}) if not plan else {}
    rep.add("## Derived vs sheet" if not plan else "## Derived (projection)")
    rep.add()
    rep.add("| Stat | Derived | Sheet | Check |")
    rep.add("|---|---|---|---|")
    rep.check("Level", level)
    rep.check("Combat Mastery", cm(level))
    rep.check("Prime", prime)
    rep.check("Attributes", " / ".join(f"{k[:3].title()} {v}" for k, v in attrs.items()))
    rep.check("Attack/Spell Check", cm(level) + prime, exp.get("attack"))
    rep.check("Save DC", 10 + cm(level) + prime, exp.get("save_dc"))
    rep.check("Initiative", cm(level) + agi, exp.get("initiative"))
    rep.check("Grit", cha + 2, exp.get("grit"))
    rep.check("HP", hp, exp.get("hp"))
    rep.check("SP", sp, exp.get("sp"))
    rep.check("MP", mp, exp.get("mp"))
    rep.check("Spells known", spells, exp.get("spells"))
    rep.check("Maneuvers known", maneuvers, exp.get("maneuvers"))
    rep.check("PD", pd, exp.get("pd"))
    rep.check("AD", ad, exp.get("ad"))
    rep.add()

    # --- choices timeline ----------------------------------------------------
    rep.add("## Choice timeline")
    rep.add()
    rep.add(f"- L1: attributes {cg['attributes']} (+ancestry), schools "
            f"{cg.get('spell_schools')}, disciplines "
            f"{next((c['picks'] for c in cg.get('class_choices', []) if 'disciplin' in c['slot']), '?')}, "
            f"spells {cg.get('spells')}, maneuvers {cg.get('maneuvers')}")
    for l in range(2, level + 1):
        for e in entries_for(ledger, l):
            tag = " [inferred]" if e.get("inferred") else ""
            rep.add(f"- L{l} {e.get('slot')}: {e.get('pick')}{tag}")
    rep.add()

    if rep.problems:
        rep.add("## PROBLEMS / OPEN ITEMS")
        rep.add()
        for p in rep.problems:
            rep.add(f"- {p}")
    else:
        rep.add("## All checks passed")
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ledger")
    ap.add_argument("--level", type=int, default=None)
    ap.add_argument("--report", action="store_true", help="write builds/reports/<name>_L<n>.md")
    args = ap.parse_args()
    with open(args.ledger, encoding="utf-8") as f:
        ledger = yaml.safe_load(f)
    level = args.level or ledger["current_level"]
    rep = replay(ledger, level)
    text = "\n".join(rep.lines) + "\n"
    print(text)
    if args.report:
        base = os.path.splitext(os.path.basename(args.ledger))[0]
        outdir = os.path.join(os.path.dirname(args.ledger), "reports")
        os.makedirs(outdir, exist_ok=True)
        path = os.path.join(outdir, f"{base}_L{level}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"[report written: {path}]")
    sys.exit(1 if rep.problems else 0)


if __name__ == "__main__":
    main()
