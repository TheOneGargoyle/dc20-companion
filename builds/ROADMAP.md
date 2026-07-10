# Build-tooling roadmap (the 4-rung ladder)

Written 2026-07-10 at the close of the rungs 1-2 thread; the re-entry point for the rung-3 conversation.

## The ladder

1. **Structured capture (DONE 2026-07-10).** One YAML ledger per PC recording every chargen/level-up decision. Schema v1 in `SCHEMA.md`; all six PCs ledgered.
2. **Replay engine (DONE 2026-07-10).** `tools/build_engine.py` replays a ledger, derives stats at any level (including plan levels), enforces budgets and legality, reports vs sheet. Status: 66/66 party checks pass; five class tables encoded (Spellblade, Warlock, Commander, Barbarian, Druid); PD/AD derived; open items live in each ledger's notes + `09`.
3. **Interactive builder UI (DESIGN DONE 2026-07-10, build not started).** A browser-based character builder that walks a user through chargen/level-up/respec interactively. **The architecture is decided and captured in `builds/RUNG3_PLAN.md`** (the re-entry point; supersedes the rough open-questions below). Headlines: reference/builder split (Companion stays static + mobile; builder is a separate PC-first page in the same repo), one engine run in-browser via Pyodide, ledger YAML as the single char format, semi-automatic round-trip (export + one-person commit), self-serve player workflow. Next step is the Phase 0 spike in RUNG3_PLAN.md section 10 (Pyodide-runs-the-engine; rules extractability; build.py wiring). Constraints below still hold and are expanded in the plan.
4. **Community tool.** Dismissed as unrealistic (full content coverage, version treadmill, hosting, support). Fun to joke about; not doing it.

## Rung 3: agreed constraints (from the 2026-07-10 discussion)

- **Scope: our six classes and their ancestries only**, level cap ~party level +2. Not a general DC20 chargen tool.
- **Encode structure, not effects.** The option catalog holds names, costs, prerequisites, and resource grants (enough to validate legality and derive numbers). Rule text stays as display text; the engine never simulates what an ability does.
- **Homebrew = overlay data packs** (extra rows in a separate file), never special-cased code. This keeps real-table content from exploding the design.
- **Data size is a non-issue at runtime**: the catalog ships as static JSON inside the app (a few hundred KB for six classes); zero tokens at runtime. The real cost is building/maintaining the catalog, mitigated by scripted extraction from `rules/*.md`.
- **Beta churn accepted**: 0.11 (full combat pillar, the only major update expected before launch) will need a one-time data refresh, which doubles as a test of the data-driven design.

## Rung 3: key open questions for the next thread

- The rungs 1-2 data model is *ledger + engine-side rules knowledge*. Rung 3 additionally needs **option catalogs** (everything choosable at each decision point: all talents, all spells per school, all maneuvers, ancestry traits with costs, path options). How much is scripted extraction vs hand-curation?
- Where does it live: a Companion tab (single-file constraint, template.html) vs a separate page on the same GitHub Pages site? The Companion's build system (`companion-src/`) already handles data-baked-into-HTML.
- What is the UI actually for, in priority order: (a) level-up night at the table (each player walks through their new level), (b) what-if respecs, (c) new-character creation? The answer shapes how much catalog is needed first (level-up night needs only the next level's options for six known builds — far smaller than full chargen).
- Validation UX: full picker menus vs free-entry-with-validation (the "validate, don't enumerate" hybrid that keeps the catalog small).
- IP: rule *text* in the app is already covered by the ORC attribution (About tab); the catalog is names/costs/prereqs, same footing.

## Current open data items (blocking nothing, tracked in `09` + ledger notes)

Jesse: Guard carry-over (Tan's sword); +2 AD light shield call. Phil: armor stack + all-day Primal Hide confirmation; L3 attribute destination; L1 ancestry itemisation (5 pts, Tough inferred); Deep Speech 1-TP over-spend. Kristian: skill breakdown; L3 attribute destination. Ed: Recovery re-pick; L3 attribute destination; Jump 6-vs-4. Damo: Infernal 1-TP over-spend; L3 attribute destination; sheet Level field 3->4 (content already proven L4). Party-wide: the `09` sheet refresh, now mechanised via the engine reports.
