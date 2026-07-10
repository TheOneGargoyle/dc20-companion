# DC20 Rules — Index (Beta 0.10.5)

**Audience: GM / co-GM (and player-safe — these are the published rules).**

Searchable markdown extracted from the official DC20 PDFs in Darryl's Dropbox. This is the home file 06 asked for: the rules live here so the assistant can **reason only from these files** for 0.10.5 mechanics, and **flag when it is inferring rather than citing.** Beta numbers change between versions — if a value isn't in these files, say so rather than guessing.

## Core rulebook — `DC20 RPG 0.10.5 Beta v1.pdf` (269 pp, current version)

| File | Covers | Source pp. |
|---|---|---|
| `core-rules.md` | Attributes, Skills, Trades, Languages, Mastery & Training, Checks & Saves, Advantage/DisADV, Attacks, Defenses, Health & Death's Door, Damage | 9–39 |
| `combat.md` | Combat Resources (Mana/Stamina/Grit), Actions, Reactions, the Martial chapter (Maneuvers) | 40–67 |
| `spells.md` | Spellcasting rules + the full spell list | 68–145 |
| `starting-combat.md` | Initiative & starting combat | 146–150 |
| `general-rules.md` | Environment, Vision, Areas of Effect, Equipment (Weapons/Armor/Shields), Conditions, Resting, **DCs**, GM Guide | 151–180 |
| `character-creation.md` | 10-step creation, progression, Talents, Character Paths | 181–192 |
| `ancestries.md` | Ancestry system, traits, origins, creation | 193–206 |
| `classes.md` | All 13 classes & subclasses (features, prose) | 207–267 |
| `changelog.md` | 0.10.5 changelog | 268–269 |
| `tables.md` | **Hand-verified wide tables**: all 13 class progression tables (per-level advancement packages), DC "by 5's" table, Armour Examples | various |

## Supplements

| File | Covers | Source |
|---|---|---|
| `bestiary.md` | ~40 monster stat blocks — Monster Starter Pack + Beta Bestiary Vols 1, 3, 4. Heavy non-humanoid variety (oozes, plants, drakes, swarms, undead) for Arc 4. Includes the **Aqua Ooze** and **Animated Armor** the party has met. | Starter Pack 0.2; Mag 06, 17, 21 |
| `encounter-building.md` | Stat-block conventions + Crafting Encounters guidance | Mag 12 (Bestiary Vol. 2), pp.3–9 |
| `challenges.md` | The formal **Skill Challenge** system — DC bands, Success Point Threshold, the 4 steps, and Combat/Exploration/Social challenge types. Underpins the house-style challenges in `house-rules.md`. | Mag 04 |
| `house-rules.md` | **Table-facing house rules & conventions** layered on the published ruleset: skill-challenge house style, the broader Sense Magic ruling, Darryl's resource-weighting/balance-maths heuristic, and free-rebuild-on-update. *(Moved from `06` on 2026-06-21.)* | Table |

## How tables were handled

The rulebook is a two-column layout. Prose extracts cleanly with correct reading order. Wide tables flatten when auto-extracted, so the high-value ones (class progressions, DC, armour) were reconstructed from PDF text coordinates and **spot-checked against the rendered pages** (Barbarian, Spellblade, Commander verified pixel-against-source). Weapon Styles, Weapon/Armour Properties, and Conditions are prose rules and live in `general-rules.md`.

## Known errata & extraction gaps

- **Spellblade — Stamina Regen (errata, corrected shortly after 0.10.5 release).** The printed 0.10.5 omitted the Spellblade's SP-regen rule by mistake; the official errata restores it. **Use this, not the book's silence:** *Stamina Regen — Once per Round, you can regain up to **half your maximum SP** after any of: (a) you **Hit** on an Attack with your **Bound Weapon**, (b) you make a **Spell Check**, or (c) you cast a **Spell with the Weapon tag**.* (Source: Darryl, errata/supporter channel, 2026-06-20.)
- **Prone condition — deliberately NOT in the alphabetical Conditions list.** Per Darryl, Prone was removed from the Conditions list this edition (to avoid awkward interactions) and now lives in the **Creatures & Combat** section (p163) — it *is* in `general-rules.md` under the `#### Prone` heading. Effect: while Prone you have **DisADV on your own Attacks**, **Ranged Attacks against you have DisADV**, and **Melee Attacks against you have ADV**; you can only Crawl; standing up costs 2 Spaces. **Note the asymmetry:** knocking a target Prone helps *melee* attackers (ADV) but *hinders* ranged attackers (DisADV) — so a Prone+Exposed target gives melee allies net ADV2 but ranged allies net *zero* (the Exposed ADV is cancelled by Prone's ranged DisADV). Corrected 2026-06-20.

## Global conventions (apply everywhere)

- **Rounding — always round UP.** *"No matter what the fraction is, you always round up in DC20"* (`core-rules.md`, in the damage-sharing example at ~l.2618). This is a global rule but the book only states it inside an example, so it's easy to miss — it governs **every** fraction: halved jump distances, halved damage/resistance, divided damage, half-Speed movement, ½-level (Combat Mastery) calcs, etc. Worked case: a halved Standing Jump of 5 → 2.5 → **3 Spaces**.

## Notes & caveats

- These are **player-safe** (published rules), unlike the numbered GM-only campaign files.
- Extraction is from the text layer, not OCR — wording is faithful. The only lossy areas are wide numeric tables (addressed in `tables.md`).
- Class features in `classes.md` are prose; the per-level point/feature grid is in `tables.md`.
- Sources skipped as superseded/off-campaign: the `Archive/` folder (rules 0.6–0.9.5), pre-written adventure modules, and class supplements for classes nobody plays.
