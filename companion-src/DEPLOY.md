# Automated deploy (Piece B) — setup guide

**What this replaces:** the manual publish ritual (build in `/tmp`, clone
`TheOneGargoyle/dc20-companion` with the PAT from `publish-token.txt`, copy
`index.html`, push). That ritual is documented in `README.md` under
"Publishing" and stays valid as a fallback until this Action is live.

**What Piece B does:** a GitHub Action (`.github/workflows/deploy.yml`) runs
`companion-src/build.py` on every push that touches the build source, and
deploys the player-safe build to GitHub Pages. It authenticates with the
built-in `GITHUB_TOKEN`, so **the PAT is no longer needed**.

The Action was verified headless before shipping: `python3 companion-src/build.py
dist/index.html` from a repo-root layout produces a 2.1 MB build ending in
`</html>`, the embedded script passes `node --check`, the ORC/About attribution
is present, and there is no GM or map-image leak. `gm files: 0` confirms the GM
files are absent and skipped.

---

## The one structural change: the source moves into the repo

Today the repo `TheOneGargoyle/dc20-companion` holds only the built
`index.html` + `.nojekyll`. The build **source** (this `companion-src/` folder
and `../rules/`) lives only in the OneDrive campaign folder. An Action can only
build what is in the repo, so the source has to live there too. This is exactly
the move the rung-3 plan anticipated (`builds/RUNG3_PLAN.md` §8: "Once the
builder is on git, git is the sync medium for the tooling; OneDrive just holds
your working copy across your two machines").

### What to commit into the repo

From the campaign folder, commit these into the repo root (same relative paths):

- `companion-src/build.py`
- `companion-src/template.html`
- `companion-src/README.md`, `companion-src/DEPLOY.md` (this file) — optional but useful
- `rules/*.md` (the DC20 ruleset — ORC-licensed, safe to publish; plus
  `house-rules.md`, which build.py skips anyway)
- `.github/workflows/deploy.yml`

### What must NOT go into the public repo

- **The GM files:** `03_factions_GM.md`, `04_secrets_GM.md`,
  `05_threads_and_clues_GM.md`, `06_pacing_and_levelling_GM.md`,
  `09_cogm_agenda_GM.md`, and `_SESSION_LOG.md`. `build.py` reads these only
  when present and the **player** build embeds none of them
  (`assemble(gm=False)` injects `[]` for GM data). With the files simply absent
  from the repo, the build prints `gm files: 0` and produces an identical
  player-safe result. Keeping them out is the belt-and-braces guarantee that no
  secret ever reaches the public site.
- **`publish-token.txt`** — the PAT. Do not commit it; once the Action is live
  it can be revoked in GitHub settings.
- Map imagery / the workshop `08`,`10`–`14` files / `sheets/` — none are read by
  the player build; leave them in OneDrive.

A `.gitignore` at the repo root is the safe way to enforce this — e.g. ignore
`*_GM.md`, `_SESSION_LOG.md`, `publish-token.txt`, `sheets/`.

---

## One-time GitHub settings

1. **Pages source → GitHub Actions.** Repo *Settings → Pages → Build and
   deployment → Source*: change from "Deploy from a branch" to **"GitHub
   Actions"**. (Until you do this the deploy job cannot publish.)
2. That's it — `permissions:` in the workflow grants Pages write and the deploy
   OIDC token; no secrets to configure.

---

## After it's live

- Push a change to `companion-src/**` or `rules/**` (or hit *Run workflow* on the
  Actions tab). Watch the run: the **build** job runs `build.py` and the guard
  step, then the **deploy** job publishes and prints the live URL.
- Live URL is unchanged: <https://theonegargoyle.github.io/dc20-companion/>
- Pages still caches ~10 min; a hard-refresh on the phone may be needed (same as
  before).
- The `builds/**` path is in the trigger already, so when the future
  `build.py` loop-closer (RUNG3 §7 step, bakes party stats from the ledgers)
  lands, committing a ledger will rebuild the Companion automatically with no
  further wiring.

## Fallback

If the Action ever misbehaves, the manual ritual in `README.md` → "Publishing"
still works unchanged (the PAT, if not yet revoked, still has Contents-write).
