# Build Ledger Schema (v1)

**Audience: table-facing** (build data is player-visible; no GM secrets in here).
**Purpose:** a structured, machine-usable record of every character-build decision from chargen through each level-up, per PC. One YAML ledger per character in `builds/`. The replay engine (`tools/build_engine.py`) consumes a ledger, derives the character's numbers at any level, checks legality against the DC20 0.10.5 rules, and reports discrepancies vs the actual sheet.

This is "rung 1" of the build-tooling ladder (see `_SESSION_LOG` 2026-07-10). Rung 2 is the engine.

## Design principles

1. **Log decisions, not derived values.** HP, CM, Save DC, Initiative, budgets and the like are computed by the engine from the class tables and formulas. Only choices go in the ledger. (Principle independently arrived at in Phil's level-up summaries, `builds/sources/`.)
2. **Structure, not effects.** A pick records its name, its slot, and (where needed) its mechanical *resource deltas* (`grants:`). The ledger never encodes what an ability does in play; that stays in `rules/`.
3. **Provenance is explicit.** Every choice is either `known` (recorded/confirmed) or `inferred` (reconstructed from the end-state sheet). Default is `known`; mark `inferred: true` otherwise.
4. **Plans are levels too.** Levels beyond `current_level` are the locked/working plan (e.g. Tan's L5-L6). Same format; the engine treats them as projections.
5. **Homebrew and equipment are overlays.** Magic items and homebrew live in an `equipment:` section with their sheet-visible modifiers, kept out of the progression proper (acquisition timing is loot, not level-up).

## Top-level fields

```yaml
schema: 1
ruleset: "DC20 0.10.5"
character: Full name
player: Name
class: Spellblade            # engine must have this class's table encoded
subclass: Paladin            # also appears as the L3 choice; here for convenience
ancestry: "Half-elf (Human + Elf trait lists)"
background: Herbalist
current_level: 4             # levels above this are plan
chargen: {...}               # Level 1 decisions (see below)
levels: {2: [...], 3: [...]} # level-up decisions (see below)
skills: {...}                # allocation state (see below)
trades: {...}
languages: {...}
equipment: [...]
expected: {...}              # sheet totals for engine validation
notes: [...]                 # free-text caveats
```

## `chargen:` (Level 1)

```yaml
chargen:
  attribute_method: point_buy          # point_buy | standard_array | roll
  attributes: {might: 2, agility: 3, charisma: -2, intelligence: 3}
  ancestry_traits:
    - {name: Attribute Increase (Might), source: Human, cost: 2}
    - {name: Nimble, source: Elf, cost: 2}
    # cost may be negative (drawback traits refund points); 0-cost minor traits allowed
  spell_schools: [Invocation, Divination]   # if the class picks schools at L1
  class_choices:                            # named choice slots the class grants at L1
    - {slot: bound_weapon_options, picks: [Illuminate, Smite, Recall]}
    - {slot: spellblade_disciplines, picks: [Acolyte, Blink Blade]}
  spells: [Close Wounds, Radiant Bolt]      # L1 spells known (count validated vs class table)
  maneuvers: [Parry]                        # L1 maneuvers known
  combat_training: [Weapons, Spell Focuses, Light Armor]
```

Budgets the engine enforces at L1: point buy = 12 points from a base of -2 in all four attributes, attribute limit 3; ancestry points = 5; background = 5 Skill Points + Intelligence, 3 Trade Points, 2 Language Points (Common is free); conversions 1 SP -> 2 TP, 1 TP -> 2 LP (one-way).

## `levels:` (2 and up)

Each level is a list of decision entries. An entry:

```yaml
- slot: talent | path | subclass | ancestry_trait | class_feature | discipline |
        spell | maneuver | attribute | skill | trade | language | other
  pick: "Name of the thing chosen"
  source: "where the slot came from, if not the class table"   # optional
  cost: 2                     # ancestry_trait entries only
  grants: {mp: 1, spells: 1}  # optional resource deltas this pick confers
  inferred: true              # optional, default false
  note: "free text"           # optional
```

Conventions:

- **Class-table grants are implicit.** The engine already knows Spellblade L3 gives +2 HP, +1 attribute point, +1 skill point, +1 trade point, +1 maneuver, +2 MP, Subclass. The ledger only records what was *chosen* with those grants (e.g. `slot: attribute, pick: might`).
- **`path` picks** are just `pick: Martial` or `pick: Spellcaster`; the engine applies the rank benefits (Martial: +1 SP, +1 maneuver, Weapons training; Spellcaster: +3 MP, +1 spell, Spell Focus training) and first-time riders.
- **`grants:`** is for picks whose deltas the engine cannot know generically (talents, disciplines, subclass features). Recognised keys: `hp, sp, mp, spells, maneuvers, skill_points, trade_points, ancestry_points, disciplines`. Source the numbers from `rules/`; cite in `note` if non-obvious.
- **Multi-part talents** (e.g. MC Warlock granting several features) are one entry with the parts in `note`, unless a part has resource deltas of its own.

## `skills:` / `trades:` / `languages:`

Point-spend history is usually not level-tagged in our sources (the known gap in Phil's summaries), so the allocation block records the *current* state plus any level-tagged spends we do know:

```yaml
skills:
  allocation_confidence: inferred      # known | inferred | mixed
  masteries:                           # current mastery LEVEL per skill (not the die bonus)
    Awareness: {mastery: Adept, limit_raise: skill_point_purchase}  # core-rules.md l.993+
    Athletics: {mastery: Novice}
  level_tagged:                        # optional; fills in as we log go-forward
    5: [{skill: Awareness, to: Expert}]
trades:
  masteries:
    Herbalism: {mastery: Adept, limit_raise: "Trade Expertise (ancestry)"}
  knowledge_trades: [Arcana, Nature]   # Arcana/Nature are Knowledge TRADES, not skills
languages:
  - {name: Common, fluency: Fluent, cost: 0}
  - {name: Elvish, fluency: Fluent, cost: 2}
```

The engine validates total points spent vs earned (background + Int + class table + talents + conversions) and mastery limits by level (Novice to L4, Adept from L5, Expert from L10; individual limit raises via traits/features/1-SP purchases per `core-rules.md`).

## `equipment:` (overlay)

```yaml
equipment:
  - {name: Greatsword of the Keepers, mods: "Spell Focus; Guardians' Regalia set"}
  - {name: Fortified Light Armour, mods: "+2 AD"}
```

Not validated against progression; listed so the engine can explain sheet-vs-derived deltas (e.g. Xanwyn's +2 HP amulet).

## `expected:` (validation targets)

Sheet totals at `current_level`, for the discrepancy report:

```yaml
expected: {hp: 14, sp: 3, mp: 6, spells: 3, maneuvers: 4, grit: 0,
           attack: 5, save_dc: 15, initiative: 5, pd: 19, ad: 12}
```

## Formulas the engine owns (0.10.5)

- CM = ceil(level / 2). Prime = highest attribute.
- Attack/Spell Check = CM + Prime. Save DC = 10 + CM + Prime.
- Initiative = CM + Agility. Grit = Charisma + 2.
- HP = class-table cumulative + Might (+ explicit `grants:`/equipment).
- SP/MP/spells/maneuvers = class-table cumulative + path ranks + `grants:`.
- Attribute limit: 3 at L1, +1 at L5, L10, L15, L20 (limit 4 from L5).
- Ancestry points: 5 at L1, +2 at L4 and L8 (class tables).
- Skill points: 5 + Int at L1, then class table; mastery bonus = 2 x mastery rank (Novice +2, Adept +4, Expert +6, Master +8, Grandmaster +10).

## File map

- `builds/SCHEMA.md` (this file)
- `builds/<name>.yaml` (one per PC: tanrielle, runt, minimus, bonan, scaletrix, xanwyn)
- `builds/sources/` (Phil's level-up summaries, 2026-07-10, provenance notes in its README)
- `tools/build_engine.py` (replay/validate; run `python3 tools/build_engine.py builds/tanrielle.yaml`)
