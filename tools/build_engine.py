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
# Class progression spines now live in DATA, not a hardcoded dict (FR-12.0, Phase 0):
# builds/catalog/class_spines.yaml is the single source of truth for per-level deltas.
# load_class_tables() reads it (cached); replay() takes an optional class_tables= so a
# caller can pass the data in, mirroring stamina_regen(ledger, cat) / damage_addons(handle, cat).
# Per-level keys: hp, attr, skill, trade, sp, man (maneuvers), mp, spells, features.

def _spine_candidates():
    here = os.path.dirname(os.path.abspath(__file__))
    return [
        "class_spines.yaml",  # Pyodide FS (baked bare name) or cwd
        os.path.join(here, "..", "builds", "catalog", "class_spines.yaml"),  # repo layout (CLI, Companion)
    ]


_CLASS_TABLES_CACHE = None


def load_class_tables(path=None):
    """Return {class_name: {level:int -> delta dict}} from class_spines.yaml.

    Replaces the old hardcoded CLASS_TABLES dict. Cached when loaded from the default
    location; pass path= (or class_tables= into replay) to override, e.g. for tests.
    """
    global _CLASS_TABLES_CACHE
    if path is None and _CLASS_TABLES_CACHE is not None:
        return _CLASS_TABLES_CACHE
    candidates = [path] if path else _spine_candidates()
    for p in candidates:
        if p and os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                tables = yaml.safe_load(f)["classes"]
            if path is None:
                _CLASS_TABLES_CACHE = tables
            return tables
    sys.exit("class_spines.yaml not found (looked in: %s)"
             % ", ".join(c for c in candidates if c))

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


def grant_flag(ledger, level, key, default=None):
    """Last non-None value of a NON-numeric grant flag (e.g. jump_from: might)."""
    val = default
    cg = ledger.get("chargen", {})
    for c in (cg.get("class_choices") or []):
        val = (c.get("grants") or {}).get(key, val)
    for t in (cg.get("ancestry_traits") or []):
        val = (t.get("grants") or {}).get(key, val)
    for _, e in all_entries(ledger, level):
        val = (e.get("grants") or {}).get(key, val)
    return val


def replay(ledger, level, class_tables=None):
    rep = Report()
    cls = ledger["class"]
    tables = class_tables if class_tables is not None else load_class_tables()
    table = tables.get(cls)
    if table is None:
        sys.exit(f"Class '{cls}' not encoded in class_spines.yaml.")
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
    # class-table attribute points, plus any granted by talents/features
    # (e.g. the Attribute Increase General Talent grants 2 Attribute Points)
    attr_budget = cumulative(table, level, "attr") + sum_grants(ledger, level, "attribute_points")
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

    # --- per-attribute saves / move / jump / spend limit / DR ---------------
    # Attribute Save bonus = Attribute + Combat Mastery (core-rules.md l.1553),
    # plus flat all-Save bonuses from equipment (an item's `saves:` field, e.g. an
    # Amulet of General Resilience +1) and any numeric `saves` grant - modelled the
    # same way as the PD/AD item bonuses. Per-attribute item bonuses aren't modelled
    # yet (no ledger needs them).
    save_bonus = (sum(it.get("saves", 0) for it in (ledger.get("equipment") or [])
                      if isinstance(it.get("saves"), (int, float)))
                  + sum_grants(ledger, level, "saves"))
    saves = {a.title(): attrs.get(a, 0) + cm(level) + save_bonus
             for a in ("might", "agility", "charisma", "intelligence")}
    # Move Speed: base 5 Spaces (ancestries.md l.154), +1 per Speed Increase
    # trait, -1 per Short-Legged, plus any numeric `speed` grant.
    speed = 5 + sum_grants(ledger, level, "speed")
    trait_names = [t.get("name", "") for t in cg.get("ancestry_traits", [])]
    trait_names += [e.get("pick", "") for _, e in all_entries(ledger, level)
                    if e.get("slot") == "ancestry_trait"]
    for nm in trait_names:
        n = str(nm)
        if n.startswith("Speed Increase"):
            speed += 1
        elif n.startswith("Short-Legged"):
            speed -= 1
    # Jump Distance = Agility (minimum 1) (character-creation.md l.159), plus any
    # numeric `jump` grant. A feature may re-key the base attribute via a
    # `jump_from: <attr>` grant (e.g. Barbarian Mighty Leap uses Might).
    jump_from = grant_flag(ledger, level, "jump_from", "agility")
    jump = max(1, attrs.get(str(jump_from).lower(), 0)) + sum_grants(ledger, level, "jump")
    # Mana / Stamina Spend Limit = half level, rounded up = Combat Mastery
    # (spells.md l.5907-5920: "spending MP up to half their level, rounded up").
    spend_limit = cm(level)
    # Damage Reduction plumbing: collect structured PDR/EDR/MDR declared on
    # equipment items (value may be an int or "half"). The current ledgers
    # don't declare these yet, so this is empty for the party - populate later.
    dr = {}
    for it in (ledger.get("equipment") or []):
        for k in ("pdr", "edr", "mdr"):
            v = it.get(k)
            if v not in (None, 0, "", False):
                dr.setdefault(k.upper(), []).append(v)

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
        # Subclass/feature-granted languages are free regardless of fluency (e.g. Eldritch
        # grants Fluent Deep Speech, classes.md l.3432): a `granted: true` language costs 0 LP.
        spent_lp = sum(l.get("cost", 0) for l in langs if not l.get("granted"))
        # conversions: TP deficit funded by SP (1->2), LP deficit funded by TP (1->2).
        # BUG-11 (CH-1 2026-07-18): compute the LP-funding conversion FIRST and include it
        # in the TP deficit, so a CHAINED conversion (SP->TP->LP) is funded too. Previously
        # conv_sp only saw the trade-mastery deficit, so a build whose TP deficit came from
        # funding languages (minimus at L5+) wrongly read OVER-SPENT despite spare SP.
        lp_deficit = max(0, spent_lp - BACKGROUND_LANG)
        conv_tp = math.ceil(lp_deficit / 2)
        tp_deficit = max(0, spent_tp + conv_tp - earned_tp)
        conv_sp = math.ceil(tp_deficit / 2)
        total_sp = spent_sp + conv_sp
        total_tp_ok = spent_tp + conv_tp <= earned_tp + conv_sp * 2
        # BUG-3: symmetric, clear verdicts. Under-spend after whole 2-for-1 conversions
        # (or before level-up night) is LEGAL and must not read as a fault; only an
        # over-spend is illegal. All three lines (skills/trades/languages) use one verdict.
        def verdict(total, avail):
            if total == avail:
                return "balanced"
            if total < avail:
                n = avail - total
                return (f"{n} SPARE (legal - a lumpy 2-for-1 conversion leftover or an "
                        f"unspent point; spend at level-up)")
            return f"OVER-SPENT by {total - avail} (illegal)"
        rep.add("## Point budgets")
        rep.add()
        rep.add(f"- Skill points: earned {earned_sp}, spent {spent_sp}"
                + (f" + {conv_sp} converted to {conv_sp*2} TP" if conv_sp else "")
                + f" = {total_sp} -> " + verdict(total_sp, earned_sp))
        if total_sp > earned_sp:
            rep.problem(f"Skill points over-spent: {total_sp} vs {earned_sp}")
        tp_total, tp_avail = spent_tp + conv_tp, earned_tp + conv_sp * 2
        rep.add(f"- Trade points: earned {earned_tp} (+{conv_sp*2} via conversion), spent {spent_tp}"
                + (f" + {conv_tp} converted to LP" if conv_tp else "")
                + f" -> " + verdict(tp_total, tp_avail))
        if not total_tp_ok:
            rep.problem("Trade points over-spent")
        lp_avail = BACKGROUND_LANG + conv_tp * 2
        rep.add(f"- Language points: {BACKGROUND_LANG} free, spent {spent_lp}"
                + (f" ({conv_tp} TP converted -> +{conv_tp*2} LP)" if conv_tp else "")
                + f" -> " + verdict(spent_lp, lp_avail))
        if spent_lp > lp_avail:
            rep.problem(f"Language points over-spent: {spent_lp} vs {lp_avail}")
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
    sgn = lambda v: ("+" if v >= 0 else "") + str(v)
    fmt_saves = lambda m: " / ".join(f"{k[:3]} {sgn(m[k.lower()] if k.lower() in m else m.get(k))}"
                                     for k in saves)
    exp_saves = exp.get("saves")
    rep.check("Saves", " / ".join(f"{k[:3]} {sgn(v)}" for k, v in saves.items()),
              fmt_saves(exp_saves) if exp_saves else None)
    rep.check("Move Speed", speed, exp.get("move"))
    rep.check("Jump Distance", jump, exp.get("jump"))
    rep.check("Spend Limit (MSL/SSL)", spend_limit, exp.get("spend_limit"))
    rep.check("Damage Reduction",
              "; ".join(f"{k} {', '.join(str(x) for x in v)}" for k, v in dr.items())
              or "none")
    # structured mirrors for consumers (the character sheet reads these)
    rep.derived["saves"] = saves
    rep.derived["move"] = speed
    rep.derived["jump"] = jump
    rep.derived["spend_limit"] = spend_limit
    rep.derived["dr"] = dr
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


def stamina_regen(ledger, regen_cat):
    """Return a character's Stamina Regen trigger(s) as [{'label','text'}] (FR-23).

    Data-driven from regen_cat (builds/catalog/stamina_regen.yaml):
      - a class with a NATIVE trigger (regen_cat['classes']) gets it from level 1;
      - a class WITHOUT one gets the Spellcaster trigger only once it has taken a
        Martial Path (character-creation.md l.741-744); until then: no regen;
      - a Martial Expansion talent adds the chosen source's trigger (its `regen_source`
        slot field: a class name or 'Spellcaster'), capped at 1 benefit/Round.
    An empty list means the character has no Stamina Regen (e.g. a spellcaster who
    never took a Martial Path). The engine is catalog-agnostic: the data is passed in.
    """
    classes = (regen_cat or {}).get("classes", {}) or {}
    spellcaster_txt = (regen_cat or {}).get("spellcaster")
    cls = ledger.get("class")
    out, seen = [], set()

    def add(label, text):
        if label and text and label not in seen:
            seen.add(label)
            out.append({"label": label, "text": text})

    decisions = []
    for _lvl, lst in (ledger.get("levels") or {}).items():
        decisions.extend(lst or [])
    took_martial_path = any(d.get("slot") == "path" and d.get("pick") == "Martial"
                            for d in decisions)

    if cls in classes:
        add(cls, classes[cls])
    elif took_martial_path:
        add("Spellcaster", spellcaster_txt)

    for d in decisions:
        if d.get("slot") == "talent" and "Martial Expansion" in str(d.get("pick", "")):
            src = d.get("regen_source")
            if not src:
                continue
            if src in classes:
                add(src, classes[src])
            elif str(src).lower() == "spellcaster":
                add("Spellcaster", spellcaster_txt)
    return out


def damage_addons(handle, dmg_cat):
    """Resolve a character's Damage Calculator config (FR-25 v1).

    Data-driven from dmg_cat (builds/catalog/damage_addons.yaml). Given the character
    handle (e.g. 'tan'), returns:
        {"base": <int>, "base_note": <str>, "addons": [<resolved def dict>, ...]}
    Each resolved add-on is the shared def (defs[<id>]) with the character's per-use
    overrides merged on top, plus its "id". An unknown handle yields base 1 / no add-ons.
    The engine is catalog-agnostic: the data is passed in.
    """
    defs = (dmg_cat or {}).get("defs", {}) or {}
    chars = (dmg_cat or {}).get("characters", {}) or {}
    entry = chars.get(handle) or {}
    out = []
    for ref in entry.get("addons", []) or []:
        if isinstance(ref, str):
            rid, over = ref, {}
        else:
            rid = ref.get("id")
            over = {k: v for k, v in ref.items() if k != "id"}
        merged = dict(defs.get(rid, {}))
        merged.update(over)
        merged["id"] = rid
        out.append(merged)
    return {
        "base": entry.get("base", 1),
        "base_note": entry.get("base_note", ""),
        "addons": out,
    }


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
