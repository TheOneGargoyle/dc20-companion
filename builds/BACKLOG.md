# DC20 Builder & Companion, Backlog

Single home for **app / tooling** work (the builder, the Companion, the engine). Living doc, updated as we triage. Started 2026-07-16.

**Completed work lives in [`BACKLOG_DONE.md`](BACKLOG_DONE.md)** (split out 2026-07-28). That file holds the Done table plus every shipped item's notes, shipping narratives and design write-ups. This file is OPEN work only.

**What lives elsewhere:** game-side rulings and player confirmations (attribute destinations, maneuver splits, rules calls) stay in `09_cogm_agenda_GM.md`, which is the canonical tracker for those. This file is only bugs / features / chores for the software. Where a software item genuinely waits on a player answer, it is marked Blocked with the person named.

**Legend.**

- Type: `bug` / `feature` / `chore`
- Area: `engine` (build_engine.py), `catalog` (builds/catalog), `data` (a ledger yaml), `builder` (builder_build.py, incl. the sheet), `companion` (companion-src), `repo`
- Priority: `P1` soon / high value or unblocks other work · `P2` should do · `P3` nice to have. **Provisional, a proper prioritisation pass is still pending.**
- Status: `ready` / `blocked` / `needs-clarification` / `parked` / `done`
- Convention: no em-dashes anywhere.
- Status cells are kept short. Detail, commit SHAs and history live in the item's note below, or in `BACKLOG_DONE.md` once the item ships.

---

## At a glance

### To Do

| ID | Title | Type | Area | Pri | Status |
|----|-------|------|------|-----|--------|
| FR-12 | Add full DC20 class + ancestry data coverage | feature | engine+catalog+builder | P2 | PLANNED (2026-07-19: full epic GO, refactor-first; `FR12_PLAN.md` Phase 3-4) |
| FR-13 | Live spell & maneuver legality (school/type filtering) | feature | engine+builder | P3 | PLANNED (maneuver half done 2026-07-19; spell half = FR-13a; `FR12_PLAN.md` Phase 2) |
| FR-33 | Rules > Ancestries: split the one big page / add dividers | feature | companion | P3 | ready |
| FR-34 | Rules > Character Creation > Class Talents: merge the many tiny pages | feature | companion | P3 | ready |
| FR-4 | Rename a char / file (display-name slice done `7676679`; handle/file half remains) | feature | builder+data | P3 | needs-clarification (scope call, see note) |
| FR-32 | Rules > Spells: drop PDF-scan subcategory + split the giant spells page | feature | companion | P2 | needs-clarification |
| FR-35 | Rules > Tables: move class tables into class pages; armour examples with armour | feature | companion | P3 | needs-clarification |
| FR-38 | Rules popup: show only the clicked line's snippet, not the whole section | feature | builder | P2 | ready (intake 2026-07-19; refines FR-6) |
| FR-39 | Points-spent "x of y" readout for skills/trades/languages (like ancestry/maneuvers) | feature | builder | P2 | ready (intake 2026-07-19) |
| FR-40 | Companion collapsible-section consistency pass (naming, stale notes, unlinked spells/maneuvers, missing sections) | feature | companion | P2 | ready (intake 2026-07-19; see note) |
| FR-41 | Per-PC "signature plays" cheat sheet on the Companion, from the optimisation workshops (08/10-16) | feature | companion | P3 | ready (intake 2026-07-19) |
| BUG-20 | Scratch: Human Trade Expertise (L1) not granting its cap+level free step | bug | builder+engine | P2 | ready (Tier-2, allocator-coupled; deferred 2026-07-25, see note) |
| BUG-26 | Scratch: Innate Power (MC Sorcerer, L2) not offering the Sorcerous Origin sub-choice / conditional +2 spells | bug | builder+catalog | P2 | ready (DEFERRED 2026-07-25 by Darryl, needs a design call, see note) |
| FR-42 | Spellcasting Expansion (general talent) adds 1 Spell Source OR 3 Spell Schools: needs a sub-choice node so its 3 spells are drawn from the chosen widening | feature | builder+catalog | P3 | ready (spotted 2026-07-27 during BUG-30, see note) |
| CH-5 | Burn down the option-coverage todo list (18 distinct options with a real unmodelled effect) | chore | catalog+engine+builder | P2 | IN PROGRESS (Tier-2 engine slice PUSHED + CHROME-VERIFIED `83c3f36` 2026-07-29; 14 of 18 closed, 4 distinct left, all four gated on BUG-20 or a design call, see note) |
| CH-6 | CI Verify takes ~3m; cache the Playwright browser download and add a `paths` filter to the `pull_request` trigger | chore | repo | P3 | ready (2026-07-28, not urgent, see note) |
| CH-7 | Assert the `rules/classes.md` source repairs so a PDF re-extraction cannot silently revert them | chore | repo+companion | P3 | ready (new 2026-07-28, see note) |
| CH-10 | Audit every duplicated fact in the repo; derive or assert each one | chore | tools+catalog | P1 | DONE 2026-08-14, deliverable is `CH10_DUPLICATED_FACTS.md`, 97 rows; spawned BUG-37..50 |
| BUG-37 | `damage_addons.yaml` freezes the Spend Limit at `cap: 2` (L4); breaks the moment the party hits L5 | bug | catalog | P1 | DONE 2026-08-14, `cap_stat: spend_limit` on both steppers; proved in-browser, 2 at L4 and 3 at L5 |
| BUG-38 | `deploy.yml` `paths:` omits `tools/**`, so engine/API fixes never reach the live pages | bug | repo | P1 | FIXED not shipped: missed `fa15db4` because the remote bridge cannot write `.github/workflows/**`; needs a hand-paste (note below) |
| BUG-39 | Bonan's ledger flattens `grants_unarmored` into an unconditional +2 AD, and names 2 wrong features | bug | data+catalog | P1 | ready (CH-10; live character) |
| BUG-40 | Companion condition pills cover 12 of ~30 conditions, and 2 of the 12 do not exist | bug | companion | P2 | ready (CH-10; players hit this every session) |
| BUG-41 | Companion accordions name a spell and a maneuver that do not exist, plus 7 more ledger mismatches | bug | companion | P2 | ready (CH-10; fold into FR-40) |
| BUG-42 | `FR20_CAT` vs `FR20_RANK` already drifted; ancestry_origin renders in the wrong group | bug | builder | P2 | ready (CH-10; check is blind, both dicts default to 3) |
| BUG-43 | Lightning and Wind Runes are priced and inert (+1 Speed, +3 Jump undeclared) | bug | catalog | P2 | ready (CH-10) |
| BUG-44 | Six Beastborn traits are missing `requires: Natural Weapon` | bug | catalog | P2 | ready (CH-10; parser cannot see a prose prerequisite) |
| BUG-45 | Three of the eight Spell Schools are unpickable in the builder | bug | catalog+builder | P2 | ready (CH-10) |
| BUG-46 | `Expanded Meta Magic` and `Expanded Boon` each declare half their rule | bug | catalog | P2 | ready (CH-10) |
| BUG-47 | Druid L1 feature `Wild Speech` missing from `class_features.yaml` | bug | catalog | P3 | ready (CH-10) |
| BUG-48 | `Human Resolve` priced at 1 point, applies nothing (death_threshold has no grant term) | bug | catalog+engine | P3 | ready (CH-10) |
| BUG-49 | `_TODO_CANON_OK` dedups by bare name, so the Trade Expertise tripwire can go green while it double-applies | bug | tools | P2 | ready (CH-10; pairs with BUG-20) |
| BUG-50 | `verify.yml` never builds the Companion and does not trigger on `companion-src/**` | bug | repo | P1 | ready (CH-10; nothing reads the published Companion at all) |
| CH-13 | Drop the `and e.get("grants")` conditional at 6 sites in `catalog_verify.py` | chore | tools | P1 | DONE 2026-08-14, all 6 sites unconditional; surfaced C5 and closed it without editing a canon ledger (note below) |
| CH-14 | Name the engine's derived-stat labels and spine-feature strings as constants and import them | chore | engine+tools | P1 | ready (CH-10 fix 2; collapses A1/A4/A10/A18/A21) |
| CH-15 | `make_map.py --check` plus one step in `verify.yml` so a stale `MAP.md` fails CI | chore | tools+repo | P2 | ready (CH-10 fix 4; `catalog_build.py` already has the pattern) |
| FR-49 | Add `hp`/`mp`/`sp` to the engine's equipment-effect keys; retires `DISPLAY_DELTAS` | feature | engine+companion | P2 | ready (CH-10 fix 6; closes a class of unmodellable item) |
| CH-12 | Offline Pyodide shim so `builder_smoke.py` runs outside CI | chore | tools | P1 | ready (new 2026-08-14; fix already proved end to end, see note) |
| CH-11 | Split the rules corpus out of `builder.html`: 81.9% of the file is one `RULES_DATA` literal | chore | builder+tools | P1 | ready (new 2026-07-30; offline-use answered, always the published URL; term-index + on-demand-bodies shape, see note) |
| FR-47 | Extend the FR-44 coverage walker to BARE-STRING option lists (subclasses today), so a whole pickable surface cannot sit outside the ledger | feature | catalog+repo | P2 | ready (split out of BUG-35 2026-07-27, see note) |
| FR-48 | A SCRATCH build has no base Combat Training: the class's own training is not catalog data, so the sheet shows only what options granted | feature | catalog+builder | P2 | ready (surfaced 2026-07-28 during BUG-34, see note) |
| CH-4 | Fill `class_features.yaml` L5-L10 (L1-L4 done) so no level falls back to the generic "Class Feature" label | chore | catalog | P3 | ready (new 2026-07-27, pure data, see note) |
| FR-11 | Gear catalog / picker (gear Tier B) | feature | engine+catalog+builder | P3 | parked |
| FR-26 | Stackable conditions (bleed/stunned) as counts not toggles | feature | companion | P3 | parked |

**Push status (confirmed 2026-07-28 from the Actions run list).** All previously "awaiting push" items are on origin and CI-green on both workflows: **FR-45** (`5f2006d`, `6a3b2bb`), **BUG-35** (`a52a707`), **BUG-34** (`b9e2071`, `1e15009`), **FR-46** (`e044d41`), and the FR-46 mutation suite plus CH-6 (`d3a9444`). Their notes are in `BACKLOG_DONE.md`. Since then **CH-8** and **CH-9** (`a842471`) and the **CH-11 filing** (`2e4019c`) are also pushed and CI-green on both workflows. **Origin is `2e4019c`** (the earlier `2e419c` in this file and in the starter was a mistyped short sha, corrected 2026-08-14). CH-8 and CH-9 have been removed from the To Do table above; their notes stay below until they are folded into `BACKLOG_DONE.md`.

**Updated 2026-08-14 (2). Origin is now `9fe3c60`** (the CH-10 audit filing), so `BACKLOG.md` and `CH10_DUPLICATED_FACTS.md` are pushed and the old "let this file ride along" advice is discharged. Re-verified the same way, by sha256-comparing every file this thread touched in OneDrive against a fresh clone of `9fe3c60`: all identical before the edits below. `builds/reports/`, `builds/sources/` and `sheets/` still differ only because `.gitignore` excludes them on purpose. **Pushed as `fa15db4`, 5 files: CH-13 and BUG-37** (`catalog_verify.py`, `damage_addons.yaml`, `companion-src/build.py`, `companion-src/template.html`, this file). **BUG-38 is NOT in it.** Its one-line `deploy.yml` edit never reached OneDrive because the remote bridge treats `.github/workflows/**` as protected, so robocopy reported `Copied 0` for `.github` and the commit message names a fix it does not contain. `builds/builder.html` is deliberately excluded too, but for a good reason: none of its baked inputs changed, so a rebuild moved only the footer stamp and was reverted.

---

## Standing context

**The builder is LIVE WITH THE PLAYERS and has been for weeks** (corrected 2026-07-27). The URL and `howto.html` went out well before the 2026-07-19 intake, players build and respec with it, and **most of the scratch-mode bug list came from them** (Darryl relays their reports; the BUG-17..27 intake is largely player-found). So none of this is a gate on releasing the builder, it is maintenance on a tool in daily use: fixes matter because someone is blocked today, and "wait for players to hit it" is not a strategy, they already have. Any old note implying the link is still being held back (e.g. the 2026-07-11 hold) is stale.

**Where the remaining open work sits.** Waves 1 to D and the bulk of the 2026-07-19 scratch-mode wave are shipped (see `BACKLOG_DONE.md`). What is left is four clusters:

- **The FR-12 / FR-13 epic** (full class + ancestry coverage, then live legality). GO, planned as a phased epic 2026-07-19, architecture in `FR12_PLAN.md`. Phase 0 (= FR-12.0) is done: `class_spines.yaml` is the authored source of truth and `CLASS_TABLES` is retired, so classes are data, not code. Remaining staircase: Phase 2 (full spell/maneuver legality data) -> Phase 3 (FR-12 class coverage) -> Phase 4 (subclass/ancestry breadth) -> Phase 5 (mobile picker UX).
- **Rules-browser structure pass, one coherent job:** FR-32, FR-33, FR-34, FR-35. Three of the four carry a design call.
- **Sub-choice and coverage leftovers from the scratch-mode wave:** BUG-20, BUG-26, FR-42, FR-47, FR-48, CH-4, CH-5 (BUG-36 closed 2026-07-28). BUG-26, FR-42 and CH-5's attribute pickers are all the same sub-choice shape, so they want one slice.
- **Independent polish:** FR-38, FR-39 (builder), FR-40, FR-41 (Companion), CH-6 (CI), FR-4 (scope call), FR-11 and FR-26 (parked).

---

## Bugs

**BUG-20. Trade / Skill Expertise, the Tier-2 allocator-coupled one.** Reframed and deferred out of the 2026-07-25 option-effects slice. These are NOT flat grants: they raise the cap and level of a CHOSEN trade/skill, which the engine models with a `limit_raise` flag on that trade in the allocator. So the fix is a sub-choice plus allocator coupling, not a catalog `grants:` copy. Also carried as a `todo:` in the FR-44 coverage ledger, and FR-46's round-trip confirms both are genuinely inert today (no name-match is quietly covering them).

**BUG-26. Innate Power / Sorcerous Origin. Needs a design call before building** (deferred 2026-07-25, Darryl's call). The reported L2 "Innate Sorcery" bug is really the **MC Sorcerer Innate Power** talent. Per `classes.md` l.2541 it gives +1 MP unconditionally, then a **Sorcerous Origin sub-choice** among Intuitive Magic / Resilient Magic / Unstable Magic, and **only Intuitive Magic grants the +2 spells** (Resilient = Dazed Resistance, Unstable = Wild Magic). The existing FR-13a slice-2 machinery DELIBERATELY conflates this: it models the sub-choice as the spell SOURCE (Arcane/Divine/Primal) and hard-authors Scaletrix's +2 Intuitive spells onto his ledger. Wiring it into scratch mode touches the most delicate builder code, with real regression risk to canon Scaletrix. Two shapes were captured: **(a)** minimal, "assume Intuitive" and reuse the source node, or **(b)** model the 3-way sub-choice and its conditional grant properly.

**Asked and answered 2026-08-14 (Darryl): if we do NOT do it here, what work fixes it?** Nothing fixes it incidentally. Checked against `FR12_PLAN.md` rather than assumed: **FR-12 Phase 3** (class coverage) says in as many words that it prioritises by multiclass-reach first and names *"Scaletrix's MC Sorcerer/Innate Power"* as one of the two drivers, and **Phase 4** is subclass breadth, which is the same shape again. So Sorcerous Origin is forced open by Phase 3 whatever we do. The sequence that costs least: **FR-42 builds the sub-choice node** on greenfield ground (Spellcasting Expansion), **BUG-26 applies it** to Innate Power, and Phase 3 then inherits a working pattern. Deferring past FR-42 does not save the work, it just moves it inside a much larger epic and next to the delicate FR-13a code that hard-authors Scaletrix's spells. **Recommendation: do it at BUG-26, shape (b), straight after FR-42.**

---

## Features

**FR-4. Rename a char / file: the handle/file half.** The display-name slice is DONE and PUSHED 2026-07-18 (origin `7676679`, live-verified; Darryl's call was to pull the trivial display-only part out and leave the rest parked). The canon metacard now renders a slim name-only rename card wired to `set_meta('character', ...)` through `refresh()`, so a rename marks the build dirty and raises the existing "EDITING CANON" warning bar; nothing saves until export. Deliberately NOT the full meta card, ancestry pickers stay scratch-only. Handle and `?char=` deep link are unchanged and the export filename slug follows the new display name. Harness section **(26)**. **Still open, and still needs the scope call first:** display-only vs handle/file vs both. The handle rename is the coordinated one: the id appears in the companion-key -> builder-handle map, the yaml filename, `PARTY_LEDGERS`/`CHARS`, localStorage keys and `?char=` deep links.

**FR-11. Gear catalog / picker (Tier B).** A curated list of the party's real items (weapons, armour, shields, focuses) so items are picked from a dropdown with properties auto-applied, instead of hand-typing effect fields. Pure convenience; would cut hand-entry transcription errors like the language ones. Parked for now; not required for any reconciliation (gear effects already work, see the Parked note on Tier A/C).

**FR-12. Add full DC20 class + ancestry data coverage.** Extend the catalog beyond the party's six classes to all 13 (and the remaining ancestries), so the party can build any character, including on mobile. **Runtime/size is NOT the blocker:** the builder runs the Python engine via Pyodide (a multi-megabyte WASM runtime from CDN), which dominates load and cold-start regardless of catalog size. The full catalog is roughly 100 to 150 KB of YAML (names/costs/prereqs/tags, not rule text), taking builder.html from ~262 KB to ~350 to 400 KB, invisible next to Pyodide; and the engine only ever replays the one character being built, so validation does not slow down. The real costs are (a) human: data entry per class plus the 0.11 beta refresh treadmill, and (b) mobile UX: pickers listing hundreds of options need search/typeahead plus FR-7 filtering to stay usable. **"Only load the classes and ancestries in use" lazy-loading was considered and rejected twice** (re-raised by Darryl 2026-07-18): shaving ~100 KB off a multi-MB load buys nothing for performance. Treat the load question as part of this epic, not a separate item. The old "each class is also a hardcoded progression table in `build_engine.py`" cost is gone since FR-12.0 data-drove the spine. Depends on FR-7 and a picker search box for the mobile experience, and on FR-13 to stay trustworthy once pickers span the full catalog. Large: treat as an epic.

**FR-13. Live spell & maneuver legality.** Enforce that each chosen spell/maneuver is actually accessible to the character: a spell from one of their chosen schools/sources (plus tag grants like Eldritch's Psychic access), and a maneuver of the right type for its slot (Pact Armor's slots need Defensive maneuvers), rather than only counting them and checking they are real catalog entries. **The maneuver-type half is DONE (2026-07-19):** pact-boon maneuver grant-children are filtered to the boon's `maneuver_type` (Pact Weapon = Attack, Pact Armor = Defense), catalog-driven via `warlock.yaml`. **The spell-source half is FR-13a, also done.** What remains is legality in the live engine: the offline harness already validates it for the six known builds (`catalog_verify.py` section 2, per-class access models), so there is no correctness risk today, but `build_engine.py` does counts and budgets and no school/type legality (its docstring lists this as "not yet", l.15). Low urgency while builds are known and hand-verified; it becomes important with FR-12's open pickers over the full catalog, where the builder should offer only legal options and flag illegal picks. Folds into the FR-12 picker work. Bundled minor: per-skill die bonuses (the engine derives skill bonus as attribute + flat mastery and models no skill-specific die mechanics), low priority.

**FR-32. Rules > Spells cleanup.** The Rules browser's Spells area carries an odd PDF-scan subcategory that does not serve navigation, and all spells render as one very long page. Drop the artefact subcategory and split the spells page (per school, per spell, or dividers) so it is browsable. Approach needs a call. Touches the shared rules corpus (`tools/rules_corpus.py`) and possibly the `rules/spells.md` source.

**FR-33. Rules > Ancestries split.** The Ancestries subsection is meaningful, but all ancestries sit on one long page that is hard to scan. Split per ancestry, or add line dividers between them.

**FR-34. Rules > Class Talents merge.** The opposite problem: Character Creation > Class Talents is many pages of one or two paragraphs each. Combine into fewer, longer pages.

**FR-35. Rules > Tables reorg.** Most entries under Tables are class progression tables; consider moving each into its class page. The Armour Examples table could live with the Armour rules (and if so, why not shields / weapons / focuses too). Needs a call on how far to take it, and it may interact with FR-32/33/34 as one rules-browser structure pass.

**FR-26. Stackable conditions.** Strictly, some conditions stack (Bleeding, Stunned) but the character-sheet pills only toggle on/off. Would need a count / stack UI. Darryl: ignore for now. Parked.

**FR-38. Rules popup snippet.** Show only the clicked line's snippet in the rules popup, not the whole section. Refines FR-6 (intake 2026-07-19).

**FR-39. Points-spent "x of y" readout** for skills / trades / languages, matching the readout ancestry points and maneuvers already have (intake 2026-07-19).

**FR-40. Companion collapsible-section consistency pass** (intake 2026-07-19): naming, stale notes, unlinked spells/maneuvers, missing sections. Folds in the two known audit leftovers: Bonan's **"Recovery"**, a maneuver that does not exist, and Minimus's **"Grease"**, which should be renamed **Oil Slick**.

**FR-41. Per-PC "signature plays" cheat sheet** on the Companion, drawn from the optimisation workshops in `08` and `10-16` (intake 2026-07-19).

**FR-42. Spellcasting Expansion needs a sub-choice node.** Spotted 2026-07-27 while doing BUG-30. The general talent adds **1 Spell Source OR 3 Spell Schools**, so its 3 spells must be drawn from whichever widening the player chose. **The BUG-30 any-list mechanism does not fit:** that one is genuinely "any list", this one is a CHOSEN widening, so it needs a sub-choice node (same shape as BUG-26 and CH-5's attribute pickers). Do it with FR-48, which touches the same Spellcasting Expansion row.

**FR-47. Extend the coverage walker to bare-string option lists.** Split out of BUG-35 2026-07-27, which is the blind spot that found it. Subclasses are stored as a bare list of strings (`subclasses: [Paladin, Rune Knight, Paragon]`), not as option dicts, so `coverage.py` never walks them and none of them was ever asked to declare an effect: the ledger reports 231 pickable options and Paragon is not one of them. So FR-44's **"0 bare" guarantee only holds for option lists shaped as dicts**, and an entire pickable surface sat outside it. Fix: extend the walker to bare-string option lists, either by requiring them to become dicts or by treating a bare string as an undeclared option, then re-run the count, which will rise. FR-46 is the independent answer to the same problem, since a round-trip that PICKS each option would have flagged Paragon regardless of how it is stored.

**FR-48. Scratch builds have no base Combat Training** (new 2026-07-28, surfaced while giving Combat Training a home on the sheet for BUG-34; the sheet row is HIDDEN while the list is empty, so a scratch build never reads "trained in nothing"). Canon ledgers hand-author `chargen.combat_training`; `blank_ledger` sets it to `[]` and nothing fills it, because a class's own training is not catalog data. Checked while filing rather than guessed at: it is **one line per class in `classes.md`**, inside the same class section `parse_subclasses` already reads (l.2821 for Spellblade, and note that one wraps mid-list, so the parse needs the continuation join the file does elsewhere). **Four sources in total**, all bounded: (1) the class base line, (2) the two Path riders (`character-creation.md` l.350 Martial -> Weapons, l.361 Spellcaster -> Spell Focuses), (3) two general talents already noted in `talents.yaml` (Martial Expansion -> Weapons + Heavy Armors + all Shields; Spellcasting Expansion -> Spell Focuses), (4) disciplines, which BUG-34 already did. The flow and the display exist, so this is a parse function plus five short data lines plus the `blank_ledger` seed. Do it with FR-42, which touches the same Spellcasting Expansion row.

---

## Chores

**CH-4 (new 2026-07-27, from the class-feature trio).** `builds/catalog/class_features.yaml` covers **L1-L4** for the five walked classes (the levels anyone is at; the party is L4). Fill **L5-L10** so no level ever falls back to the generic "Class Feature" label. Two things to know when doing it: (1) `classes.md` has **no "#### Level 5 Class Features" heading**, so the L5 feature ("Expert <Class>") sits inside the L4 block, and the class table in `class_spines.yaml` is the authority for which level owns a feature (L4 = Talent + Ancestry + Path only); (2) **Expert Spellblade grants +1 Discipline**, which is where Tanrielle's L5 Spell Breaker comes from, so it wants `grants: {disciplines: 1}` and will render a discipline child via the BUG-21 machinery. Mechanism is done, this is pure data.

**CH-5. Burn down the option-coverage todo list.** Created by FR-44 (the coverage ledger). Run `python3 tools/coverage.py` for the live list; `catalog_verify` prints the count every run and **it should only ever go DOWN**. Started at 18 distinct options with a real unmodelled effect.

**Tier-1 SHIPPED 2026-07-27, burn-down 18 -> 11 distinct (29 -> 18 rows).** Seven closed: `Frail` {hp: -2}, `Brittle` {ad: -1}, `Reckless` {pd: -1} (flat grants); `Thick-Skinned` {ad: 1}, `Quick Reactions` {pd: 1}, `Hard Shell` {ad: 1} plus an unconditional {speed: -1} (`grants_unarmored`); and `Unfathomable Strength` {jump: 1} (Titanic Leap, `character-creation.md` l.381), which turned out to need BUG-33 as well as the data. The unarmoured three needed a builder change as well as data: `_set_trait` copied only `grants`, so `grants_unarmored` (which had existed for class features since BUG-22) is now honoured on ancestry traits too, merged into the entry's grants when `is_unarmored(ledger)` and annotated either way in the row's note; no engine change, since the merge happens before `sum_grants` sees it. Files: `builds/catalog/ancestries.yaml`, `builds/catalog/talents.yaml`, `tools/builder_build.py`, `tools/builder_verify.py`, regenerated `builds/builder.html`. Verified: coverage.py 18 rows / 11 distinct, catalog_verify 90/90, builder_verify PASS (630 checks, new sections `(CH5)` and `(CT)`), PARTY_DERIVED byte-identical to origin.

**Tier-2, the engine slice, PUSHED + CHROME-VERIFIED `83c3f36`, 2026-07-29. Burn-down 11 -> 4 distinct (18 -> 7 rows).** Seven closed, not the six this entry predicted: `Speed Increase` {speed: 1}, `Short-Legged` {speed: -1}, the three fixed-target `Might / Charisma / Intelligence Attribute Decrease` {attr_<name>: -1}, and BOTH targeted Human rows, `Attribute Increase` and `Attribute Decrease`. The full note is in `BACKLOG_DONE.md`; the short version is that the plan changed shape twice on contact.

- **The three name-matches came out as planned**, but `{attribute_points: +/-1}` was the wrong target shape for the ancestry trait: that key is the class-table budget carrier and would have spawned a rider pick where the trait gives a fixed +1 to a chosen Attribute. So per-attribute `attr_<name>` grant keys, with the target carried in the KEY rather than parsed out of the option name.
- **The generic `Attribute Decrease` closed here too, not in the FR-42 sub-choice slice.** It needs a target, but `Attribute Increase` already had one via the decorated per-attribute variants the picker emits, so making the variant machinery catalog-driven (`targets: attributes`) closed both. FR-42 and BUG-26 still need real sub-choice nodes; this row does not, and it was previously the worse kind of broken: priced at -1 (a free ancestry point) and applying nothing.
- **The remaining 4 are all gated on something other than data:** `Skill Expertise` / `Trade Expertise` are allocator-coupled (BUG-20), `Fiendish Aura` is **PARKED until 0.11** (Darryl, 2026-08-14: there is no spell named Sorcery and no such thing as Cantrips in 0.10.5, both are 0.9.5 holdovers in the source text, so there is nothing to model and no ruling to make; revisit when 0.11 lands), `Natural Armor` needs unarmoured-PDR plumbing in the engine's equipment-only `dr` path. So CH-5's data burn-down is effectively finished; what is left is four decisions.

Canon is unaffected: `catalog_verify` asserts that no walked ledger depends on a todo option, and after Tier-2 there is exactly ONE documented exception left (Tanrielle's `Trade Expertise`, hand-authored in her `trades` block, retired by BUG-20). These were scratch-mode-only wrong answers, which is exactly why they arrived as player reports instead of harness failures. **The harness sections assert the DERIVED STAT, not the catalog row:** `(CH5)` and `(CH5b)` build a scratch character per ancestry, pick the trait and check the number moved by the right amount, including the negative cases (a Dwarf wearing Half Plate must NOT get Thick-Skinned's +1 AD, and the row's note must say so). That shape is deliberate: every bug in this family was "the data says it, nothing applies it", so a check that read the catalog would have passed throughout.

**CH-7 (new 2026-07-28).** `rules/classes.md` is NOT a clean PDF extraction. It was hand-repaired at source on 2026-07-05: the 13 wide class-progression tables rebuilt from `tables.md` and inlined as `####` sub-sections inside their own class, two mid-sentence `### Shields` promotions rejoined, a garbled duplicate `### Barbarian` merged away, and `### Subclasses` x13 demoted to `#### <Class> Subclasses`. The build-time strip in `companion-src/build.py` was then REMOVED as superseded, so there is no runtime safety net either. **Re-extracting the file silently reverts all of it and nothing catches it**: the rules section count is printed by the build, never asserted, and it has already drifted (README says 216, the build now reports 191 merged to 172, so the number moving is not even a signal). This is trap 2 in a different costume, a hand-repair with no assertion guarding it. Fix: assert in a harness that all 13 inlined `####` class tables are present and that no `### Subclasses` heading survives, which converts a silent revert into a failure. Full repair recipe is in the 2026-07-05 entry of `logs/2026-07-early.md`, grep for `classes.md repaired at the source`. While in there, correct the README's stale 216.

**CH-8 (DONE 2026-07-30).** `builder_verify.py`'s `ok()` printed a 78-char `OK` line for every
passing check. Measured: 79 checks emitted 7,525 bytes; the full ~770-check suite is therefore
about 76KB, roughly 19k tokens, per run, whose entire information content is "nothing is wrong".
Section 6's ritual runs the harnesses 4 to 8 times per fix across three `--only` chunks, so one bug
fix could spend 75k to 150k tokens printing OK, and the cost grew every time the suite grew (458
checks mid-July, 770 by 07-29). **This, not the item count, is why closures per weekly usage limit
fell 47, then 17, then 3: Darryl was rate-limited each week, sooner each time, for less returned.**
Fix: `--quiet` prints failures only plus a one-line check count. Same section re-measured at 213
bytes, a 97 per cent cut, check count preserved (79), and the failure path verified directly
(`ok(label, False)` still prints FAIL and appends to FAILS under `--quiet`). CI omits the flag on
purpose. `CLAUDE.md` sections 1 and 6 now mandate `--quiet` for all local runs. Note for whoever
adds the next section: the cost of a check is no longer zero, so prefer one assertion over ten.

**CH-9. DONE 2026-07-30, note moved to `BACKLOG_DONE.md`.** `tools/builder_api.py` exists,
`builder_build.py` is 1,082 lines, trap 1 is closed. `CLAUDE.md` trap 1 is now a historical note.

**CH-10. DONE 2026-08-14. Deliverable: [`CH10_DUPLICATED_FACTS.md`](CH10_DUPLICATED_FACTS.md).**
Filed as its own file rather than a table here because it runs to **97 rows**, the same reason
`BACKLOG_DONE.md` and `FR12_PLAN.md` were split out. Produced by five independent sweeps, one per
region, each required to verify the guard claim rather than assume it.

**The answer to the question CH-10 was filed to ask.** The bound is **97 duplicated facts: 6 derived,
18 asserted, 73 unguarded.** The 73 are not 73 bugs; **14 of them are already wrong today** and are
filed above as BUG-37 to BUG-50. The rest are correct and unprotected, which is the state every
closed bug in this project was in the day before it broke.

**The four costumes collapse into three mechanisms, and the audit adds a fourth that was not named
before.** (1) A hand-written list that new data does not join, 19 rows, all of them BUG-31 in a new
costume, all failing by *omission*, which is the mode no test can see. (2) A formula or vocabulary
implemented twice, 22 rows. (3) An assertion written against a copy rather than the artifact, 11 rows
and the most corrosive because each one looks like a guard: `builder_verify.ORACLE` is a hand
transcription of `template.html` labelled as its oracle, and `deploy.yml`'s GM canary words
transcribe files the repo deliberately excludes, so nobody can ever confirm they still appear.
(4) **NEW: an assertion that shares the implementation's silent default.** `check_fr36` compares
`FR20_CAT.get(slot, 3)` with `FR20_RANK.get(slot, 3)`; `check_sheet` recomputes a skill bonus with
the same `attrs.get(gov, 0)` fallback the sheet uses. **A check that shares the subject's escape
hatch cannot see the subject fall through it.** Two live defects are green right now because of it,
and it is why the FR-44 declare-an-effect gate can be satisfied by a *wrong* declaration:
`no_effect: situational` is accepted as readily on a rune that grants +1 Speed as on an inert one.

**The reassuring half, measured not assumed:** 27 of 28 documentation line-citations still resolve,
`tools/MAP.md` regenerates **byte-identical** (all 8 headers and ~390 line ranges correct), and every
count that sits behind an `expect()` is right: 90/90, 770, 231 options, the CH-11 byte measurements,
the `API_PY` sha. **The rot is exactly and only where nothing asserts.** That correlation is the
strongest argument the project has for the assert-it discipline.

**Ranked by rows closed per unit of work, do these in order. All six now carry IDs so they cannot be lost with this note:**

1. **CH-13. DONE 2026-08-14.** Delete `and e.get("grants")` at `catalog_verify.py:282, 334, 342, 353,
   362, 374`. Extends CH-5's discipline from ancestry traits to subclasses, disciplines, pact boons
   and talents. The CH-5 guard turns out to be **an ancestry-trait guard, not a ledger guard**: one
   category, 6 firings, catalog to ledger only. **What it actually cost, because the prediction was
   half right.** It fired on **C5** as predicted (Tanrielle's Paladin subclass carries no `grants`)
   but **not on BUG-39**, which lives in `class_features.yaml` and `catalog_verify` still never loads
   that file (see BUG-47), so BUG-39 stays open and unasserted. C5 needed a judgement call, not six
   characters: the catalog grant is `{disciplines: 1}`, a **pick-budget** key, and Tanrielle's ledger
   spends it on a sibling `{slot: discipline, pick: Magus}` entry at the same level, while Xanwyn
   spends the same-shaped `{runes: 2}` on `granted_runes` children. So the site now **splits the two
   kinds of key**: effect keys are compared outright (the engine reads effects off the ledger entry,
   so an omission is silently wrong), and a pick-budget key must be **accounted for** by children or
   by that many sibling entries at that level. **The shape that was tried first and rejected:** re-model
   Tanrielle's Magus as a grant-child with `granted_effects`. Derived stats came out identical, but
   `builder_verify` refused it, and it is right to. A canon ledger carrying `granted_effects` breaks
   the **PARTY_DERIVED guarantee** (the load-time-resync check at `builder_verify.py:2920`), which is
   a real invariant: `granted_effects` is the builder's derived half, so a hand-authored copy can
   silently disagree with the bake the Companion ships. Do not put it in a canon ledger.
2. **CH-14. Name the engine's derived-stat labels and spine-feature strings as constants in
   `build_engine.py`** and import them everywhere. Collapses five rows and removes the string-matching
   layer that four of the six confirmed-silent breakages travel through.
3. **BUG-38**, one line, and without it nothing else here reaches production anyway. **Fixed but NOT
   shipped in `fa15db4`, and the reason generalises.** The Claude sandbox writes into the OneDrive
   folder over the desktop bridge, and that bridge **refuses `.github/workflows/**` as protected**.
   Every other tracked file lands; a CI file silently does not, robocopy then reports `Copied 0` for
   `.github`, and the commit goes up looking complete. The line to add to `deploy.yml` `paths:`, after
   `builds/**`, is `- "tools/**"`. **CH-15 and BUG-50 are both CI-file items, so they will hit this
   too:** plan on hand-pasting them and confirming before calling the item shipped.
4. **CH-15. `make_map.py --check` plus one CI step.** `catalog_build.py` already has the pattern, and
   `BACKLOG_DONE.md:288` records that MAP.md staleness has only ever been caught by a human.
5. **BUG-50**, then assert against the generated Companion HTML. Almost every unguarded row in the
   companion region becomes checkable the moment something reads the output.
6. **FR-49. Add `hp`/`mp`/`sp` to the engine's equipment-effect keys.** Retires `DISPLAY_DELTAS` and closes
   a whole class of unmodellable item.

**BUG-37, DONE 2026-08-14, and it set a convention worth reusing.** `cap: 2` on `mp_to_damage` and
`gen_damage` became **`cap_stat: spend_limit`**, a third allowed `cap_stat` alongside `sp` and `mp`.
The Companion resolves it at render time, so the plumbing is: `build.py` bakes `spend_limit` from
`rep.derived` into `PARTY_DERIVED`, `template.html` copies it onto the character in the same list
that already copies `hp`/`mp`/`sp`, and `dmg.max` carries it. **The check had to change too, and
that is the real lesson:** `catalog_verify` asserted `cap == 2` **against the same literal it was
checking**, so it could only ever agree with the catalog. It now asserts the derivation instead
(`cap_stat == "spend_limit"` and **no** `cap` key), which is a claim the data can actually fail.
**Proved, not assumed:** the built Companion was opened in headless chromium and the MP-to-damage
row read `cap 2`, then `cap 3` once `spend_limit` was 3, with no console errors. The engine gives
`spend_limit` 2 at L4 and 3 at L5 for Tanrielle. Any future per-level cap should be a `cap_stat`.

**Two findings worth knowing even if the fixes wait.** `rules/ancestries.md:30-31` says Ancestry
Points arrive at L4 and **L7**, while every class table says L4 and **L8**; the rules contradict
themselves, nothing records that a choice was made, and the party is three levels from it. And the
`66/66 oracle` string is quoted in five live documents including a **definition of done in
`FR12_PLAN.md:104` that can never be satisfied**, because the harness has asserted 90 since
2026-07-16 and has never emitted 66.

**CH-11 (new 2026-07-30).** Split the baked rules corpus out of `builds/builder.html`.
**Measured at `a842471`, not estimated:** the file is 2,600,533 bytes and the
`const RULES_DATA = [...];` literal is 2,129,365 of them, **81.9 per cent** (slice from
`const RULES_DATA = ` to the next `];`, which is why this reads slightly higher than the
2,120,149 quoted in the 2026-07-30 review: that number excluded the declaration prefix).
Removing it leaves roughly 471KB, so every rebuild, diff, deploy and Chrome verification pass
gets about 5x cheaper. Pairs naturally with CH-9: that removed 96 per cent of
`builder_build.py`, this removes 82 per cent of its output.

**The trap: this is NOT a CH-9-shaped extraction.** `API_PY` was inert text being moved. `RULES_DATA`
is live FR-6 functionality, consumed at runtime by `RULE_CORPUS`, `DEFINED`, `CONDSECTIONS`, `_home`,
`_condTarget` and `openRulePanel` (`builder_build.py` L353-378).

**Offline use: answered by Darryl 2026-07-30. The builder is ALWAYS loaded from the published URL,
players never save it locally.** So a `fetch()` is legitimate and this is unblocked.

**Recommended shape, which is not one of the three obvious ones.** The naive split (fetch the whole
corpus on load, or lazily on first popup) has a catch: the corpus is needed at INITIAL RENDER, not
just when a popup opens, because `ruleTag` calls `_linkable` (L359, L377) to decide whether each
option even shows a `rule` chip, and that reads `DEFINED` and `RULE_CORPUS`. Lazy-on-first-popup
therefore makes every chip appear a beat late or forces a re-render. **Split it in two instead:**
bake only the TERM INDEX that `_linkable` needs (the `DEFINED` word set plus the multi-word keys
`_corpusHas` tests, tens of KB) and fetch section BODIES on demand when a popup actually opens.
Chips stay synchronous and correct, the 2MB of section HTML never loads for most sessions.

**Deploy is straightforward, because the published builder is built fresh in CI**, not served from
the committed file: `deploy.yml` L70 runs `builder_build.py --out dist/builder.html` and Pages
serves it beside `index.html` and `howto.html`. Adding a sibling artifact means emitting it into
`dist/` in that job and extending the guard block at L90-103 to assert it exists and is non-empty,
or the popup 404s in production while every local harness passes. **Note also deploy.yml L24: the
committed `builds/builder.html` is only a dev/harness convenience**, so 2.1MB of the repo's weight
is being carried purely for the harnesses.

**Harness impact, known up front so it is not discovered mid-split.** `check_fr6` in
`builder_verify.py` (section 17, from L1645) asserts the corpus is baked INTO `builder.html`, greps
the literal back out of the HTML, and reuses that same block as a node runtime harness. Three `ok()`
calls plus the node harness change shape with the payload. **Repoint them at the new artifact, do not
delete them**, or the split trades an 82 per cent size win for a hole in the FR-6 verification.
`rules_corpus.build_rules_data(REPO)` remains the single source either way, and the Companion already
shares it, so no third copy of the corpus appears.

**CH-12 (new 2026-08-14). Offline Pyodide shim for `builder_smoke.py`.** Until now the DOM smoke test
was CI-only, and the standing reason ("chromium will not launch in the sandbox, no sudo, no system
deps") is **out of date**. In the Claude cloud container chromium launches fine and Playwright is
preinstalled. What actually blocks it is narrower and was measured, not assumed: **CPython has full
egress, the BROWSER has none.** In headless chromium `example.com` gives `ERR_CONNECTION_RESET` and
`pypi.org` gives `ERR_CERT_AUTHORITY_INVALID`, while `curl` and `urllib` reach both. So the page's
`<script src="https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js">` (`builder_build.py` L104)
never loads and every journey dies on `wait_for_function` after 120s. **This is sandbox egress policy
for browser traffic, not a per-site allowlist anyone can approve**, and pointing chromium at the
container proxy (`--proxy-server=http://127.0.0.1:46545` plus `ignore_https_errors`) does not help.

**The fix, already proved end to end on 2026-08-14 against origin `2e4019c`: `builder_smoke.py --require`
PASSED in 2m46s, all five sections.** Intercept ONLY the `https://cdn.jsdelivr.net/pyodide/` prefix
with Playwright `page.route()` and fulfil from a disk cache populated by `urllib`. Six assets, ~10MB
of wasm, cached after the first run; Pyodide then boots in 6.5s. Install it in `SmokeSession.recycle()`
immediately after `self.browser.new_page()`.

**Three things to get right when landing it.** (1) The handler must `route.continue_()` on ANY fetch
failure, so CI keeps hitting the real CDN and its behaviour is unchanged; the shim must be a pure
fallback, never a new dependency. (2) Match on the URL prefix only, and `continue_()` everything else,
or the local http server that serves the repo gets intercepted too. (3) The cache key must include the
pyodide VERSION, so bumping the CDN URL in `builder_build.py` cannot silently serve stale wasm; simplest
is to hash the full URL, which the proved patch does.

**Why P1 despite being a harness-only change:** it moves layer 3 of the verification model from
CI-only to locally runnable, which is the layer that caught CH-5 Tier-2's CI blocker and the whole
BUG-31/32 family. **BUG-26 and FR-42 both touch the delicate FR-13a code that hard-authors Scaletrix's
spells**, and doing that with a browser check in the loop rather than a CI round trip is the difference
between one careful pass and several. Do CH-12 before them.

**CH-6. CI Verify takes ~3m** (asked and answered 2026-07-28, when Darryl asked whether Verify runs twice). Not urgent.

- **It does not run twice.** Every push touching `builds/**` or `rules/**` fires TWO DIFFERENT workflows, by design and true since both existed: **Verify** (`.github/workflows/verify.yml`, ~3m, runs the three harnesses) and **Deploy Companion** (`.github/workflows/deploy.yml`, ~30s, builds and publishes to Pages). Their `paths:` filters overlap on `builds/**` and `rules/**`. One checks correctness, the other ships. Worth writing down because the pair looks like a duplicate at a glance, and the run numbers differ (Verify #7 vs Deploy #92), which makes it look stranger still.
- **Where the ~3m goes:** only about a third is the test suite, the browser setup is the bulk. `playwright install --with-deps chromium` 50s, `builder_verify` 60s (45s local, runners are slower), `builder_smoke` (Pyodide in headless chromium) 40s, `pip install markdown pyyaml pypdf playwright` 25s, checkout + setup-python 10s, catalog_verify 5s, builder_build 5s. FR-46 added roughly 15s; Verify was already 2m30 to 3m on the three commits before it (2m30, 2m38, 3m01), so that section did not change the shape.
- **CH-5 Tier-2 moved it to 3m41 (Verify #11, 2026-07-29), which is the largest single jump so far.** Two causes, both real work rather than waste: the `(CH5b)` and `(RT)` additions cost about 7s of CPython, and the six new `builder_smoke.py` trait journeys each need a real page load with Pyodide warm, which is the expensive part. If this keeps climbing, the browser cache in item (1) below buys back 40s and the journeys are the thing to look at next, because they are per-trait-name by design and the catalog will keep growing.
- **The two things worth doing, when it starts to annoy:** (1) **cache the browser**, `~/.cache/ms-playwright` is cacheable with `actions/cache` and `playwright install` is pure setup cost paid on every run, worth about 40s; (2) **add a `paths` filter to the `pull_request` trigger**, since Verify filters paths on `push` but not on `pull_request`, so a PR touching only markdown still runs the full browser suite.
- **What NOT to do:** do not drop or conditionalise the smoke test to save time. It is the browser check. (**Parenthetical corrected 2026-08-14:** the old reason, "chromium will not launch in the Claude sandbox without system deps and there is no sudo", is no longer true. Chromium and Playwright are preinstalled in the cloud container; the real blocker was browser egress, and CH-12 fixes it.) and the ordering in verify.yml is already cheapest-signal-first on purpose.

---

## Parked / out of scope

- **Gear Tier A (done):** the engine already reads structured effect fields off free-text equipment entries (item `pd`/`ad`/`saves`, and `pdr`/`edr`/`mdr` for DR). This is how PD/AD/saves/DR reconcile today. No work needed; adding an essential item = add an entry with its effect fields.
- **Gear Tier C (out of scope):** full gear system, weapon attack-line derivation, attunement / magic-item slots, encumbrance, shopping. The "encode structure, not effects" line from ROADMAP.
- **Full-auto round-trip (v2):** players self-committing exports. Deliberately parked; one person commits for now.
- **Player-facing curated rules slice / separate container:** long horizon, the "last thing to build".
- **Community tool (rung 4):** dismissed on maintenance cost.

---

## Needs clarification

Initial triage complete (2026-07-16): all of Darryl's two lists plus the scattered scan items are deduped and logged. New items land here first, then move up once scoped.
