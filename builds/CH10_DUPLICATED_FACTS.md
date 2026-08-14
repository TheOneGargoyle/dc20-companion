# CH-10: the duplicated-fact audit

**Done 2026-08-14 against origin `2e4019c`.** Filed as a separate file rather than a table inside
`builds/BACKLOG.md` because it runs to 97 rows; the backlog carries the summary and the new item IDs.
Same reason `BACKLOG_DONE.md` and `FR12_PLAN.md` were split out.

## Why this exists, and what it answers

Every systemic root cause this project has found is one meta-pattern: **a fact that must agree in two
places, with nothing asserting that it does.** The question CH-10 was filed to answer is "how many
more of these are there", on the theory that the discovery rate is not random and not infinite, it is
bounded by the length of this list.

**The list is 97 rows.** That is the bound. It was produced by five independent sweeps, one per
region, each asked to check the guard claim rather than assume it.

| Region | Rows | Derived | Asserted | UNGUARDED |
|---|---|---|---|---|
| A. `tools/` internals | 26 | 1 | 4 | 21 |
| B. `builds/catalog/` vs `rules/` | 22 | 2 | 6 | 14 |
| C. `builds/*.yaml` ledgers | 16 | 0 | 6 | 10 |
| D. `companion-src/` | 20 | 1 | 1 | 18 |
| E. docs + CI | 13 | 2 | 1 | 10 |
| **Total** | **97** | **6** | **18** | **73** |

**Read the 73 carefully: they are not 73 bugs.** 14 of them are already wrong today (see "Live
defects" below). The rest are correct right now and unprotected, which is the state every closed bug
in this project was in the day before it broke.

**The one genuinely reassuring finding:** the citation discipline is holding. 27 of 28 documentation
line-references still resolve to the text they claim, and `tools/MAP.md` regenerates **byte-identical**,
so all ~390 of its line ranges are accurate. The rot is concentrated exactly where nothing asserts.

## The four costumes, re-derived from the data

The backlog listed four costumes. The audit says they collapse into **three mechanisms**, and adds a
fourth that was not previously named:

1. **A hand-written list that new data does not join.** The single most common shape, 19 rows.
   The six-character key set exists in five independent literals; `rules/`'s file list in three;
   the GM filename set in four; the class roster in four. Each fails by *omission*, which is the
   mode no test can see, because the missing thing generates no output. Every one is BUG-31 (CATPATHS)
   in a new costume.
2. **A formula or vocabulary implemented twice.** 22 rows. The engine and the client API each
   compute things the other computes; `catalog_verify` re-types parsers that already exist in
   `builder_build`.
3. **An assertion written against a copy rather than against the artifact.** 11 rows, and the most
   corrosive, because each one *looks* like a guard. `builder_verify.ORACLE` is a hand-transcription
   of `template.html` labelled as its oracle. `catalog_verify._EXPECT_DMG` is a hand-transcription of
   `damage_addons.yaml`. `deploy.yml`'s GM canary words are a hand-transcription of files the repo
   deliberately excludes, so nobody can ever confirm the canaries still appear in the GM prose.
4. **NEW, not previously named: an assertion that shares the implementation's silent default.**
   `check_sheet` recomputes a skill bonus with the same `attrs.get(gov, 0)` fallback the sheet uses.
   `check_fr36` compares `FR20_CAT.get(slot, 3)` against `FR20_RANK.get(slot, 3)`, and both default
   to 3. **A check that shares the subject's escape hatch cannot see the subject fall through it.**
   This is why two of the live defects below are green right now. It is the reason the "declare an
   effect" gate can be satisfied by a *wrong* declaration: `no_effect: situational` is accepted as
   readily on Lightning Rune (which grants +1 Speed) as on a genuinely inert option.

## Live defects found while auditing

These are wrong **now**, not hypothetically. Each needs an ID; proposed IDs in brackets. Ordered by
what it costs at the table.

1. **[BUG-37] `damage_addons.yaml` freezes the Mana/Stamina Spend Limit at `cap: 2` for L4.** The
   party is L4 and Arc 4's band is L4 to 6. On the level-up, both Damage Calculators silently
   under-report maximum damage by 1 per resource, and every check still passes, because
   `catalog_verify` asserts `cap == 2` against the same literal the catalog holds. The engine already
   derives `spend_limit`. The file's own comment predicts the breakage ("rises to 3 at L5") and does
   nothing about it. **Fix before the party levels.**
2. **[BUG-38] `deploy.yml`'s `paths:` filter omits `tools/**`.** Both deployed artifacts are built by
   code that now lives there. This gap widened enormously on 2026-07-30 when CH-9 moved 2,788 lines
   of the builder's Python into `tools/builder_api.py`. Today a fix to the engine or the API passes
   Verify green and **never reaches the live page**, silently and indefinitely. One line to fix.
3. **[BUG-39] Bonan's ledger flattens an armour-conditional grant into an unconditional one.**
   `bonan.yaml:27` hand-copies Barbarian L1 as `grants: {ad: 2, speed: 1, jump_from: might}`, but
   `class_features.yaml:42-47` declares the `+2 AD` as `grants_unarmored`. Put Bonan in armour and
   the engine keeps the +2 *and* adds the armour's AD. His entry also names `Battlecry` (an L2
   feature), names `Shouts` (which occurs zero times in `rules/classes.md`), and omits
   `Shattering Force`. Nothing reconciles `class_features` on a ledger at all.
4. **[BUG-40] The Companion's condition pills cover 12 of the ruleset's ~30 conditions, and two of
   the twelve do not exist.** Blinded, Restrained, Burning, Paralyzed, Slowed, Weakened, Doomed,
   Exhaustion, Incapacitated and eleven more cannot be tracked. `Poisoned` appears zero times in
   `general-rules.md`/`combat.md`, and `Grappled` is not a Conditions-List entry, so tapping either
   falls through to the generic home link. Players hit this every session.
5. **[BUG-41] The Companion names a spell and a maneuver that do not exist in the ruleset it ships.**
   `template.html:975` says **Grease**, which the ledger and `rules/spells.md` call **Oil Slick**;
   `:1014` says **Recovery**, which `maneuvers.yaml:9` records as "not a 0.10.5 maneuver and
   deliberately absent" and which the ledger corrected to **Recover** on 2026-07-12. Both are
   unresolvable in the app's own rules search. Runt's listed spell set is also wrong (names
   `Psychic Imbued`, which he does not have; omits `Lightning Bolt`), and a resolved question about
   his Staff of Lightning is still printed as open. This overlaps FR-40, which should absorb it.
6. **[BUG-42] `FR20_CAT` and `FR20_RANK` have already drifted, and the check cannot see it.**
   `ancestry_origin` and `source_choice` are in `SHEET_GROUPS` but absent from `FR20_CAT`, so they
   silently take rank 3. Verified live on Scaletrix: the Dragonborn/Fiendborn Origin pickers render
   under the amber "Resources" sub-header, detached from the ancestry block they belong to.
   `check_fr36` passes because both dicts default to 3. Costume 4.
7. **[BUG-43] Two Spellblade Runes are priced and inert.** `rules/classes.md:3103` gives the
   Lightning Rune *"Your Speed increases by 1"* and `:3114-3116` gives the Wind Rune *"+3 Jump
   Distance"*. Both are declared `no_effect: situational` in `spellblade.yaml`. `speed` and `jump`
   are first-class engine grant keys, so a scratch Rune Knight who picks either is permanently short.
   Xanwyn picked Flame and Water, which is the only reason the oracle is clean.
8. **[BUG-44] Six Beastborn traits are missing their prerequisite.** `rules/ancestries.md:927` says
   *"The following Traits require the Natural Weapon Trait:"* and lists six. None carries `requires:`.
   `requires` IS enforced by the builder, so a scratch Beastborn can buy Rend or Venomous Natural
   Weapon with no Natural Weapon and the build reports clean. The existing parser only reads an
   inline `(requires X)`, so a prerequisite stated as a preceding sentence is structurally invisible.
9. **[BUG-45] Three of the eight Spell Schools are unpickable.** `spell_schools.yaml` curates five;
   `rules/spells.md` enumerates eight. The picker is built directly from the curated list, so a
   scratch Spellblade or Warlock physically cannot choose Astromancy, Conjuration or Enchantment, and
   gets no message saying why. `spell_sources.yaml` already lists spells under all eight names.
10. **[BUG-46] Two talents declare half their rule.** `Expanded Meta Magic` declares `{mp: 2}` and
    drops *"You gain 2 additional Meta Magic Spell Enhancement"*, though the `metamagic` grant key
    and its picker already exist. `Expanded Boon` declares `no_effect: situational` while its `note:`
    field admits the effect exists; the rules give 1 additional Pact Boon, worth 2 Maneuvers.
11. **[BUG-47] The Druid is missing a Level 1 class feature.** `Wild Speech` (`classes.md:1456`) is
    absent from `class_features.yaml`. Every other walked class lists its L1 Flavor Feature.
    `class_features.yaml` is never loaded by `catalog_verify` at all.
12. **[BUG-48] `Human Resolve` is priced at 1 Ancestry Point and applies nothing.** The rules expand
    the Death's Door Threshold by 1; the catalog declares `no_effect: narrative`. `death_threshold`
    is a real displayed derived stat computed with no grant term. Tanrielle is Half-elf, so this is
    one click from a canon build.
13. **[BUG-49] `_TODO_CANON_OK` has a dedup hole.** The Trade Expertise tripwire keys on a bare name
    deduplicated across four ancestry lists. Model the Human row alone, leave Elf's a todo, and the
    tripwire stays green **while the effect double-applies** to Tanrielle. Nothing anywhere checks
    that a `limit_raise` string naming an Expertise is backed by an actual trait on that ledger.
14. **[BUG-50] `verify.yml` never builds the Companion and does not trigger on `companion-src/**`.**
    A push touching only `template.html` runs deploy but not verify, then publishes. Nothing anywhere
    reads the generated Companion page. Its entire correctness gate is four greps and a `tail`.
    The ORC/attribution card, the one condition under which publishing DC20 text is permissible, is
    checked by nothing.

## The cheapest fixes, ranked by rows closed per unit of work

1. **Delete `and e.get("grants")` at `catalog_verify.py:282, 334, 342, 353, 362, 374`.** Six
   characters, and it extends CH-5's exact discipline from ancestry traits to subclasses,
   disciplines, pact boons and talents. **Closes 5 rows and the omission failure mode in five
   categories at once.** Do this first.
2. **Name the engine's derived-stat labels and spine-feature strings as constants in
   `build_engine.py` and import them everywhere.** Collapses rows A1, A4, A10, A18, A21 and removes
   the string-matching layer that four of the six confirmed-silent breakages travel through.
3. **Add `tools/**` to `deploy.yml` paths** (BUG-38). One line, and without it nothing else here
   reaches production anyway.
4. **Give `make_map.py` a `--check` flag and one step in `verify.yml`.** `catalog_build.py` already
   has the pattern. `BACKLOG_DONE.md:288` records that MAP.md staleness has only ever been caught by
   a human reviewer.
5. **Add `companion-src/**` to `verify.yml` paths, build the page there, and assert against the
   generated HTML.** Almost every UNGUARDED row in region D becomes checkable the moment something
   reads the output.
6. **Add `hp`/`mp`/`sp` to the engine's equipment-effect keys.** Retires `DISPLAY_DELTAS`, the only
   hardcoded per-character delta in the Companion, and closes a whole class of unmodellable item.

---

# The table

Guard values: **D** derived (one side computes from the other), **A** asserted (a named check
compares them), **U** unguarded. A row marked **LIVE** is already wrong.

## Region A: `tools/` internals

| # | Fact that must agree | A | B | Guard | Fix |
|---|---|---|---|---|---|
| A1 | Derived-stat LABELS are a wire protocol between engine and API | `build_engine.py:481-507` | `builder_api.py:2189`, `builder_build.py:464-488` | U | derive |
| A2 | Skill governing-attribute keys vs engine attribute names | `skills_trades.yaml` skills keys | `builder_api.py:2134` abbrev map | U **LIVE-risk** | derive + assert |
| A3 | Point-buy budget 12 and L1 attribute cap 3 | `build_engine.py:62,73` | `builder_api.py:1459-1460`, `builder_build.py:737` | U | derive |
| A4 | Path slot levels `[2,4,6,8]` vs the class spine | `build_engine.py:68` | `class_spines.yaml` features | U | derive |
| A5 | FR20 slot to category-rank map | `builder_api.py:66-79` | `builder_verify.py:1709-1717` | U **LIVE** (BUG-42) | derive + assert |
| A6 | The `attr_` grant-key prefix | `build_engine.py:166` | `builder_api.py:2409`, `catalog_verify.py:903` | A (by accident, via FR-46) | derive |
| A7 | FR-36 category accent colours | `builder_build.py:149-152` CSS | `builder_build.py:794` `CATCOL` | U (A for the CSS pair only) | derive |
| A8 | Rank to category-NAME vocabulary | `builder_api.py:66-80` comments | `builder_build.py:793` `CATLBL` | U | derive |
| A9 | The `spells.md` metadata parser | `builder_build.py:65-77` | `catalog_verify.py:131-139` (retyped) | U | derive (import it) |
| A10 | Grant-key to derived-stat-label map | `builder_verify.py:2957` `RT_STAT` | `builder_smoke.py:55` `GRANT_STAT` | U, **already drifted** (`sp` missing) | derive |
| A11 | `PLACEHOLDER_MARKERS` sentinels | `builder_api.py:81` | `catalog_verify.py:47` | U | derive |
| A12 | `base_name` / `norm` normalisation rule | `builder_api.py:115` | `catalog_verify.py:67-73`, `builder_build.py:356` (deliberately different) | U | derive A/B, document C |
| A13 | The multiclass long-form grammar | `builder_api.py:1656` regex | `catalog_verify.py:250` regex | U | derive |
| A14 | The five-class roster and its spelling | `builder_build.py:56` | `builder_api.py:86`, `catalog_verify.py:111`, `catalog_build.py:127` | U (partial one-way) | derive from spine |
| A15 | The Mastery ladder and its level thresholds | `build_engine.py:70,77` | `builder_api.py:82,1042`; `MB` in `builder_api.py:2139` vs `builder_verify.py:616` | U for A/B, A for the `MB` pair | derive |
| A16 | The L10 builder ceiling | `builder_api.py:2064,2098,2715,2750` | `class_spines.yaml` max level | U | derive |
| A17 | The `(undecided)` sentinel | `builder_api.py:83` | `builder_build.py:667,734`; 7 re-declarations in `builder_verify.py` | U | derive |
| A18 | Engine-stat mismatch whitelist labels | `builder_verify.py:154` | `catalog_verify.py:99` | U | derive |
| A19 | `ATTR_BASE_SUM = -8` vs the four live copies of `-2` | `build_engine.py:63` (zero readers) | `build_engine.py:286`, `builder_api.py:158,1459`, `builder_build.py:737` | U, costume 1 | derive or delete |
| A20 | The two Path names and which resource each riders | `catalog_build.py:275` | `build_engine.py:346,564` (`startswith` vs `==`), `builder_api.py:2446` | U | derive |
| A21 | The `"2 Ancestry Points"` spine-feature string | `build_engine.py:212,230` | `builder_api.py:2661` (and `Talent`/`Path`/`Subclass` alongside) | U | derive |
| A22 | Background point budgets (5 skill + Int, 3 trade, 2 lang) | `build_engine.py:65-67` | `builder_verify.py:254-256` fixture | U, and **fails open** (under-spend is legal) | derive + assert balanced |
| A23 | Language fluency vocabulary and cost | `builder_api.py:85` | `builder_build.py:321,894` | U | derive |
| A24 | The canon ledger set | `builder_build.py:55` `CHARS` | `builds/*.yaml` (globbed by `catalog_verify.py:88`) | U | derive |
| A25 | The EV tier ladder, implemented twice in one file | `ev_model.py:41-46` | `ev_model.py:62-67` | U (no harness at all) | derive |
| A26 | The page SHELL vs the committed `builder.html` | `builder_build.py` `TEMPLATE` | `builder_verify.py:101-113` hashes blobs only | U for the shell | assert |

## Region B: `builds/catalog/` vs `rules/`

| # | Fact that must agree | Catalog | Rules | Guard | Fix |
|---|---|---|---|---|---|
| B1 | 130 class-progression cells across 5 classes | `class_spines.yaml:9-63` | `tables.md`, `classes.md` (both hand-rebuilt) | U | derive |
| B2 | The levels granting +2 Ancestry Points | `class_spines.yaml` L4/L8 | **`ancestries.md:30-31` says L4 and L7; the class tables say L4 and L8** | U, and the rules **contradict each other** | assert + errata note |
| B3 | What each Spellblade Rune grants | `spellblade.yaml:116-121` | `classes.md:3103,3114` | U **LIVE** (BUG-43) | data fix + assert |
| B4 | Subclasses must declare an effect | `barbarian.yaml:80-84` (bare strings) | `classes.md:254-257` Spirit Guardian grants a Maneuver | U, structurally (see FR-47) | assert |
| B5 | `Expanded Meta Magic` grants | `talents.yaml:47` | `character-creation.md:548-553` | U **LIVE** (BUG-46) | data fix |
| B6 | `Expanded Boon` grants | `talents.yaml:55` | `character-creation.md:609-612` | U **LIVE** (BUG-46) | data fix |
| B7 | `Human Resolve` effect | `ancestries.yaml:50` | `ancestries.md:338` | U **LIVE** (BUG-48) | data fix |
| B8 | Six Beastborn traits' prerequisite | `ancestries.yaml:227-232` | `ancestries.md:927` | U **LIVE** (BUG-44) | extend the parser |
| B9 | Named class features per level | `class_features.yaml` | `classes.md` per-class blocks | U, file never loaded by `catalog_verify` | derive |
| B10 | Every talent's prerequisite / `once` / level | `talents.yaml:26-62` | `character-creation.md` (17 lines) | U (name presence only); **all 17 currently identical** | derive |
| B11 | Class cardinalities and spell-access model | `catalog_build.py:126-170` literals | `classes.md:2834,2873,3204,3229` | U | derive (the phrases are regular) |
| B12 | The Spell School enumeration | `spell_schools.yaml` (5) | `spells.md` (8) | A one-way only | assert set + name the gap |
| B13 | Sorcerous Origin options and the +2 spells | **no catalog row exists** | `classes.md:2541-2551` | U, applied by name-match in 2 files | add rows (this is BUG-26) |
| B14 | A `spells: N` grant must declare its reach | `talents.yaml:79`, `:60` | `classes.md:3529` | A for ancestries only | hoist the BUG-25 loop |
| B15 | The Mana/Stamina Spend Limit cap | `damage_addons.yaml:49,56` `cap: 2` | `spells.md:5907`, engine `spend_limit` | A against a mirrored literal | derive **LIVE at L5** (BUG-37) |
| B16 | `Pact Familiar` effect | `warlock.yaml:97-99` | `classes.md:3296` | U, and inconsistent with `Fiendish Aura`'s todo | reconcile |
| B17 | Battlefield Tactics: amount, melee-only, ally-facing | `damage_addons.yaml:74-78` | `classes.md:1254-1256` | A on the id set only | assert the arithmetic |
| B18 | List completeness (traits, skills, trades, languages, talents) | 9 + 12 + 28 + 15 + 7 lists | `rules/` | A **one-way only**; complete today | assert set equality |
| B19 | Maneuver names and their TYPE | `maneuvers.yaml:14-48` | `combat.md` four `####` sections | A, but against a **magic line window** `[967:1684]` and type-blind | split on headings |
| B20 | The Paragon subclass grants, fanned to 5 files | `catalog_build.py:114-121` | `character-creation.md:757-780` | U | derive |
| B21 | Stamina Regen trigger wording per class | `stamina_regen.yaml:14-23` | `classes.md` + `_INDEX.md` errata | A, keyword-only (the errata pinning is the repo's best guard) | leave, comment |
| B22 | `# rules/... l.N` provenance citations | `class_features.yaml:55,71,86` | actual sections | U; **three are wrong** (Commander cites the Bard) | fix by hand |

## Region C: `builds/*.yaml` ledgers

**The boundary, which is the most valuable single output of this region.** The CH-5 ledger-reconcile
guard (`catalog_verify.py:862-911`) is **an ancestry-trait guard, not a ledger guard**. It walks one
option category, fires 6 times, checks catalog to ledger only (an *extra* grant is not caught),
numeric grants only, and resolves catalog rows by bare name while ignoring the entry's own `source:`.

| # | Fact that must agree | Ledger | Other | Guard | Fix |
|---|---|---|---|---|---|
| C1 | Bonan's L1 class-feature grants | `bonan.yaml:27` | `class_features.yaml:42-47` | U **LIVE** (BUG-39) | derive |
| C2 | Companion `audit`/`skills`/`stats`/`rolls` prose | `builds/*.yaml` resolved state | `template.html:474,498` | U, **already drifted** | derive / delete |
| C3 | Xanwyn's Amulet of Health +2 HP | `xanwyn.yaml:84` prose | `companion-src/build.py:67` `DISPLAY_DELTAS` | U, engine has no `hp` channel | add the channel |
| C4 | Trade Expertise applied exactly once | `tanrielle.yaml:94` | `ancestries.yaml:53` todo | A **with a dedup hole** (BUG-49) | key on (list, name) |
| C5 | Tanrielle's Paladin subclass grants | `tanrielle.yaml:48` (omitted) | `spellblade.yaml:130-134` | **Conditional**, so omission is silent | drop the conditional |
| C6 | Class-talent grants | `bonan.yaml:47`, `scaletrix.yaml:50` | `talents.yaml:39` | U entirely | extend the lookup |
| C7 | Equipment effect numbers across ledgers | `tanrielle.yaml:109` = `xanwyn.yaml:82`; Guard +1 PD in 3 ledgers | no equipment catalog | U | assert cross-ledger |
| C8 | Runt's Pact Armor +1 AD placement | `runt.yaml:187-192` | `warlock.yaml:88-93` | **A, both directions. This is the pattern to copy.** | leave |
| C9 | `SCHEMA.md` grant-key list | doc | engine reads 11 more keys | U | assert the enumerations |
| C10 | `SCHEMA.md` equipment fields, slot enum, dead `level_tagged`, 2 wrong worked examples | doc | code + live ledgers | U | fix + assert |
| C11 | `granted_spells` count vs its `grants` | 6 sites | runes and metamagic have the check; spells and maneuvers do not | A in aggregate only | assert per entry |
| C12 | Scaletrix's Angelborn trait needs `Redeemed` on the ledger | `scaletrix.yaml:26` | `ancestries.yaml:142` `opens:` | U for canon ledgers | port `_allowed_lists` |
| C13 | `spell_access` copied onto an entry | `scaletrix.yaml:23` | `ancestries.yaml:145` | U (CH-5 filters to numerics) | extend the block |
| C14 | `limit_raise` free text vs a substring match | `tanrielle.yaml:94` | `build_engine.py:423-426` | U | closed vocabulary |
| C15 | `damage_addons` per-character rows vs ledgers | `damage_addons.yaml:90-125` | 6 ledgers' equipment | A against a mirror | assert against the ledger |
| C16 | Top-level `subclass:` vs the L3 pick | `bonan.yaml:8` vs `:43` | n/a | U, cosmetic | derive |

**Verified clean and already guarded** (so they are not re-audited): the `expected:` blocks (genuinely
derived-checked, and `expect(total_ok == 90)` fails if any key is dropped); the six ledgers baked into
`builder.html` (sha256); ancestry-trait costs and prerequisites; spell/maneuver counts vs budget;
pact-boon grants; subclass-granted languages. `builds/reports/` is gitignored and regenerated on
demand, so there is nothing to reconcile.

## Region D: `companion-src/`

**The fact that changes the weight of every row here:** `verify.yml` does not trigger on
`companion-src/**` and never runs `build.py`. Nothing anywhere reads the generated Companion page.
Every U below means "will reach players' phones silently".

| # | Fact that must agree | A | B | Guard | Fix |
|---|---|---|---|---|---|
| D1 | The six-character key set | `build.py:56-59`, `template.html:440,574`, `builder_build.py:55`, `damage_addons.yaml` | `builds/*.yaml` | U | derive |
| D2 | Stat/roll LABELS gate the entire engine bake, matched by `===` | `template.html:444-446` | `template.html:522-533` | U, **fails open** | assert |
| D3 | The condition pill list | `template.html:435` (12) | `general-rules.md:1811` (~30) | U **LIVE** (BUG-40) | derive |
| D4 | The House Rules tab | `template.html:321-332` | `rules/house-rules.md` | U, structurally (corpus skips the file) | derive |
| D5 | Accordion spell / maneuver / item names, 9 mismatches | `template.html:975,987,996,1010,1014,1024,1040,983` | 6 ledgers | U **LIVE** (BUG-41) | derive |
| D6 | Character display names | `template.html:441,500` | `tanrielle.yaml:8`, `xanwyn.yaml` | U **LIVE** (inverted for Tanrielle) | derive |
| D7 | Tan's accordion hardcodes 6 derived numbers | `build.py:122-152` | `PARTY_DERIVED`, `tanrielle.yaml` expected | U; all agree today, **all break at L5** | derive |
| D8 | `DISPLAY_DELTAS` hardcodes one item | `build.py:67` | `xanwyn.yaml` equipment | U | model it |
| D9 | Static help text quotes `+5` and `SP regen (2)` | `template.html:234,450,509` | derived attack and sp | U; **breaks at L5** | derive |
| D10 | `builder_verify.ORACLE` claims to be the Companion's values | `builder_verify.py:660-668` | `template.html:444-446` | A **against a hand-copy**, costume 3 | parse the real file |
| D11 | The FR-6 linkify engine, 19 declarations | `template.html:403-411,435-439,892-898` | `builder_build.py:355-375` | U; byte-identical today | hoist to `rules_corpus` |
| D12 | README's healthy-build section count | `README.md:18` says 191 | build prints **172** | U, drifted twice (216, 191, 172) | assert the count |
| D13 | README's architecture description | `README.md:19,38-41,59` | current `build.py` | U, five separate drifts | assert token coverage |
| D14 | The IP-hygiene canary words | `deploy.yml:82,93,100` | GM files, **not in the repo** | A in form only, costume 3 | assert positively |
| D15 | The map guard greps only JPEG | `deploy.yml:86` | `build.py:98-108` block deleted, format unrecorded | U | broaden to `data:image/` |
| D16 | The private-accordion cut is positional | `build.py:217-219` | `build.py:169,178` | Half-asserted (no post-check on the L5-L6 block) | mirror the Beseech pattern |
| D17 | The ORC / attribution card | `template.html:339-343` | `DEPLOY.md:13-17` claims it is verified | **U. The highest-consequence check in the file, and it does not exist.** | one grep |
| D18 | The ruleset version string | `template.html:320,342` | `ruleset:` in 16 yaml files | U | derive via a token |
| D19 | The live URL and published filenames | `template.html:346,347,573` | `deploy.yml:70,73` | U | make relative |
| D20 | `rules/` enumerated by hand three times | `rules_corpus.py:195-200` | the directory (15 files) | U, fails silently both ways | assert |

## Region E: docs and CI

| # | Claim | Where | Actual | Status | Fix |
|---|---|---|---|---|---|
| E1 | Deploy triggers cover every build input | `deploy.yml:33-37` | omits `tools/**` | **STALE, LIVE** (BUG-38) | add the path |
| E2 | "A healthy build prints `rules sections: 191`" | `companion-src/README.md:18` | prints `...cleanup+merge: 172` | STALE (number and string) | assert in code |
| E3 | Deploy copies `builder.html` verbatim | `RUNG3_PLAN.md:145` | it regenerates from source | STALE, and it invalidates the stated safety argument | delete |
| E4 | Install line for `build.py` | `companion-src/README.md:17` | omits PyYAML, which `build.py` hard-exits without | STALE | fix |
| E5 | CI installs `pypdf` | `verify.yml:46` | nothing imports it | STALE, vestigial | drop |
| E6 | Interpreter version | `verify.yml:43` 3.11 vs `deploy.yml:61` 3.12 | divergent | CORRECT but unasserted | pin once |
| E7 | "66/66 oracle" | `ROADMAP.md:8`, `FR12_PLAN.md:29,83,104`, `catalog/SCHEMA.md:13,31`, `catalog_verify.py:65` comment | **90/90**, asserted since 2026-07-16 | STALE in 5 live docs; `FR12_PLAN:104` is a definition-of-done that cannot be met | replace |
| E8 | `builder.html` is ~262 KB | `FR12_PLAN.md:41`, `BACKLOG.md:84` | **2,600,533 bytes** | STALE by ~10x, and it is the cost model for a live epic | update |
| E9 | `catalog_build.py` l.31 imports `CLASS_TABLES` | `FR12_PLAN.md:23` | L34, `load_class_tables` | STALE (the only bad citation of 28) | tense-mark |
| E10 | Three template placeholders | `companion-src/README.md:38` | five | STALE | `assert "__" not in tpl` |
| E11 | `tools/MAP.md` is current | `MAP.md:3` | **byte-identical on regeneration; all 8 headers and ~390 ranges correct** | CORRECT | `--check` flag + CI step |
| E12 | Doc line-number citations | 28 spot-checked | 27 resolve correctly | CORRECT (96%) | leave |
| E13 | Quiet-suite log volume ~76KB; chunks 311/223/245 | `BACKLOG.md:133`, `BACKLOG_DONE.md:247` | 67,098 bytes; the chunks sum to 779 vs 770 because `--only` matches substrings and overlaps | STALE, harmless | note it |

**Numbers verified CORRECT and asserted:** 90/90, 770 checks, 231 options, 7 rows / 4 distinct,
30 maneuvers, 9 ancestry lists, 12 skills / 28 trades / 6 knowledge, `API_PY` sha `010a9c6c`,
`builder_build.py` at 1,082 lines, the CH-11 measurements (2,600,533 bytes / 2,129,345 / 81.9% /
~471KB), and the whole `catalog/SCHEMA.md` worked example. The counts that sit behind an `expect()`
are all right. That is the pattern worth generalising.
