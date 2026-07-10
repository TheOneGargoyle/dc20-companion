#!/usr/bin/env python3
"""Build the DC20 Companion single-file HTML app."""
import base64, io, json, re, sys, tempfile
from pathlib import Path
import markdown
try:
    from PIL import Image  # only needed if the maps block is restored for a local build
except ImportError:
    Image = None

CAMP = Path(__file__).resolve().parent.parent  # campaign folder = parent of companion-src
OUT = CAMP / "DC20 Companion (GM).html"
TEMPLATE = Path(__file__).parent / "template.html"

MD = markdown.Markdown(extensions=["tables", "fenced_code", "sane_lists"])

def render(md_text: str) -> str:
    MD.reset()
    html = MD.convert(md_text)
    return html.replace("</", "<\\/")  # keep </script> etc. safe inside JS strings? no—this is for embedding

def render_raw(md_text: str) -> str:
    MD.reset()
    return MD.convert(md_text)

def split_sections(text: str, fname: str, min_level=2, max_level=3):
    """Split markdown into sections by ## and ### headings."""
    lines = text.split("\n")
    sections = []
    cur_title, cur_lines = None, []
    pat = re.compile(r"^(#{%d,%d})\s+(.*)" % (min_level, max_level))
    preamble = []
    for ln in lines:
        m = pat.match(ln)
        if m:
            if cur_title is not None:
                sections.append((cur_title, "\n".join(cur_lines)))
            elif cur_lines:
                preamble = cur_lines
            cur_title = re.sub(r"[*_`]", "", m.group(2)).strip()
            cur_lines = []
        else:
            cur_lines.append(ln)
    if cur_title is not None:
        sections.append((cur_title, "\n".join(cur_lines)))
    elif cur_lines:
        preamble = cur_lines
    out = []
    if preamble and any(l.strip() for l in preamble):
        # find the H1 for a title
        t = fname
        for l in preamble:
            if l.startswith("# "):
                t = l[2:].strip()
                break
        out.append((t + " — intro", "\n".join(preamble)))
    out.extend(sections)
    return out

def clean_for_search(md_text: str) -> str:
    t = re.sub(r"[#*_`>|\[\]()]", " ", md_text)
    t = re.sub(r"\s+", " ", t)
    return t.lower().strip()

# ---------- PDF-extraction reformatter ----------
STOPWORDS = {"a","an","and","as","at","by","for","from","in","into","of","on","or",
             "per","the","to","vs","vs.","with","your","you","d20","d4","d6","d8","d10","d12"}
SENT_STARTERS = {"The","If","When","While","You","Your","It","Its","This","That","These","Those",
                 "A","An","In","On","At","For","To","Once","After","Before","During","Then",
                 "They","There","He","She","We","I","Make","Making","Each","Any","All","Some",
                 "Both","Their","Instead","However","Additionally","Otherwise","See","Only"}
TIP_SPLIT = re.compile(r"\s+(?=(?:DC Tip|Examples?|Player Tip|GM Tip)\s*[:—-])")
TIP_HEAD = re.compile(r"^(DC Tip|Examples?|Player Tip|GM Tip)\s*[:—-]\s*(.*)", re.S)
LABEL = re.compile(r"(?:^|(?<=[.!?…”\")]))\s*([A-Z][A-Za-z’'()\d /&-]{1,30}?):(?=\s)")
RUNIN = re.compile(r"([.!?…”\")]) ((?:[A-Z][a-z’'-]{1,15}(?: |$)){1,3})(?=[A-Z])")
TRAIL = re.compile(r"([.!?…”\")]) ([A-Z][a-z’'-]+(?: (?:[a-z]{1,3}|[A-Z][a-z’'-]+)){0,3})\s*$")

def _valid_label(lbl: str) -> bool:
    core = re.sub(r"\([^)]*\)", "", lbl).strip()
    words = core.split()
    if not (1 <= len(words) <= 4):
        return False
    if words[0][0].islower():
        return False
    caps = sum(1 for w in words if w[0].isupper())
    return caps >= max(1, len(words) - 2)

def _valid_runin(phrase: str) -> bool:
    words = phrase.strip().split()
    if not (1 <= len(words) <= 3) or len(phrase) > 36:
        return False
    if words[0] in SENT_STARTERS or words[0].lower() in STOPWORDS:
        return False
    return all(w[0].isupper() or w.lower() in STOPWORDS for w in words)

def _labels(seg: str) -> str:
    def rep(m):
        return "\n\n**" + m.group(1) + ":**" if _valid_label(m.group(1)) else m.group(0)
    return LABEL.sub(rep, seg)

def _runins(seg: str) -> str:
    def rep(m):
        ph = m.group(2).strip()
        return m.group(1) + "\n\n**" + ph + "**\n\n" if _valid_runin(ph) else m.group(0)
    seg = RUNIN.sub(rep, seg)
    def rep2(m):
        ph = m.group(2).strip()
        return m.group(1) + "\n\n**" + ph + "**" if _valid_runin(ph) else m.group(0)
    return TRAIL.sub(rep2, seg)

def process_paragraph(p: str):
    """Unwrapped paragraph -> list of markdown blocks (tips as blockquotes, labels/headings broken out)."""
    blocks = []
    for seg in TIP_SPLIT.split(p):
        seg = seg.strip()
        if not seg:
            continue
        m = TIP_HEAD.match(seg)
        if m:
            blocks.append("> **%s:** %s" % (m.group(1), m.group(2).strip()))
        else:
            blocks.append(_runins(_labels(seg)).strip())
    return blocks

def looks_like_heading(line: str, prev: str) -> bool:
    s = line.strip()
    if not (2 <= len(s) <= 48):
        return False
    if s[-1] in ".!?,;:—-" or s.endswith("…"):
        return False
    if s[0].islower() or s[0] in "([&+*>#|0123456789":
        return False
    p = prev.strip()
    if p and p[-1] not in ".!?:”\")" and len(p) > 40 and not p.endswith("Sidebar"):
        return False
    if p.endswith((",", ";", "—", "-", " and", " or", " the", " a", " an", " of", " to", " with")):
        return False
    core = re.sub(r"\([^)]*\)", "", s)
    if re.search(r"\d", core):
        return False
    words = [w for w in re.split(r"[\s/–—-]+", core) if w]
    if not words or len(words) > 7:
        return False
    for w in words:
        if w[0].islower() and w.lower() not in STOPWORDS:
            return False
    return True

def reflow_pdf_text(text: str) -> str:
    out, buf = [], []
    prev = ""
    def flush():
        if buf:
            for b in process_paragraph(" ".join(buf)):
                out.append("")
                out.append(b)
            out.append("")
            buf.clear()
    for ln in text.split("\n"):
        s = ln.strip()
        if not s or s.startswith(("#", ">", "|", "-", "*", "+")) or re.match(r"^\d+\.", s):
            flush(); out.append(ln); prev = ln; continue
        if looks_like_heading(s, prev):
            flush(); out.extend(["", "**%s**" % s, ""]); prev = ln; continue
        buf.append(s); prev = ln
    flush()
    return "\n".join(out)

REFLOW_FILES = {"core-rules.md","combat.md","general-rules.md","classes.md","spells.md",
                "ancestries.md","character-creation.md","starting-combat.md",
                "encounter-building.md","bestiary.md","challenges.md"}

# (2026-07-05, superseded same day: the strip_class_table_blobs() build-time workaround
# was removed — classes.md itself was repaired at the source instead: the 13 garbled
# PDF class-table blobs replaced with the hand-rebuilt tables from tables.md (as ####
# sub-sections inside each class), the two mid-sentence '### Shields' promotions and
# the duplicate '### Barbarian' rejoined, and the 13 generic '### Subclasses' headings
# renamed to '### <Class> Subclasses'.)

# ---------- rules cleanup helpers ----------
def _plain(md):
    return re.sub(r"\s+", " ", re.sub(r"[#>*_`|]", " ", md)).strip()

def _trivial_intro(body):
    keep = [l for l in body.split("\n")
            if l.strip() and not l.lstrip().startswith(("#", ">"))
            and "Source:" not in l and ".pdf" not in l.lower() and "Audience:" not in l]
    return len(" ".join(keep).strip()) < 120

# ---------- rules data ----------
rules_data = []
rule_files = sorted((CAMP / "rules").glob("*.md"))
order = ["_INDEX.md", "house-rules.md", "core-rules.md", "combat.md", "starting-combat.md",
         "general-rules.md", "classes.md", "spells.md", "ancestries.md", "character-creation.md",
         "challenges.md", "tables.md", "bestiary.md", "encounter-building.md", "changelog.md"]
rule_files.sort(key=lambda p: order.index(p.name) if p.name in order else 99)
for f in rule_files:
    if f.name in ("_INDEX.md", "house-rules.md"):
        continue  # navigation/meta index + the table's own house rules — not part of the DC20 rules browser
    text = f.read_text(encoding="utf-8", errors="replace")
    if f.name in REFLOW_FILES:
        text = reflow_pdf_text(text)
    label = f.stem.replace("_", "").replace("-", " ").title()
    for title, body in split_sections(text, label):
        if not body.strip():
            continue
        if title.endswith("— intro") and _trivial_intro(body):
            continue  # drop 'File — intro' stubs that are just the source-pdf blurb
        if len(_plain(body)) < 40:
            continue  # drop truncated fragment sections (e.g. 'Attributes &')
        rules_data.append({
            "f": label, "t": title,
            "h": render_raw(body),
            "x": clean_for_search(title + " " + body),
        })
print(f"rules sections: {len(rules_data)}")

# Merge sections that share (file, title) — the PDF's repeated running-headers
# produce duplicate/fragment sections (e.g. 5x "Maneuvers"); consolidate them in order.
_merged = {}; _order = []
for _r in rules_data:
    _k = (_r["f"], _r["t"])
    if _k in _merged:
        _merged[_k]["h"] += _r["h"]; _merged[_k]["x"] += " " + _r["x"]
    else:
        _merged[_k] = _r; _order.append(_k)
rules_data = [_merged[_k] for _k in _order]
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

def assemble(gm: bool) -> str:
    tpl = TEMPLATE.read_text(encoding="utf-8")
    tpl = tpl.replace("__RULES_DATA__", js_embed(rules_data))
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
