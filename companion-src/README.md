# Companion app build source

**What this is:** the source for the single-file mobile app (Party sheets, dice, searchable rules, About, session logger), **published at https://theonegargoyle.github.io/dc20-companion/**. Persisted here 2026-07-04 so any Claude session on any machine can rebuild it. Claude memory does NOT sync between machines; this folder is the shared medium. **The built HTML is no longer kept in this folder** (removed 2026-07-05): `build.py` writes it to a temp dir and the published copy lives on GitHub Pages — this folder holds **source only**.

## ⚠️ Maps removed — IP hygiene (2026-07-05)

The **Maps tab was retired and replaced by an About tab.** The app is publicly hosted (GitHub Pages, no auth), and the map images are **Games Workshop / Warhammer** material (World & Region maps unaltered; Local ~90% GW-derived) which is **not** open-licensed — so it must not ship in the published build. The **DC20 rules DO ship**: DC20 is released under the **ORC (Open RPG Creative) License**, and the About tab carries the attribution + a non-commercial / "unofficial, not affiliated" notice + links (DC20 site, ORC license, Kickstarter). The geography prose (`known-geography.md`) was tied to the Maps tab, so it went too. The template no longer references `__GEO_HTML__` / `__MAPS__`, and `build.py` no longer embeds them (the `encode_map`/`maps` block + the two `.replace()` lines were removed; `PIL` import is now optional). **To restore maps for a LOCAL-only build**, re-add that block + the two replaces — but never publish that build. *(Rules search-only-not-browse was considered and deferred — Darryl will ask the DC20 devs about beta-content/attribution when he shows them the app.)*

## ⚠️ Before rebuilding — check for divergence

This source matches the live app as of **2026-07-05** (maps removed / About tab added; all **six** PCs incl. Xanwyn present). The **Party tab** is a data-driven `CHARS` engine (character switcher, per-character localStorage state, `CHARS.*.acc` accordion strings near the end of the template's script). Character data source of truth: workshop files `08`, `10`–`14` + the sheet PDFs in `../sheets/`. `__TAN_ACCORDIONS__` injects Tan's accordions from build.py; the other five PCs' accordions live in the template itself. If the live HTML (GitHub Pages) is newer than this date, re-check for divergence before rebuilding.

## How to rebuild

**⚠️ Do the whole build in a local temp dir, NOT on the OneDrive mount.** The sandbox reads this synced folder through a mount that intermittently serves **stale or tail-clipped** copies of files — especially ones just edited — which has silently corrupted builds (a truncated `build.py` once "succeeded" writing nothing). So don't build in place; work in `/tmp`:

1. Requirements: `pip install markdown --break-system-packages`. *(pillow no longer needed — maps removed; the `PIL` import is optional.)*
2. **Copy sources to a local dir and integrity-check them.** e.g. `mkdir -p /tmp/b/companion-src /tmp/b/rules && cp companion-src/build.py companion-src/template.html /tmp/b/companion-src/ && cp rules/*.md /tmp/b/rules/` (also copy the GM files `03/04/05/06/09` + `_SESSION_LOG.md` for fidelity, though the player build embeds none of them). **Cheap clip check:** `wc -l` each copied file vs a Windows-side Read/Grep count — a clipped file shows *new content at the OLD length*. Repair a clipped file by **overlap-merge**: keep the good head (`head -n N`), append the true tail (read via the Read tool). A healthy build prints `rules sections: 216`.
3. `cd /tmp/b/companion-src && python3 build.py` — writes to `$TMPDIR/dc20-companion/DC20 Companion.html` by default, or pass a path: `python3 build.py /tmp/out.html`. Player-safe edition only (**no GM tab / no GM data** — an in-file gate would be cosmetic since the HTML source is readable; also drops Tan's two Darryl-facing accordions + her Beseech Patron line). *(**GM edition retired 2026-07-05.** Template keeps the `__GM_DATA__` machinery and `assemble(gm=True)` — revert = uncomment the two `OUT` lines in `build.py`.)*
4. **Verify the temp output:** ends with `</html>`; extract the `<script>` and `node --check` it; `grep -c` GM strings ("Withdrawn", "puppets", "Returner", "metaplot") = 0; no `data:image/jpeg;base64` or `__MAPS__` (maps stay out); About tab + the three links present.

## Publishing (the live URL)

GitHub Pages is the delivery mechanism — the table bookmarks one URL that updates in place. **The pushed `index.html` is the authoritative published copy; there is no persistent HTML in this folder.**

- **Live URL: https://theonegargoyle.github.io/dc20-companion/** (repo `TheOneGargoyle/dc20-companion`, public — safe because only the player-safe edition is ever published).
- **Publish ritual (all in `/tmp`, after building there per "How to rebuild"):**
  1. `git clone https://x-access-token:<TOKEN>@github.com/TheOneGargoyle/dc20-companion.git /tmp/repo` — TOKEN = first line of `publish-token.txt` (fine-grained PAT, Contents-write on that one repo only; don't echo it).
  2. Copy the **verified** temp build over `/tmp/repo/index.html`; keep `.nojekyll`.
  3. `git -C /tmp/repo commit -am "…"` and `git -C /tmp/repo push`.
  4. Check the deploy: `GET /repos/TheOneGargoyle/dc20-companion/pages/builds/latest` → `status: built`, `error: None`.
- ⚠️ **Before pushing**, confirm `index.html` ends with `</html>` (mount-clip guard — building in `/tmp` avoids the mount, so this is just belt-and-braces).
- ⚠️ **`.nojekyll` is mandatory** (don't delete): without it Pages runs Jekyll over the ~2 MB HTML and the deploy hangs then errors. Kick a stuck deploy with `POST /repos/.../pages/builds`.
- Pages caches ~10 min; players may need one hard-refresh. localStorage tracker state persists per-browser on the https origin.

## Architecture

- `template.html` — the whole app (CSS/HTML/JS) with three active placeholder tokens: `__RULES_DATA__`, `__GM_DATA__`, `__TAN_ACCORDIONS__`. *(`__GEO_HTML__` / `__MAPS__` retired 2026-07-05 — see "Maps removed" above.)*
- `build.py` — reads `../rules/*.md` (split into sections on `##`/`###`, rendered via python-markdown, plus a search index), GM files (03/04/05/06/09 + `_SESSION_LOG.md`), and injects everything as JSON (escaping `</` → `<\/`). *(Geography/maps embedding removed 2026-07-05.)*
- **PDF-extraction reformatter** (in build.py): the `rules/*.md` files are raw PDF text. `reflow_pdf_text()` promotes standalone Title-Case lines to headings; `process_paragraph()` does sentence-level surgery on the unwrapped paragraphs — inline `Label:` breakouts, run-in heading detection, `DC Tip:`/`Example:` → blockquote callouts. Hand-written files (`house-rules.md`, `_INDEX.md`, `tables.md`, `changelog.md`) are deliberately NOT reflowed (see `REFLOW_FILES`).
- **Party engine:** all six PCs' sheet data is hand-coded in the `CHARS` object in `template.html` (stats, toggles with `pd`/`round`/`rest` flags, rolls, skills, audit notes); Tan's accordions come from the `TAN_ACCORDIONS` string in `build.py`. Source of truth: workshop files `../08`, `../10`–`14` + the PDFs in `../sheets/`; EV maths via `../tools/ev_model.py`.

## On level-up to L5 (changes nearly every number)

Attack/Spell +5→+7 · Save DC 15→17 · PD +2 · MP 6→7 · SP 3→4 · MSL/SSL 2→3 · HP +2 · Awareness +10, Herbalism +9, Arcana/Nature +7 · new spell Luminous Burst · Expert Spellblade + Spell Breaker. Full cited table in `08` → "Verified L5/L6 progression". Update both template stats and the accordions.

## Gotchas learned the hard way

- **File truncation:** on the desktop Cowork setup, files written/edited through Claude's file tools were sometimes truncated at ~32 KB when read back through the sandbox mount. Symptom: build output missing `</html>`, or Python `SyntaxError: unterminated triple-quoted string`. Fix: write big files via shell (heredoc/python), and always verify the output ends with `</html>`.
- **Stale/clipped mount reads (corollary):** the sandbox (bash) view of this OneDrive folder can also serve *stale or 32 KB-clipped* copies of files recently synced **from the other machine** — on 2026-07-04 the desktop session wrongly concluded the laptop's changes "hadn't synced" because bash showed old sizes/mtimes and truncated content, while the files were complete on the Windows side. Before declaring cross-machine changes missing (or overwriting them), verify with Claude's Read tool (Windows path), not just bash.
- **Phone caching:** Chrome on Android caches the opened file aggressively — after a rebuild, fully close and reopen from OneDrive.
- **localStorage:** may not persist across full closes when opened via a `content://` URI; the app degrades to in-memory state by design (see `sget`/`sset`).
- **Reasoning discipline:** all mechanics content must be cited from `../rules/` (see `../rules/house-rules.md` header) — don't invent numbers when editing the accordions.
- **Cheap mount-integrity check (2026-07-05):** before building, compare `wc -l` (bash) against a Windows-side line count for every recently-edited input — clipped files serve new content at the old byte-length and can *look* plausible. Repair = overlap-merge the true tail (from Read or the complete built app), never build from a file that fails the check.
- **classes.md class tables:** repaired at the source 2026-07-05 — the 13 garbled PDF table blobs were replaced with the hand-rebuilt tables from `tables.md` (inlined as `####` sub-sections), extraction heading noise cleaned (Shields/duplicate-Barbarian/generic-Subclasses). If the ruleset is ever **re-extracted from the PDF**, these repairs must be redone (see the 2026-07-05 session-log entry for the exact steps).

## Possible next steps discussed

~~Per-PC tabs/sheets~~ (done 2026-07-04: the Party tab / `CHARS` engine). Remaining: accordion content (spells/maneuvers/combos) for Minimus, Runt, Scaletrix, Bonan (`acc` currently empty for them — source: files 10–13); Xanwyn (needs a sheet); resolve the audit flags in `CHARS` (Runt MP 8 vs 9, Bonan Jump 6 vs 4 + the "Recovery" maneuver, Minimus/Bonan blank trade values); bestiary stat-block cards. ~~pins on the maps~~ (maps removed 2026-07-05).
