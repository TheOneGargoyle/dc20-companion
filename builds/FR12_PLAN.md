# FR-12 / FR-13 / FR-13a: Full Coverage Epic, Decided Plan

**Status: architecture decided 2026-07-19 (design thread, no code written by intent). Re-entry point for the full-coverage epic, same role RUNG3_PLAN.md played for the builder.** Phase 0 is teed up as the next thread's work.

Audience: GM / tooling. Convention: no em-dashes anywhere. If this doc and `builds/BACKLOG.md` + `_SESSION_LOG.md` disagree, trust the log + BACKLOG (this is the durable design record; the log is the running state).

---

## 1. The decision

Darryl's call 2026-07-19: **do the full epic** (all three goals selected: multiclass/respec depth for our six, build-any-class for NPCs and new/returning PCs, and full completeness), and **do the foundational refactor first**. This supersedes the long-standing "questionable value for a fixed six-PC party" defer.

**What tipped it:** the headline con was the "0.11 beta-refresh treadmill." That con turned out to be mostly self-inflicted and fixable (see section 2), so the pros now outweigh it.

**What this doc leaves for the build threads:** the how, phased so nothing large is attempted before its foundation exists, and so each step is independently shippable and harness-locked.

---

## 2. The crux: the treadmill has a fixable root

Today, adding a class costs two things: a catalog YAML (data) AND a hardcoded per-level progression table in `build_engine.py` (`CLASS_TABLES`, code). And it is wired backwards: `tools/catalog_build.py` does `from build_engine import CLASS_TABLES` (l.31) and GENERATES each class spine YAML from the engine's hardcoded dict. So:

- the Python dict is the source of truth,
- every class is a code change,
- a 0.11 beta refresh means hand-editing Python in up to 13 places.

That is what made the con feel heavy. It is fixable cheaply, because the generated spines are already byte-equivalent to the engine dict. We **invert the source of truth**: author each class's progression as data, have the engine read it, retire the hardcoded dict. Feed the same numbers back in and nothing derived changes, so the refactor is guarded by the existing **66/66 (`catalog_verify` derived-stat checks) + 90/90** harnesses staying byte-identical.

After the inversion, adding a class is pure data, and a beta refresh is a data edit (and eventually a re-extract from `rules/tables.md`, the way rule text already regenerates via `tools/rules_corpus.py`). The treadmill's teeth come out. That is the "how" that changes the pros/cons math.

**Precedent already in the codebase:** the engine is meant to be catalog-agnostic with data passed in. `build_engine.stamina_regen(ledger, regen_cat)` and `build_engine.damage_addons(handle, cat)` already take catalog data as an argument rather than hardcoding it. Phase 0 makes the class progression follow the same pattern.

---

## 3. What is actually cheap vs expensive

Do not mis-price this epic.

- **Cheap and boring:** the class tables and per-class catalog spines. Size was never the blocker. The full 13-class catalog is roughly 100 to 150 KB of YAML (names/costs/prereqs/tags, not rule text), taking `builder.html` from ~262 KB to ~350 to 400 KB, invisible next to the multi-MB Pyodide runtime. The engine only ever replays the one character being built, so validation does not slow down with catalog size. "Lazy-load only classes in use" was considered and rejected (saves ~100 KB off a multi-MB load, buys nothing).
- **Expensive and unglamorous (the long pole):** **legality data for FR-13 at full scope.** To let open pickers filter correctly across the whole catalog, every spell and maneuver needs school/source/tag tagging, not just the slice our six exercise. This is the biggest single data task and the least glamorous. Our own casters (FR-13a) only need a fraction of it. School tagging may be largely free (`spells.md` already has a flattened "Spells sorted by Schools" list); source tagging is the real labor.
- **The other scope knob: subclass breadth.** 13 base classes is modest. 13 classes times their full subclass trees is a different animal. Phaseable by use (section 4, Phase 4).

**Two cons that do NOT vanish even after the refactor, on the record:** (a) the legality-tagging pass is genuine labor, low-risk but the bulk of "full completeness"; (b) full coverage means more surface to re-verify each beta, though the refactor makes that a data re-extract rather than code surgery. Everything else the refactor genuinely defuses.

---

## 4. The staircase (phases)

Ordered so each step makes the next cheaper and nothing big is attempted before its foundation. Each phase is its own thread (or a small batch of threads), independently shippable, harness-locked.

**Phase 0. Foundation: data-drive the class progression.** (NEXT THREAD. Detailed spec in section 5.)
Move `CLASS_TABLES` out of `build_engine.py` into per-class catalog data; the engine reads the spine as passed-in data (the `stamina_regen`/`damage_addons` pattern); `catalog_build.py` stops importing the spine from the engine. Pure refactor, no behaviour change, 66/66 + 90/90 byte-identical. Self-contained. This is the linchpin: after it, a class is one data file and a beta refresh is a data edit. Ship it on its own before committing real hours to data, to prove the "adding a class is now data-only" claim.

**Phase 1. Sourcing machinery + FR-13a (our casters).**
Generalize the FR-8 slice-5 Eldritch constrained-grant pattern into a reusable system: every spell/maneuver grant carries its source/school/tag, the picker filters to it, and the grant is childed under the granting feature (Scaletrix's Command childed under the Fiendish Magic ANCESTRY trait, not as a class spell). Model the currently-unmodelled **Sorcerous Origin** sub-choice + the Intuitive Magic list pick. Fixes Scaletrix's real gap now (the auto-heal ready slots are the visible symptom) and builds the exact machinery FR-12/FR-13 lean on. Small blast radius (our six). **Data ask: Damo's four chosen Arcane spells** (machinery can be built with placeholders meanwhile). This is FR-13a as scoped in BACKLOG.

**Phase 2. Spell/maneuver legality data (the long pole, phased).**
Tag the full spell/maneuver list by school/source/type so open pickers filter correctly (FR-13 proper). The maneuver-TYPE half is already done (pact-boon pickers, 2026-07-19). Phaseable: start with the schools/sources our six + likely MC targets use, expand outward. School tagging likely largely free from the flattened list; source tagging is the labor. This is what makes Phase 3's open pickers trustworthy.

**Phase 3. Class coverage (FR-12).**
Add the remaining 8 base classes as data files (progression + base features), one at a time or lightly batched, each independently verifiable. **Prioritize by multiclass-reach first** (our PCs already dip into other classes: Tan's MC Warlock, Scaletrix's MC Sorcerer/Innate Power), then by likely NPC/new-PC use. Where a real known build exists, validate against it; otherwise validate against the rules tables.

**Phase 4. Subclass + ancestry breadth.**
Fill subclass trees per class and the remaining ancestries. Incremental, data-only, prioritized by use.

**Phase 5. Mobile picker UX.**
Search/typeahead + FR-7 filtering so pickers with hundreds of options stay usable on a phone. Needed once the catalog is large. FR-12's BACKLOG note already flags this dependency.

**Dependency summary:** Phase 0 first (everything rides on it). Phase 1 next (builds the legality spine, fixes a real bug, low risk). Phase 2 underpins the trustworthiness of Phases 3 to 4 but coverage can be ADDED before full legality lands, with legality catching up. Phase 5 last.

---

## 5. Phase 0 detailed spec (the next thread)

**Goal:** the engine derives every number from a class progression that lives in DATA, not in a hardcoded Python dict. Adding or refreshing a class touches data only, never `build_engine.py`.

**Guardrail (the whole point):** the six ledgers must derive byte-identical numbers before and after. `catalog_verify` 66/66 zero deltas and `builder_verify` PASS exit 0 are the oracle. This is a provably-safe refactor because the authored data is fed back the same numbers the engine hardcodes today.

**The shape (recommended, following the codebase's own catalog-agnostic-engine precedent):**

1. The per-level spine (numbers + feature labels: `hp/sp/mp/man/spells/attr/skill/trade` + the `features:` list like `Subclass`, `Talent`, `Path`, `2 Ancestry Points`) becomes authored DATA. It already exists in this exact shape as the `spine:` block of each `builds/catalog/<class>.yaml`.
2. `build_engine.replay(ledger, level)` reads the class table as passed-in data (a `class_table=` argument, defaulting to a small loader that reads the spine from the catalog), exactly like `stamina_regen(ledger, regen_cat)` and `damage_addons(handle, cat)` already do. The engine keeps its only dependency as PyYAML.
3. `CLASS_TABLES` the hardcoded dict is retired. `catalog_build.py` no longer does `from build_engine import CLASS_TABLES`.

**The key Phase-0 design sub-decision to settle at the top of that thread (do not pre-commit here):** where exactly is the spine authored, and what happens to `catalog_build.py`'s generator role?

- **Option A (recommended): the per-class catalog YAML becomes the single hand-authored home for everything about a class** (spine + curated disciplines/pact-boons/subclasses/spellcasting). Drop the "SCRIPTED, do not hand-edit" model for the spine. This gives the cleanest door-open story: one data file per class IS the unit you add. Cost: `catalog_build.py`'s spine-generation role is retired (its hand-authored curated bits, e.g. `WARLOCK_PACT_BOONS`, move into the class YAMLs or a thinner generator).
- **Option B (minimal): keep `catalog_build.py` as the generator, but move the authoritative numbers out of `build_engine.CLASS_TABLES` into a data file that BOTH the engine and `catalog_build.py` read.** Smaller change, keeps the generator indirection. Less clean door-open story.

Recommendation leans A (kills the indirection, best door-open unit), but it is a real call worth making deliberately with the file diff in view. Flag it first thing in the Phase 0 thread.

**Watch-outs for Phase 0:**
- The `features:` label strings are STRUCTURAL: the builder and engine key on them (`Subclass`, `Path`, `2 Ancestry Points`, etc.). Preserve them exactly; they are part of the progression data, not cosmetic.
- Pyodide: the engine runs in-browser baked via `builder_build.py`. If the engine now needs spine data, that data must be baked/passed in the same way the catalog already is (the builder already bakes `CATALOG` + `CATPATHS`). Confirm the in-browser path, not just CLI.
- `companion-src/build.py` also replays all six ledgers through the engine to bake `PARTY_DERIVED`. It must supply the spine data the same way. Verify the Companion rebuild stays byte-identical (`PARTY_DERIVED` unchanged).
- Regenerate `builds/builder.html` (`python3 tools/builder_build.py`) since the baked engine changes; sha-check clone to mount.

**Definition of done for Phase 0:** `CLASS_TABLES` gone from `build_engine.py`; engine reads spine from data; `catalog_build.py` no longer imports it; `catalog_verify` 66/66 + 90/90 zero deltas; `builder_verify` PASS; Companion `PARTY_DERIVED` byte-identical; `builder.html` regenerated + sha-matched; no em-dashes. Then, as a smoke test of the payoff, sketch (do not necessarily ship) adding one new class as data-only to confirm zero engine edits are required.

---

## 6. Open decisions (carry into the relevant phase)

- **Phase 0 spine home + `catalog_build.py` fate:** Option A vs B (section 5). Settle at the top of the Phase 0 thread.
- **Phase 2 legality depth:** full spell/source tagging vs "legal-for-grants + trust the user on free picks." Full completeness implies the former eventually; can start partial.
- **Phase 3/4 subclass depth:** all subclasses vs base-classes-first. Prioritize by use.
- **Auto-extraction from `rules/tables.md`** (stretch): makes beta refreshes cheaper still (re-extract vs re-author). The `CLASS_TABLES` comments already cite the `tables.md` line ranges. Nice-to-have, error-prone, not required for Phase 0. Revisit once the data-driven engine exists.

---

## 7. Working discipline (unchanged, from `_NEXT_THREAD_STARTER.md`)

Regression-test FIRST: fresh `git clone` of `https://github.com/TheOneGargoyle/dc20-companion.git` into a new unique `/tmp` dir at the current `origin/main`; `catalog_verify.py` (90/90 zero deltas) and `builder_verify.py` (PASS exit 0) must both pass before touching anything. Do NOT `git stash`/`git reset` on a clone you have `cp`'d mount files into. Edit mount files with the Read/Edit tools (Windows-side, reliable), then `cp` mount to clone and grep a canary before running harnesses (guards mount-staleness). Regenerate `builds/builder.html` with `python3 tools/builder_build.py` if the builder/engine/ledgers/catalog changed; `builds/catalog/*.yaml` with `python3 tools/catalog_build.py` if the scripted spines change; `companion-src/build.py` if the Companion is touched. No push credentials in the sandbox: Claude builds + verifies + stages on the mount, gives the file list + commit message; Darryl runs `sync-to-repo.bat` + commits + pushes via GitHub Desktop + Chrome-verifies. `builds/*.md` (this file, BACKLOG) ARE git-tracked; `_SESSION_LOG.md` / `_NEXT_THREAD_STARTER.md` are OneDrive-only (never hit the repo).

---

## 8. Ask-the-players standing list (relevant to this epic)

- **Damo:** name Scaletrix's 4 unrecorded Arcane spells (2 Innate Power "Intuitive" + 2 Spellcaster-path) for Phase 1 / FR-13a; also his paper sheet reads Level 3, should be L4.
- **Phil:** Runt PD 15-vs-17 confirm (standing, not epic-specific).
