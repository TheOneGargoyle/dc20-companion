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
| CH-5 | Burn down the option-coverage todo list (18 distinct options with a real unmodelled effect) | chore | catalog+engine+builder | P2 | IN PROGRESS (Tier-1 done 2026-07-27, 7 of 18 closed, 11 distinct left, see note) |
| CH-6 | CI Verify takes ~3m; cache the Playwright browser download and add a `paths` filter to the `pull_request` trigger | chore | repo | P3 | ready (2026-07-28, not urgent, see note) |
| CH-7 | Assert the `rules/classes.md` source repairs so a PDF re-extraction cannot silently revert them | chore | repo+companion | P3 | ready (new 2026-07-28, see note) |
| FR-47 | Extend the FR-44 coverage walker to BARE-STRING option lists (subclasses today), so a whole pickable surface cannot sit outside the ledger | feature | catalog+repo | P2 | ready (split out of BUG-35 2026-07-27, see note) |
| FR-48 | A SCRATCH build has no base Combat Training: the class's own training is not catalog data, so the sheet shows only what options granted | feature | catalog+builder | P2 | ready (surfaced 2026-07-28 during BUG-34, see note) |
| CH-4 | Fill `class_features.yaml` L5-L10 (L1-L4 done) so no level falls back to the generic "Class Feature" label | chore | catalog | P3 | ready (new 2026-07-27, pure data, see note) |
| FR-11 | Gear catalog / picker (gear Tier B) | feature | engine+catalog+builder | P3 | parked |
| FR-26 | Stackable conditions (bleed/stunned) as counts not toggles | feature | companion | P3 | parked |

**Push status (confirmed 2026-07-28 from the Actions run list).** All previously "awaiting push" items are on origin and CI-green on both workflows: **FR-45** (`5f2006d`, `6a3b2bb`), **BUG-35** (`a52a707`), **BUG-34** (`b9e2071`, `1e15009`), **FR-46** (`e044d41`), and the FR-46 mutation suite plus CH-6 (`d3a9444`). Their notes are in `BACKLOG_DONE.md`. **Origin is `d3a9444`.**

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

**The remaining 11, and what FR-46's round-trip established about them on its first run.** This changes the shape of the work:

- **Two already behave correctly, by name-match, so that item is a refactor with no player-visible change, not a fix.** `Speed Increase` (+1) and `Short-Legged` (-1) both move Move Speed today because `build_engine.py` l.265-268 matches them by NAME; the Human `Attribute Increase` trait is the same, offered as decorated per-attribute variants (`Attribute Increase (charisma)`) and name-matched at l.176. The data is inert, the player-visible behaviour is not. Materially lower risk than this entry originally implied, and the round-trip now asserts those three keep moving the right stat, so making them data-driven cannot silently change what a player sees. Registries `RT_NAME_MATCHED` / `RT_VARIANT_MATCHED`; each entry retires with the refactor.
- **Eight are genuinely inert, and confirmed so:** `Attribute Decrease` (the sub-choice one), the three fixed-target Beastborn ones (`Charisma / Intelligence / Might Attribute Decrease`), `Natural Armor`, `Fiendish Aura`, `Skill Expertise`, `Trade Expertise`.
- **The engine slice (6 options).** Retire the three name-matches into `grants: {speed: +/-1}` / `{attribute_points: +/-1}` and delete the special cases, and **add the per-attribute grant key while in there**: there is none today (the engine has no handler at all for a decrease), which is why the four attribute decreases are not "one line of data each" as the original entry assumed. This is the pre-FR-12.0 pattern the class-spine refactor retired everywhere else. **Touches the engine, so check PARTY_DERIVED and rebuild the Companion if it moves. Tanrielle has both Speed Increase and Attribute Increase, so it must land as a single atomic change or her Move Speed 6 drops to 5.**
- **Allocator-coupled (2):** `Skill Expertise` / `Trade Expertise`, which raise the cap and level of a CHOSEN skill/trade via `limit_raise`. Tracked as BUG-20 and staying deferred.
- **Needs a call before it can be data (2):** `Fiendish Aura` learns the Sorcery Cantrip, so does a cantrip count against Spells known? `Natural Armor` gives unarmoured PDR and the engine's `dr` plumbing is equipment-only today (its `grants_unarmored` half is solved by the Tier-1 trait work; only the unarmoured-PDR plumbing remains).
- **Sub-choice targets (2):** `Attribute Increase` / `Attribute Decrease` also need a target picker, the same shape as FR-42 and BUG-26, so do them in that slice.

Canon is unaffected by all of them: `catalog_verify` asserts that no walked ledger depends on a todo option, with Tanrielle's three documented exceptions. These are scratch-mode-only wrong answers today, which is exactly why they arrived as player reports instead of harness failures. **The harness sections assert the DERIVED STAT, not the catalog row:** `(CH5)` builds a scratch character per ancestry, picks the trait and checks the number moved by the right amount, including the negative cases (a Dwarf wearing Half Plate must NOT get Thick-Skinned's +1 AD, and the row's note must say so). That shape is deliberate: every bug in this family was "the data says it, nothing applies it", so a check that read the catalog would have passed throughout.

**CH-7 (new 2026-07-28).** `rules/classes.md` is NOT a clean PDF extraction. It was hand-repaired at source on 2026-07-05: the 13 wide class-progression tables rebuilt from `tables.md` and inlined as `####` sub-sections inside their own class, two mid-sentence `### Shields` promotions rejoined, a garbled duplicate `### Barbarian` merged away, and `### Subclasses` x13 demoted to `#### <Class> Subclasses`. The build-time strip in `companion-src/build.py` was then REMOVED as superseded, so there is no runtime safety net either. **Re-extracting the file silently reverts all of it and nothing catches it**: the rules section count is printed by the build, never asserted, and it has already drifted (README says 216, the build now reports 191 merged to 172, so the number moving is not even a signal). This is trap 2 in a different costume, a hand-repair with no assertion guarding it. Fix: assert in a harness that all 13 inlined `####` class tables are present and that no `### Subclasses` heading survives, which converts a silent revert into a failure. Full repair recipe is in the 2026-07-05 entry of `logs/2026-07-early.md`, grep for `classes.md repaired at the source`. While in there, correct the README's stale 216.

**CH-6. CI Verify takes ~3m** (asked and answered 2026-07-28, when Darryl asked whether Verify runs twice). Not urgent.

- **It does not run twice.** Every push touching `builds/**` or `rules/**` fires TWO DIFFERENT workflows, by design and true since both existed: **Verify** (`.github/workflows/verify.yml`, ~3m, runs the three harnesses) and **Deploy Companion** (`.github/workflows/deploy.yml`, ~30s, builds and publishes to Pages). Their `paths:` filters overlap on `builds/**` and `rules/**`. One checks correctness, the other ships. Worth writing down because the pair looks like a duplicate at a glance, and the run numbers differ (Verify #7 vs Deploy #92), which makes it look stranger still.
- **Where the ~3m goes:** only about a third is the test suite, the browser setup is the bulk. `playwright install --with-deps chromium` 50s, `builder_verify` 60s (45s local, runners are slower), `builder_smoke` (Pyodide in headless chromium) 40s, `pip install markdown pyyaml pypdf playwright` 25s, checkout + setup-python 10s, catalog_verify 5s, builder_build 5s. FR-46 added roughly 15s; Verify was already 2m30 to 3m on the three commits before it (2m30, 2m38, 3m01), so that section did not change the shape.
- **The two things worth doing, when it starts to annoy:** (1) **cache the browser**, `~/.cache/ms-playwright` is cacheable with `actions/cache` and `playwright install` is pure setup cost paid on every run, worth about 40s; (2) **add a `paths` filter to the `pull_request` trigger**, since Verify filters paths on `push` but not on `pull_request`, so a PR touching only markdown still runs the full browser suite.
- **What NOT to do:** do not drop or conditionalise the smoke test to save time. CI is the only place it runs at all (chromium will not launch in the Claude sandbox without system deps and there is no sudo), so it is the browser check, and the ordering in verify.yml is already cheapest-signal-first on purpose.

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
