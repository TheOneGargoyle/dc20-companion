#!/usr/bin/env python3
"""Generate builds/builder.html - the rung-3 character builder, ALL SIX characters
plus new-from-scratch mode.

Build-order step 5 (RUNG3_PLAN section 7) on top of the step-4 generalisation. The page:

- loads any of the six ledgers by handle (?char=tanrielle|... plus an on-page switcher),
  renders the full decision timeline, and edits decisions through the five reusable widgets
  (point-buy, option-picker, ancestry-spend, skill/trade allocator, review);
- ADD-A-LEVEL (the level-up-night flow): bumps current_level, generates the new level's
  decision slots from the class spine (talent/path/subclass/ancestry-points/attribute/
  spell/maneuver per level), or PROMOTES an existing plan level (e.g. Tanrielle's locked L5);
  the sheet-total 'expected' block is demoted to 'expected_at_L<n>' history because the new
  level's numbers now come FROM the builder;
- NEW-FROM-SCRATCH (?new=<class> or the switcher): a blank L1 ledger for any of the five
  walked classes, chargen driven entirely by the widgets (point-buy, ancestry pick + spend,
  spell schools, class L1 choices, background skill/trade/language points), exporting a
  valid new YAML;
- RESPEC POLISH (section 8): a loud you-are-editing-canon banner once a canonical ledger is
  dirty, respec export to <handle>.respec.yaml vs a confirm-gated canon export to
  <handle>.yaml, in-progress persistence via localStorage, and a load-your-own-YAML input
  (the section 5 self-serve round trip; the engine re-validates anything loaded);
- COMMENT-PRESERVING EXPORT: export_yaml() re-anchors the source ledger's own YAML
  comments (header provenance, EOL notes, aligned continuation blocks, section
  markers) onto the re-serialised file using composer line-paths (format-neutral,
  PyYAML only - no new deps); the expected <-> expected_at_L<n> rename is followed,
  and any comment whose anchor was edited away is collected, clearly marked, at the
  bottom of the file instead of being silently dropped.

Every edit re-runs the REAL tools/build_engine.py via Pyodide; the catalog files supply
option lists and the catalog-level legality pass; a builder-level pass reports undecided
slots. Bakes engine + full catalog + ALL SIX ledgers + a scripted spells-metadata extract
+ the glue module into ONE self-contained page (base64), fetch()-first with the bake as
the file:// fallback.

SCRIPTED - regenerate whenever the engine, catalog, or any ledger changes, so the page can
never drift from them (same discipline as tools/catalog_build.py):

    python3 tools/builder_build.py

Headless regression harness: python3 tools/builder_verify.py
"""
import argparse
import base64
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)  # tools/.. == campaign/repo root

CHARS = ["tanrielle", "runt", "minimus", "bonan", "scaletrix", "xanwyn"]
NEWCLASSES = ["spellblade", "warlock", "commander", "barbarian", "druid"]
CATALOG = NEWCLASSES + ["ancestries", "spell_schools", "spell_sources", "maneuvers",
           "talents", "skills_trades"]

# ---- scripted spells-metadata extract (the tag/school data the pickers need) ----

def extract_spell_meta(spells_md_path):
    meta = {}
    lines = open(spells_md_path, encoding="utf-8").read().splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith("School:") and i >= 2 and lines[i - 1].startswith("Source:"):
            name = lines[i - 2].strip()
            srcs = [s.strip() for s in lines[i - 1].split(":", 1)[1].split(",")]
            school = ln.split(":", 1)[1].strip()
            tags = []
            if i + 1 < len(lines) and lines[i + 1].startswith("Tags:"):
                tags = [t.strip() for t in lines[i + 1].split(":", 1)[1].split(",")]
            meta[name] = {"sources": srcs, "school": school, "tags": tags}
    return meta


# ---- Python glue that runs inside Pyodide (wraps the real engine + catalog) ----
API_PY = r"""
import copy
import json, re
import yaml
import build_engine as eng

EDITABLE_SLOTS = {'talent', 'path', 'subclass', 'discipline', 'spell', 'maneuver',
                  'attribute', 'ancestry_trait'}
PLACEHOLDER_MARKERS = ('not itemised', 'does NOT exist')
MASTERIES = [None, 'Novice', 'Adept', 'Expert']
UNDECIDED = '(undecided)'
BUILDER_NOTE = 'Added in builder'
LANG_COSTS = {'Limited': 1, 'Fluent': 2}
CLASS_NAMES = {'spellblade': 'Spellblade', 'warlock': 'Warlock', 'commander': 'Commander',
               'barbarian': 'Barbarian', 'druid': 'Druid'}
ATTRS = ('might', 'agility', 'charisma', 'intelligence')


def base_name(pick):
    return re.sub(r"\s*\([^)]*\)\s*$", '', str(pick).replace('’', "'")).strip()


def is_composite(pick):
    s = str(pick)
    return (',' in s or ' + ' in s or ':' in s.split('(')[0] and s.lower().startswith(('4th',))
            or any(m in s for m in PLACEHOLDER_MARKERS))


def blank_ledger(cls, ccat):
    sp1 = ccat['spine'][1]
    cg = {'attribute_method': 'point_buy',
          'attributes': {a: -2 for a in ATTRS},
          'ancestry_traits': [],
          'spells': [UNDECIDED] * sp1.get('spells', 0),
          'maneuvers': [UNDECIDED] * sp1.get('maneuvers', 0),
          'combat_training': []}
    sc = ccat.get('spellcasting') or {}
    if sc.get('model') == 'schools':
        cg['spell_schools'] = [UNDECIDED] * sc.get('schools_chosen', 0)
    if ccat.get('disciplines_pick_l1'):
        cg['class_choices'] = [{'slot': 'spellblade_disciplines',
                                'picks': [UNDECIDED] * ccat['disciplines_pick_l1']}]
    elif ccat.get('pact_boons_pick_l1'):
        cg['class_choices'] = [{'slot': 'pact_boons',
                                'picks': [UNDECIDED] * ccat['pact_boons_pick_l1']}]
    return {'schema': 1, 'ruleset': 'DC20 0.10.5', 'character': 'New ' + cls,
            'player': '', 'class': cls, 'subclass': None, 'ancestry': '',
            'background': '', 'current_level': 1, 'chargen': cg, 'levels': {},
            'skills': {'allocation_confidence': 'known', 'masteries': {}},
            'trades': {'masteries': {}},
            'languages': [{'name': 'Common', 'fluency': 'Fluent', 'cost': 0}],
            'equipment': [],
            'notes': ['Created in the rung-3 builder (new-from-scratch mode).']}



# ---------- comment-preserving YAML export ----------
def _line_paths(text):
    # {physical line -> node path} for every mapping key / sequence item, via the
    # real YAML composer - format-neutral, so hand-written and dumped layouts agree.
    loader = yaml.SafeLoader(text)
    try:
        node = loader.get_single_node()
    finally:
        loader.dispose()
    pairs = []

    def walk(n, path):
        if isinstance(n, yaml.MappingNode):
            for k, v in n.value:
                p = path + (str(k.value),)
                pairs.append((k.start_mark.line, p))
                walk(v, p)
        elif isinstance(n, yaml.SequenceNode):
            for i, item in enumerate(n.value):
                pairs.append((item.start_mark.line, path + (i,)))
                walk(item, path + (i,))
    if node is not None:
        walk(node, ())
    line2path, path2line = {}, {}
    for ln, p in pairs:
        line2path[ln] = p            # deeper key wins on shared lines - same rule both sides
        path2line.setdefault(p, ln)
    return line2path, path2line


def _split_comment(line):
    # -> (code, comment-including-#, column) or (line, None, -1); quote-aware
    q = None
    for i, ch in enumerate(line):
        if q:
            if ch == q:
                q = None
        elif ch in ('"', "'"):
            q = ch
        elif ch == '#' and (i == 0 or line[i - 1] in ' \t'):
            return line[:i].rstrip(), line[i:], i
    return line, None, -1


def _extract_comments(text):
    # -> (header_lines, anchors, tail_lines); anchors are dicts:
    #    {'kind': 'eol',   'path': p, 'text': '# ...', 'col': n}
    #    {'kind': 'lead'|'trail', 'path': p, 'lines': [raw, ...]}
    lines = text.splitlines()
    line2path, _ = _line_paths(text)
    header, tail, anchors = [], [], []
    eol_at = {}
    for n in line2path:
        _, com, col = _split_comment(lines[n])
        if com:
            anchors.append({'kind': 'eol', 'path': line2path[n], 'text': com, 'col': col})
            eol_at[n] = (line2path[n], col)

    def is_free(n):                  # comment-only or blank line
        s = lines[n].strip()
        return n not in line2path and (not s or s.startswith('#'))

    n, N, seen = 0, len(lines), False
    while n < N:
        if not is_free(n):
            seen = True
            n += 1
            continue
        start = n
        while n < N and is_free(n):
            n += 1
        run = lines[start:n]
        if n >= N and not any(l.strip() for l in run):
            continue                 # pure trailing blanks
        prev = start - 1
        indent0 = len(run[0]) - len(run[0].lstrip())
        if not seen:
            header.extend(run)
        elif n >= N:
            tail.extend(run)
        elif prev in eol_at and run[0].strip().startswith('#') \
                and indent0 >= eol_at[prev][1]:
            # aligned under the previous line's EOL comment -> continuation block
            anchors.append({'kind': 'trail', 'path': eol_at[prev][0], 'lines': run})
        else:
            m = n                    # attach to the NEXT structural line
            while m < N and m not in line2path:
                m += 1
            if m < N:
                anchors.append({'kind': 'lead', 'path': line2path[m], 'lines': run})
            else:
                tail.extend(run)
    return header, anchors, tail


def merge_comments(src_text, dumped):
    # re-anchor src_text's comments onto the freshly dumped YAML (same data, new text)
    header, anchors, tail = _extract_comments(src_text)
    _, path2line = _line_paths(dumped)
    top_new = {p[0] for p in path2line if len(p) == 1}

    def resolve(path):
        if path in path2line:
            return path
        k = str(path[0])             # the promote/undo rename: expected <-> expected_at_L<n>
        if k == 'expected' or k.startswith('expected_at_'):
            for cand in top_new:
                c = str(cand)
                if c == 'expected' or c.startswith('expected_at_'):
                    p2 = (cand,) + tuple(path[1:])
                    if p2 in path2line:
                        return p2
        return None

    lead, eol, trail, orphans = {}, {}, {}, []
    for a in anchors:
        p = resolve(a['path'])
        if p is None:
            orphans.append(a)
            continue
        ln = path2line[p]
        if a['kind'] == 'lead':
            lead.setdefault(ln, []).extend(a['lines'])
        elif a['kind'] == 'eol':
            eol[ln] = (a['text'], a['col'])
        else:
            trail.setdefault(ln, []).extend(a['lines'])
    out = list(header)
    for n, ln in enumerate(dumped.splitlines()):
        if n in lead:
            out.extend(lead[n])
        if n in eol:
            text, col = eol[n]
            ln = ln + ' ' * max(col - len(ln), 2) + text
        out.append(ln)
        if n in trail:
            out.extend(trail[n])
    out.extend(tail)
    if orphans:
        out.append('')
        out.append('# --- comments from the source ledger whose anchor was edited away; '
                   're-home or drop: ---')
        for a in orphans:
            if a['kind'] == 'eol':
                out.append('# (was on: %s)  %s'
                           % ('.'.join(str(x) for x in a['path']), a['text']))
            else:
                out.extend(l for l in a['lines'] if l.strip())
    return '\n'.join(out) + '\n'


class BuilderAPI:
    # Loads one ledger by handle (or a blank one, or raw YAML text) + the full catalog;
    # exposes a JSON decision-model API.
    def __init__(self, handle, catalog_paths, meta_path='spells_meta.json',
                 ledger_text=None, new_class=None):
        self.cat = {k: yaml.safe_load(open(p, encoding='utf-8'))
                    for k, p in catalog_paths.items()}
        self.meta = json.load(open(meta_path, encoding='utf-8'))
        if new_class:
            key = str(new_class).lower()
            self.ledger = blank_ledger(CLASS_NAMES[key], self.cat[key])
            self.handle = 'new-' + key
            self.src_text = None
        elif ledger_text is not None:
            self.ledger = yaml.safe_load(ledger_text)
            self.handle = str(handle)
            self.src_text = ledger_text
        else:
            self.handle = str(handle)
            self.src_text = open(self.handle + '.yaml', encoding='utf-8').read()
            self.ledger = yaml.safe_load(self.src_text)
        self.scratch = (bool(new_class) or self.handle.startswith('new-')
                        or any('new-from-scratch' in str(n)
                               for n in (self.ledger.get('notes') or [])))
        self.cls = self.ledger['class']
        self.ccat = self.cat[self.cls.lower()]
        self.aliases = self.cat['ancestries'].get('source_aliases', {})
        self._added = None
        self._undo = None

    # ---------- ancestry lists ----------
    def _declared_lists(self):
        # lists named on the ledger's ancestry line (incl. aliases like Beast -> Beastborn)
        out = []
        anc_text = str(self.ledger.get('ancestry') or '')
        for lst in self.cat['ancestries']['ancestries']:
            if lst in anc_text:
                out.append(lst)
        for al, lst in self.aliases.items():
            if al in anc_text and lst not in out:
                out.append(lst)
        return out

    def _allowed_lists(self):
        # declared lists + lists OPENED by taken cross-list traits (Redeemed -> Angelborn,
        # Fallen -> Fiendborn), to a fixpoint
        allowed = self._declared_lists()
        changed = True
        while changed:
            changed = False
            for t in self._traits():
                nm = base_name(t.get('name'))
                if not nm or str(t.get('name')) == UNDECIDED:
                    continue
                for lst in list(allowed):
                    for row in self.cat['ancestries']['ancestries'][lst]:
                        if (row['name'] == nm or nm in (row.get('aliases') or [])) \
                                and row.get('opens') \
                                and row['opens'] in self.cat['ancestries']['ancestries'] \
                                and row['opens'] not in allowed:
                            allowed.append(row['opens'])
                            changed = True
        return allowed

    def _anc_lists(self):
        if self.scratch:
            # scratch mode: the DECLARED ancestry governs (+ opened lists); trait sources
            # do not grandfather themselves in, so an ancestry change flags stale picks
            return self._allowed_lists()
        lists, extra = [], []
        for t in self._traits():
            src = self.aliases.get(t.get('source'), t.get('source'))
            if src and src in self.cat['ancestries']['ancestries'] and src not in lists:
                lists.append(src)
        for t in self._traits():   # unsourced / cross-list traits (Redeemed -> Angelborn etc.)
            if str(t.get('name')) == UNDECIDED:
                continue
            if self._anc_row(t.get('source'), t.get('name')) is None:
                for lst, rows in self.cat['ancestries']['ancestries'].items():
                    if any(r['name'] == base_name(t['name']) or
                           base_name(t['name']) in (r.get('aliases') or []) for r in rows):
                        if lst not in lists and lst not in extra:
                            extra.append(lst)
        # lists named on the ancestry line (drives scratch mode + trait-less ledgers)
        anc_text = str(self.ledger.get('ancestry') or '')
        for lst in self.cat['ancestries']['ancestries']:
            if lst in anc_text and lst not in lists and lst not in extra:
                extra.append(lst)
        for al, lst in self.aliases.items():
            if al in anc_text and lst not in lists and lst not in extra:
                extra.append(lst)
        return lists + extra

    def _anc_row(self, source, name):
        nm = base_name(name)
        lst = self.aliases.get(source, source)
        for row in self.cat['ancestries']['ancestries'].get(lst, []) or []:
            if row['name'] == nm or nm in (row.get('aliases') or []):
                return row
        return None

    def _anc_find(self, name):
        nm = base_name(name)
        for lst in self._anc_lists():
            for row in self.cat['ancestries']['ancestries'][lst]:
                if row['name'] == nm or nm in (row.get('aliases') or []):
                    return lst, row
        return None, None

    def _anc_find_any(self, name):
        nm = base_name(name)
        for lst, rows in self.cat['ancestries']['ancestries'].items():
            for row in rows or []:
                if row['name'] == nm or nm in (row.get('aliases') or []):
                    return lst, row
        return None, None

    def _trait_problem(self, name, cost):
        # None if fine, else a catalog problem string (off-list beats unknown)
        row = self._anc_find(name)[1]
        if row is None:
            lst2, row2 = self._anc_find_any(name)
            if row2 is not None:
                return ("catalog: ancestry trait %r is from %s, not one of this "
                        "character's ancestry lists" % (base_name(name), lst2))
            return 'catalog: ancestry trait %r unknown' % name
        if cost != row['cost']:
            return ('catalog: %s costs %s, ledger says %s'
                    % (base_name(name), row['cost'], cost))
        return None

    def _anc_options(self):
        opts = []
        for lst in self._anc_lists():
            for row in self.cat['ancestries']['ancestries'][lst]:
                if str(row['name']) == 'Attribute Increase':
                    # emit per-attribute variants; a target-less pick is meaningless to
                    # the engine (and used to crash its '(target)' parse)
                    for a in ATTRS:
                        nm = 'Attribute Increase (%s)' % a
                        opts.append({'name': nm, 'cost': row['cost'], 'group': lst,
                                     'label': '%s (%s, cost %s)' % (nm, lst, row['cost'])})
                    continue
                opts.append({'name': row['name'], 'cost': row['cost'], 'group': lst,
                             'label': '%s (%s, cost %s)' % (row['name'], lst, row['cost'])})
        return opts

    def _traits(self):
        for t in self.ledger['chargen'].get('ancestry_traits') or []:
            yield t
        for lvl in sorted(self.ledger.get('levels') or {}):
            for e in self.ledger['levels'][lvl] or []:
                if e.get('slot') == 'ancestry_trait':
                    yield {'name': e.get('pick'), 'source': e.get('source'),
                           'cost': e.get('cost', 0)}

    # ---------- spell / maneuver / talent option lists ----------
    def _ssi_schools(self):
        out = []
        for lvl in sorted(self.ledger.get('levels') or {}):
            for e in self.ledger['levels'][lvl] or []:
                if e.get('slot') == 'talent' and str(e.get('pick', '')).startswith('Spell School Initiate:'):
                    out.append(str(e['pick']).split(':', 1)[1].strip())
        return out

    def _grant_tags(self):
        tags = set()
        sg = self.ccat.get('subclass_grants') or {}
        for lvl in sorted(self.ledger.get('levels') or {}):
            for e in self.ledger['levels'][lvl] or []:
                if e.get('slot') == 'subclass':
                    g = sg.get(base_name(e['pick']))
                    if g and 'spell_access' in g:
                        tags.add(g['spell_access']['tag'])
        return tags

    def _spell_access(self):
        # -> (options set, describe(name) -> why-legal string or None)
        model = self.ccat['spellcasting']['model']
        if model == 'schools':
            chosen = [s for s in (list(self.ledger['chargen'].get('spell_schools') or [])
                                  + self._ssi_schools()) if str(s) != UNDECIDED]
            tags = set(self.ccat['spellcasting'].get('tag_access') or []) | self._grant_tags()
            names = set()
            for sch in chosen:
                names |= set(self.cat['spell_schools']['schools'].get(sch, []))
            names |= {n for n, m in self.meta.items() if set(m['tags']) & tags}

            def why(n):
                m = self.meta.get(n)
                if not m:
                    return None
                if m['school'] in chosen:
                    return 'school ' + m['school']
                hit = set(m['tags']) & tags
                return ('tag ' + '/'.join(sorted(hit))) if hit else None
            return names, why
        if model == 'source':
            src = self.ccat['spellcasting']['source']
            names = {sp for sch in self.cat['spell_sources']['sources'][src].values() for sp in sch}

            def why(n):
                m = self.meta.get(n)
                if not m:
                    return None
                if src in m['sources']:
                    return src + ' source'
                return ('Arcane grant slot' if 'Arcane' in m['sources'] else None)
            return names, why
        # model none: path-rider list choice unrecorded -> existence only
        return set(self.meta.keys()), (lambda n: 'path-rider list (unpinned)' if n in self.meta else None)

    def _spell_options(self):
        names, why = self._spell_access()
        return [{'name': n, 'group': (self.meta.get(n) or {}).get('school', '?'),
                 'label': '%s (%s)' % (n, (self.meta.get(n) or {}).get('school', '?'))}
                for n in sorted(names)]

    def _maneuver_options(self):
        return [{'name': m, 'group': typ, 'label': '%s (%s)' % (m, typ)}
                for typ, lst in self.cat['maneuvers']['maneuvers'].items() for m in lst]

    def _talent_options(self):
        t = self.cat['talents']
        opts = [{'name': r['name'], 'group': 'General', 'label': r['name'] + ' (General)'}
                for r in t['general']]
        for r in t['class_talents'].get(self.cls, []):
            opts.append({'name': r['name'], 'group': self.cls + ' talents',
                         'label': '%s (%s talent)' % (r['name'], self.cls)})
        for r in t['mc_features']:
            opts.append({'name': r['name'], 'group': 'Multiclass features',
                         'label': '%s (%s L%s via %s)' % (r['name'], r['class'],
                                                          r['feature_level'], r['via'])})
        return opts

    def _options_for(self, slot):
        if slot == 'ancestry_trait':
            return self._anc_options()
        if slot == 'spell':
            return self._spell_options()
        if slot == 'maneuver':
            return self._maneuver_options()
        if slot == 'talent':
            return self._talent_options()
        if slot == 'attribute':
            return [{'name': a, 'group': '', 'label': a} for a in ATTRS]
        if slot == 'path':
            return [{'name': p, 'group': '', 'label': p} for p in self.ccat['paths']]
        if slot == 'subclass':
            return [{'name': s, 'group': '', 'label': s} for s in self.ccat['subclasses']]
        if slot == 'discipline':
            return [{'name': d['name'], 'group': '',
                     'label': d['name'] + (' %s' % d['grants'] if d.get('grants') else '')}
                    for d in self.ccat.get('disciplines', [])]
        if slot == 'pact_boon':
            return [{'name': b['name'], 'group': '',
                     'label': b['name'] + (' %s' % b['grants'] if b.get('grants') else '')}
                    for b in self.ccat.get('pact_boons', [])]
        if slot == 'spell_school':
            return [{'name': s, 'group': '', 'label': s}
                    for s in self.cat['spell_schools']['schools']]
        return []

    # ---------- catalog-level legality (the layer the engine does not do) ----------
    def catalog_problems(self):
        probs = []
        names, why = self._spell_access()
        model = self.ccat['spellcasting']['model']
        spell_names, off_source = [], 0
        for s in self.ledger['chargen'].get('spells') or []:
            if not is_composite(s) and str(s) != UNDECIDED:
                spell_names.append(str(s))
        for lvl in sorted(self.ledger.get('levels') or {}):
            for e in self.ledger['levels'][lvl] or []:
                if e.get('slot') == 'spell' and not is_composite(e.get('pick')) \
                        and str(e.get('pick')) != UNDECIDED:
                    spell_names.append(base_name(e['pick']) if '(' in str(e['pick']) else str(e['pick']))
        for s in spell_names:
            if s in names:
                # in a chosen school / the class source list: legal, whether or not the
                # spells.md entry extract knows it (the rulebook's listing pages carry a
                # few names, e.g. 'Absorb Element', whose full entries are spelled
                # differently or absent - the list is authoritative for membership)
                continue
            if s not in self.meta:
                probs.append('catalog: spell %r not found in spells.md' % s)
            elif why(s) is None:
                probs.append('catalog: spell %s not legal for this %s (%s)'
                              % (s, self.cls, self.meta[s]['school']))
            elif model == 'source' and why(s) == 'Arcane grant slot':
                off_source += 1
        if model == 'source' and off_source:
            slots = 0
            for lvl in sorted(self.ledger.get('levels') or {}):
                for e in self.ledger['levels'][lvl] or []:
                    if e.get('slot') == 'talent' and 'Innate Power' in str(e.get('pick')) \
                            and 'Intuitive' in str(e.get('pick')):
                        slots += 2
            for t in self._traits():
                if base_name(t['name']) in ('Fiendish Magic', 'Arcane Spell'):
                    slots += 1
            if off_source > slots:
                probs.append('catalog: %d off-source spells vs %d Arcane grant slots'
                              % (off_source, slots))
        all_man = {m for lst in self.cat['maneuvers']['maneuvers'].values() for m in lst}
        for m in self.ledger['chargen'].get('maneuvers') or []:
            if not is_composite(m) and str(m) != UNDECIDED and m not in all_man:
                probs.append('catalog: maneuver %r does not exist in 0.10.5' % m)
        for lvl in sorted(self.ledger.get('levels') or {}):
            for e in self.ledger['levels'][lvl] or []:
                if e.get('slot') == 'maneuver' and not is_composite(e.get('pick')) \
                        and str(e.get('pick')) != UNDECIDED \
                        and str(e['pick']) not in all_man:
                    probs.append('catalog: maneuver %r does not exist in 0.10.5' % e['pick'])
                if e.get('slot') == 'ancestry_trait' and str(e.get('pick')) != UNDECIDED:
                    p = self._trait_problem(e['pick'], e.get('cost'))
                    if p:
                        probs.append(p)
        for t in self.ledger['chargen'].get('ancestry_traits') or []:
            if any(mk in str(t.get('name')) for mk in PLACEHOLDER_MARKERS) \
                    or str(t.get('name')) == UNDECIDED:
                continue
            p = self._trait_problem(t['name'], t.get('cost', 0))
            if p:
                probs.append(p)
        return probs

    # ---------- builder-level completeness (undecided slots) ----------
    def builder_problems(self):
        probs = []
        cg = self.ledger['chargen']

        def cnt(label, seq):
            n = sum(1 for x in seq if str(x) == UNDECIDED)
            if n:
                probs.append('builder: %d %s pick(s) undecided' % (n, label))
        cnt('L1 spell', cg.get('spells') or [])
        cnt('L1 maneuver', cg.get('maneuvers') or [])
        cnt('L1 spell-school', cg.get('spell_schools') or [])
        for c in cg.get('class_choices') or []:
            cnt('L1 %s' % c['slot'], c.get('picks') or [])
        for t in cg.get('ancestry_traits') or []:
            if str(t.get('name')) == UNDECIDED:
                probs.append('builder: L1 ancestry trait undecided')
        cur = self.ledger['current_level']
        for lvl in sorted(self.ledger.get('levels') or {}):
            if lvl > cur:
                continue
            for e in self.ledger['levels'][lvl] or []:
                if str(e.get('pick')) == UNDECIDED:
                    probs.append('builder: L%d %s undecided' % (lvl, e.get('slot')))
        if self.scratch and not str(self.ledger.get('ancestry') or '').strip():
            probs.append('builder: ancestry not chosen')
        return probs

    # ---------- the decision model ----------
    def _decisions(self):
        ds = []
        cg = self.ledger['chargen']
        cur = self.ledger['current_level']
        ds.append({'id': 'cg:attrs', 'level': 1, 'slot': 'attributes', 'widget': 'pointbuy',
                   'attrs': cg['attributes'],
                   'spent': sum(v + 2 for v in cg['attributes'].values()),
                   'budget': 12, 'limit': 3, 'editable': True})
        for i, s in enumerate(cg.get('spell_schools') or []):
            ds.append(self._dec('cg:school:%d' % i, 1, 'spell_school', s, None, False, True))
        for i, t in enumerate(cg.get('ancestry_traits') or []):
            ph = any(mk in str(t.get('name')) for mk in PLACEHOLDER_MARKERS)
            ds.append(self._dec('cg:trait:%d' % i, 1, 'ancestry_trait', t['name'],
                                t.get('cost'), bool(t.get('inferred')), not ph,
                                note='placeholder - itemisation pending' if ph else None,
                                removable=self.scratch or BUILDER_NOTE in str(t.get('note', ''))))
        for ci, c in enumerate(cg.get('class_choices') or []):
            opt_slot = ('discipline' if c['slot'] == 'spellblade_disciplines'
                        else 'pact_boon' if c['slot'] == 'pact_boons' else None)
            if opt_slot:
                for pi, p in enumerate(c.get('picks') or []):
                    ds.append(self._dec('cg:choice:%d:%d' % (ci, pi), 1, opt_slot, p,
                                        None, False, not is_composite(p)))
            else:
                ds.append({'id': None, 'level': 1, 'slot': c['slot'],
                           'pick': ', '.join(str(x) for x in c['picks']),
                           'widget': 'fixed', 'editable': False, 'cost': None, 'inferred': False})
        for i, s in enumerate(cg.get('spells') or []):
            ds.append(self._dec('cg:spell:%d' % i, 1, 'spell', s, None, False, not is_composite(s)))
        for i, m in enumerate(cg.get('maneuvers') or []):
            ds.append(self._dec('cg:man:%d' % i, 1, 'maneuver', m, None, False, not is_composite(m)))
        for lvl in sorted(self.ledger.get('levels') or {}):
            for i, e in enumerate(self.ledger['levels'][lvl] or []):
                editable = (lvl <= cur and e.get('slot') in EDITABLE_SLOTS
                            and not is_composite(e.get('pick')))
                ds.append(self._dec('L%d:%d' % (lvl, i), lvl, e.get('slot'), e.get('pick'),
                                    e.get('cost'), bool(e.get('inferred')), editable,
                                    note=e.get('note'), plan=lvl > cur,
                                    removable=(e.get('slot') == 'ancestry_trait'
                                               and (self.scratch or BUILDER_NOTE in str(e.get('note', ''))))))
        return ds

    def _dec(self, did, lvl, slot, pick, cost, inferred, editable, note=None, plan=False,
             removable=False):
        d = {'id': did, 'level': lvl, 'slot': slot, 'pick': pick, 'cost': cost,
             'inferred': inferred, 'editable': editable and not plan, 'plan': plan,
             'widget': 'picker' if (editable and not plan) else 'fixed',
             'removable': removable}
        if note:
            d['note'] = note
        if d['widget'] == 'picker':
            d['options'] = self._options_for(slot)
            if str(pick) == UNDECIDED:
                d['current'] = UNDECIDED
                return d
            d['current'] = (base_name(pick) if slot in ('ancestry_trait', 'talent', 'spell',
                                                        'maneuver', 'subclass') else str(pick))
            if slot == 'ancestry_trait':
                lst, row = self._anc_find(pick)
                if lst is not None:
                    d['current_group'] = lst   # dedupe same-named traits across lists
                if base_name(pick) == 'Attribute Increase':
                    m = re.search(r'\(([^)]+)\)', str(pick))
                    d['current'] = 'Attribute Increase (%s)' % (m.group(1).strip().lower() if m else 'might')
                elif row is not None:
                    d['current'] = row['name']   # resolve ledger aliases (e.g. Arcane Spell)
            if slot == 'talent':
                m = re.match(r'MC \w+(?: \((?:Novice|Adept|Expert|Master)\))?:\s*(.*)', str(pick))
                d['current'] = base_name((m.group(1) if m else str(pick)).split(':')[0])
        return d

    def _alloc(self):
        out = []
        for kind in ('skills', 'trades'):
            for name, m in ((self.ledger.get(kind) or {}).get('masteries') or {}).items():
                out.append({'id': '%s:%s' % (kind, name), 'kind': kind, 'name': name,
                            'mastery': m.get('mastery'), 'limit_raise': m.get('limit_raise'),
                            'options': [str(x) for x in MASTERIES],
                            'removable': self.scratch or BUILDER_NOTE in str(m.get('note', ''))})
        return out

    def _skill_trade_options(self):
        stc = self.cat.get('skills_trades') or {}
        have = {k: set((self.ledger.get(k) or {}).get('masteries') or {})
                for k in ('skills', 'trades')}
        opts = [{'kind': 'skills', 'name': n, 'group': 'Skills (%s)' % attr}
                for attr, lst in (stc.get('skills') or {}).items() for n in lst
                if n not in have['skills']]
        kn = set(stc.get('knowledge_trades') or [])
        opts += [{'kind': 'trades', 'name': n,
                  'group': 'Knowledge Trades' if n in kn else 'Trades'}
                 for n in (stc.get('trades') or []) if n not in have['trades']]
        return opts

    def _langs(self):
        out = []
        for i, l in enumerate(self.ledger.get('languages') or []):
            out.append({'i': i, 'name': l.get('name'), 'fluency': l.get('fluency'),
                        'cost': l.get('cost', 0), 'fixed': l.get('name') == 'Common'})
        return out

    def _sections(self, lines):
        stats, budgets, sect = [], [], None
        for ln in lines:
            if ln.startswith('## '):
                h = ln[3:].strip()
                sect = ('budgets' if h.startswith('Point budgets')
                        else 'stats' if h.startswith('Derived') else None)
                continue
            if sect == 'stats' and ln.startswith('| '):
                c = [x.strip() for x in ln.strip('|').split('|')]
                if len(c) == 4 and c[0] not in ('Stat', '---'):
                    stats.append(c)
            elif sect == 'budgets' and ln.startswith('- '):
                budgets.append(ln[2:])
        return stats, budgets

    def next_level_info(self):
        cur = self.ledger['current_level']
        if cur >= 10:
            return None
        row = self.ccat['spine'].get(cur + 1, {})
        bits = []
        for k, lab in (('hp', 'HP'), ('sp', 'SP'), ('mp', 'MP'), ('spells', 'spell'),
                       ('maneuvers', 'maneuver'), ('attribute_points', 'attribute pt'),
                       ('skill_points', 'skill pt'), ('trade_points', 'trade pt')):
            v = row.get(k, 0)
            if v:
                bits.append('+%d %s' % (v, lab))
        return {'level': cur + 1, 'summary': ', '.join(bits),
                'features': [f for f in row.get('features', []) if f != 'Class Features'],
                'has_plan': bool((self.ledger.get('levels') or {}).get(cur + 1))}

    def state(self):
        cur = self.ledger['current_level']
        rep = eng.replay(self.ledger, cur)
        stats, budgets = self._sections(rep.lines)
        planned = [l for l in sorted(self.ledger.get('levels') or {}) if l > cur]
        anc_levels = [1] + [l for l in sorted(self.ccat['spine']) if l <= cur and
                            '2 Ancestry Points' in (self.ccat['spine'][l].get('features') or [])]
        return json.dumps({
            'handle': self.handle,
            'character': self.ledger.get('character'),
            'player': self.ledger.get('player'),
            'background': self.ledger.get('background'),
            'klass': self.cls,
            'subclass': self.ledger.get('subclass'),
            'ancestry': self.ledger.get('ancestry'),
            'level': cur, 'planned': planned,
            'scratch': self.scratch,
            'next': self.next_level_info(),
            'undo_level': self._added,
            'anc_levels': anc_levels,
            'anc_lists_all': sorted(self.cat['ancestries']['ancestries'].keys()),
            'skill_trade_options': self._skill_trade_options(),
            'decisions': self._decisions(),
            'alloc': self._alloc(),
            'languages': self._langs(),
            'stats': stats, 'budgets': budgets,
            'advisories': [b for b in budgets if 'UNDER-SPENT' in b],
            'problems': rep.problems,
            'catalog_problems': self.catalog_problems(),
            'builder_problems': self.builder_problems(),
        })

    # ---------- edits ----------
    def set_decision(self, did, value):
        did = str(did)
        value = str(value)
        if did.startswith('cg:'):
            parts = did.split(':')
            kind = parts[1]
            cg = self.ledger['chargen']
            if kind == 'choice':
                ci, pi = int(parts[2]), int(parts[3])
                row_ch = cg['class_choices'][ci]
                row_ch['picks'][pi] = value
                # aggregate grants across picks (Magus mp/spells, Pact Weapon maneuvers, ...)
                pool = (self.ccat.get('disciplines') or []) + (self.ccat.get('pact_boons') or [])
                agg = {}
                for p in row_ch['picks']:
                    r = next((d for d in pool if d['name'] == p), None)
                    for k2, v2 in ((r or {}).get('grants') or {}).items():
                        agg[k2] = agg.get(k2, 0) + v2
                if agg:
                    row_ch['grants'] = agg
                else:
                    row_ch.pop('grants', None)
            elif kind == 'school':
                cg['spell_schools'][int(parts[2])] = value
            elif kind == 'spell':
                cg['spells'][int(parts[2])] = value
            elif kind == 'man':
                cg['maneuvers'][int(parts[2])] = value
            elif kind == 'trait':
                self._set_trait(cg['ancestry_traits'][int(parts[2])], value)
        else:
            lvl, idx = did[1:].split(':')
            e = self.ledger['levels'][int(lvl)][int(idx)]
            slot = e.get('slot')
            if slot == 'ancestry_trait':
                self._set_trait(e, value, entry=True)
            elif slot == 'discipline':
                row = next((d for d in self.ccat.get('disciplines', [])
                            if d['name'] == value), {})
                e['pick'] = value
                if row.get('grants'):
                    e['grants'] = dict(row['grants'])
                else:
                    e.pop('grants', None)
                self._edited(e)
            elif slot == 'talent':
                row = next((t for t in self.cat['talents']['mc_features']
                            if t['name'] == value), None) \
                    or next((t for t in self.cat['talents']['general']
                             if t['name'] == value), None)
                e['pick'] = value
                if row and row.get('grants'):
                    e['grants'] = dict(row['grants'])
                else:
                    e.pop('grants', None)
                self._edited(e)
            elif slot == 'subclass':
                e['pick'] = value
                self.ledger['subclass'] = value
                self._edited(e)
            else:
                e['pick'] = value
                self._edited(e)
                if slot == 'path' and BUILDER_NOTE in str(e.get('note', '')):
                    self._sync_path_rider(int(lvl), value)
        return self.state()

    def _set_trait(self, t, value, entry=False):
        lst, row = self._anc_find(value)
        key = 'pick' if entry else 'name'
        t[key] = value
        if row is not None:
            t['cost'] = row['cost']
            t['source'] = lst
        was_added = BUILDER_NOTE in str(t.get('note', ''))
        t['note'] = ('%s; cost %s from catalog (%s).'
                     % (BUILDER_NOTE if was_added else 'Edited in builder',
                        row['cost'] if row else '?', lst))
        t.pop('inferred', None)

    def _edited(self, e):
        if BUILDER_NOTE not in str(e.get('note', '')):
            e['note'] = 'Edited in builder (%s).' % self.handle
        e.pop('inferred', None)

    def _sync_path_rider(self, lvl, path):
        # a builder-added Path pick carries its rank rider: Martial -> +1 maneuver pick,
        # Spellcaster -> +1 spell pick (the engine already counts the resource; the rider
        # slot records WHICH one was chosen). Canon entries are never touched.
        ents = self.ledger['levels'][lvl]
        for e in list(ents):
            if str(e.get('source', '')).startswith('path rider') \
                    and BUILDER_NOTE in str(e.get('note', '')):
                ents.remove(e)
        want = ('maneuver' if str(path).startswith('Martial')
                else 'spell' if str(path).startswith('Spellcaster') else None)
        if want:
            ents.append({'slot': want, 'pick': UNDECIDED,
                         'source': 'path rider (%s)' % path, 'note': BUILDER_NOTE})

    def set_attr(self, name, value):
        self.ledger['chargen']['attributes'][str(name)] = int(value)
        return self.state()

    def set_mastery(self, did, value):
        kind, name = str(did).split(':', 1)
        m = self.ledger[kind]['masteries'][name]
        m['mastery'] = None if value in ('None', '', 'null') else str(value)
        return self.state()

    def add_mastery(self, kind, name):
        kind, name = str(kind), str(name).strip()
        if kind in ('skills', 'trades') and name:
            ms = self.ledger.setdefault(kind, {}).setdefault('masteries', {})
            if name not in ms:
                ms[name] = {'mastery': 'Novice', 'note': BUILDER_NOTE}
        return self.state()

    def remove_mastery(self, did):
        kind, name = str(did).split(':', 1)
        ((self.ledger.get(kind) or {}).get('masteries') or {}).pop(name, None)
        return self.state()

    def add_language(self, name, fluency):
        name, flu = str(name).strip(), str(fluency)
        if name:
            self.ledger.setdefault('languages', []).append(
                {'name': name, 'fluency': flu, 'cost': LANG_COSTS.get(flu, 2),
                 'note': BUILDER_NOTE})
        return self.state()

    def set_language(self, idx, fluency):
        l = self.ledger['languages'][int(idx)]
        flu = str(fluency)
        l['fluency'] = flu
        if l.get('name') != 'Common':
            l['cost'] = LANG_COSTS.get(flu, 2)
        return self.state()

    def remove_language(self, idx):
        l = self.ledger['languages'][int(idx)]
        if l.get('name') != 'Common':
            del self.ledger['languages'][int(idx)]
        return self.state()

    def add_trait(self, level):
        level = int(level)
        if level <= 1:
            self.ledger['chargen'].setdefault('ancestry_traits', []).append(
                {'name': UNDECIDED, 'cost': 0, 'note': BUILDER_NOTE})
        else:
            self.ledger.setdefault('levels', {}).setdefault(level, []).append(
                {'slot': 'ancestry_trait', 'pick': UNDECIDED, 'cost': 0, 'note': BUILDER_NOTE})
        return self.state()

    def remove_decision(self, did):
        did = str(did)
        if did.startswith('cg:trait:'):
            del self.ledger['chargen']['ancestry_traits'][int(did.split(':')[2])]
        elif did.startswith('L'):
            lvl, idx = did[1:].split(':')
            del self.ledger['levels'][int(lvl)][int(idx)]
        return self.state()

    def set_meta(self, field, value):
        if str(field) in ('character', 'player', 'background'):
            self.ledger[str(field)] = str(value)
        return self.state()

    def set_ancestry(self, l1, l2):
        l1, l2 = str(l1), str(l2)
        if l2 and l2 not in ('-', 'None', ''):
            self.ledger['ancestry'] = '%s + %s (trait lists)' % (l1, l2)
        else:
            self.ledger['ancestry'] = l1
        return self.state()

    # ---------- add-a-level (the level-up-night flow) ----------
    def add_level(self):
        cur = self.ledger['current_level']
        if cur >= 10:
            return self.state()
        new = cur + 1
        levels = self.ledger.setdefault('levels', {})
        self._undo = {'cur': cur, 'expected': copy.deepcopy(self.ledger.get('expected')),
                      'had_plan': new in levels, 'plan': copy.deepcopy(levels.get(new))}
        if new not in levels:
            # generate the level's decision slots from the class spine
            row = self.ccat['spine'].get(new, {})
            ents = []
            for _ in range(row.get('attribute_points', 0)):
                ents.append({'slot': 'attribute', 'pick': UNDECIDED, 'note': BUILDER_NOTE})
            for f in row.get('features', []):
                if f == 'Talent':
                    ents.append({'slot': 'talent', 'pick': UNDECIDED, 'note': BUILDER_NOTE})
                elif f == 'Path':
                    ents.append({'slot': 'path', 'pick': UNDECIDED, 'note': BUILDER_NOTE})
                elif f == 'Subclass':
                    ents.append({'slot': 'subclass', 'pick': UNDECIDED, 'note': BUILDER_NOTE})
                elif f == '2 Ancestry Points':
                    ents.append({'slot': 'ancestry_trait', 'pick': UNDECIDED, 'cost': 0,
                                 'note': BUILDER_NOTE})
                elif f == 'Class Features':
                    pass
                else:
                    ents.append({'slot': 'class_feature', 'pick': f,
                                 'note': 'auto - see classes.md. ' + BUILDER_NOTE})
            for _ in range(row.get('spells', 0)):
                ents.append({'slot': 'spell', 'pick': UNDECIDED,
                             'source': 'class table L%d' % new, 'note': BUILDER_NOTE})
            for _ in range(row.get('maneuvers', 0)):
                ents.append({'slot': 'maneuver', 'pick': UNDECIDED,
                             'source': 'class table L%d' % new, 'note': BUILDER_NOTE})
            levels[new] = ents
        # else: PROMOTE the existing plan level - its entries simply become current
        self.ledger['current_level'] = new
        if self.ledger.get('expected') is not None:
            # the sheet totals documented the OLD level; keep them as history, the new
            # level's numbers now come FROM the builder
            self.ledger['expected_at_L%d' % cur] = self.ledger.pop('expected')
        self._added = new
        return self.state()

    def undo_add_level(self):
        if not self._undo:
            return self.state()
        u = self._undo
        new = u['cur'] + 1
        levels = self.ledger.get('levels') or {}
        if u['had_plan']:
            levels[new] = u['plan']
        else:
            levels.pop(new, None)
        self.ledger['current_level'] = u['cur']
        self.ledger.pop('expected_at_L%d' % u['cur'], None)
        if u['expected'] is not None:
            self.ledger['expected'] = u['expected']
        self._added = None
        self._undo = None
        return self.state()

    def export_yaml(self):
        # width=4096: no line-wrapping, so an EOL comment can never land inside a
        # wrapped plain scalar
        dumped = yaml.dump(self.ledger, sort_keys=False, allow_unicode=True, width=4096)
        if not getattr(self, 'src_text', None):
            return ('# Build ledger: %s. Created in the rung-3 builder '
                    '(new-from-scratch mode).\n# Schema: builds/SCHEMA.md (v1).\n'
                    % self.ledger.get('character')) + dumped
        try:
            return merge_comments(self.src_text, dumped)
        except Exception as e:       # comment merge must never block an export
            print('comment merge failed (%s); exporting without comments' % e)
            return dumped
"""

TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DC20 Character Builder</title>
<script src="https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js"></script>
<style>
:root{--ink:#1f2430;--muted:#6b7280;--line:#c9ced8;--paper:#f7f8fa;--accent:#3d5a80;
 --ok:#2e7d32;--bad:#b23;--warn:#b7791f}
*{box-sizing:border-box}
body{font-family:system-ui,Segoe UI,Arial,sans-serif;color:var(--ink);margin:0;background:#eef0f4;line-height:1.42}
.wrap{max-width:1120px;margin:0 auto;padding:1.3rem 1.3rem 3rem}
h1{font-size:1.35rem;margin:.1rem 0;display:inline-block}
.badge{display:inline-block;font-size:.66rem;letter-spacing:.04em;text-transform:uppercase;
 background:var(--accent);color:#fff;border-radius:4px;padding:.12rem .45rem;vertical-align:middle}
.sub{color:var(--muted);font-size:.9rem;margin:.25rem 0 .9rem}
#charsel{border:1px solid var(--accent);border-radius:6px;padding:.3rem .5rem;background:#fff;
 font-size:.9rem;margin-left:.8rem;vertical-align:middle}
.loadlbl{font-size:.78rem;color:var(--muted);margin-left:.8rem}
#status{font-size:.85rem;font-weight:600;background:#e9edf5;border:1px solid var(--line);
 border-radius:6px;padding:.5rem .75rem;margin-bottom:1rem}
#status.err{background:#fdecec;border-color:#f3b6b6;color:var(--bad)}
#status.ready{background:#e9f6ea;border-color:#a9d6ab;color:var(--ok)}
#resume{display:none;font-size:.85rem;background:#fff8e6;border:1px solid #e4c86a;border-radius:6px;
 padding:.5rem .75rem;margin-bottom:1rem}
#canonbar{display:none;font-size:.9rem;font-weight:700;background:#fdecec;border:2px solid var(--bad);
 color:var(--bad);border-radius:8px;padding:.6rem .8rem;margin-bottom:1rem}
.builder{display:grid;grid-template-columns:170px 1fr;gap:1rem}
.card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:1rem;margin-bottom:1rem}
h3.sec{font-size:.72rem;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin:.1rem 0 .55rem}
.rail ol{list-style:none;margin:0;padding:0}
.rail li{border:1px solid var(--line);border-radius:6px;padding:.4rem .5rem;margin-bottom:.35rem;font-size:.83rem;background:var(--paper)}
.rail li.cur{border-color:var(--accent);background:#eaf1f8;font-weight:600}
.rail li.next{border-style:dashed;color:var(--accent)}
.dec{border:1px solid var(--line);border-radius:7px;padding:.45rem .6rem;margin-bottom:.45rem;font-size:.86rem;display:flex;gap:.5rem;align-items:baseline;flex-wrap:wrap}
.dec .lv{font-size:.7rem;color:#fff;background:var(--muted);border-radius:4px;padding:.05rem .4rem;min-width:26px;text-align:center}
.dec .slot{font-size:.7rem;color:var(--muted);text-transform:uppercase;letter-spacing:.03em;min-width:104px}
.dec .pick{flex:1;min-width:230px}
.dec.inferred .pick{color:var(--muted);font-style:italic}
.dec.edit{border:1.2px solid var(--accent);background:#f4f8fc}
.dec.edit .slot{color:var(--accent)}
.dec.plan{opacity:.62;border-style:dashed}
.dec.newlvl{border-left:4px solid var(--warn)}
.wlabel{font-size:.64rem;text-transform:uppercase;letter-spacing:.05em;color:#fff;background:var(--accent);border-radius:4px;padding:.08rem .4rem}
.select{border:1px solid var(--accent);border-radius:6px;padding:.28rem .45rem;background:#fff;font-size:.84rem;max-width:420px}
input.select{max-width:180px}
.pb{display:flex;gap:1rem;flex-wrap:wrap;align-items:center}
.pb label{font-size:.8rem;color:var(--muted);text-transform:capitalize}
.pb .spent{font-size:.82rem;font-weight:600}
.pb .spent.bad{color:var(--bad)}
table.derived{border-collapse:collapse;width:100%;font-size:.83rem;margin-top:.2rem}
table.derived th,table.derived td{border:1px solid var(--line);padding:.24rem .5rem;text-align:left}
table.derived th{background:var(--paper);color:var(--muted);font-weight:600;font-size:.72rem;text-transform:uppercase}
.mk-OK{color:var(--ok);font-weight:600}
.mk-MISMATCH{color:var(--bad);font-weight:700}
.budget{font-size:.82rem;margin:.15rem 0;color:#333}
.prob{background:#fdecec;border:1px solid #f3b6b6;color:var(--bad);border-radius:6px;padding:.5rem .7rem;font-size:.83rem;margin-top:.6rem}
.prob.clean{background:#e9f6ea;border-color:#a9d6ab;color:var(--ok)}
.prob.adv{background:#fff8e6;border-color:#e4c86a;color:#8a6d1a}
details.lvlgrp{border:1px solid var(--line);border-radius:8px;margin-bottom:.5rem;background:var(--paper)}
details.lvlgrp>summary{cursor:pointer;font-size:.8rem;font-weight:600;color:var(--accent);padding:.4rem .6rem;user-select:none}
details.lvlgrp[open]>summary{border-bottom:1px solid var(--line)}
details.lvlgrp>.dec{margin:.45rem .45rem}
details.lvlgrp.plan>summary{color:var(--muted);font-style:italic}
.prob ul{margin:.3rem 0 0;padding-left:1.1rem}
.alloc{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:.4rem}
.alloc .row,.langs .row{border:1px solid var(--line);border-radius:6px;padding:.3rem .5rem;font-size:.82rem;display:flex;justify-content:space-between;align-items:center;gap:.4rem;background:var(--paper)}
.alloc .row .nm{overflow:hidden;text-overflow:ellipsis}
.langs{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:.4rem;margin-top:.3rem}
.addrow{margin-top:.55rem;display:flex;gap:.4rem;align-items:center;flex-wrap:wrap}
.exportbtn{margin-top:.7rem;background:var(--accent);color:#fff;border:none;border-radius:6px;padding:.5rem .95rem;font-size:.88rem;cursor:pointer}
.exportbtn:disabled{opacity:.5;cursor:default}
.exportbtn.small{margin-top:0;padding:.3rem .6rem;font-size:.8rem}
.exportbtn.canonbtn{background:var(--bad)}
.lvlbtn{width:100%;margin-top:.5rem}
a.rm{color:var(--bad);text-decoration:none;font-weight:700;font-size:.95rem;padding:0 .2rem}
.foot{font-size:.76rem;color:var(--muted);margin-top:1rem}
.src{font-size:.72rem;color:var(--muted);margin-top:.4rem}
pre.yaml{background:#111;color:#c8e6c9;padding:.7rem;border-radius:6px;font-size:.76rem;white-space:pre-wrap;max-height:260px;overflow:auto;display:none}
</style></head>
<body><div class="wrap">
<h1>DC20 Character Builder</h1> <span class="badge">rung 3 - step 5</span>
<select id="charsel"></select>
<label class="loadlbl">or load a YAML: <input type="file" id="loadyaml" accept=".yaml,.yml"></label>
<p class="sub">The real <code>build_engine.py</code> runs in your browser via Pyodide; every edit
re-validates live against the engine AND the option catalog. Export writes the updated ledger YAML.</p>
<div id="status">Booting Pyodide (first load pulls a few MB from the CDN)&hellip;</div>
<div id="resume"></div>
<div id="canonbar"></div>

<div class="builder" id="app" style="display:none">
  <div class="card rail">
    <h3 class="sec">Levels</h3>
    <ol id="rail"></ol>
    <div id="levelctl"></div>
  </div>
  <div>
    <div class="card" id="metacard" style="display:none"></div>
    <div class="card">
      <h3 class="sec">Decisions <span class="wlabel">point-buy</span> <span class="wlabel">option-picker</span> <span class="wlabel">ancestry-spend</span></h3>
      <div id="decisions"></div>
      <div class="addrow"><select class="select" id="tradd-lvl" style="max-width:80px"></select>
        <button class="exportbtn small" id="tradd">+ ancestry trait</button>
        <span class="src">extra trait slot (the engine keeps the point budget honest)</span></div>
      <div class="src" id="srcinfo"></div>
    </div>
    <div class="card">
      <h3 class="sec">Skills &amp; Trades <span class="wlabel">skill/trade allocator</span></h3>
      <div class="alloc" id="alloc"></div>
      <div class="addrow"><select class="select" id="ska-pick" style="max-width:220px"></select>
        <input class="select" id="ska-name" placeholder="custom name" style="display:none">
        <select class="select" id="ska-kind" style="max-width:100px;display:none"><option value="skills">skill</option><option value="trades">trade</option></select>
        <button class="exportbtn small" id="ska-btn">+ add</button></div>
      <h3 class="sec" style="margin-top:.8rem">Languages</h3>
      <div class="langs" id="langs"></div>
      <div class="addrow"><input class="select" id="lang-name" placeholder="new language">
        <select class="select" id="lang-flu" style="max-width:110px"><option>Limited</option><option selected>Fluent</option></select>
        <button class="exportbtn small" id="lang-btn">+ add</button></div>
    </div>
    <div class="card">
      <h3 class="sec">Review <span class="wlabel">live from replay() + catalog</span></h3>
      <table class="derived"><thead id="statshead"><tr><th>Stat</th><th>Derived</th><th>Sheet</th><th>Check</th></tr></thead>
        <tbody id="stats"></tbody></table>
      <div class="src" id="sheetnote" style="display:none">No sheet to compare against (new character, or just
      levelled) &mdash; the builder is the source of truth now; this export becomes the sheet.</div>
      <div id="budgets" style="margin-top:.55rem"></div>
      <div id="problems"></div>
      <div id="exports"></div>
      <details id="yamlwrap" style="display:none;margin-top:.5rem"><summary class="src" style="cursor:pointer">view / copy the exported YAML</summary>
      <pre class="yaml" id="yamlout" style="display:block"></pre></details>
    </div>
  </div>
</div>

<p class="foot">Self-contained: engine, full catalog and all six ledgers are baked in (regenerate with
<code>tools/builder_build.py</code>). The page tries a live <code>fetch()</code> of the sibling source files first
and falls back to the bake, so it runs from <code>file://</code> or a server. Pick a character with
<code>?char=&lt;handle&gt;</code>, start fresh with <code>?new=&lt;class&gt;</code>, or use the dropdown. In-progress
work is kept in this browser's local storage and offered for resume; you can also re-load your own exported
YAML (the engine re-validates anything loaded). Export PRESERVES the ledger's own YAML comments (header
provenance, inline notes, section markers) by re-anchoring them onto the re-serialised file; any comment whose
anchor was edited away is collected, marked, at the bottom for review. It round-trips cleanly through the engine.</p>

<script>
const CHARS = __CHARS_JSON__;
const NEWC = __NEWC_JSON__;
const B64 = __B64_JSON__;
const REL = __REL_JSON__;
const dec64 = b => new TextDecoder().decode(Uint8Array.from(atob(b), c=>c.charCodeAt(0)));
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

function modeFromURL(){
  const q = new URLSearchParams(location.search);
  const n = (q.get('new')||'').toLowerCase();
  if(NEWC.includes(n)) return {newClass:n};
  const h = q.get('char');
  return {char: CHARS.includes(h) ? h : CHARS[0]};
}
async function srcText(key){
  if(REL[key]){ try{ const r = await fetch(REL[key]); if(r.ok) return {text:await r.text(), via:"fetch"}; }catch(e){} }
  return {text: dec64(B64[key]), via:"baked"};
}

let api=null, pyodide=null, viaNote="", dirty=false, ST=null;
let mode = modeFromURL();
let handle = mode.newClass ? "new-"+mode.newClass : mode.char;
const storeKey = () => "dc20builder:" + handle;
const isCanon = () => ST && !ST.scratch && CHARS.includes(ST.handle);
const slug = s => ((s.character||"").trim().toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-+|-+$/g,"") || s.handle);

async function boot(){
  const sel = $('charsel');
  sel.innerHTML = '<optgroup label="party">' +
      CHARS.map(c=>`<option value="${c}" ${(!mode.newClass && c===handle)?'selected':''}>${c}</option>`).join("") +
    '</optgroup><optgroup label="new from scratch">' +
      NEWC.map(c=>`<option value="new:${c}" ${(mode.newClass===c)?'selected':''}>new ${c}</option>`).join("") +
    '</optgroup>';
  sel.onchange = () => {
    const u = new URL(location); u.searchParams.delete('char'); u.searchParams.delete('new');
    if(sel.value.startsWith('new:')) u.searchParams.set('new', sel.value.slice(4));
    else u.searchParams.set('char', sel.value);
    location.href = u;
  };
  pyodide = await loadPyodide();
  $('status').textContent = "Pyodide up. Installing PyYAML...";
  await pyodide.loadPackage("pyyaml");
  $('status').textContent = "Loading engine, catalog and ledgers...";
  const vias = {fetch:0, baked:0};
  for(const key of Object.keys(B64)){
    const fname = key === "engine" ? "build_engine.py" : key === "api" ? "builder_api.py"
                : key === "meta" ? "spells_meta.json" : key + ".yaml";
    const {text,via} = await srcText(key);
    pyodide.FS.writeFile(fname, text);
    vias[via]++;
  }
  viaNote = `sources: ${vias.fetch} fetched, ${vias.baked} baked`;
  await pyodide.runPythonAsync(
    "import builder_api\n" +
    "CATPATHS = {\n" +
    "    'spellblade':'spellblade.yaml','warlock':'warlock.yaml','commander':'commander.yaml',\n" +
    "    'barbarian':'barbarian.yaml','druid':'druid.yaml','ancestries':'ancestries.yaml',\n" +
    "    'spell_schools':'spell_schools.yaml','spell_sources':'spell_sources.yaml',\n" +
    "    'maneuvers':'maneuvers.yaml','talents':'talents.yaml',\n" +
    "    'skills_trades':'skills_trades.yaml'}\n" +
    "def make_api(handle):\n" +
    "    return builder_api.BuilderAPI(handle, CATPATHS)\n" +
    "def make_api_new(cls):\n" +
    "    return builder_api.BuilderAPI(None, CATPATHS, new_class=cls)\n" +
    "def make_api_text(handle, text):\n" +
    "    return builder_api.BuilderAPI(handle, CATPATHS, ledger_text=text)\n");
  api = mode.newClass ? pyodide.globals.get("make_api_new")(mode.newClass)
                      : pyodide.globals.get("make_api")(handle);
  render(JSON.parse(api.state()));
  $('app').style.display = "grid";
  $('status').className = "ready";
  $('status').textContent = "Ready - engine running in the browser. Edit any highlighted decision.";
  checkWIP();
}

function checkWIP(){
  let w = null;
  try{ w = JSON.parse(localStorage.getItem(storeKey())||"null"); }catch(e){}
  if(!w || !w.yaml) return;
  $('resume').style.display = "block";
  $('resume').innerHTML = `In-progress work for <b>${esc(handle)}</b> saved ${esc(new Date(w.ts).toLocaleString())} in this browser.
    <a href="#" id="res-yes">Resume it</a> &middot; <a href="#" id="res-no">Discard it</a>`;
  $('res-yes').onclick = ev => { ev.preventDefault();
    api = pyodide.globals.get("make_api_text")(handle, w.yaml);
    dirty = true; $('resume').style.display = "none";
    render(JSON.parse(api.state())); };
  $('res-no').onclick = ev => { ev.preventDefault();
    localStorage.removeItem(storeKey()); $('resume').style.display = "none"; };
}

function saveWIP(){
  try{ localStorage.setItem(storeKey(), JSON.stringify({yaml: api.export_yaml(), ts: Date.now()})); }catch(e){}
}

function optHTML(options, current, curGroup){
  const isCur = o => o.name===current && (!curGroup || o.group===curGroup);
  const groups = {};
  let found = false;
  for(const o of options){ (groups[o.group||''] ||= []).push(o); if(isCur(o)) found=true; }
  if(!found && current!=null){  // fall back to name-only if the group hint missed
    curGroup = undefined;
    for(const o of options) if(o.name===current) found=true;
  }
  let h = found ? "" : `<option value="${esc(current)}" selected>${current==='(undecided)'?'&mdash; choose &mdash;':esc(current)+' (off-catalog)'}</option>`;
  for(const [g, os] of Object.entries(groups)){
    const inner = os.map(o=>`<option value="${esc(o.name)}" ${isCur(o)?'selected':''}>${esc(o.label||o.name)}</option>`).join("");
    h += g ? `<optgroup label="${esc(g)}">${inner}</optgroup>` : inner;
  }
  return h;
}

function render(s){
  ST = s;
  document.title = "DC20 Builder - " + s.character;
  // canon loudness
  const canon = !s.scratch && CHARS.includes(s.handle);
  if(canon && dirty){
    $('canonbar').style.display = "block";
    $('canonbar').innerHTML = `&#9888; EDITING CANON &mdash; these changes touch <b>${esc(s.character)}</b>'s canonical
      ledger in-memory only. Nothing is saved until you export; a <b>respec export</b>
      (<code>${esc(s.handle)}.respec.yaml</code>) can never replace the party version, only the confirm-gated
      canon export can.`;
  } else $('canonbar').style.display = "none";
  // rail
  let rail="";
  for(let l=1; l<=s.level; l++) rail += `<li class="${l===s.level?'cur':''}">L${l}${l===s.level?' &larr; current':''}</li>`;
  for(const p of s.planned) rail += `<li class="next">+ L${p} <span style="font-size:.68rem">planned</span></li>`;
  $('rail').innerHTML = rail;
  let lv = "";
  if(s.next){
    lv += `<button class="exportbtn lvlbtn" id="addlevel">&#8679; ${s.next.has_plan ? 'Promote planned L'+s.next.level : 'Add level '+s.next.level}</button>
      <div class="src">${esc(s.next.summary)}${s.next.features.length? '<br>features: '+esc(s.next.features.join(', ')):''}</div>`;
  }
  if(s.undo_level) lv += `<div class="src"><a href="#" id="undolevel">undo add L${s.undo_level}</a></div>`;
  $('levelctl').innerHTML = lv;
  if($('addlevel')) $('addlevel').onclick = () => refresh(api.add_level());
  if($('undolevel')) $('undolevel').onclick = ev => { ev.preventDefault(); refresh(api.undo_add_level()); };
  // meta card (new-from-scratch)
  if(s.scratch){
    const found = s.anc_lists_all.filter(a => (s.ancestry||"").includes(a));
    const ancSel = (id, cur, blankLbl) => `<select class="select" id="${id}" style="max-width:130px">` +
      `<option value="-" ${cur?'':'selected'}>${blankLbl}</option>` +
      s.anc_lists_all.map(a=>`<option ${a===cur?'selected':''}>${a}</option>`).join("") + `</select>`;
    $('metacard').style.display = "block";
    $('metacard').innerHTML = `<h3 class="sec">Character <span class="wlabel">new from scratch</span></h3>
      <div class="pb">
        <label>name <input class="select" id="m-character" value="${esc(s.character||'')}"></label>
        <label>player <input class="select" id="m-player" style="max-width:110px" value="${esc(s.player||'')}"></label>
        <label>background <input class="select" id="m-background" style="max-width:130px" value="${esc(s.background||'')}"></label>
        <label>ancestry ${ancSel('m-anc1', found[0], '&mdash; choose &mdash;')} + ${ancSel('m-anc2', found[1], '-')}</label>
      </div>`;
    for(const f of ['character','player','background'])
      $('m-'+f).onchange = el => refresh(api.set_meta(f, $('m-'+f).value));
    const anc = () => refresh(api.set_ancestry($('m-anc1').value==='-'?'':$('m-anc1').value, $('m-anc2').value));
    $('m-anc1').onchange = anc; $('m-anc2').onchange = anc;
  } else $('metacard').style.display = "none";
  // decisions - grouped by level into collapsers; current level (and anything
  // undecided) open, history + plan collapsed
  const undecAt = {};
  for(const t of s.decisions) if(!t.plan && String(t.pick)==="(undecided)") undecAt[t.level]=(undecAt[t.level]||0)+1;
  const rowHTML = t => {
    if(t.widget === "pointbuy"){
      const sel = a => { let o=""; for(let v=-2; v<=t.limit; v++) o += `<option value="${v}" ${t.attrs[a]===v?'selected':''}>${v}</option>`; return o; };
      const bad = t.spent !== t.budget ? " bad" : "";
      return `<div class="dec edit"><span class="lv">L1</span><span class="slot">attributes</span>
        <span class="pick pb">` +
        Object.keys(t.attrs).map(a=>`<label>${a} <select class="select" style="max-width:70px" data-attr="${a}">${sel(a)}</select></label>`).join("") +
        `<span class="spent${bad}">point buy: ${t.spent}/${t.budget}</span></span></div>`;
    }
    const isnew = String(t.note||"").includes("Added in builder");
    const cls = "dec" + (t.editable?" edit":"") + (t.inferred?" inferred":"") + (t.plan?" plan":"") + (isnew?" newlvl":"");
    let body;
    if(t.editable && t.options){
      body = `<span class="pick"><select class="select" data-dec="${esc(t.id)}">${optHTML(t.options, t.current, t.current_group)}</select>` +
        ((t.cost!==null && t.cost!==undefined) ? ` <span style="font-size:.72rem;color:var(--warn)">(cost ${t.cost})</span>`:"") +
        (t.removable ? ` <a href="#" class="rm" data-rm="${esc(t.id)}" title="remove this slot">&times;</a>`:"") + `</span>`;
    } else {
      const cost = (t.cost!==null && t.cost!==undefined) ? ` <span style="font-size:.72rem;color:var(--warn)">(cost ${t.cost})</span>`:"";
      const allocHint = (!t.plan && (t.slot==='skill'||t.slot==='trade'))
        ? ' <span style="font-size:.7rem;color:var(--accent)">&rarr; apply mastery changes in the allocator below</span>' : '';
      body = `<span class="pick">${esc(t.pick)}${cost}${t.inferred?' <span style="font-size:.7rem">[inferred]</span>':''}${t.plan?' <span style="font-size:.7rem">[plan]</span>':''}${t.note?` <span style="font-size:.7rem;color:var(--warn)">${esc(t.note)}</span>`:''}${allocHint}</span>`;
    }
    return `<div class="${cls}"><span class="lv">L${t.level}</span><span class="slot">${esc(t.slot)}</span>${body}</div>`;
  };
  let d = `<div style="font-size:.85rem;margin-bottom:.5rem"><b>${esc(s.character)}</b> - ${esc(s.klass)} (${esc(s.subclass||'?')}) | ${esc(s.ancestry||'')}</div>`;
  const byLevel = {};
  for(const t of s.decisions) (byLevel[t.level] ||= []).push(t);
  for(const lvl of Object.keys(byLevel).map(Number).sort((a,b)=>a-b)){
    const rows = byLevel[lvl].map(rowHTML).join("");
    const plan = byLevel[lvl].every(t=>t.plan);
    const open = (!plan && (lvl===s.level || undecAt[lvl])) || (lvl===1 && s.level===1);
    const label = lvl===1 ? "Level 1 &mdash; character creation" : `Level ${lvl}` + (plan?" (plan)":"") +
      (lvl===s.level?" &larr; current":"") + (undecAt[lvl]?` &mdash; ${undecAt[lvl]} undecided`:"");
    d += `<details class="lvlgrp${plan?' plan':''}" ${open?'open':''}><summary>${label}</summary>${rows}</details>`;
  }
  $('decisions').innerHTML = d;
  $('srcinfo').textContent = viaNote;
  document.querySelectorAll('[data-dec]').forEach(el => el.onchange = () => refresh(api.set_decision(el.dataset.dec, el.value)));
  document.querySelectorAll('[data-attr]').forEach(el => el.onchange = () => refresh(api.set_attr(el.dataset.attr, el.value)));
  document.querySelectorAll('[data-rm]').forEach(el => el.onclick = ev => { ev.preventDefault(); refresh(api.remove_decision(el.dataset.rm)); });
  // + ancestry trait control
  $('tradd-lvl').innerHTML = s.anc_levels.map(l=>`<option value="${l}">L${l}</option>`).join("");
  $('tradd').onclick = () => refresh(api.add_trait($('tradd-lvl').value));
  // skills / trades allocator
  $('alloc').innerHTML = s.alloc.map(a =>
    `<div class="row"><span class="nm" title="${esc(a.name)}">${esc(a.kind==='skills'?'':'[T] ')}${esc(a.name)}${a.limit_raise?' *':''}</span>
     <span><select class="select" style="max-width:110px" data-mast="${esc(a.id)}">` +
     a.options.map(o=>`<option value="${esc(o)}" ${String(a.mastery)===o?'selected':''}>${o==='None'?'-':esc(o)}</option>`).join("") +
     `</select>${a.removable?` <a href="#" class="rm" data-mastrm="${esc(a.id)}">&times;</a>`:''}</span></div>`).join("");
  document.querySelectorAll('[data-mast]').forEach(el => el.onchange = () => refresh(api.set_mastery(el.dataset.mast, el.value)));
  document.querySelectorAll('[data-mastrm]').forEach(el => el.onclick = ev => { ev.preventDefault(); refresh(api.remove_mastery(el.dataset.mastrm)); });
  const stg = {};
  for(const o of s.skill_trade_options) (stg[o.group] ||= []).push(o);
  $('ska-pick').innerHTML = Object.entries(stg).map(([g,os]) =>
      `<optgroup label="${esc(g)}">${os.map(o=>`<option value="${esc(o.kind)}|${esc(o.name)}">${esc(o.name)}</option>`).join("")}</optgroup>`
    ).join("") + `<option value="::custom">custom&hellip;</option>`;
  const skaCustom = () => { const c = $('ska-pick').value === "::custom";
    $('ska-name').style.display = c ? "" : "none"; $('ska-kind').style.display = c ? "" : "none"; };
  $('ska-pick').onchange = skaCustom; skaCustom();
  $('ska-btn').onclick = () => {
    const v = $('ska-pick').value;
    if(v === "::custom"){ const n = $('ska-name').value.trim(); if(n) refresh(api.add_mastery($('ska-kind').value, n)); }
    else { const [kind, name] = [v.slice(0, v.indexOf('|')), v.slice(v.indexOf('|')+1)]; refresh(api.add_mastery(kind, name)); }
  };
  // languages
  $('langs').innerHTML = s.languages.map(l =>
    `<div class="row"><span class="nm">${esc(l.name)}</span>
     <span><select class="select" style="max-width:100px" data-lang="${l.i}" ${l.fixed?'disabled':''}>` +
     ['Limited','Fluent'].map(f=>`<option ${l.fluency===f?'selected':''}>${f}</option>`).join("") +
     `</select> <span style="font-size:.72rem;color:var(--warn)">(${l.cost} LP)</span>` +
     (l.fixed?'':` <a href="#" class="rm" data-langrm="${l.i}">&times;</a>`) + `</span></div>`).join("");
  document.querySelectorAll('[data-lang]').forEach(el => el.onchange = () => refresh(api.set_language(el.dataset.lang, el.value)));
  document.querySelectorAll('[data-langrm]').forEach(el => el.onclick = ev => { ev.preventDefault(); refresh(api.remove_language(el.dataset.langrm)); });
  $('lang-btn').onclick = () => { const n = $('lang-name').value.trim(); if(n) refresh(api.add_language(n, $('lang-flu').value)); };
  // stats (collapse the Sheet/Check columns when there is no sheet to compare against)
  const noSheet = s.stats.every(r=>r[2]==='-');
  $('statshead').innerHTML = noSheet ? `<tr><th>Stat</th><th>Derived</th></tr>`
    : `<tr><th>Stat</th><th>Derived</th><th>Sheet</th><th>Check</th></tr>`;
  $('sheetnote').style.display = noSheet ? "block" : "none";
  $('stats').innerHTML = s.stats.map(r=> noSheet
    ? `<tr><td>${esc(r[0])}</td><td>${esc(r[1])}</td></tr>`
    : `<tr><td>${esc(r[0])}</td><td>${esc(r[1])}</td><td>${esc(r[2])}</td><td class="mk-${r[3]}">${esc(r[3])}</td></tr>`).join("");
  // budgets
  $('budgets').innerHTML = s.budgets.map(b=>`<div class="budget">&bull; ${esc(b)}</div>`).join("");
  // problems (engine + catalog + builder) + advisories (legal but probably unfinished)
  const probs = s.problems.map(p=>"engine: "+p).concat(s.catalog_problems).concat(s.builder_problems);
  let ph = "";
  if(probs.length){
    ph = `<div class="prob"><b>${probs.length} problem(s):</b>
      <ul>${probs.map(p=>`<li>${esc(p)}</li>`).join("")}</ul></div>`;
  } else {
    ph = `<div class="prob clean">&check; All checks passed - budgets balanced, no illegal picks.</div>`;
  }
  if((s.advisories||[]).length){
    ph += `<div class="prob adv"><b>Unspent points</b> (legal, but level-up night usually spends them):
      <ul>${s.advisories.map(p=>`<li>${esc(p)}</li>`).join("")}</ul></div>`;
  }
  $('problems').innerHTML = ph;
  // exports
  let eb;
  if(s.scratch){
    eb = `<button class="exportbtn" id="exp-new">&darr; Export ${esc(slug(s))}.yaml</button>`;
  } else if(canon){
    eb = `<button class="exportbtn" id="exp-respec">&darr; Respec export &rarr; ${esc(s.handle)}.respec.yaml</button>
          <button class="exportbtn canonbtn" id="exp-canon">&darr; CANON export &rarr; ${esc(s.handle)}.yaml</button>
          <div class="src">Respec = a scratch file for what-ifs; it is never in the party include set. CANON is the
          level-up-night export: once committed it REPLACES ${esc(s.handle)}.yaml for the whole party.</div>`;
  } else {
    eb = `<button class="exportbtn" id="exp-new">&darr; Export ${esc(s.handle)}.yaml</button>`;
  }
  $('exports').innerHTML = eb;
  const undecided = s.builder_problems.length;
  if($('exp-new')) $('exp-new').onclick = () => doExport((s.scratch ? slug(s) : s.handle) + ".yaml");
  if($('exp-respec')) $('exp-respec').onclick = () => doExport(s.handle + ".respec.yaml");
  if($('exp-canon')) $('exp-canon').onclick = () => {
    let msg = `CANON export: committing ${s.handle}.yaml REPLACES ${s.character}'s canonical ledger for the whole party.\n\nFor a what-if, cancel and use the respec export instead.`;
    if(undecided) msg = `${undecided} builder problem(s) are still open (undecided picks).\n\n` + msg;
    if(probs.length && !undecided) msg = `${probs.length} problem(s) are still flagged in the review panel.\n\n` + msg;
    if(confirm(msg)) doExport(s.handle + ".yaml");
  };
}

function refresh(stateJson){
  dirty = true;
  render(JSON.parse(stateJson));
  saveWIP();
}

function doExport(fname){
  const y = api.export_yaml();
  $('yamlwrap').style.display = "block";
  $('yamlout').textContent = y;
  const blob = new Blob([y], {type:"text/yaml"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = fname; a.click();
  URL.revokeObjectURL(a.href);
}

$('loadyaml').onchange = async ev => {
  const f = ev.target.files[0]; if(!f || !pyodide) return;
  try{
    const text = await f.text();
    const base = f.name.replace(/\.ya?ml$/i, "");
    handle = base.split('.')[0];
    api = pyodide.globals.get("make_api_text")(handle, text);
    dirty = true;
    render(JSON.parse(api.state()));
    $('status').className = "ready";
    $('status').textContent = `Loaded ${f.name} - the engine has re-validated it (see Review).`;
  }catch(e){
    $('status').className = "err";
    $('status').textContent = "Could not load that YAML: " + e;
  }
};

boot().catch(e => { $('status').className="err";
  $('status').textContent = "ERROR: " + (e && e.stack ? e.stack : e); });
</script>
</div></body></html>
"""


def b64_file(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def b64_str(s):
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def main():
    ap = argparse.ArgumentParser(description="Generate builds/builder.html (six characters + scratch mode).")
    ap.add_argument("--out", default=os.path.join(REPO, "builds", "builder.html"))
    args = ap.parse_args()

    meta = extract_spell_meta(os.path.join(REPO, "rules", "spells.md"))
    b64 = {"engine": b64_file(os.path.join(REPO, "tools", "build_engine.py")),
           "api": b64_str(API_PY),
           "meta": b64_str(json.dumps(meta, ensure_ascii=False))}
    rel = {"engine": "../tools/build_engine.py"}
    for c in CHARS:
        b64[c] = b64_file(os.path.join(REPO, "builds", c + ".yaml"))
        rel[c] = c + ".yaml"
    for c in CATALOG:
        b64[c] = b64_file(os.path.join(REPO, "builds", "catalog", c + ".yaml"))
        rel[c] = "catalog/" + c + ".yaml"

    html = (TEMPLATE
            .replace("__CHARS_JSON__", json.dumps(CHARS))
            .replace("__NEWC_JSON__", json.dumps(NEWCLASSES))
            .replace("__B64_JSON__", json.dumps(b64))
            .replace("__REL_JSON__", json.dumps(rel)))
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)
    print("wrote %s (%d bytes; %d spells in meta)" % (args.out, len(html), len(meta)))


if __name__ == "__main__":
    main()
