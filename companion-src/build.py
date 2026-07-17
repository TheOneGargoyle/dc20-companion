#!/usr/bin/env python3
"""Build the DC20 Companion single-file HTML app."""
import base64, io, json, os, re, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path
import markdown
try:
    from PIL import Image  # only needed if the maps block is restored for a local build
except ImportError:
    Image = None

CAMP = Path(__file__).resolve().parent.parent  # campaign folder = parent of companion-src
sys.path.insert(0, str(CAMP / "tools"))
from rules_corpus import render_raw, split_sections, build_rules_data  # FR-6: shared rules corpus

OUT = CAMP / "DC20 Companion (GM).html"
TEMPLATE = Path(__file__).parent / "template.html"

# ---------- rules data (shared module: tools/rules_corpus.py) ----------
rules_data = build_rules_data(CAMP)
print(f"rules sections after cleanup+merge: {len(rules_data)}")

# ---------- GM data ----------
gm_files = ["03_factions_GM.md", "04_secrets_GM.md", "05_threads_and_clues_GM.md",
            "06_pacing_and_levelling_GM.md", "09_cogm_agenda_GM.md", "_SESSION_LOG.md"]
gm_labels = {"03_factions_GM.md": "03 Factions", "04_secrets_GM.md": "04 Secrets",
             "05_threads_and_clues_GM.md": "05 Threads & Clues",
             "06_pacing_and_levelling_GM.md": "06 Pacing & Levelling",
             "09_cogm_agenda_GM.md": "09 Co-GM Agenda", "_SESSION_LOG.md": "Session Log"}
gm_data = []
for name in gm_files:
    p = CAMP / name
    if not p.exists():
        continue
    text = p.read_text(encoding="utf-8", errors="replace")
    secs = [{"t": t, "h": render_raw(b)} for t, b in split_sections(text, gm_labels[name]) if b.strip()]
    gm_data.append({"f": gm_labels[name], "secs": secs})
print(f"gm files: {len(gm_data)}")

# ---------- party derived stats (baked from the build ledgers) ----------
# Runs the true build engine (tools/build_engine.py) over builds/<handle>.yaml and
# bakes the derived numbers into the page as PARTY_DERIVED; template.html merges them
# over CHARS at load. This closes the rung-3 loop: commit an updated ledger -> the
# Action (which already watches builds/**) rebuilds -> the Companion shows the new
# numbers. Hand-authored CHARS prose (toggles, notes, audits, skills, saves) is
# untouched; only engine-derived numbers are overwritten.
import importlib.util as _ilu
try:
    import yaml
except ImportError:
    sys.exit("build.py now needs PyYAML for the party-stats stage (pip install pyyaml)")
_spec = _ilu.spec_from_file_location("build_engine", CAMP / "tools" / "build_engine.py")
_be = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_be)

PARTY_LEDGERS = {  # CHARS key -> ledger file (the curated include set, by id — see RUNG3_PLAN section 8)
    "tan": "tanrielle.yaml", "min": "minimus.yaml", "runt": "runt.yaml",
    "scale": "scaletrix.yaml", "bonan": "bonan.yaml", "xan": "xanwyn.yaml",
}
# Companion-display deltas ON TOP of engine-derived values — each documented in the
# ledger itself. These preserve the table-facing numbers the party plays with:
#  - xan hp +2: Amulet of Health (worn item; the ledger's expected block deliberately
#    excludes it as an "equipment overlay" — xanwyn.yaml).
#  - (runt pd +2 delta RETIRED 2026-07-16: BUG-7 closed. The armour is Deflecting Heavy
#    (+2 PD) and Pact Armor's +1 is AD not PD, so the engine now derives PD 16 / AD 13
#    directly = Phil's confirmed reading. The Primal Hide +2 toggle brings PD to 18 in play.)
DISPLAY_DELTAS = {("xan", "hp"): 2}

party_derived = {}
for _k, _fn in PARTY_LEDGERS.items():
    _led = yaml.safe_load((CAMP / "builds" / _fn).read_text(encoding="utf-8"))
    _lvl = _led["current_level"]
    _rep = _be.replay(_led, _lvl)
    _d = _rep.derived
    party_derived[_k] = {
        "level": _d["Level"], "cm": _d["Combat Mastery"],
        "attack": _d["Attack/Spell Check"], "save_dc": _d["Save DC"],
        "initiative": _d["Initiative"], "grit": _d["Grit"],
        "hp": _d["HP"], "sp": _d["SP"], "mp": _d["MP"],
        "pd": _d["PD"], "ad": _d["AD"],
        "dr": _d.get("dr", {}),  # FR-16A: engine-derived Damage Reduction, e.g. {"PDR":["half"],"MDR":["half"]}
    }
    for (_dk, _f), _delta in DISPLAY_DELTAS.items():
        if _dk == _k:
            party_derived[_k][_f] += _delta
    for _p in _rep.problems:
        print(f"  ledger flag ({_fn}): {_p}")  # known audit items surface here; the oracle is catalog_verify.py
print("party derived: " + ", ".join(
    f"{k} L{v['level']} hp{v['hp']} pd{v['pd']}" for k, v in party_derived.items()))

# ---------- geography & maps ----------
# REMOVED 2026-07-05 (IP hygiene): the Maps tab was retired and replaced by an
# About tab (template.html). The map images (World/Region unaltered Games Workshop
# material; Local ~90% GW-derived) are NOT open-licensed and must NOT ship in the
# published, publicly-hosted build. The DC20 rules DO ship — DC20 is released under
# the ORC license — with attribution in the About tab. The geography prose
# (known-geography.md) is our own but was tied to the Maps tab, so it goes too.
# The template no longer references __GEO_HTML__ / __MAPS__, so nothing is injected.
# To restore maps for a LOCAL-only build, re-add the encode_map()/maps block and the
# two .replace() lines in assemble() — but never publish that build. (PIL/`Image`
# import kept only in case that block is restored.)

# ---------- Tan accordions (hand-crafted from 08/07, cited facts only) ----------
TAN_ACCORDIONS = """
<details open><summary>Spells (3) &amp; Pact riders</summary><div class="inner">
<div class="card"><h3>Radiant Bolt <span class="small">(Invocation · standing Pact Spell · vs PD)</span></h3>
Her spine spell — usually folded into a greatsword swing via <b>Spellstrike</b> (1 AP less, one combined attack; crit/Heavy applies once to the package).<br>
<b>Pact riders:</b> Death's Toll (+1 dmg vs Bloodied) · Range Increase · <b>Patron's Favor</b> (free ADV to cast it, 1/round).<br>
<b>Expose (+1 MP):</b> target fails a Physical Save → <b>Exposed</b> (allies attack it with ADV). The headline enabler move.
</div>
<div class="card"><h3>Close Wounds <span class="small">(Invocation · 1 AP)</span></h3>
The RP-funded heal — refunds Life-Tapped HP out of combat via Rest Points, keeping the pools for allies.
</div>
<div class="card"><h3>Primal Hide <span class="small">(buff)</span></h3>
Her armour spell — PD 17 → <b>19</b> while up (the sheet default). Toggle it on the tracker above.
</div>
</div></details>

<details><summary>Maneuvers (4)</summary><div class="inner">
<div class="card"><h3>Parry <span class="small">(reaction)</span></h3>+5 PD against a hit — reactions on others' turns are <b>MCP-exempt</b> (roll clean). Maths says Parry beats Side Step for pure mitigation at every accuracy.
</div>
<div class="card"><h3>Swift Strike <span class="small">(1 AP + 1 SP)</span></h3>Move up to Speed (6) + melee attack — her cheap gap-closer (swapped in for Side Step, 2026-06-20).<br>
<b>Subsequent Strike (+1 AP +1 SP):</b> +½ Speed move, attack a 2nd creature with the <b>same</b> Attack Check (no MCP). Ruling settled: bonus damage (Smite/Spellstrike rider) applies to <b>one</b> target only; Heavy/Crit computes per target. The two-target line: 6.00 EV vs 5.69 for two normal attacks.
</div>
<div class="card"><h3>Meteor Strike <span class="small">(1 AP + 1 SP)</span></h3>Jump-and-strike; her only other 1-AP gap-close. <b>Table ruling (settled):</b> it's a Standing Jump → halved → Agility 3 +2 = 5, halved, round up = <b>3 Spaces</b>. Blink Blade's 1-Space teleport makes effective reach ≈ 4. <b>Impact Crater (+1 AP +1 SP):</b> aura save-or-<b>Prone</b>. Remember: Prone helps <i>melee</i> allies (ADV), hurts ranged (DisADV).
</div>
<div class="card"><h3>Whirlwind</h3>1-Space aura attack vs AD — taken at L4 to be ready for the L5 <b>Whirlwind + Luminous Burst</b> AoE Spellstrike combo.
</div>
</div></details>

<details><summary>Class features &amp; kit</summary><div class="inner">
<div class="card"><h3>The engine</h3>
<b>Spellstrike</b> — once/turn, fold a spell into a Martial Attack for 1 AP less; one combined attack.<br>
<b>Bound Weapon</b> — Greatsword of the Keepers; bonded options <b>Illuminate, Smite, Recall</b>. Smite = +1 Bound dmg/SP + a free Martial Enhancement (her pick: +1 dmg) ⇒ <b>1 SP Smite = +2 dmg</b>, radiant (Divine Strike).<br>
<b>Stamina Regen (errata)</b> — once/round after a Bound-Weapon hit, Spell Check, or Weapon-tag spell: regain up to <b>2 SP</b> (half max). Smite every round is sustainable.<br>
<b>Life Tap</b> — pay MP costs with HP (total ≤ MSL 2), 1/Long Rest, <b>regained on Initiative</b>.<br>
<b>Acolyte + Lay on Hands</b> — 1 AP/1 MP heal pool (DC 10 Spell Check: pool 2/3, +1 per 5 over) or cure; LoH 1/LR = Acolyte at 0 MP and +5.<br>
<b>Aura of Protection</b> — allies within 2 Spaces: ADV on Mental Saves. Always on — remind the table!<br>
<b>Disciplines:</b> Acolyte, Blink Blade (1-Space teleport tied to attack, 1/turn), Magus (+1 MP, +1 spell).<br>
<b>Sense Magic (as played)</b> — broader than RAW at this table: senses magic generally (creatures, items, effects); adjudication loose/GM-driven, sometimes via Awareness.<br>
<b>Beseech Patron</b> — 1/LR, enter the Inner Sanctum to seek the Spirit of Nature. Run <b>off-session</b>, insight-only, lossy memory.</div>
<div class="card"><h3>Kit</h3>
<b>Greatsword of the Keepers</b> (2H/Heavy/Impact — base 2 slashing; Impact: +1 on Heavy Hits) + <b>Amulet of Steadfastness</b> = <b>Guardians' Regalia</b> set (Spell Focus properties stack; the 2-pt <b>Powerful</b> focus = +1 spell dmg, Jesse-approved through Spellstrike). Longbow · Light Armour (Fortified +2 AD) · First Aid Kit (5) · Healing Balm ×1.</div>
<div class="card"><h3>Saves &amp; attributes</h3>
Might 2 · Agility 3 · Int 3 · Cha −2 · <b>Prime 3</b>.<br>Saves: Mig +4 · Agi +5 · Int +5 · Cha +0.<br>Ancestry: Human (Attr→Might, Trade Expertise→Herbalism) · Elf (Discerning Sight, Nimble, Speed Increase).</div>
</div></details>

<details><summary>⚡ Signature plays (cheat sheet)</summary><div class="inner">
<div class="card"><h3>1 · Expose setup <span class="small">(the enabler default)</span></h3>
Greatsword attack + <b>Spellstrike Radiant Bolt + Expose (1 MP)</b> → target <b>Exposed</b>, allies swing at ADV. Patron's Favor makes the cast reliable (free ADV). Add Smite (1 SP → +2) for personal damage. ~1 MP/round is her sustainable budget; MSL 2/action = nova only.</div>
<div class="card"><h3>2 · All-out offense <span class="small">(when the target must die NOW)</span></h3>
<b>Attack 1:</b> Swift Strike + Smite — 2 AP / 3 SP → 5 base / 7 Heavy (1 AP buys ADV).<br>
<b>Attack 2:</b> Spellstrike Radiant Bolt (Pact) — 2 AP / 1 MP → 6 base / 8 Heavy, +1 vs Bloodied (Patron's Favor nets ADV1).<br>
<b>Turn: 4 AP / 3 SP / 1 MP · EV ≈ 13</b> (ceiling 15 all-Heavy). Nova top-up: +2 MP on Attack 2 → EV ≈ 17. Use deliberately, not as the default gear (Tightrope 1).</div>
<div class="card"><h3>3 · Healing engine <span class="small">(L4 version)</span></h3>
<b>Lay on Hands → Acolyte Heal</b>: 0 MP, Spell Check +5 <b>+5</b> = +10, DC 10 → pool ≈ 4.7–5.4, distribute within 5 Spaces. 1/Long Rest. (The big ~8–9 engine unlocks at L5 with Expert Spellblade's MP-scaling + Life Tap.)</div>
<div class="card"><h3>4 · Sparring partner reminders</h3>
Full Dodge habit (Nimble): bank 1 AP → attacks at you at DisADV — but attackers can buy ADV to cancel it.<br>
Defence-targeting choice: Radiant Bolt hits <b>PD</b>, (L5) Luminous Burst hits <b>AD</b> — pick the weaker door.</div>
</div></details>

<details><summary>🎭 Player craft crib (Tightropes)</summary><div class="inner">
<div class="card"><h3>Tightrope 1 — spotlight</h3>
Calibrate, don't suppress. Risk is <b>cumulative</b>, not per-moment. Levers: build toward enabling (done), coach others, sequencing (go early sometimes; hand off finishing blows), spend the nova on beats that <i>matter</i>. All-out offense is a legitimate counter-gear when a protectee's attacker must die now — just don't let it become every fight.</div>
<div class="card"><h3>Tightrope 2 — GM knowledge</h3>
<b>Play the instinct, never the knowledge.</b> Play her doubting her own instinct (grief-haunted, unsure). Ask Jesse for diegetic cover; use the 30-second "am I leaking?" check-in. The Patron dream-link gives instincts a legitimate in-world origin — keep it rare, insight-only.</div>
<div class="card"><h3>Dump-stat playbook (Cha −2)</h3>
Cede the social lane to Bonan (and Runt/Minimus). In skill challenges: <b>Repeated Checks</b> pushes everyone onto their best skills — let it. Core move: <b>assist-Checks that arm the talker</b> (Herbalism/Nature/Medicine/Awareness feeds their leverage). Feed reads, don't deliver verdicts ("psst — he keeps eyeing the door"). Take the Help Action (1 AP) on a face PC's roll. Play the Cha whiff for comedy. Stay emotionally present — hand off the Check, not the character.</div>
</div></details>

<details><summary>📈 L5–L6 locked plan (snapshot)</summary><div class="inner">
<div class="card">
<b>L5:</b> CM→3, Agility→4 (Prime→4) ⇒ <b>Attack/Spell +7, Save DC 17, +2 PD</b>; MP 7, SP 4, MSL/SSL 3. Expert Spellblade (AoE Spellstrike; Acolyte MP-scaling; Bound dmg ignores Resistance). Spell: <b>Luminous Burst</b>. 4th Discipline: <b>Spell Breaker</b>. Skills: Awareness→Expert +10, Herbalism→Expert +9, Arcana/Nature→Adept +7.<br><br>
<b>L6:</b> Martial path (SP 5, regen 3, maneuver → <b>Side Step</b> restored). Talent: Expert MC Warlock → <b>Radiant Imbued + Bless</b>, 2nd Pact Spell (Luminous Burst), Life Tap grants ADV. Stealth→Adept +8.<br><br>
<b>Open:</b> the L8 Talent (deliberately uncommitted). Rulings parked for Jesse: the "additional-MP" healing reading (assumed generous) and Beseech Patron sign-off.</div>
</div></details>
"""

# ---------- assemble ----------
def js_embed(obj) -> str:
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")

GM_NAV_BUTTON = """  <button data-tab="gm" onclick="go('gm')"><span class="ic">🛡️</span>GM</button>\n"""

# ---------- build stamp (About tab) ----------
# Answers "did the page actually rebuild?" at a glance. Sydney wall-clock time
# (falls back to UTC if tzdata is missing) + the short commit SHA when built by
# the Action (GITHUB_SHA); local builds say "local".
try:
    from zoneinfo import ZoneInfo
    _now = datetime.now(ZoneInfo("Australia/Sydney"))
except Exception:
    _now = datetime.now(timezone.utc)
BUILD_STAMP = _now.strftime("%Y-%m-%d %H:%M %Z") + " · " + (os.environ.get("GITHUB_SHA", "local")[:7])
print(f"build stamp: {BUILD_STAMP}")

def assemble(gm: bool) -> str:
    tpl = TEMPLATE.read_text(encoding="utf-8")
    tpl = tpl.replace("__BUILD_STAMP__", BUILD_STAMP)
    tpl = tpl.replace("__RULES_DATA__", js_embed(rules_data))
    tpl = tpl.replace("__PARTY_DERIVED__", js_embed(party_derived))
    # Player edition: GM data is NEVER embedded (an in-file gate would be
    # cosmetic — the HTML source is readable), and the GM nav button is removed.
    tpl = tpl.replace("__GM_DATA__", js_embed(gm_data if gm else []))
    # __GEO_HTML__ / __MAPS__ removed 2026-07-05 (IP hygiene — see the geography & maps note above).
    tan_acc = TAN_ACCORDIONS
    if not gm:
        # Drop the two Darryl-facing accordions (player-craft crib + L5–L6 plan
        # — the latter references the private Patron thread agenda).
        cut = tan_acc.find('<details><summary>🎭 Player craft crib')
        assert cut > 0, "player-craft accordion anchor not found"
        tan_acc = tan_acc[:cut]
        # …and the Beseech Patron line in "Class features & kit" (private thread).
        assert "Beseech Patron" in tan_acc
        tan_acc = re.sub(r"<br>\n<b>Beseech Patron</b>[^\n]*?(?=</div>|\n)", "", tan_acc)
        assert "Beseech Patron" not in tan_acc
    tpl = tpl.replace("__TAN_ACCORDIONS__", js_embed(tan_acc))
    if gm:
        tpl = tpl.replace("<title>DC20 Companion — Shadowdale</title>",
                          "<title>DC20 Companion — Shadowdale (GM)</title>")
    else:
        assert tpl.count(GM_NAV_BUTTON) == 1, "GM nav button anchor not found"
        tpl = tpl.replace(GM_NAV_BUTTON, "")
    return tpl

OUT_PLAYER = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "dc20-companion" / "DC20 Companion.html"
OUT_PLAYER.parent.mkdir(parents=True, exist_ok=True)
OUT_PLAYER.write_text(assemble(gm=False), encoding="utf-8")
print(f"Wrote {OUT_PLAYER} — {OUT_PLAYER.stat().st_size/1024/1024:.2f} MB")
