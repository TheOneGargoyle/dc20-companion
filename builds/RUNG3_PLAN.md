# Rung 3 plan: the character builder

**Audience: table-facing (tooling).** Drafted and revised 2026-07-10 in the rung-3 design thread, off the back of `builds/ROADMAP.md`. This is a working plan for discussion, not a locked spec. It records the decisions taken in that thread, the architecture we landed on, an honest read on how doable each piece is, and the questions still open. Revision folded in: Pyodide as the one-engine approach (section 4), commit workflow (section 5), the correctness oracle and reverse-engineered UI (section 6), and the decisions on hosting, rule text, party-by-id and the two-machine question (section 8).

---

## 1. What rung 3 is

A character builder / respeccer for our six PCs. It does three jobs, in priority order:

1. **Level-up night at the table.** Walk a PC forward one level, making the new choices, with the numbers validated live.
2. **What-if respecs.** Re-open a past decision, change it, see the knock-on effects, without touching canon until you deliberately save.
3. **New character from scratch.** Full chargen for one of our six classes. Lowest frequency, so it rides in on the same machinery rather than driving the design.

Jobs 1 and 2 are the same UI: a level-up appends the next decision, a respec edits an existing one. Build that editing surface once and both fall out. Job 3 is the same surface again, started from an empty ledger.

---

## 2. The decisions we locked this thread

- **Purpose:** level-up and respec together (job 3 comes along for free-ish).
- **Validation style:** validate, don't enumerate. Free-ish entry plus short pickers only where the option list is naturally tiny (ancestry traits, path choices). The engine's rules reject anything illegal or over budget. This keeps the option catalog small, which is the whole cost driver.
- **Architecture:** a clean split into a light read-only reference app and a heavy write-capable authoring tool. See section 3.
- **One canonical character format:** the builder reads and writes the **same ledger YAML** the engine already replays (`builds/*.yaml`, schema in `SCHEMA.md`). No parallel character format, ever. This is the rule that keeps us from having two disagreeing versions of who Tanrielle is.
- **One engine, run in the browser:** rather than maintain a Python engine and a duplicate JavaScript one, run the real `build_engine.py` client-side via Pyodide (Python compiled to WebAssembly). Single source of truth for both data and logic. A hand-written JS mirror is the fallback if Pyodide proves fiddly. See section 4.
- **Party membership by id:** the Companion builds the party from a curated list of character ids, not from whatever files happen to exist. Respecs and archived versions therefore never create duplicate party members. See section 8.
- **Data-driven, never hardcoded:** classes, ancestries and options are catalog data rows, not special-cased code. This is what keeps the door open to more classes later without an engine rewrite. See section 9.
- **Same GitHub repo** as the Companion; **show rule text** in the builder if it fits (revisit only if it becomes a burden). See section 8.
- **Round-trip:** semi-automatic now, fully-automatic parked as a later treat. Exactly one person (you) commits; players never touch git. See section 5.

---

## 3. The architecture: three pieces

### Piece A. The Companion stays exactly what it is

Static HTML, mobile-first, lightweight, data baked in at build time, no big scripts, no big payloads. Nothing about the builder is allowed to make the Companion heavier. Players keep the same bookmarked URL. The Companion is read-only: it shows the party, it never edits it.

### Piece B. Automated rebuild (a freebie worth grabbing on its own)

Right now, publishing the Companion is a manual ritual (`build.py` plus a personal access token out of `companion-src/`). Replace that with a **GitHub Action**: when updated character data lands in the repo, the Action runs `build.py` and redeploys the Pages site. No more manual publish step. This is worth doing whether or not the builder ever gets built, because it removes an existing chore.

### Piece C. The builder (the new thing)

A separate, PC-first, browser-based page (no install). Heavier by design, because it only loads when you sit down to build, on a real screen. It can:

- start a fresh character, or load an existing ledger by a handle (for example `?char=tanrielle`),
- expose every past decision and let you change it, or append the next level,
- validate live as you go (budgets, limits, legality),
- export the updated ledger YAML at the end.

The Companion links out to the builder passing the character handle. The builder does its work and produces a new ledger file. That file, once committed, triggers Piece B, which rebuilds the Companion with the updated party.

### How the data flows

```
Companion (phone, read-only)
   |  deep link  ?char=tanrielle
   v
Builder (PC, read/write)  <-- reads builds/tanrielle.yaml
   |  export updated YAML
   v
builds/tanrielle.yaml  (the one canonical char file)
   |  commit
   v
GitHub Action runs build.py
   v
Companion redeploys, party now updated
```

---

## 4. Where the validation logic lives (resolved: one engine, in the browser)

The engine that knows our budgets and legality (`tools/build_engine.py`) is **Python**, and a browser cannot run Python directly. The naive fix is to write the same validation logic a second time in JavaScript so it runs in the browser: two engines doing the identical job in two runtimes, kept in sync forever. That duplication is the thing to avoid.

**The resolution is to run the actual Python engine inside the browser via Pyodide** (CPython compiled to WebAssembly). The builder page loads `build_engine.py` and runs it client-side. That gives us:

- **One source of truth for both data and logic.** No second engine, no drift, no reconciling two codebases when the beta bumps.
- **Instant feedback with no server.** The engine runs in the page as the player clicks; nothing round-trips to a backend.
- **The engine we already trust.** It is the same code that passes 66/66 checks against the real sheets, running unchanged.

The cost is a several-MB download the first time the builder page loads (Pyodide plus PyYAML), and a second or two of startup. That is why this belongs only on the **PC builder page**, never in the phone Companion: heavy-on-a-PC-that-caches-it is fine; heavy-on-a-phone is not. This is precisely why the reference/builder split matters.

**Data still gets separated from code.** The v0.10.5 specifics (class tables, ancestry costs, spell-school and maneuver lists, defense formulas) live as a **catalog** the engine reads, extracted once from `rules/*.md` and the engine's existing `CLASS_TABLES`. When 0.11 drops, you refresh the catalog and retrigger the rebuild; you do not rewrite logic. So "update only the data on a version bump" still holds, and now there is only ever one engine consuming that data.

**Fallback:** if Pyodide proves fiddly in practice (load weight, packaging), the backup is the hand-written JavaScript mirror reading the same catalog, with the Python engine kept as the offline CI authority. We would only fall back if Pyodide genuinely misbehaves.

Either way everything stays on free static hosting (GitHub Pages). No server, no database, no browser-held secrets.

---

## 5. The round-trip: semi-automatic now, full-automatic later

The tempting version is: click Save in the builder, it commits the file, triggers the rebuild, and bounces you back to the freshly-updated Companion, all automatically. That last mile is where the cost hides. Each leg (save-back by handle, auto-triggering the rebuild) needs an authenticated commit, and a static browser page cannot safely hold a write token. Making it fully automatic therefore forces either a standing server or a GitHub OAuth flow: real infrastructure to pay for and maintain, for a workflow that fires maybe a dozen times a year.

So the plan is **semi-automatic**:

- Companion deep-links to the builder with the char handle. (Trivial, no backend.)
- Builder loads, you edit, it **exports** the updated YAML (a download button, or a copy box). (Trivial.)
- That file lands in the repo, the Action rebuilds, next load shows the change. (The one manual step: committing the file.)

**Who commits, and no, players never touch git.** In this semi-automatic plan, exactly one person (you) has write access to the repo and lands the exported file. That is either a git client or, simpler, the GitHub website's edit-file button: no git command line, no commands to learn. This fits the real workflow of level-up night: on your laptop, players tell you their picks, you drive the builder, you export and commit. The players interact with a URL and nothing else. Self-service saving *by players* is the only thing that would ever require someone else to be involved in the commit, and that is the parked v2 (a serverless function or a GitHub OAuth flow hiding the commit behind a button). It is not a prerequisite for anything.

We keep every piece of the vision except the automatic hand-back. If the manual commit later proves genuinely annoying, that is the moment to spend that v2 effort, deliberately, not up front.

### The workflow this unlocks: players self-serve

Because the builder is a public, stateless web page and the only gated step is landing the file in the repo, **every player can have the builder URL and do everything themselves.** A player opens the page, builds or respecs their character as much as they like, hits Download, and sends you the resulting YAML (Discord, email, whatever). You drop it into the git-synced folder and commit, and the Companion updates. Players get the entire builder and never touch git; the one thing only you do is the commit. This is now arguably the **primary** workflow, ahead of "you drive it on your laptop on level-up night," and it needs zero extra infrastructure over what is already planned.

Two wrinkles, neither a dealbreaker:

- **Not losing in-progress work.** If a player closes the tab mid-build they would lose it unless we persist. Easy answers: they keep their own downloaded YAML and re-load it next time (the builder loads YAML anyway), and/or the page remembers their working character in the browser's local storage between visits. (Local storage is fine here because this is a real hosted page, not a Claude artifact.)
- **Trusting a received file.** A player could hand-edit the YAML or send something malformed. You do not have to eyeball it: load their file back into your own builder (or run the engine over it) before committing, and an illegal build is caught before it reaches canon. A bad file cannot quietly corrupt the party.

---

## 6. How doable is each piece (honest read)

- **Piece A (Companion unchanged):** zero new work. It already exists and stays as-is.
- **Piece B (GitHub Action rebuild):** **low.** Standard CI. One workflow file that runs `build.py` on push and deploys Pages. Main fiddle is Pages deploy permissions and retiring the manual token. Call it an afternoon of tinkering.
- **The catalog:** **medium.** This is the real content work: scripting extraction of costs, prerequisites and tables from `rules/*.md` plus the engine's `CLASS_TABLES`. Bounded to six classes, and validate-don't-enumerate keeps it small. A lot of it already exists inside the engine, so this is more "reshape and export" than "author from scratch." See the correctness note below.
- **Builder page UI:** **medium to high, but not as high as it looks.** With Pyodide there is no second validator to write (the Python engine runs in the page). The work is the UI, and the UI is data-driven, not hand-built screen by screen. See the UI note below.
- **Pyodide integration:** **low to medium.** Loading Pyodide, installing PyYAML, and calling `build_engine.py` from JavaScript is well-trodden. The fiddle is packaging the engine and catalog into the page and managing the first-load weight.
- **Deep link and YAML export:** **low.** A URL parameter and a file download.
- **Full-auto round-trip (v2):** **high relative to its value.** Deliberately out of scope for now.

**Correctness note (addresses "the JSON has to be word-perfect").** We do not need the whole rulebook perfect, and we already have a lie-detector. Scope: validate-don't-enumerate plus six-classes-only means we encode only the slice those builds touch, plus a level or two ahead, not hundreds of pages. Verification: the engine already passes **66/66 checks against the real character sheets**, so the data those six builds use is already proven against ground truth. When we reshape it into the catalog, we re-run all six ledgers through it; if 66/66 still pass, the walked paths are verified by the same oracle we trust today. Content nobody has picked yet is validated more weakly, but it is low-stakes and surfaces (and gets fixed) the first time someone walks that path, with the engine catching any illegal result. The fear shrinks from "transcribe the book flawlessly" to "encode the paths we use, verified by tests we already pass, fix the rest lazily."

**UI note (addresses "the builder UI looks daunting").** We reverse-engineer the UI from the decision sequence the ledger and engine already encode. Chargen is an ordered list of decisions; each level-up is a known set of decisions the class table dictates. So the UI is not 40 bespoke screens, it is roughly **five reusable decision widgets** (a point-buy allocator, an option-picker, a skill/trade allocator, an ancestry-spend allocator, a review screen), and the ledger sequence decides which appear and in what order. Adding a level or a class adds data, not screens. This warrants a light design pass (a wireframe of those widgets and the level-up-night flow, roughly half a day), folded into build-order step 3, not a separate project.

No single piece is scary. The aggregate is a real project, but it is incrementally shippable: Piece B stands alone, and the builder can go live for one PC before the other five exist.

---

## 7. Suggested build order

1. **Piece B first.** Automate the rebuild. It pays off immediately and is independent of everything else. **STATUS (2026-07-10): ✅ DONE / LIVE.** `.github/workflows/deploy.yml` (build.py on push → guard → Pages via `deploy-pages@v4`, `GITHUB_TOKEN` not PAT) is committed to `TheOneGargoyle/dc20-companion` with the source (`companion-src/`, `rules/`; GM files git-ignored). Pages source set to "GitHub Actions"; first run went green and the live site serves the Action-built edition. Manual PAT ritual retired (PAT to be revoked). See the Piece B session-log entry. **Next build-order step = 2 (Spellblade/Tanrielle catalog).**
2. **Catalog for one class (Spellblade / Tanrielle),** the rung 1-2 pilot. Prove the extract-once design, and verify it by re-running Tanrielle's ledger through it (her checks must still pass). **STATUS (2026-07-10): ✅ DONE / VERIFIED.** New `builds/catalog/`: `spellblade.yaml` (SCRIPTED spine — per-level table, 8 Disciplines with resource `grants`, 3 Subclasses, spellcasting model — generated straight from `CLASS_TABLES` by `tools/catalog_build.py`, so it can't drift from the engine), plus CURATED cross-cutting lists `ancestries.yaml` (Human + Elf trait costs) and `spell_schools.yaml` (Invocation + Divination membership + the Weapon/Ward tag-access rule), documented in `builds/catalog/SCHEMA.md`. `tools/catalog_verify.py` is the oracle harness: **66/66 derived-stat checks still pass** across all six ledgers, and the catalog reconciles with `tanrielle.yaml` (spine == engine; all 5 ancestry costs; all 4 spells legal — 3 via Invocation, Primal Hide via its Ward tag; disciplines/subclass present; Magus grant == ledger) and with `ancestries.md`/`spells.md` (no transcription drift). **Next build-order step = 3 (builder skeleton, Tanrielle only).**
3. **Builder skeleton, Tanrielle only.** First a quick wireframe of the ~5 decision widgets and the level-up-night flow (half a day). Then: get Pyodide running `build_engine.py` in the page, load `tanrielle.yaml`, show her decisions, edit one, live-validate via the engine, export. This is the whole flow end to end on one character, and it de-risks Pyodide before we commit further. **STATUS (2026-07-11): ✅ DONE / VERIFIED in-browser (committed + pushed to main).** Design pass: `builds/builder-wireframe.html` (static mock of the 5 widgets + the 6-step level-up-night flow). Live skeleton: `builds/builder.html`, generated by NEW `tools/builder_build.py` (SCRIPTED, base64-bakes the real engine + the three `catalog/` files + `tanrielle.yaml` + a small Python glue module into one self-contained page, the `pyodide-spike.html` approach; also fetch()-first so a served copy reads fresh files, bake is the file:// fallback so it can't drift; regenerate with `python3 tools/builder_build.py`). The page runs the true `build_engine.py` via Pyodide, renders Tanrielle's decision timeline, and makes **one** decision editable (her L4 ancestry-trait spend) via a catalog-backed option-picker (the ancestry-spend widget). Each edit re-runs `replay()` on the evolving ledger and refreshes the review panel live; Export re-serialises the ledger YAML (download). **Headless-verified in sandbox CPython (== what Pyodide runs):** all 5 embedded blobs are byte-identical (sha256) to source; baseline = 0 problems / 15 stats OK; switching the L4 trait to a cost-1 option live-trips `Ancestry points: 6 spent vs 7 budget`, back to cost-2 re-balances; export round-trips through the engine and an illegal pick is still caught on reload. Pyodide load + the DOM render (the only browser-only bits) were then confirmed by Darryl's screenshots: the L4 dropdown flips the review panel red on a cost-1 pick (`Ancestry points: 6 spent vs 7 budget`) and green on a cost-2 pick, `sources: ...baked` showing the file:// bake fallback in use. **Next build-order step = 4 (fan out to the other five classes, mostly catalog data; the widgets are built).**
4. **Fan out to the other five classes** (mostly catalog data, the widgets are already built). **STATUS (2026-07-11): ✅ DONE / VERIFIED in-browser (Darryl's screenshots, Runt).** Catalog: `tools/catalog_build.py` now scripts ALL FIVE class spines (`builds/catalog/{spellblade,warlock,commander,barbarian,druid}.yaml` — per-level tables from `CLASS_TABLES`, Disciplines / Pact Boons, Subclasses incl. the Eldritch Psychic-tag `subclass_grants`, spellcasting models); curated cross-cutting lists extended/added: `ancestries.yaml` (9 trait lists: Human, Elf, Dwarf, Halfling, Giantborn, Dragonborn, Fiendborn, Angelborn via Redeemed, Beastborn; with source/trait aliases), `spell_schools.yaml` (+Elemental, Nullification, Transmutation), NEW `spell_sources.yaml` (Primal, tracked source→school→spells per the §11 wrinkle), NEW `maneuvers.yaml` (30 names by type; "Recovery" deliberately absent — the known 0.10.5 audit item), NEW `talents.yaml` (general + multiclass + walked class talents + the 7 MC-reachable features). `tools/catalog_verify.py` now reconciles ALL SIX ledgers against the catalog (ancestry costs incl. alias/Redeemed fallback, per-class spell-access models, maneuvers, talents, discipline/boon/subclass grants) plus all curated lists against `rules/*.md` — PASS, 66/66 oracle intact. Builder: `builds/builder.html` (via `tools/builder_build.py`) generalised to all six — `?char=<handle>` + on-page switcher, all five widgets live (point-buy, option-picker, ancestry-spend, skill/trade allocator, review), every clean single-name decision editable, catalog-level legality pass (spell access / maneuver existence / trait costs) surfaced beside the engine problems, per-character YAML export. Headless-verified in sandbox CPython for ALL SIX: baked blobs sha256-match sources; baseline 11 stats OK each; ancestry wrong-cost edit trips + re-balances; point-buy, spell-legality and allocator trips work; export round-trips clean and an exported illegal edit is still caught on reload. Browser render then confirmed by Darryl's screenshots (2026-07-11, Runt): decision timeline renders with pickers, a cost-1 ancestry pick trips `engine: Ancestry points: 6 spent vs 7 budget` red, the cost-2 pick goes green with all 11 stats OK, and the skill/trade allocator works live (dropping Cooking to "-" clears the known trade over-spend; restoring it brings the flag back). **Step 4 fully closed.** **Next build-order step = 5 (new-from-scratch mode + respec polish).**
5. **New-from-scratch mode** and **respec polish** once level-up night works. **STATUS (2026-07-11): ✅ DONE / VERIFIED in-browser** (Darryl: Tanrielle promote-L5 with canon banner + both exports + amber unspent-points advisory; "Test Commander" new-from-scratch built, exported and levelled to L2; resume bar on reload). Feedback iterations folded in same day: per-level collapsers, ledger notes displayed, allocator hints on plan prose rows, the engine's trade/language budget lines now honestly report UNDER-SPENT (surfaced 4 true baseline findings incl. a floating LP on runt/scaletrix/xanwyn), a curated `skills_trades.yaml` picker for the allocator (+ custom fallback), declared-ancestry legality in scratch mode with `opens:` reachability (Redeemed→Angelborn, Fallen→Fiendborn), Sheet/Check columns collapse when no sheet exists, export YAML copy-box collapsed. Original build: Three pieces, all in `builds/builder.html` via the rewritten `tools/builder_build.py`: (a) **Add-a-level, the level-up-night flow:** bumps `current_level`, GENERATES the new level's decision slots from the class spine (attribute / talent / path / subclass / 2-ancestry-points / spell / maneuver; auto class features render informational), or PROMOTES an existing plan level (Tanrielle's locked L5) whose entries simply become current and editable; single-step undo; builder-added Path picks spawn their rank-rider slot (Martial → maneuver, Spellcaster → spell) and swap it if the path changes; the `expected:` sheet block is demoted to `expected_at_L<n>` history on level-up because the new level's numbers now come FROM the builder. The allocator can now ADD new skills/trades (free-text, validate-don't-enumerate — the engine keeps budgets honest) and languages, not just edit existing masteries. (b) **New-from-scratch** (`?new=<class>` or the switcher): a blank L1 ledger for any of the five walked classes; chargen driven entirely by the widgets — point-buy, ancestry pick (two catalog trait lists) + trait spend with add/remove slots, spell schools, class L1 choices (Spellblade Disciplines / Warlock Pact Boons are now editable pickers whose `grants` aggregate onto the ledger), spells/maneuvers, background skill/trade/language points, name/player/background — exporting a valid new YAML. (c) **Respec polish** (the §8 UX question, now RESOLVED): a loud EDITING-CANON banner once a canonical ledger is dirty; respec export → `<handle>.respec.yaml` vs a confirm-gated CANON export → `<handle>.yaml` (the confirm spells out that committing it replaces the party version, and warns about undecided/flagged problems); in-progress persistence in localStorage with a resume/discard bar per handle; and a load-your-own-YAML input (the §5 self-serve round trip — the engine re-validates anything loaded). A builder-level completeness pass reports undecided slots beside the engine + catalog problems. **NEW `tools/builder_verify.py`** formalises the headless harness in one command: baked-blob shas vs sources, inline-JS parse, six baselines vs the known whitelist, the four widget trips, fresh-L1 ×5 driven to 0 problems + export round-trip, add-level (promote + generate + undo), and received-file safety — PASS, with the 66/66 oracle intact via `catalog_verify.py`. Fixed in passing: the catalog's target-less "Attribute Increase" option could crash the engine's `(target)` parse — the ancestry picker now emits per-attribute variants. Data wrinkle recorded: a few names on the rulebook's listing pages (`Absorb Element`, `Illuminate`, `Revivify`, the Summon spells) have no matching full spell entry in `spells.md`; list membership is authoritative for legality, so those remain legal picks rather than false "not found" flags. Remaining browser-only leg (same as steps 3-4): Pyodide load + DOM render of the new widgets.
6. **Only if wanted:** revisit the full-auto round-trip.

---

## 8. Decisions and remaining open questions

**Decided this thread:**

- **Hosting:** the builder lives in the **same GitHub repo** as the Companion (a second page on the same Pages site). Simpler for the shared build tooling and the automated rebuild.
- **Show rule text:** yes, attempt it. On a PC builder page the extra payload is acceptable, and IP is already covered by the ORC attribution (the text is display-only display data in the catalog). We revisit only if assembling that text turns out to be a disproportionate burden; then we fall back to names-and-costs.
- **No duplicate party members (the overwrite-vs-new-file question).** The Companion party is built from a **curated list of character ids**, not from whatever YAML files exist in the folder. So: a **level-up** replaces `tanrielle.yaml` (same id), and the party simply shows the new version, no duplicate. A **respec what-if** exports to a scratch file that is *not* in the include set, so it never appears in the party; it exists only for comparison until you deliberately promote it to be the canonical `tanrielle.yaml`. Old versions can be archived (for example `tanrielle.L4.yaml`) so history survives while only the current one shows. Duplicates cannot happen because membership is by id from a curated list, not by file count.
- **The "two machines / OneDrive" caveat is about you, not the players.** It refers to *you personally* running Claude on a desktop and a laptop, with the OneDrive campaign folder syncing your own two machines. It is an authoring-workflow note. This plan does **not** require players to share a OneDrive folder and never touches their storage. Players reach the Companion and the builder as **public URLs they bookmark** (GitHub Pages): no OneDrive, no shared folder, no install. Once the builder is on git, git is the sync medium for the tooling; OneDrive just holds your working copy across your two machines.

**Still genuinely open:**

- **Catalog: how much scripted vs hand-curated?** The engine already holds class tables; spell-school and maneuver lists and ancestry-trait costs are the likely hand-curation. Worth a quick audit of what extracts cleanly from `rules/*.md` before committing to an approach.
- **Respec safety UX:** ~~how loud should the "you are editing canon" moment be, and where exactly does the promote-to-canonical step live?~~ **RESOLVED (step 5, 2026-07-11):** the builder shows a loud EDITING-CANON banner the moment a canonical ledger is dirty, and the export step splits in two — a respec export to `<handle>.respec.yaml` (never in the party include set) and a confirm-gated CANON export to `<handle>.yaml` whose dialog spells out that committing it replaces the party version. Promote-to-canonical therefore lives exactly where §5 wanted it: in the deliberate export-then-commit, never inside the builder.

---

## 9. What this plan deliberately does NOT do

- No database. Six characters are six files; git is the store.
- No standing server. Everything is static hosting plus a build-time Action.
- No second source of truth for a character. One ledger YAML, both tools consume it.
- No secrets in the browser. The builder exports; a human commits.
- No general DC20 chargen tool *yet*. Our six classes and their ancestries only, cap around party level plus two. (This matches the rung-3 constraints already in `ROADMAP.md`.)

**Keeping the door open (because that constraint will not hold forever).** We are not closing the door to more classes, and the architecture we chose keeps it open for free *provided we hold one discipline: data-driven, never hardcoded.* Classes, ancestries and options are catalog rows, not `if class == 'spellblade'` branches, so adding a class is adding data, not rewriting the engine. The specific things to bank now, all of which we are already doing: keep the schema class-agnostic (it is), make the catalog additive (a new class is new rows, never edits to existing ones, the homebrew-overlay principle from `ROADMAP.md`), never bake the number six into anything structural (party by id list, per section 8), and prefer validate-don't-enumerate (it degrades gracefully to content we have not curated, whereas pre-built pickers would not). The one thing that genuinely does not come free is **catalog completeness** for more classes, and that is data-entry effort plus the beta-version treadmill, not an architectural wall. That is the rung-4 tar pit (dismissed on maintenance cost, not on design), so expanding later is "just" content, done at leisure. The cold shower is only required the day you volunteer to maintain full coverage of classes nobody at the table plays.

**A free consequence: the builder is already a standalone character generator.** By construction it builds from scratch, exports YAML, and loads / edits / re-exports, with no dependency on the Companion or the repo. So a standalone chargen tool is not a separate thing to build; it is the same page with the URL handed to someone who does not care about the Companion. For our six classes, giving it out costs nothing. The freebie is "a standalone generator for our six classes." The thing that is emphatically *not* free is "a generator for the wider world," because the moment a stranger uses it they want their class, which is full catalog coverage, the beta treadmill, other people's homebrew, and support requests. Nothing we build now closes that door, so the "make it public for everyone" call can wait until there is real usage to judge it by.

---

## 10. Readiness audit: what is actually left

A comprehensive pass at the close of the design thread (2026-07-10). Short version: **the design is settled. There are no big open questions left, but there is real build work, and two cheap unknowns worth de-risking before we commit to it.**

### Settled (no further decision needed)

Purpose, validation style, the reference/builder split, one-engine-via-Pyodide, one canonical YAML, party-by-id, data-driven discipline, same repo, show rule text, the semi-automatic round-trip, the self-serve player workflow, and the standalone-generator consequence. All the architecture-level forks are closed.

### Genuinely open decisions (both small, both fine to resolve during build)

- **Catalog: scripted extraction vs hand-curation split.** Answered by the extractability spike below, not by more discussion.
- **Respec-safety UX loudness and where the promote-to-canonical step lives.** A wireframe detail (build-order step 3), not a blocker.

### Build work the plan implies but has not yet built (this is effort, not open questions)

1. **The option catalog does not exist yet.** This is the important one. The engine today validates *arithmetic* against costs the ledger states (each ancestry trait and language carries its own `cost:`); it does not know which options exist or what they cost and require. Validate-don't-enumerate still needs a catalog of legal names, costs and prerequisites to check a free-entry pick against. This catalog is the main new content artifact of rung 3. **Medium effort.**
2. **The engine is a batch validator, not an interactive one.** `replay(ledger, level)` checks a *finished* ledger and reports vs sheet. The builder needs stepwise feedback: remaining budget as a live number, and legality of the choice just made. Good news: `replay()` is already a clean callable function (dict plus int, returns a report with a `problems` list) with only PyYAML as a dependency, so the realistic approach is to re-run it on the evolving partial ledger after each choice and surface the problems, plus add small helpers that expose remaining budgets. Additions, not a rewrite. **Low to medium effort.**
3. **`build.py` does not read the ledgers.** It bakes `rules_data` and `gm_data` from the rules markdown; the Companion's party data is maintained separately. For "commit a ledger, the Companion updates" to actually work, `build.py` needs a new step that runs the engine over the ledgers, emits the party stats, and bakes them in. This wiring closes the loop and is currently unbuilt. **Medium effort.**
4. **Spell / maneuver legality vs school lists** (and per-skill die bonuses) are still on the engine's "not yet" list. For a builder that validates picks, the school-list part folds into the catalog work in item 1.

### Cheap unknowns to de-risk first (a "Phase 0" spike)

- **Pyodide actually running the engine.** Load Pyodide plus PyYAML in a page, call `replay()` on `tanrielle.yaml`, confirm it works and the first-load weight and startup are acceptable. This is the linchpin of the one-engine approach; prove it before building UI on top of it.
- **Rules extractability.** Take one class (Spellblade) and see how cleanly costs, prerequisites and option lists pull out of `rules/*.md` versus needing hand-curation. This sizes item 1 above and answers the one genuinely open catalog decision.

### Verdict

We are out of decisions and out of objections; we are not out of work, but none of the remaining work is uncertain in *kind*, only in *amount*, and the two spikes above measure the amount cheaply. Recommended next action is that Phase 0 spike (Pyodide hello-world running the engine, plus a Spellblade extractability sample, plus confirming the `build.py` to engine to Companion wiring). If all three come back green, build in the section 7 order starting with the rebuild Action. This is the natural start of the *next* thread; nothing further needs deciding in this one.

---

## 11. Phase 0 spike results (2026-07-10)

All three Phase 0 spikes were run. Headline: **spike 1 core green, spikes 2 and 3 green, no architectural pivot needed.**

**Spike 1 (Pyodide runs the engine): GREEN on the core question.** The real `tools/build_engine.py` was called exactly the way the browser will call it, `replay(ledger_dict, 4)`, and it works unchanged: it returns a `Report` with `.lines` and `.problems`, all of Tanrielle's L4 checks pass, and it runs in about 0.4 ms. The engine's only non-stdlib dependency is PyYAML, which is a first-class Pyodide package. Because Pyodide is CPython on WebAssembly, "runs in sandbox CPython with only PyYAML" transfers directly. The one thing sandbox CPython cannot measure is Pyodide's browser first-load weight and startup, so a self-contained measurement page was built for exactly that: `builds/spikes/pyodide-spike.html` (engine and ledger embedded as base64, Pyodide and PyYAML pulled from the jsdelivr CDN, four timers shown on the page). Open it in a desktop browser and read the timers. Expected ballpark is a few MB and a couple of seconds cold, near-instant warm once cached, which the plan already treats as fine for a PC-only page. This measurement is the only open item on spike 1.

**Step-4 addendum (2026-07-11) on the source-heading wrinkle:** it is even smaller than step 2 found. Reading the actual class texts: the **Warlock chooses 3 Spell Schools** (classes.md l.3204), exactly like the Spellblade, so it also uses the flattened by-Schools list and needs NO source tracking. Of the six PCs, only the **Druid** draws from a Source ("any Spell on the Primal Spell Source", l.1315-16) — the parent-source-heading tracking now lives in `builds/catalog/spell_sources.yaml` (source → school → spells) and is only needed there. The martials (Commander, Barbarian) have no Spell List at all; their spells ride the Spellcaster-Path "Spell List of choice from any Class" rider (character-creation.md l.753-756), which the sheets never recorded, so the catalog checks existence + consistency only.

**Spike 2 (rules extractability, Spellblade sample): GREEN with a bounded hand-curation tail.** The class spine extracts cleanly: the Spellblade class table is already a clean markdown table (and already lives in the engine's `CLASS_TABLES`); the eight Disciplines, the three Subclasses, and the per-level Features are clean headed lists and prose, good enough to display as rule text. The catalog's real work is the cross-cutting lists, and it is moderate, not scary: (a) spell-school lists are clean bullet lists per school, but school names repeat across the three magic sources (Arcane / Divine / Primal), so extraction must track the parent source heading, not just the `#### <School>` line; (b) ancestry-trait point costs live in `ancestries.md` as inline values in prose and need a small parser; (c) Talents and Maneuvers are cross-class lists, not sampled here. Crucially, validate-don't-enumerate means none of these need to be complete: the engine already validates arithmetic against ledger-stated costs, so the catalog only needs option names, costs and prereqs for the paths people actually walk, verified by the 66/66 oracle. Resolution of the one open catalog decision: script the class spine (reshape what the engine already holds), hand-curate the small cross-cutting cost lists.

**UPDATE (2026-07-10, step-2 build):** the spell-school wrinkle turned out *smaller* than spike 2 feared for the Spellblade. `spells.md` carries a pre-flattened **"Spells sorted by Schools"** section (l.332-519) alongside the by-source one, and the Spellblade "draws magic from Spell Schools" (classes.md l.2834) — so the school-flattened list is the correct source and **no parent-magic-source tracking is needed for the Spellblade**. That source-heading wrinkle only bites source-drawing classes (Cleric/Druid/Sorcerer/Wizard), to handle when their catalogs are built. Also confirmed: off-school picks are legal via the **Weapon/Ward tag** rule (Tanrielle's Primal Hide is School Transmutation but Tags include Ward), so the catalog records `tag_access: [Weapon, Ward]` beside the chosen-school lists. Ancestry costs parsed cleanly from the `(N) Trait:` prefix in `ancestries.md` (small parser, as predicted).

**Spike 3 (build.py to engine to Companion wiring): GREEN, target confirmed.** `build.py` today bakes `rules_data` and `gm_data` from the rules and GM markdown; it does not read the ledgers, and the party's numbers are hand-maintained in a `CHARS` object in `template.html` (for example Tanrielle `hp:14,mp:6,sp:3,grit:0,pd:17,ad:12` plus a `stats` array of Attack +5 / Save DC 15 / Initiative +5). Those are exactly the numbers `replay()` derives. So the loop-closing step is well defined: add a build.py stage that runs the engine over each `builds/*.yaml`, pulls the derived block, and injects it into `CHARS`, replacing the hand-kept numbers. Bounded wrinkle: `CHARS` also carries non-derived play-aids (the toggles, and Move / Jump / MSL, which the engine does not compute yet), so those stay hand-authored for now or get small engine additions later. Medium effort, no surprises.

**Net: no fork reopened, no pivot.** Proceed in the section 7 order starting with the rebuild Action (Piece B), once the `pyodide-spike.html` load timing is eyeballed and acceptable. If the load weight ever proves unacceptable on the table's hardware, the JS-mirror fallback in section 4 is the escape hatch, but nothing seen here suggests needing it.
