# DC20 Builder & Companion, Backlog

Single home for **app / tooling** work (the builder, the Companion, the engine). Living doc, updated as we triage. Started 2026-07-16.

**What lives elsewhere:** game-side rulings and player confirmations (attribute destinations, maneuver splits, rules calls) stay in `09_cogm_agenda_GM.md`, which is the canonical tracker for those. This file is only bugs / features / chores for the software. Where a software item genuinely waits on a player answer, it is marked Blocked with the person named.

**Legend.**

- Type: `bug` / `feature` / `chore`
- Area: `engine` (build_engine.py), `catalog` (builds/catalog), `data` (a ledger yaml), `builder` (builder_build.py, incl. the sheet), `companion` (companion-src), `repo`
- Priority: `P1` soon / high value or unblocks other work · `P2` should do · `P3` nice to have. **Provisional, a proper prioritisation pass is still pending.**
- Status: `ready` / `blocked` / `needs-clarification` / `parked` / `done`
- Convention: no em-dashes anywhere.

---

## At a glance

| ID | Title | Type | Area | Pri | Status |
|----|-------|------|------|-----|--------|
| BUG-1 | Xanwyn Elven fluency wrong (Fluent should be Limited) | bug | data | P2 | done (2026-07-16) |
| BUG-2 | Subclass/feature-granted languages not modelled as free (Deep Speech) | bug | engine+catalog+data | P1 | done (2026-07-16) |
| BUG-3 | Point-budget messaging: legal-spare vs over-spent, symmetric language verdict | bug | engine | P2 | done (2026-07-16) |
| BUG-4 | Character sheet overlay not mobile-responsive (iPhone) | bug | builder | P1 | done (2026-07-16, real-phone check pending) |
| BUG-5 | L3 attribute picker options show lower-case not capitalised | bug | builder | P3 | done (2026-07-16) |
| BUG-6 | Runt armour mis-modelled + staff Guard / Pact Armor AD+MDR / DR unpopulated | bug | engine+data | P1 | done (2026-07-16) |
| BUG-7 | Runt AD reads 12, RAW says 14 after the armour fix | bug | data | P2 | blocked (Phil / re-audit); now surfaced red by design |
| FR-1 | Sort the builder character picker alphabetically | feature | builder | P3 | done (2026-07-16) |
| FR-2 | Finish DR (PDR/EDR/MDR) for the rest of the party + rules references | feature | engine | P2 | ready |
| FR-3 | Level-up plans for all PCs (like Tan) | feature | builder+data | P2 | ready |
| FR-4 | Rename a char / file | feature | builder+data | P3 | needs-clarification |
| FR-5 | Unsaved-changes guard when switching character | feature | builder | P2 | done (2026-07-16) |
| FR-6 | Show rules text for a chosen trait/ability (link or hover) | feature | builder | P2 | ready |
| FR-7 | Refilter dropdowns to hide already-chosen options | feature | builder | P2 | done (2026-07-16, spell/maneuver/talent/spell_school; ancestry/pact_boon/discipline later) |
| FR-8 | Choice-bearing talents/subclasses need pickers/slots (epic) | feature | engine+catalog+builder | P1 | ready |
| FR-9 | Expand ancestry traits into slots (like maneuvers) | feature | builder | P2 | ready (Runt data resolved) |
| FR-10 | Echo next-level preview text into the level's section header | feature | builder | P3 | ready |
| FR-11 | Gear catalog / picker (gear Tier B) | feature | engine+catalog+builder | P3 | parked |
| FR-12 | Add full DC20 class + ancestry data coverage | feature | engine+catalog+builder | P2 | ready (epic) |
| FR-13 | Live spell & maneuver legality (school/type filtering) | feature | engine+builder | P3 | ready |
| FR-14 | Recent Files list in the picker + auto-add on deeplink | feature | builder | P2 | done (2026-07-16, incl. Level A) |
| CH-1 | Re-audit all six ledgers' languages/skills/trades vs paper sheets | chore | data | P2 | ready |
| CH-2 | Standardise Elven / Elvish / Elvan spelling | chore | data+catalog | P3 | ready |
| CH-3 | Drop the vestigial tracked root index.html | chore | repo | P3 | ready |

---

## Prioritisation (locked 2026-07-16)

Worked top to bottom. Wave 1 is designed to verify in a single regression cycle.

- **Wave 1, correctness + cheap wins:** BUG-1, BUG-2, BUG-6 (and log BUG-7), BUG-5, plus applying Runt's now-known ancestry itemisation to the ledger. Optionally CH-1 alongside (it validates these data fixes).
- **Wave 2, high-impact UX:** BUG-4, FR-14 (with Level A), FR-5, FR-1, FR-7, BUG-3.
- **Wave 3, bigger features:** FR-3, FR-6, FR-10, FR-2.
- **Wave 4, epics (interdependent):** FR-8, then FR-12 (needs FR-7 + picker search), with FR-13 alongside FR-12.
- **Low / when convenient:** CH-2, CH-3, FR-4 (needs scoping), FR-11 (parked).

**Shipped 2026-07-16 (pushed, head `e26963b` then `caca1d0`):** all of Wave 1 (BUG-1, BUG-2, BUG-5, BUG-6 + Runt L1 ancestry itemisation) plus BUG-4 (mobile sheet); BUG-7 now surfaces as a red MISMATCH by design (pending Phil). Baseline is now **89/90** (the 1 delta is BUG-7). Stray `runt_old.yaml` removed from the repo; `BACKLOG.md` added. Companion `template.html` sknotes aligned to the ledger fixes (Xanwyn Elven limited; Runt Deep Speech Fluent Eldritch grant).

**Wave 2 remainder SHIPPED + PUSHED (head `253c30e`) + LIVE-VERIFIED 2026-07-16:** FR-14 (Recent Files in the picker, per-device localStorage, deeplink `?char=` auto-adds; plus Level A: the baked party is no longer listed in the default dropdown but still resolves by deeplink), FR-1 (new-from-scratch list sorted alphabetically; the party list is delisted by Level A so the alpha-sort applies there and recents stay recency-ordered by design), FR-5 (unsaved-changes confirm-guard when switching character in the dropdown; Cancel reverts the selection), FR-7 (pickers hide options already chosen elsewhere for spell / maneuver / talent / spell_school; ancestry_trait / pact_boon / discipline left to a later pass because of their budget / choice-count machinery and existing harness expectations), BUG-3 (symmetric, clearer budget verdicts: balanced / "N SPARE (legal)" / OVER-SPENT on all three of skills/trades/languages; the language line is no longer asymmetric, and "UNDER-SPENT" is retired so a legal lumpy-conversion spare no longer reads as a fault). Harness section (12) added (238 OK; catalog_verify still 89/90). Files: `tools/build_engine.py`, `tools/builder_build.py`, `tools/builder_verify.py`, regenerated `builds/builder.html`, and this `BACKLOG.md`. Remaining in the plan: Wave 3 (FR-3, FR-6, FR-10, FR-2), then the Wave 4 epics.

**Demo context (2026-07-16).** Next session is tomorrow night. Nothing here is required for the game, it runs fine as-is: zero must-do, the session is not blocked whatever we do. Everything working by then is an "above and beyond" demo bonus, and players (Phil especially, on Runt) will likely use the builder live on their phones if enough works. So for the demo the highest-leverage subset is the mobile sheet (BUG-4) and Runt's correctness (BUG-2, BUG-6, the ancestry itemisation), since those are what the players would actually touch; FR-14 Level A makes the picker demo cleaner. Anything meant to be live for the demo must be synced + committed + pushed by Darryl (or shown from a local build).

---

## Bugs

**BUG-1. Xanwyn Elven fluency.** Sheet shows Elven and Fey each at 1 dot (Limited); the ledger records Elven as Fluent (cost 2). Fix `xanwyn.yaml`: Elven -> Limited, cost 1. Then Xanwyn spends 2 LP = the 2 free, balanced, no conversion, and the spurious under-spent flag clears. Data-only, same-total error, which is why no budget check caught it.

**BUG-2. Granted languages not free.** Runt is Warlock / Eldritch, and Eldritch grants Fluent Deep Speech for free (classes.md l.3432). The ledger records Deep Speech as a bought Limited language (cost 1). That phantom 1 LP forces a TP->LP conversion, which is the real cause of Runt's "Trade points over-spent" and the "Language under-spent" noise. Fix: add a language grant (Deep Speech, Fluent) to Eldritch in `catalog/warlock.yaml`; teach the engine to treat granted languages as 0 cost; fix `runt.yaml` (Deep Speech Fluent, granted, cost 0). This retires the long-standing whitelisted "Runt trade over-spend" (ROADMAP / 09) as actually fixed, not suppressed. RAW-confirmed, not blocked. Overlaps FR-8.

**BUG-3. Point-budget messaging.** The "under-spent" verdicts are mostly not errors: conversions happen in whole 2-for-1 points, so an odd requirement leaves a legal spare (Xanwyn's 1 spare TP after converting 2 SP for a 3-TP need). But the wording reads like a fault, and the language line is asymmetric (only ever prints UNDER-SPENT or nothing, never balanced/over). Make the language verdict symmetric and clearly distinguish "you have a legal spare point" from "illegal / over-spent". Conversion rates themselves are correct (1 SP -> 2 TP, 1 TP -> 2 LP, character-creation.md l.90/97).

**BUG-4. Sheet overlay not mobile-responsive.** On a phone the character-sheet overlay's fixed 3-column grid (`.sh-cols` 196px+214px+1fr inside a 794px `.sh-paper`, builder_build.py l.1430) overflows and the columns overlap; the 55%-opaque backdrop lets the builder page show through behind. The `@media (max-width:640px)` block (l.1403) only restyles the builder UI, not the sheet. Fix: add narrow-width rules to stack `.sh-cols` to one column and let `.sh-paper` size fluidly, same pattern the builder already uses. Verify on a real iPhone (Phil hit this).

**BUG-5. L3 attribute picker casing.** The attribute-choice picker lists options in lower case (might, agility, ...) because that is how they are stored in the ledger. Capitalise them for display only.

**BUG-6. Runt armour / defences / DR.** Runt's armour is confirmed (magic-item audit): magical Ancestral Dwarf Armor = Defensive Heavy (+1 PD, +1 AD, PDR Half) with Rigid and Bulky stripped (the 2 Magical Power cost), so no Speed -1 and no DisADV Agility. The ledger currently mis-models it as "Deflecting Heavy +2 PD / +0 AD" with Speed/Agility penalties. Compensating errors keep PD correct (old: armour +2 / staff +0; correct: armour +1 / staff Guard +1; both sum to +2, so unbuffed PD stays 15, sheet 17 = 15 + Primal Hide daily buff). Fix set: correct the armour entry (pd 1 / ad 1 / pdr half, drop the Deflecting/Speed/DisADV note); model the wielded Quarterstaff's Guard +1 PD; apply Pact Armor's RAW +1 AD and MDR (catalog marks it "contextual, not a grant", so it is currently unmodelled, warlock.yaml l.90); populate DR = PDR Half + MDR Half, EDR none. Then run the engine to verify. Not blocked. Surfaces BUG-7.

**BUG-7. Runt AD 12 vs 14.** Once the armour is fixed, RAW AD = 12 base + armour 1 + Pact Armor 1 = 14, but the sheet / expected block records 12. Either the sheet under-counts (should be 14) or something offsets it. Confirm with Phil, or catch via CH-1. Replaces the now-closed "PD 15 vs 17" question.

---

## Features

**FR-1. Sort character picker alphabetically.** The Companion party chips already sort; the builder's picker may not. Minor.

**FR-2. Finish DR.** The engine's DR mechanism is done and plumbed (collects `pdr`/`edr`/`mdr` off equipment, value int or "half"). Runt's values are now known and handled in BUG-6. Remaining: work out the other PCs' DR (most likely none for the non-heavy-armour PCs) and show the rules reference alongside each DR entry.

**FR-3. Level-up plans for all PCs.** Extend Tan's L5/L6 plan support to the others. Needs: an "Add Planned Level" button (and Undo must not vanish when used), and the ledger's `skills` section folded into the per-level blocks rather than sitting separately, so planned levels can carry their own skill picks. (Merges the two level-up-plan entries from Darryl's list.)

**FR-4. Rename a char / file.** Needs a scoping decision first. Display-name rename is trivial (builder already separates `character` from the stable `handle`). Handle/file rename is the coordinated one: the id appears in the companion-key -> builder-handle map, the yaml filename, PARTY_LEDGERS/CHARS, localStorage keys, and `?char=` deep links. Decide display-only vs handle/file vs both.

**FR-5. Unsaved-changes guard.** If edits are unsaved and a different character is picked from the dropdown, warn that changes will be discarded and offer to save/export first.

**FR-6. Rules text for a chosen option.** Some way to see the rule for a chosen trait/ability/spell (link to, or hover over). The Companion already auto-links bold rules terms (linkifyTerms); reuse that idea in the builder.

**FR-7. Refilter dropdowns.** Remove already-chosen items from a dropdown's options so the same one cannot be picked twice.

**FR-8. Choice-bearing talents/subclasses need pickers (epic).** Talents and subclasses that grant a set of choices should present real slots/pickers, with the granted items flowing from the choice rather than being baked into a name. Examples: Rune Knight subclass (choose 2 runes); Sorcerer L4 talent (choose 2 metamagic); Sorcerer L2 talent (choose 2 spells); Warlock Eldritch subclass (grants Deep Speech + a Psychic-only spell); Martial Expansion (maneuver slots); Pact Armor / Pact Weapon (grant Defensive / Offensive maneuvers, currently named in text, should be removed from the name and granted). Pact Weapon/Armor is partly done (granted_maneuvers captured structurally); the remove-from-name step and the general pattern remain. Overlaps BUG-2 (Eldritch language grant). Large: treat as an epic and split when we plan it.

**FR-9. Expand ancestry traits into slots.** Same slot/expand treatment the maneuvers got (confirmed). Note it is more involved than maneuvers: ancestry traits are budget-constrained, each has a variable cost (0 / 1 / 2, or a negative drawback that refunds points) and some have prerequisites, so the generated slots must sum to the L1 budget (5 points, +2 at later levels), not just fill a fixed count. This cost/budget machinery is exactly why ancestry_trait was excluded from the original maneuver reconcile.

Runt's data is now resolved (Darryl supplied Runt's L1 sheet, 2026-07-16). His 5 Ancestry Points itemise fully from the Giantborn (ogre) list: Powerful Build (2), Brute (1), Tough (1), Titanic Toss (1), Mighty Hurl (1), Unyielding Movement (0), Heavy Riser (-1) = 5. All seven are already in the catalog with these exact costs (ancestries.yaml Giantborn l.84 to 98), so no catalog work is needed, only a `runt.yaml` edit: replace the "L1 traits not itemised (remainder)" placeholder and drop the inferred flag on Tough, listing the seven traits explicitly. Tough's source tag is correct (it is in the Giantborn list l.86 as well as Dwarf l.54), so the earlier source-slip worry is void. This closes the ROADMAP / 09 "Runt L1 ancestry itemisation, ASK PHIL" open item. Bonus: Powerful Build / Brute / Titanic Toss / Mighty Hurl are the mechanical basis of Runt's grapple-and-throw build in file 10, now structured.

**FR-10. Level preview in the section header.** The sidebar shows a text strip previewing what you get at the next level-up (next to the level-up button). Echo that text into the collapsible section header for the level.

**FR-11. Gear catalog / picker (Tier B).** A curated list of the party's real items (weapons, armour, shields, focuses) so items are picked from a dropdown with properties auto-applied, instead of hand-typing effect fields. Pure convenience; would cut hand-entry transcription errors like the language ones. Parked for now; not required for any reconciliation (gear effects already work, see Parked note on Tier A/C).

**FR-12. Add full DC20 class + ancestry data coverage.** Extend the catalog beyond the party's six classes to all 13 (and remaining ancestries), so the party can build any character, including on mobile. Runtime/size is NOT the blocker: the builder runs the Python engine via Pyodide (a multi-megabyte WASM runtime from CDN), which dominates load and cold-start regardless of catalog size. The full catalog is roughly 100 to 150 KB of YAML (names/costs/prereqs/tags, not rule text), taking builder.html from ~262 KB to ~350 to 400 KB, invisible next to Pyodide, and the engine only ever replays the one character being built, so validation does not slow down. The real costs are (a) human: each class needs a catalog file AND a hardcoded level-progression table in `build_engine.py`, plus data entry, plus the 0.11 beta refresh treadmill; and (b) mobile UX: pickers listing hundreds of options need search/typeahead and FR-7 filtering to stay usable. "Only load classes in use" lazy-loading was considered and rejected, it would shave ~100 KB off a multi-MB load, so buys nothing for performance. Large: treat as an epic. Depends on FR-7 (and ideally a picker search box) for the mobile experience, and on FR-13 to stay trustworthy once pickers span the full catalog.

**FR-13. Live spell & maneuver legality.** Enforce that each chosen spell/maneuver is actually accessible to the character: a spell from one of their chosen schools/sources (plus tag grants like Eldritch's Psychic access), and a maneuver of the right type for its slot (Pact Armor's slots need Defensive maneuvers), rather than only counting them and checking they are real catalog entries. Current state: the offline harness already validates this for the six known builds (catalog_verify.py section 2, per-class access models), so there is no correctness risk today. The gap is in the live engine the builder runs (build_engine.py), which does counts and budgets but no school/type legality (its docstring lists this as "not yet", l.15). Low urgency now (known, hand-verified builds), but it becomes important with FR-8 (choice pickers) and especially FR-12 (open pickers over the full catalog): the builder should then offer only legal options and flag illegal picks. Folds into the FR-8 / FR-12 picker work. Bundled minor: per-skill die bonuses (the engine derives skill bonus as attribute + flat mastery, and models no skill-specific die mechanics), low priority.

**FR-14. Recent Files + deeplink auto-add.** A "Recent Files" list at the top of the character picker, persisted in localStorage (already used for the resume/in-progress state, l.1736), auto-adding a character when the builder is opened via a Companion deeplink (`?char=<handle>`). Straightforward, self-contained, and it pairs with the level-up-night flow (each player deeplinks from the Companion, their character lands in their own recent list). Do this part regardless.

Folded-in design decision (Darryl's motivation): use it to stop showing the hard-coded party in the default dropdown, so outsiders given the builder do not see our characters. Key finding from the code: on the live site the party ledgers are base64-**baked** into builder.html and that bake is what serves (the deploy publishes only builder/index/howto html, so the fetch-first path 404s and falls back to the bake). Two levels:
- **Level A (minimal, no deploy change):** stop *listing* the party in the default dropdown but keep them baked, so deeplinks still resolve (a `?char=` lookup hits the baked blob directly, independent of the dropdown). Outsiders see an empty picker (New / Load / Recent); the party arrives via deeplink and auto-populates recent files. Declutter + soft privacy, deeplinks and robustness preserved.
- **Level B (stronger, needs a deploy change):** stop baking the party ledgers and publish the yaml to `dist/` so the page ships with no embedded party data and deeplinks fetch it. Only this actually removes the party from the public page source (today anyone with the builder URL can read the full party builds out of the baked blob). Tradeoff: exercises the fetch path in production (currently dev-only), and the yaml is still fetchable at known URLs, so it is not-embedded / not-shown, not access-controlled. Party data is table-facing (no GM secrets), so soft privacy is acceptable.

Caveat: Recent Files is a convenience layer (per-device, user-clearable, transient), so it must not become the only route to a party character. The canonical ledger must still exist and resolve (baked in Level A, published in Level B); the hard-coded *source* is not redundant, it just need not be *shown*. Recommendation: ship the Recent Files feature + Level A; treat Level B as an optional follow-on.

---

## Chores

**CH-1. Sheet re-audit.** Re-check all six ledgers' languages / skills / trades against the paper sheets. Justified: a same-total swap (Xanwyn) and a granted-language mis-model (Runt) both slipped through undetected, so other silent faithfulness errors are plausible. Feeds BUG-7.

**CH-2. Standardise Elven spelling.** "Elvan" (Xanwyn ledger + ancestry catalog key + L4 report + Companion), "Elven" (correct), "Elvish" (Tan). No hard data-matching issue today because language values allow free text; the only exact-match dependency is the ancestry catalog key, so any rename there must change catalog and ledger together. Cosmetic, low priority.

**CH-3. Vestigial root index.html.** The repo tracks a root `index.html` the live site does not serve (the deploy Action rebuilds `dist/index.html` from the template). Harmless drift; `git rm --cached index.html` would drop it. (Kept 2026-07-16.)

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
