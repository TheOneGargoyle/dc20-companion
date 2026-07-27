#!/usr/bin/env python3
"""Headless DOM smoke test for builds/builder.html: drive the REAL PAGE in a REAL BROWSER.

    python3 tools/builder_smoke.py            # run (skips cleanly if Playwright is absent)
    python3 tools/builder_smoke.py --require  # fail instead of skipping (use this in CI)
    python3 tools/builder_smoke.py --headed   # watch it

WHY THIS EXISTS (the discovery gap, 2026-07-27). `catalog_verify.py` checks the catalog against the
rules and the six canon ledgers; `builder_verify.py` runs the exact API glue the page runs, in CPython,
against the real catalog. Both read the MODEL. Nothing drove the PAGE, and on 2026-07-27 two changes
shipped COMPLETELY INERT through a green harness: BUG-31 (the page's CATPATHS was a hand-written
literal, so a baked catalog file never reached the API) and BUG-32 (the sheet's catLabels literal
dropped whole slot kinds). Five of the nine bugs closed that day were found by Darryl clicking in
Chrome after a push. This harness is the answer to that whole family: it asserts what the browser
RENDERS, so a change that is correct in the model but unreachable in the page fails here.

WHAT IT IS NOT. It is not a replacement for builder_verify (which is faster, deeper and has no
browser dependency) and not a full UI test suite. It is a thin, canonical set of journeys chosen so
that the *plumbing between model and page* is exercised end to end. Keep it that way: depth belongs
in builder_verify, reachability belongs here.

DESIGN NOTES worth keeping.

  * It serves the repo over http and loads `builds/builder.html`, the GENERATED artifact. Never point
    it at the inputs the page is built from, or it will pass while the browser does nothing (that is
    precisely the BUG-31 failure mode).
  * Pyodide boots once (tens of seconds, pulls from the CDN). Every journey then reuses the same page
    by re-selecting from `#charsel`, which re-inits the API without another boot. Adding a journey is
    therefore cheap; adding a page reload is not.
  * The expectations are DERIVED FROM THE CATALOG, not hand-listed. Class-feature names come from
    `class_features.yaml`, trait effects from `ancestries.yaml`. That is the 2026-07-27 anti-mirror
    lesson (BUG-31/32/33 were all one hand-maintained list disagreeing with another), and it means a
    newly added option is covered here the moment it is added. The trait journey also asserts that
    the curated journey list still COVERS every catalog trait with a flat stat grant, so adding one
    without a journey fails closed.

Exit 0 on PASS or SKIP, 1 on any failure.
"""
import argparse
import functools
import http.server
import os
import socketserver
import sys
import threading

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
PAGE = os.path.join(REPO, "builds", "builder.html")

# numeric grant key -> the label the page prints in the derived-stats table
GRANT_STAT = {"hp": "HP", "sp": "SP", "mp": "MP", "ad": "AD", "pd": "PD",
              "speed": "Move Speed", "jump": "Jump Distance"}

# Curated trait journeys: (ancestry, [prerequisite traits to pick first], trait).
# The expected DELTAS are read from the catalog, not written here. Coverage is asserted per trait
# NAME rather than per (ancestry, name) pair: the same name is the same catalog row shape down the
# same code path on every ancestry that offers it, so one journey per name is the honest unit and
# keeps the run to one page load each.
TRAIT_JOURNEYS = [
    ("Elf", [], "Frail"),
    ("Elf", [], "Brittle"),
    ("Elf", [], "Quick Reactions"),
    ("Dwarf", [], "Thick-Skinned"),
    ("Dwarf", [], "Tough"),
    ("Beastborn", [], "Reckless"),
    ("Beastborn", [], "Jumper"),
    ("Beastborn", ["Thick-Skinned"], "Hard Shell"),
    ("Angelborn", [], "Mana Increase"),
]

# Checks that are EXPECTED to fail because they describe an open, filed bug. A red CI that everyone
# learns to ignore is worse than no CI, so a documented open bug reports as KNOWN and does not fail
# the build. The registry is not a way to silence things: if a known-failing check starts PASSING,
# that is itself a failure ("BUG-xx looks fixed"), which forces the entry to be removed along with
# the fix. Key = the `bug` string passed to ok(); value = a one-line reason.
KNOWN_FAIL = {
    "BUG-34": "granted disciplines apply nothing (grant-children are assumed to be leaves)",
}

FAILS = []
KNOWN_HITS = []


def ok(label, cond, detail="", bug=None):
    if bug and bug in KNOWN_FAIL:
        if cond:
            # the bug appears to be fixed: fail loudly so the registry entry gets retired
            print("  %-62s UNEXPECTED PASS" % label[:62], flush=True)
            FAILS.append("%s now PASSES: retire the KNOWN_FAIL entry (%s)"
                         % (bug, KNOWN_FAIL[bug]))
        else:
            print("  %-62s KNOWN %s" % (label[:62], bug), flush=True)
            KNOWN_HITS.append("%s | %s | %s" % (bug, label, detail))
        return
    print("  %-68s %s" % (label[:68], "OK" if cond else "FAIL"), flush=True)
    if not cond:
        FAILS.append("%s%s" % (label, (" | %s" % (detail,)) if detail else ""))


def load(name):
    with open(os.path.join(REPO, "builds", "catalog", name + ".yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def flat_stat_grants(row):
    """The row's numeric effects that land on a derived stat, unarmoured merged in (a fresh scratch
    character carries no equipment, so the unarmoured half always applies in these journeys)."""
    out = {}
    for src in (row.get("grants") or {}, row.get("grants_unarmored") or {}):
        for k, v in src.items():
            if k in GRANT_STAT and isinstance(v, (int, float)):
                out[k] = out.get(k, 0) + v
    return out


def _force_close(browser):
    print("  !! WATCHDOG: journey exceeded its time budget, closing the browser", flush=True)
    try:
        browser.close()
    except Exception:
        pass


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    # the page pulls ~25 files on every (re)boot; their access log drowns the checks
    def log_message(self, *a, **k):
        pass


def serve(port):
    handler = functools.partial(_QuietHandler, directory=REPO)
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


# ------------------------------------------------------------------ page driver
class Page:
    # Every page load boots a Pyodide runtime with the whole catalog in it, which is hundreds of MB.
    # Closing the TAB is not enough on a memory-tight host: chromium holds onto renderer processes,
    # and around the seventh journey the OOM killer takes the whole run (observed on a 4 GB box on
    # 2026-07-27, and it kills the python parent too, so nothing gets reported). So the BROWSER
    # itself is relaunched every few journeys. CI runners have the headroom not to need this; the
    # cost is a couple of seconds per relaunch, which is worth paying for a suite that finishes.
    BROWSER_EVERY = 4

    def __init__(self, launch, url):
        self.launch = launch
        self.url = url
        self.errors = []
        self.pg = None
        self.browser = launch()
        self.n = 0
        self.recycle()

    def recycle(self):
        if self.pg is not None:
            try:
                self.pg.close()
            except Exception:
                pass
        self.n += 1
        if self.n % self.BROWSER_EVERY == 0:
            try:
                self.browser.close()
            except Exception:
                pass
            self.browser = self.launch()
        pg = self.browser.new_page()
        pg.set_default_timeout(25000)
        pg.on("pageerror", lambda e: self.errors.append(str(e)[:300]))
        pg.on("dialog", lambda d: d.accept())   # FR-5 unsaved-changes guard
        self.pg = pg

    def stats(self):
        return self.pg.evaluate(
            "Object.fromEntries([...document.querySelectorAll('#stats tr')]"
            ".map(r=>[r.cells[0].innerText.trim(), r.cells[1].innerText.trim()]))")

    def stat(self, key):
        return self.stats().get(key)

    def rows(self):
        return self.pg.evaluate(
            "[...document.querySelectorAll('#decisions .dec')].map(d=>({"
            " slot:(d.querySelector('.slot')||{}).innerText||'',"
            " pick:(d.querySelector('.pick')||{}).innerText||''}))")

    def decs(self, pattern=""):
        # the pattern is passed as an ARGUMENT, not interpolated: an empty pattern interpolated into
        # a JS regex literal produces `//`, which is a line comment, not a match-anything regex
        return self.pg.evaluate(
            "p => [...document.querySelectorAll('#decisions [data-dec]')]"
            ".map(s=>s.dataset.dec).filter(d=>new RegExp(p).test(d))", pattern)

    def options(self, did):
        return self.pg.evaluate(
            "d => [...document.querySelector('[data-dec=\"'+d+'\"]').options].map(o=>o.value)", did)

    def choose(self, did, value):
        self.pg.select_option("[data-dec='%s']" % did, value)
        self.pg.wait_for_timeout(250)

    def start(self, cls):
        # Always a REAL page load in a FRESH TAB, never a re-select of the value already in #charsel.
        # Selecting the same option fires no change event, so the journey would silently run on top
        # of the previous one's character. Pyodide is warm in the HTTP cache, so this is ~3 seconds.
        self.recycle()
        self.pg.goto("%s?new=%s" % (self.url, cls))
        self.pg.wait_for_function(
            "!/Booting|Installing/.test(document.getElementById('status').innerText)",
            timeout=300000)
        self.pg.wait_for_function(
            "document.querySelectorAll('#decisions .dec').length > 0", timeout=120000)
        self.pg.wait_for_timeout(250)

    def point_buy(self):
        for a, v in (("might", "3"), ("agility", "1"),
                     ("charisma", "0"), ("intelligence", "0")):
            self.pg.select_option("[data-attr='%s']" % a, v)
            self.pg.wait_for_timeout(150)

    def ancestry(self, name):
        self.pg.select_option("#m-anc1", name)
        self.pg.wait_for_timeout(600)

    def add_trait(self, name):
        self.pg.click("#tradd")
        self.pg.wait_for_timeout(500)
        did = self.decs("trait")[-1]
        self.choose(did, name)
        self.pg.wait_for_timeout(350)

    def add_level(self):
        self.pg.click("#addlevel")
        self.pg.wait_for_timeout(700)


# ------------------------------------------------------------------ journeys
def j_boot_and_class_features(P, classes, cfcat):
    """(S1) Every scratch class boots, renders derived stats, and shows its L1 class features BY NAME.
    This is the BUG-19 + BUG-31 guard: the names live in class_features.yaml, and the only way they
    reach the browser is through the baked catalog and the generated CATPATHS. When BUG-31 shipped,
    the model held these and the page showed nothing, and every model-level harness passed."""
    print("## (S1) boot + L1 class features render by name, per scratch class")
    for cls in classes:
        P.start(cls)
        hp = P.stat("HP")
        ok("%-11s derived stats render (HP is a number)" % cls,
           hp is not None and hp.lstrip("-").isdigit(), hp)
        want = [f["name"] for f in
                (((cfcat.get("classes") or {}).get(cls.title()) or {}).get(1) or [])]
        shown = " | ".join(r["pick"] for r in P.rows()
                           if "class_feature" in r["slot"].lower())
        missing = [w for w in want if w not in shown]
        ok("%-11s all %d L1 catalog features appear in the page" % (cls, len(want)),
           bool(want) and not missing, "missing %s | shown %r" % (missing, shown[:120]))
        ok("%-11s no bare 'Class Feature' placeholder rendered" % cls,
           "Class Feature" not in shown or not want, shown[:120])


def j_trait_effects(P, anccat):
    """(S2) CH-5: a picked ancestry trait moves the RENDERED derived stat by the catalog's own amount.
    Covers both `grants` and `grants_unarmored`. The coverage check at the end is the anti-mirror
    guard: a new flat-stat trait in the catalog with no journey here fails."""
    print("## (S2) ancestry trait effects reach the rendered stats table (CH-5)")
    traits = anccat.get("ancestries") or {}
    for anc, prereqs, name in TRAIT_JOURNEYS:
        row = next((r for r in (traits.get(anc) or []) if r.get("name") == name), None)
        if row is None:
            ok("%s / %s present in ancestries.yaml" % (anc, name), False)
            continue
        want = flat_stat_grants(row)
        P.start("barbarian")
        P.point_buy()
        P.ancestry(anc)
        for pre in prereqs:
            P.add_trait(pre)
        before = P.stats()
        P.add_trait(name)
        after = P.stats()
        bad = []
        for k, delta in want.items():
            label = GRANT_STAT[k]
            try:
                got = int(after[label]) - int(before[label])
            except (KeyError, TypeError, ValueError):
                got = None
            if got != delta:
                bad.append("%s want %+d got %s" % (label, delta, got))
        ok("%-10s %-16s %s" % (anc, name,
                               ", ".join("%s %+d" % (GRANT_STAT[k], v) for k, v in want.items())),
           bool(want) and not bad, "; ".join(bad))
    # Coverage guard (the anti-mirror half): no trait NAME with a flat stat grant may exist in the
    # catalog without a journey above. Add a trait, and this fails until it is driven in a browser.
    covered = {n for _, _, n in TRAIT_JOURNEYS}
    uncovered = sorted({r["name"] for rows in traits.values() if isinstance(rows, list)
                        for r in rows if isinstance(r, dict) and flat_stat_grants(r)}
                       - covered)
    ok("every catalog trait name with a flat stat grant has a journey here",
       not uncovered, uncovered[:8])


def j_class_talents(P):
    """(S3) BUG-33: a class talent picked in the browser applies its grant. Spellblade's Expanded
    Disciplines is the sharpest case, because the effect is STRUCTURAL: two new discipline pickers
    must appear in the page, which is something only a DOM check can see. Note the levels: a
    Spellblade's talents land at L2 and L4 (L3 is the Subclass), so the journey advances to L4 and
    then FINDS the slot that offers the talent rather than assuming which level owns it."""
    print("## (S3) class talents apply their grants in the page (BUG-33)")
    P.start("spellblade")
    P.point_buy()
    P.ancestry("Human")
    for _ in range(3):
        P.add_level()
    did = next((d for d in P.decs("") if "Expanded Disciplines" in P.options(d)), None)
    ok("Expanded Disciplines is offered to an L4 Spellblade", did is not None)
    if did:
        before = len(P.decs("disc"))
        P.choose(did, "Expanded Disciplines")
        P.pg.wait_for_timeout(600)
        after = len(P.decs("disc"))
        ok("...and picking it renders 2 more discipline pickers",
           after - before == 2, "%d -> %d" % (before, after))
        # BUG-34: those two pickers are grant-children, and a grant-child that is itself
        # grant-bearing must still apply its own effect. Magus is {mp: 1, spells: 1}.
        kids = [d for d in P.decs("^GC#") if "disc" in d]
        if len(kids) >= 1 and "Magus" in P.options(kids[0]):
            b = (P.stat("MP"), P.stat("Spells known"))
            P.choose(kids[0], "Magus")
            P.pg.wait_for_timeout(500)
            a = (P.stat("MP"), P.stat("Spells known"))
            ok("...and a granted Magus discipline still applies its own +1 MP / +1 spell",
               int(a[0]) - int(b[0]) == 1 and int(a[1]) - int(b[1]) == 1,
               "MP/Spells %s -> %s" % (b, a), bug="BUG-34")
        else:
            ok("a granted discipline picker offers Magus", False, kids[:3])
    P.start("barbarian")
    P.point_buy()
    P.ancestry("Human")
    for _ in range(2):
        P.add_level()
    did = next((d for d in P.decs("")
                if "Unfathomable Strength" in P.options(d)), None)
    ok("Unfathomable Strength is offered to an L3 Barbarian", did is not None)
    if did:
        before = P.stat("Jump Distance")
        P.choose(did, "Unfathomable Strength")
        P.pg.wait_for_timeout(400)
        after = P.stat("Jump Distance")
        ok("...and picking it raises the rendered Jump Distance by 1",
           int(after) - int(before) == 1, "%s -> %s" % (before, after))


def j_sheet(P, cfcat):
    """(S4) BUG-32: the character sheet overlay must DISPLAY everything the model holds. The sheet had
    been silently dropping whole slot kinds for weeks while every per-feature test passed, because
    nothing checked the artifact against the model. Here: a fresh barbarian's L1 class features must
    appear on the sheet, not just in the decision list."""
    print("## (S4) character sheet renders the groups the model holds (BUG-32)")
    P.start("barbarian")
    P.pg.click("#sheetbtn")
    P.pg.wait_for_selector("#sheetOverlay", state="visible", timeout=30000)
    P.pg.wait_for_timeout(600)
    text = P.pg.inner_text("#sheetOverlay")
    ok("the sheet overlay opens and has content", len(text) > 200, len(text))
    want = [f["name"] for f in
            (((cfcat.get("classes") or {}).get("Barbarian") or {}).get(1) or [])]
    missing = [w for w in want if w not in text]
    ok("the L1 class features reach the SHEET, not just the decision list",
       bool(want) and not missing, missing)
    P.pg.click("#shClose")
    P.pg.wait_for_timeout(300)


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--require", action="store_true",
                    help="fail if Playwright or its browser is missing (use in CI)")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--only", default="",
                    help="comma-separated section ids to run (s1,s2,s3,s4). Each section is "
                         "independent, so this both speeds up debugging and lets a memory-tight "
                         "machine run the suite in slices.")
    ap.add_argument("--port", type=int, default=8891)
    args = ap.parse_args()

    if not os.path.exists(PAGE):
        print("FAIL - %s does not exist; run tools/builder_build.py first" % PAGE)
        sys.exit(1)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        msg = ("Playwright is not installed. Install with:\n"
               "    pip install playwright --break-system-packages\n"
               "    python3 -m playwright install --with-deps chromium")
        if args.require:
            print("FAIL - " + msg)
            sys.exit(1)
        print("SKIPPED - " + msg)
        sys.exit(0)

    classes = sorted((load("class_spines") or {}).get("classes", {}).keys())
    classes = [c.lower() for c in classes] or ["barbarian", "commander", "druid",
                                               "spellblade", "warlock"]
    cfcat = load("class_features")
    anccat = load("ancestries")

    httpd = serve(args.port)
    url = "http://127.0.0.1:%d/builds/builder.html" % args.port
    print("driving %s" % url)
    try:
        with sync_playwright() as p:
            launch = functools.partial(p.chromium.launch, headless=not args.headed)
            try:
                launch().close()
            except Exception as e:
                httpd.shutdown()
                msg = ("could not launch chromium (%s). Install it with:\n"
                       "    python3 -m playwright install --with-deps chromium"
                       % str(e).splitlines()[0][:120])
                if args.require:
                    print("FAIL - " + msg)
                    sys.exit(1)
                print("SKIPPED - " + msg)
                sys.exit(0)
            P = Page(launch, url)
            P.pg.goto(url)
            print("## (S0) Pyodide boot")
            P.pg.wait_for_function(
                "!/Booting|Installing/.test(document.getElementById('status').innerText)",
                timeout=300000)
            ok("the page boots Pyodide and clears its booting banner", True)
            # A wall-clock watchdog per journey. Playwright's own timeouts cover "the selector never
            # showed up"; they do NOT cover "the renderer died", where the CDP call simply never
            # returns. Closing the browser from another thread makes that blocked call raise, so a
            # wedged run reports a failure instead of hanging forever in CI.
            def watchdog(seconds):
                t = threading.Timer(seconds, lambda: _force_close(P.browser))
                t.daemon = True
                t.start()
                return t

            # each journey is isolated: a blow-up in one is reported as a failure and the rest still
            # run, so one bad selector never costs a whole run's worth of signal
            want = {s.strip().lower() for s in args.only.split(",") if s.strip()}
            for sid, fn, arg, budget in (("s1", j_boot_and_class_features, (classes, cfcat), 240),
                                         ("s2", j_trait_effects, (anccat,), 400),
                                         ("s3", j_class_talents, (), 240),
                                         ("s4", j_sheet, (cfcat,), 120)):
                if want and sid not in want:
                    continue
                t = watchdog(budget)
                try:
                    fn(P, *arg)
                except Exception as e:
                    ok("journey %s completed without raising" % fn.__name__, False,
                       str(e).splitlines()[0][:160])
                finally:
                    t.cancel()
            print("## (S5) console health")
            ok("no uncaught page errors during any journey",
               not P.errors, P.errors[:3])
            try:
                P.browser.close()
            except Exception:
                pass
    finally:
        httpd.shutdown()

    print("=" * 62)
    if KNOWN_HITS:
        print("%d known failure(s), each tracked as an open bug in builds/BACKLOG.md:"
              % len(KNOWN_HITS))
        for k in KNOWN_HITS:
            print("  - " + k)
        print("-" * 62)
    if FAILS:
        print("FAIL - %d check(s) failed:" % len(FAILS))
        for f in FAILS:
            print("  - " + f)
        sys.exit(1)
    print("PASS - the deployed page boots, renders and responds in a real browser:")
    print("       every scratch class shows its L1 class features BY NAME (BUG-19/31)")
    print("       ancestry traits move the rendered derived stats (CH-5, grants + grants_unarmored)")
    print("       class talents apply flat and structural grants (BUG-33)")
    print("       the character sheet displays what the model holds (BUG-32)")
    sys.exit(0)


if __name__ == "__main__":
    main()
