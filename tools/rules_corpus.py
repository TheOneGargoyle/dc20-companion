#!/usr/bin/env python3
"""Shared DC20 rules-corpus builder.

Single source of truth for the searchable/linkable rules corpus used by BOTH
the Companion (companion-src/build.py, its Rules browser) and the builder
(tools/builder_build.py, FR-6 rule links on chosen options). Keeping the
section-split / PDF-reflow / merge logic in one module guarantees the two apps
bake byte-identical corpora and cannot drift. Extracted verbatim from
companion-src/build.py (2026-07-17, FR-6); no behaviour change.
"""
import json
import re
from pathlib import Path

import markdown

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

# ---------- rules cleanup helpers ----------
def _plain(md):
    return re.sub(r"\s+", " ", re.sub(r"[#>*_`|]", " ", md)).strip()

def _trivial_intro(body):
    keep = [l for l in body.split("\n")
            if l.strip() and not l.lstrip().startswith(("#", ">"))
            and "Source:" not in l and ".pdf" not in l.lower() and "Audience:" not in l]
    return len(" ".join(keep).strip()) < 120

# ---------- corpus assembly ----------
def build_rules_data(camp):
    """Return the merged rules corpus (list of {f,t,h,x}) from <camp>/rules/*.md.

    Identical to the logic previously inline in companion-src/build.py. camp is
    the campaign root (Path); the Companion passes its CAMP, the builder passes REPO.
    """
    camp = Path(camp)
    rules_data = []
    rule_files = sorted((camp / "rules").glob("*.md"))
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
    return rules_data

def corpus_embed(obj) -> str:
    """JS-safe embed of the corpus (matches companion-src/build.py js_embed)."""
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


# ---------- CH-11: the linkable-term index ----------
# The builder used to bake the whole 2.1MB corpus into builder.html purely so `_linkable` could
# answer, at INITIAL RENDER, "does this option have a rule to show?" (it gates the `rule` chip on
# every option row). Only two questions are asked that early:
#   single word  -> is it a bolded/heading term anywhere in the rules?   (the JS `DEFINED` set)
#   multi word   -> does the phrase occur in the plain-text corpus?      (the JS `_corpusHas`)
# Both are decidable at build time, and the answers compress to about 40KB, so the corpus itself
# moves to a fetched artifact and only the answers stay in the page.
#
# PARITY IS THE WHOLE POINT. These constants and regexes mirror the page's JS exactly. If you
# change one side, change the other, and let builder_verify's equivalence check catch you: it
# replays both implementations over every term either could ever be asked about.
JS_STOP = {"same", "each", "both", "more", "move", "hit", "turn", "target", "attack", "damage",
           "with", "when", "your", "this", "that", "from", "into", "also", "next", "once",
           "they", "their", "then", "than", "only", "used", "gain", "give", "make", "take", "have"}
_BOLD_RE = re.compile(r"<(?:strong|b|h[1-6])[^>]*>([^<]{2,40})</(?:strong|b|h[1-6])>", re.I)
_H3_RE = re.compile(r"<h3>([^<]{3,48}?)(\s*)(<span|</h3>)", re.I)


def js_clean(text: str) -> str:
    """The page's `_clean`: drop a parenthetical tail, drop a colon/semicolon tail, collapse space."""
    t = re.sub(r"\s*\(.*$", "", str(text))
    t = re.sub(r"[:;].*$", "", t)
    return re.sub(r"\s+", " ", t).strip()


def search_corpus(data) -> str:
    """The page's `RULE_CORPUS`: every section's search text, space-delimited for phrase lookup."""
    joined = " ".join(s.get("x") or "" for s in data)
    joined = re.sub(r"[^a-z0-9 '’/-]+", " ", joined)
    return " " + re.sub(r"\s+", " ", joined) + " "


def defined_words(data) -> set:
    """The page's `DEFINED`: single words that appear bolded or as a heading somewhere."""
    out = set()
    for s in data:
        for m in _BOLD_RE.finditer(s.get("h") or ""):
            t = re.sub(r"[:.,;]+$", "", m.group(1)).lower().strip()
            if t and " " not in t and len(t) >= 4 and t not in JS_STOP:
                out.add(t)
    return out


def phrase_candidates(data, extra=()) -> set:
    """Every multi-word phrase `_linkable` could ever be asked about.

    Two sources, and they are exhaustive by construction. `linkifyTerms` only ever asks about text
    the corpus itself emphasises, so bold/h3 text covers the in-panel cross-links; `ruleTag` only
    ever asks about a decision row's name, so the catalog/ledger strings passed in as `extra` cover
    the option chips. A phrase outside both sets cannot be clicked, because nothing renders it.
    """
    out = set()
    for s in data:
        h = s.get("h") or ""
        for m in _BOLD_RE.finditer(h):
            t = js_clean(re.sub(r"[:.,;]+$", "", m.group(1))).lower()
            if " " in t:
                out.add(t)
        for m in _H3_RE.finditer(h):
            t = js_clean(m.group(1)).lower()
            if " " in t:
                out.add(t)
    for e in extra:
        t = js_clean(e).lower()
        if " " in t:
            out.add(t)
    return out


def linkable_index(data, extra=()) -> dict:
    """{"d": [single words], "m": [multi-word phrases that occur]} - the baked answer set."""
    corpus = search_corpus(data)
    multi = sorted(t for t in phrase_candidates(data, extra) if (" " + t + " ") in corpus)
    return {"d": sorted(defined_words(data)), "m": multi}
