#!/usr/bin/env python3
"""Generate builds/builder.html - the rung-3 character builder, ALL SIX characters.

Build-order step 4 (RUNG3_PLAN section 7): the step-3 skeleton generalised. The page loads
any of the six ledgers by handle (?char=tanrielle|runt|minimus|bonan|scaletrix|xanwyn, plus
an on-page switcher), renders the character's full decision timeline, and makes the decisions
editable through the five reusable widgets from the wireframe: point-buy allocator (chargen
attributes), option-picker (spells / maneuvers / talents / attributes / paths / subclasses /
disciplines / spell schools), ancestry-spend allocator (ancestry traits, catalog-priced),
skill/trade allocator (mastery levels), and the review screen (live replay() + catalog
legality). Every edit re-runs the REAL tools/build_engine.py via Pyodide; the catalog files
supply option lists and a catalog-level legality pass the engine does not do (spell access
models per class, maneuver existence, talent resolution).

Bakes the engine + the full builds/catalog/ + ALL SIX ledgers + a scripted spells-metadata
extract (name -> source/school/tags, from rules/spells.md) + the Python glue module into ONE
self-contained page as base64, so it runs from file:// with no external data dependency. The
page ALSO tries a live fetch() of the sibling source files first, so a deployed https copy
reads fresh data; the bake is the fallback.

SCRIPTED - regenerate whenever the engine, catalog, or any ledger changes, so the page can
never drift from them (same discipline as tools/catalog_build.py):

    python3 tools/builder_build.py
"""
import argparse
import base64
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)  # tools/.. == campaign/repo root

CHARS = ["tanrielle", "runt", "minimus", "bonan", "scaletrix", "xanwyn"]
CATALOG = ["spellblade", "warlock", "commander", "barbarian", "druid",
           "ancestries", "spell_schools", "spell_sources", "maneuvers", "talents"]

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
import json, re
import yaml
import build_engine as eng

EDITABLE_SLOTS = {'talent', 'path', 'subclass', 'discipline', 'spell', 'maneuver',
                  'attribute', 'ancestry_trait'}
PLACEHOLDER_MARKERS = ('not itemised', 'does NOT exist')
MASTERIES = [None, 'Novice', 'Adept', 'Expert']


def base_name(pick):
    return re.sub(r"\s*\([^)]*\)\s*$", '', str(pick).replace('’', "'")).strip()


def is_composite(pick):
    s = str(pick)
    return (',' in s or ' + ' in s or ':' in s.split('(')[0] and s.lower().startswith(('4th',))
            or any(m in s for m in PLACEHOLDER_MARKERS))


class BuilderAPI:
    # Loads one ledger by handle + the full catalog; exposes a JSON decision-model API.
    def __init__(self, handle, catalog_paths, meta_path='spells_meta.json'):
        self.handle = handle
        self.ledger = yaml.safe_load(open(handle + '.yaml', encoding='utf-8'))
        self.cat = {k: yaml.safe_load(open(p, encoding='utf-8'))
                    for k, p in catalog_paths.items()}
        self.meta = json.load(open(meta_path, encoding='utf-8'))
        self.cls = self.ledger['class']
        self.ccat = self.cat[self.cls.lower()]
        self.aliases = self.cat['ancestries'].get('source_aliases', {})

    # ---------- ancestry lists ----------
    def _anc_lists(self):
        lists, extra = [], []
        for t in self._traits():
            src = self.aliases.get(t.get('source'), t.get('source'))
            if src and src in self.cat['ancestries']['ancestries'] and src not in lists:
                lists.append(src)
        for t in self._traits():   # unsourced / cross-list traits (Redeemed -> Angelborn etc.)
            if self._anc_row(t.get('source'), t.get('name')) is None:
                for lst, rows in self.cat['ancestries']['ancestries'].items():
                    if any(r['name'] == base_name(t['name']) or
                           base_name(t['name']) in (r.get('aliases') or []) for r in rows):
                        if lst not in lists and lst not in extra:
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

    def _anc_options(self):
        opts = []
        for lst in self._anc_lists():
            for row in self.cat['ancestries']['ancestries'][lst]:
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
            chosen = list(self.ledger['chargen'].get('spell_schools') or []) + self._ssi_schools()
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
            return [{'name': a, 'group': '', 'label': a} for a in
                    ('might', 'agility', 'charisma', 'intelligence')]
        if slot == 'path':
            return [{'name': p, 'group': '', 'label': p} for p in self.ccat['paths']]
        if slot == 'subclass':
            return [{'name': s, 'group': '', 'label': s} for s in self.ccat['subclasses']]
        if slot == 'discipline':
            return [{'name': d['name'], 'group': '',
                     'label': d['name'] + (' %s' % d['grants'] if d.get('grants') else '')}
                    for d in self.ccat.get('disciplines', [])]
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
            if not is_composite(s):
                spell_names.append(str(s))
        for lvl in sorted(self.ledger.get('levels') or {}):
            for e in self.ledger['levels'][lvl] or []:
                if e.get('slot') == 'spell' and not is_composite(e.get('pick')):
                    spell_names.append(base_name(e['pick']) if '(' in str(e['pick']) else str(e['pick']))
        for s in spell_names:
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
            if not is_composite(m) and m not in all_man:
                probs.append('catalog: maneuver %r does not exist in 0.10.5' % m)
        for lvl in sorted(self.ledger.get('levels') or {}):
            for e in self.ledger['levels'][lvl] or []:
                if e.get('slot') == 'maneuver' and not is_composite(e.get('pick')) \
                        and str(e['pick']) not in all_man:
                    probs.append('catalog: maneuver %r does not exist in 0.10.5' % e['pick'])
                if e.get('slot') == 'ancestry_trait':
                    row = self._anc_find(e['pick'])[1]
                    if row is not None and e.get('cost') != row['cost']:
                        probs.append('catalog: %s costs %s, ledger says %s'
                                      % (base_name(e['pick']), row['cost'], e.get('cost')))
        for t in self.ledger['chargen'].get('ancestry_traits') or []:
            if any(mk in str(t.get('name')) for mk in PLACEHOLDER_MARKERS):
                continue
            row = self._anc_find(t['name'])[1]
            if row is None:
                probs.append('catalog: ancestry trait %r unknown' % t['name'])
            elif t.get('cost', 0) != row['cost']:
                probs.append('catalog: %s costs %s, ledger says %s'
                              % (base_name(t['name']), row['cost'], t.get('cost', 0)))
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
                                note='placeholder - itemisation pending' if ph else None))
        for c in cg.get('class_choices') or []:
            ds.append({'id': None, 'level': 1, 'slot': c['slot'], 'pick': ', '.join(c['picks']),
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
                                    plan=lvl > cur))
        return ds

    def _dec(self, did, lvl, slot, pick, cost, inferred, editable, note=None, plan=False):
        d = {'id': did, 'level': lvl, 'slot': slot, 'pick': pick, 'cost': cost,
             'inferred': inferred, 'editable': editable and not plan, 'plan': plan,
             'widget': 'picker' if (editable and not plan) else 'fixed'}
        if note:
            d['note'] = note
        if d['widget'] == 'picker':
            d['options'] = self._options_for(slot)
            d['current'] = (base_name(pick) if slot in ('ancestry_trait', 'talent', 'spell',
                                                        'maneuver', 'subclass') else str(pick))
            if slot == 'ancestry_trait':
                row = self._anc_find(pick)[1]
                if row is not None:
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
                            'options': [str(x) for x in MASTERIES]})
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

    def state(self):
        cur = self.ledger['current_level']
        rep = eng.replay(self.ledger, cur)
        stats, budgets = self._sections(rep.lines)
        planned = [l for l in sorted(self.ledger.get('levels') or {}) if l > cur]
        return json.dumps({
            'handle': self.handle,
            'character': self.ledger.get('character'),
            'klass': self.cls,
            'subclass': self.ledger.get('subclass'),
            'ancestry': self.ledger.get('ancestry'),
            'level': cur, 'planned': planned,
            'decisions': self._decisions(),
            'alloc': self._alloc(),
            'stats': stats, 'budgets': budgets,
            'problems': rep.problems,
            'catalog_problems': self.catalog_problems(),
        })

    # ---------- edits ----------
    def set_decision(self, did, value):
        did = str(did)
        value = str(value)
        if did.startswith('cg:'):
            _, kind, idx = did.split(':')
            i = int(idx)
            cg = self.ledger['chargen']
            if kind == 'school':
                cg['spell_schools'][i] = value
            elif kind == 'spell':
                cg['spells'][i] = value
            elif kind == 'man':
                cg['maneuvers'][i] = value
            elif kind == 'trait':
                self._set_trait(cg['ancestry_traits'][i], value)
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
        return self.state()

    def _set_trait(self, t, value, entry=False):
        lst, row = self._anc_find(value)
        key = 'pick' if entry else 'name'
        t[key] = value
        if row is not None:
            t['cost'] = row['cost']
            t['source'] = lst
        t['note'] = 'Edited in builder; cost %s from catalog (%s).' % (
            row['cost'] if row else '?', lst)
        t.pop('inferred', None)

    def _edited(self, e):
        e['note'] = 'Edited in builder (%s).' % self.handle
        e.pop('inferred', None)

    def set_attr(self, name, value):
        self.ledger['chargen']['attributes'][str(name)] = int(value)
        return self.state()

    def set_mastery(self, did, value):
        kind, name = str(did).split(':', 1)
        m = self.ledger[kind]['masteries'][name]
        m['mastery'] = None if value in ('None', '', 'null') else str(value)
        return self.state()

    def export_yaml(self):
        return yaml.dump(self.ledger, sort_keys=False, allow_unicode=True)
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
#status{font-size:.85rem;font-weight:600;background:#e9edf5;border:1px solid var(--line);
 border-radius:6px;padding:.5rem .75rem;margin-bottom:1rem}
#status.err{background:#fdecec;border-color:#f3b6b6;color:var(--bad)}
#status.ready{background:#e9f6ea;border-color:#a9d6ab;color:var(--ok)}
.builder{display:grid;grid-template-columns:150px 1fr;gap:1rem}
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
.wlabel{font-size:.64rem;text-transform:uppercase;letter-spacing:.05em;color:#fff;background:var(--accent);border-radius:4px;padding:.08rem .4rem}
.select{border:1px solid var(--accent);border-radius:6px;padding:.28rem .45rem;background:#fff;font-size:.84rem;max-width:420px}
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
.prob ul{margin:.3rem 0 0;padding-left:1.1rem}
.alloc{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:.4rem}
.alloc .row{border:1px solid var(--line);border-radius:6px;padding:.3rem .5rem;font-size:.82rem;display:flex;justify-content:space-between;align-items:center;gap:.4rem;background:var(--paper)}
.alloc .row .nm{overflow:hidden;text-overflow:ellipsis}
.exportbtn{margin-top:.7rem;background:var(--accent);color:#fff;border:none;border-radius:6px;padding:.5rem .95rem;font-size:.88rem;cursor:pointer}
.exportbtn:disabled{opacity:.5;cursor:default}
.foot{font-size:.76rem;color:var(--muted);margin-top:1rem}
.src{font-size:.72rem;color:var(--muted);margin-top:.4rem}
pre.yaml{background:#111;color:#c8e6c9;padding:.7rem;border-radius:6px;font-size:.76rem;white-space:pre-wrap;max-height:260px;overflow:auto;display:none}
</style></head>
<body><div class="wrap">
<h1>DC20 Character Builder</h1> <span class="badge">rung 3 - all six</span>
<select id="charsel"></select>
<p class="sub">The real <code>build_engine.py</code> runs in your browser via Pyodide; every edit
re-validates live against the engine AND the option catalog. Export writes the updated ledger YAML.</p>
<div id="status">Booting Pyodide (first load pulls a few MB from the CDN)&hellip;</div>

<div class="builder" id="app" style="display:none">
  <div class="card rail">
    <h3 class="sec">Levels</h3>
    <ol id="rail"></ol>
  </div>
  <div>
    <div class="card">
      <h3 class="sec">Decisions <span class="wlabel">point-buy</span> <span class="wlabel">option-picker</span> <span class="wlabel">ancestry-spend</span></h3>
      <div id="decisions"></div>
      <div class="src" id="srcinfo"></div>
    </div>
    <div class="card">
      <h3 class="sec">Skills &amp; Trades <span class="wlabel">skill/trade allocator</span></h3>
      <div class="alloc" id="alloc"></div>
    </div>
    <div class="card">
      <h3 class="sec">Review <span class="wlabel">live from replay() + catalog</span></h3>
      <table class="derived"><thead><tr><th>Stat</th><th>Derived</th><th>Sheet</th><th>Check</th></tr></thead>
        <tbody id="stats"></tbody></table>
      <div id="budgets" style="margin-top:.55rem"></div>
      <div id="problems"></div>
      <button class="exportbtn" id="export" disabled>&darr; Export YAML</button>
      <pre class="yaml" id="yamlout"></pre>
    </div>
  </div>
</div>

<p class="foot">Self-contained: engine, full catalog and all six ledgers are baked in (regenerate with
<code>tools/builder_build.py</code>). The page tries a live <code>fetch()</code> of the sibling source files first
and falls back to the bake, so it runs from <code>file://</code> or a server. Pick a character with
<code>?char=&lt;handle&gt;</code> or the dropdown. Export is a clean re-serialisation (inline YAML comments are
not preserved yet - a v-next item); it round-trips cleanly through the engine.</p>

<script>
const CHARS = __CHARS_JSON__;
const B64 = __B64_JSON__;
const REL = __REL_JSON__;
const dec64 = b => new TextDecoder().decode(Uint8Array.from(atob(b), c=>c.charCodeAt(0)));
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

function handleFromURL(){
  const h = new URLSearchParams(location.search).get('char');
  return CHARS.includes(h) ? h : CHARS[0];
}
async function srcText(key){
  if(REL[key]){ try{ const r = await fetch(REL[key]); if(r.ok) return {text:await r.text(), via:"fetch"}; }catch(e){} }
  return {text: dec64(B64[key]), via:"baked"};
}

let api=null, pyodide=null, viaNote="", handle=handleFromURL();
async function boot(){
  const sel = $('charsel');
  sel.innerHTML = CHARS.map(c=>`<option value="${c}" ${c===handle?'selected':''}>${c}</option>`).join("");
  sel.onchange = () => { const u = new URL(location); u.searchParams.set('char', sel.value); location.href = u; };
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
    "def make_api(handle):\n" +
    "    return builder_api.BuilderAPI(handle, {\n" +
    "        'spellblade':'spellblade.yaml','warlock':'warlock.yaml','commander':'commander.yaml',\n" +
    "        'barbarian':'barbarian.yaml','druid':'druid.yaml','ancestries':'ancestries.yaml',\n" +
    "        'spell_schools':'spell_schools.yaml','spell_sources':'spell_sources.yaml',\n" +
    "        'maneuvers':'maneuvers.yaml','talents':'talents.yaml'})\n" +
    "api = make_api('" + handle + "')\n");
  api = pyodide.globals.get("api");
  render(JSON.parse(api.state()));
  $('app').style.display = "grid";
  $('status').className = "ready";
  $('status').textContent = "Ready - engine running in the browser. Edit any highlighted decision.";
  $('export').disabled = false;
  $('export').onclick = doExport;
}

function optHTML(options, current){
  const groups = {};
  let found = false;
  for(const o of options){ (groups[o.group||''] ||= []).push(o); if(o.name===current) found=true; }
  let h = found ? "" : `<option value="${esc(current)}" selected>${esc(current)} (off-catalog)</option>`;
  for(const [g, os] of Object.entries(groups)){
    const inner = os.map(o=>`<option value="${esc(o.name)}" ${o.name===current?'selected':''}>${esc(o.label||o.name)}</option>`).join("");
    h += g ? `<optgroup label="${esc(g)}">${inner}</optgroup>` : inner;
  }
  return h;
}

function render(s){
  document.title = "DC20 Builder - " + s.character;
  // rail
  let rail="";
  for(let l=1; l<=s.level; l++) rail += `<li class="${l===s.level?'cur':''}">L${l}${l===s.level?' &larr; current':''}</li>`;
  for(const p of s.planned) rail += `<li class="next">+ L${p} <span style="font-size:.68rem">planned</span></li>`;
  $('rail').innerHTML = rail;
  // decisions
  let d = `<div style="font-size:.85rem;margin-bottom:.5rem"><b>${esc(s.character)}</b> - ${esc(s.klass)} (${esc(s.subclass||'?')}) | ${esc(s.ancestry||'')}</div>`;
  for(const t of s.decisions){
    if(t.widget === "pointbuy"){
      const sel = a => { let o=""; for(let v=-2; v<=t.limit; v++) o += `<option value="${v}" ${t.attrs[a]===v?'selected':''}>${v}</option>`; return o; };
      const bad = t.spent !== t.budget ? " bad" : "";
      d += `<div class="dec edit"><span class="lv">L1</span><span class="slot">attributes</span>
        <span class="pick pb">` +
        Object.keys(t.attrs).map(a=>`<label>${a} <select class="select" style="max-width:70px" data-attr="${a}">${sel(a)}</select></label>`).join("") +
        `<span class="spent${bad}">point buy: ${t.spent}/${t.budget}</span></span></div>`;
      continue;
    }
    const cls = "dec" + (t.editable?" edit":"") + (t.inferred?" inferred":"") + (t.plan?" plan":"");
    let body;
    if(t.editable && t.options){
      body = `<span class="pick"><select class="select" data-dec="${esc(t.id)}">${optHTML(t.options, t.current)}</select>` +
        ((t.cost!==null && t.cost!==undefined) ? ` <span style="font-size:.72rem;color:var(--warn)">(cost ${t.cost})</span>`:"") + `</span>`;
    } else {
      const cost = (t.cost!==null && t.cost!==undefined) ? ` <span style="font-size:.72rem;color:var(--warn)">(cost ${t.cost})</span>`:"";
      body = `<span class="pick">${esc(t.pick)}${cost}${t.inferred?' <span style="font-size:.7rem">[inferred]</span>':''}${t.plan?' <span style="font-size:.7rem">[plan]</span>':''}${t.note?` <span style="font-size:.7rem;color:var(--warn)">${esc(t.note)}</span>`:''}</span>`;
    }
    d += `<div class="${cls}"><span class="lv">L${t.level}</span><span class="slot">${esc(t.slot)}</span>${body}</div>`;
  }
  $('decisions').innerHTML = d;
  $('srcinfo').textContent = viaNote;
  document.querySelectorAll('[data-dec]').forEach(el => el.onchange = () => refresh(api.set_decision(el.dataset.dec, el.value)));
  document.querySelectorAll('[data-attr]').forEach(el => el.onchange = () => refresh(api.set_attr(el.dataset.attr, el.value)));
  // skills / trades allocator
  $('alloc').innerHTML = s.alloc.map(a =>
    `<div class="row"><span class="nm" title="${esc(a.name)}">${esc(a.kind==='skills'?'':'[T] ')}${esc(a.name)}${a.limit_raise?' *':''}</span>
     <select class="select" style="max-width:110px" data-mast="${esc(a.id)}">` +
     a.options.map(o=>`<option value="${esc(o)}" ${String(a.mastery)===o?'selected':''}>${o==='None'?'-':esc(o)}</option>`).join("") +
     `</select></div>`).join("");
  document.querySelectorAll('[data-mast]').forEach(el => el.onchange = () => refresh(api.set_mastery(el.dataset.mast, el.value)));
  // stats
  $('stats').innerHTML = s.stats.map(r=>
    `<tr><td>${esc(r[0])}</td><td>${esc(r[1])}</td><td>${esc(r[2])}</td><td class="mk-${r[3]}">${esc(r[3])}</td></tr>`).join("");
  // budgets
  $('budgets').innerHTML = s.budgets.map(b=>`<div class="budget">&bull; ${esc(b)}</div>`).join("");
  // problems (engine + catalog)
  const probs = s.problems.map(p=>"engine: "+p).concat(s.catalog_problems);
  if(probs.length){
    $('problems').innerHTML = `<div class="prob"><b>${probs.length} problem(s):</b>
      <ul>${probs.map(p=>`<li>${esc(p)}</li>`).join("")}</ul></div>`;
  } else {
    $('problems').innerHTML = `<div class="prob clean">&check; All checks passed - budgets balanced, no illegal picks.</div>`;
  }
}

function refresh(stateJson){ render(JSON.parse(stateJson)); }

function doExport(){
  const y = api.export_yaml();
  $('yamlout').style.display = "block";
  $('yamlout').textContent = y;
  const blob = new Blob([y], {type:"text/yaml"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = handle + ".yaml"; a.click();
  URL.revokeObjectURL(a.href);
}

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
    ap = argparse.ArgumentParser(description="Generate builds/builder.html (all six characters).")
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
            .replace("__B64_JSON__", json.dumps(b64))
            .replace("__REL_JSON__", json.dumps(rel)))
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)
    print("wrote %s (%d bytes; %d spells in meta)" % (args.out, len(html), len(meta)))


if __name__ == "__main__":
    main()
