
import copy
import json, re
import yaml
import build_engine as eng

EDITABLE_SLOTS = {'talent', 'path', 'subclass', 'discipline', 'spell', 'maneuver',
                  'attribute', 'ancestry_trait', 'pact_boon'}
# Slots whose composite/invalid entry can be re-picked via an escape-hatch dropdown
# (single clean-value slots; ancestry_trait/attribute excluded - they have cost/budget
# machinery and 'remainder not itemised' placeholders that a single pick can't replace).
REPLACEABLE_SLOTS = {'talent', 'subclass', 'discipline', 'spell', 'maneuver'}
# FR-7: slots whose picker hides options already chosen elsewhere (so the same one can't
# be picked twice). Kept to the clear "collectibles"; ancestry_trait / pact_boon /
# discipline are left to a later pass (they carry budget / choice-count machinery and
# existing harness expectations).
FR7_FILTER_SLOTS = {'spell', 'maneuver', 'talent', 'spell_school'}
# FR-8 slice 2: pickable grant resources that auto-materialise typed child picker-slots under
# their granting parent (boon / discipline / talent / subclass). Maps the plural grants key ->
# the singular child-slot name. Maneuvers/spells are deliberately NOT here: they keep the
# existing flat-pool + expand_composite model (the surgical slice-2 boundary). The rune /
# metamagic catalogs land in slices 3/4; the backbone is data-driven so those slices only add
# catalog data + an _options_for branch, no new plumbing.
# FR-3 slice 2: 'skills' joins the backbone so a PLANNED level's skill-point budget materialises
# editable skill child picker-slots (one per point). The picks live in granted_skills on a per-plan-
# level carrier entry (slot 'skills', grants {skills:N}); only add_planned_level emits that carrier,
# so completed/current levels keep the flat skills.masteries aggregate untouched (the Hybrid split).
# FR-17 (2026-07-18): 'trades' joins the backbone too, so a PLANNED level's trade-point budget
# materialises editable trade child picker-slots exactly like skills (grants {trades:M} on a per-
# plan-level carrier, picks in granted_trades). Skills AND trades share the point-buy plan model.
# BUG-32: the character sheet's "Features & Abilities" list. This ORDERED map is the single source of
# truth for which decision slots appear there and under what label; sheet() emits the rendered groups
# and the page just prints them. It used to be a hand-written list in the page JS, which silently
# dropped every slot nobody remembered to add: Xanwyn's runes, Runt's pact boons, Scaletrix's
# metamagic and her origin nodes were all invisible on the sheet, and the plural `class_features`
# row added for BUG-19 was too. builder_verify asserts every slot a real sheet can emit is covered.
SHEET_GROUPS = [('subclass', 'Subclass'), ('class_feature', 'Class features'),
                ('discipline', 'Disciplines'), ('pact_boon', 'Pact boons'), ('rune', 'Runes'),
                ('metamagic', 'Meta Magic'), ('path', 'Path'),
                ('bound_weapon_options', 'Bound weapon'), ('maneuver', 'Maneuvers'),
                ('talent', 'Talents'), ('ancestry_trait', 'Ancestry'),
                ('ancestry_origin', 'Origin'), ('spell_school', 'Spell schools'),
                ('source_choice', 'Spell source')]
# slots that are deliberately NOT in the abilities list: spells have their own panel, and these are
# point-buy / attribute bookkeeping rather than abilities.
SHEET_SLOT_SKIP = {'spell', 'spell_tagged', 'spell_sourced', 'spell_any',
                   'skills', 'trades', 'skill', 'trade', 'attribute'}
# ledger slot spellings that mean the same group (plural chargen carriers vs per-level rows)
SHEET_SLOT_ALIAS = {'class_features': 'class_feature', 'pact_boons': 'pact_boon',
                    'spellblade_disciplines': 'discipline'}

GRANT_CHILD_SLOTS = {'runes': 'rune', 'metamagic': 'metamagic', 'skills': 'skill', 'trades': 'trade',
                     'disciplines': 'discipline'}   # BUG-21: Paladin Lay on Hands grants one
# FR-17: a planned skill/trade pick can buy a Mastery-Limit raise ("cap+", core-rules.md l.991-1005):
# it may sit ONE tier above the level cap and costs 2 points (the tier step + the limit raise). The
# purchase is recorded as a " (cap+)" suffix on the granted value ("Awareness: Expert (cap+)"). A
# bare CAPARM value marks a slot that is armed for cap+ but not yet filled (so the picker offers the
# above-cap option before a skill is chosen).
CAPARM = '(cap+)'
PLAN_POINTBUY = ('skills', 'trades')   # FR-3/FR-17 plan-level point-buy carriers
# FR-20: within a level the decision pickers render in chargen-flow order
# (Darryl's call 2026-07-18): attributes -> class/subclass -> ancestry -> resources.
# Each top-level row's slot maps to a category rank; grant-child rows (GC#...) inherit
# their parent block's rank so they stay glued directly under the parent (see
# _reorder_decisions). Unknown slots fall to resources (rank 3).
FR20_CAT = {
    # 0: attributes (point-buy at chargen; Attribute Increase at a level)
    'attributes': 0, 'attribute': 0,
    # 1: class / subclass structure
    'subclass': 1, 'pact_boon': 1, 'discipline': 1, 'spell_school': 1,
    'talent': 1, 'path': 1, 'class_feature': 1, 'class_features': 1,
    'spellblade_disciplines': 1, 'bound_weapon_options': 1,
    # 2: ancestry
    'ancestry_trait': 2, 'ancestry_traits': 2,
    # 3: resources (spells, maneuvers, skill/trade point-buy carriers + their children)
    'spell': 3, 'maneuver': 3, 'spell_tagged': 3, 'spell_sourced': 3, 'spell_any': 3,
    'spells': 3, 'maneuvers': 3,
    'skills': 3, 'trades': 3, 'skill': 3, 'trade': 3, 'rune': 3, 'metamagic': 3,
}
FR20_DEFAULT_RANK = 3
PLACEHOLDER_MARKERS = ('not itemised', 'does NOT exist')
MASTERIES = [None, 'Novice', 'Adept', 'Expert']
UNDECIDED = '(undecided)'
BUILDER_NOTE = 'Added in builder'
LANG_COSTS = {'Limited': 1, 'Fluent': 2}
CLASS_NAMES = {'spellblade': 'Spellblade', 'warlock': 'Warlock', 'commander': 'Commander',
               'barbarian': 'Barbarian', 'druid': 'Druid'}
# DERIVED from the engine's tuple, not a second copy of it: an ATTRS/ATTRIBUTES divergence
# would silently change which variants the picker offers and which grant keys it writes
# (trap 2, and the seam CH-5 added).
ATTRS = tuple(eng.ATTRIBUTES)

# BUG-10 (2026-07-16): picker labels used to print the raw grants dict
# (e.g. "Pact Weapon {'maneuvers': 2}"). Format grants into readable text instead.
_GRANT_WORDS = {'mp': 'MP', 'sp': 'SP', 'spells': 'spell', 'maneuvers': 'maneuver',
                'disciplines': 'discipline', 'trade_points': 'trade point',
                'skill_points': 'skill point'}


def _fmt_grants(grants):
    # Render a grants dict as e.g. " (+2 maneuvers, +1 MP)"; empty string when nothing to show.
    if not grants:
        return ''
    parts = []
    for k, v in grants.items():
        word = _GRANT_WORDS.get(k, k.replace('_', ' '))
        if isinstance(v, int):
            plural = word if (word.isupper() or abs(v) == 1) else word + 's'
            parts.append('%+d %s' % (v, plural))
        else:
            parts.append('%s %s' % (v, word))
    return ' (' + ', '.join(parts) + ')' if parts else ''


def base_name(pick):
    return re.sub(r"\s*\([^)]*\)\s*$", '', str(pick).replace('’', "'")).strip()


def is_composite(pick):
    s = str(pick)
    return (',' in s or ' + ' in s or ':' in s.split('(')[0] and s.lower().startswith(('4th',))
            or any(m in s for m in PLACEHOLDER_MARKERS))


def class_feature_rows(cfcat, cls, level):
    # BUG-19: the NAMED class features a class gains at one level (class_features.yaml), or [] when
    # that level has none / is outside the curated range. Flavor features are included (they are real
    # features, just never mechanical).
    return list(((cfcat.get('classes') or {}).get(cls) or {}).get(level) or [])


def class_feature_grants(rows, unarmored=True):
    # BUG-22: aggregate the numeric effects of a level's class features. `grants_unarmored` is only
    # counted when nothing armour-like is worn (Barbarian Berserker Defense, classes.md l.114-115);
    # grants on a feature that is really an existing picker (`choice:`) are left to that picker.
    agg = {}
    for f in rows:
        if f.get('choice'):
            continue
        src = dict(f.get('grants') or {})
        if unarmored:
            src.update(f.get('grants_unarmored') or {})
        for k, v in src.items():
            agg[k] = (agg.get(k, 0) + v) if isinstance(v, (int, float)) else v
    return agg


def is_unarmored(ledger):
    # the equipment model carries no armour TYPE, so match on the item name (documented heuristic in
    # class_features.yaml). A fresh scratch build has no equipment at all, so it reads unarmoured.
    return not any(re.search(r'armor|armour', str(e.get('name') or ''), re.I)
                   for e in (ledger.get('equipment') or []))


def blank_ledger(cls, ccat, cfcat=None):
    sp1 = ccat['spine'][1]
    cg = {'attribute_method': 'point_buy',
          'attributes': {a: -2 for a in ATTRS},
          'ancestry_traits': [],
          'spells': [UNDECIDED] * sp1.get('spells', 0),
          'maneuvers': [UNDECIDED] * sp1.get('maneuvers', 0),
          'combat_training': []}
    # BUG-19 / BUG-22: seed the L1 class features by NAME with their effects applied, so a fresh
    # character starts with what the class actually gives it (a scratch build previously showed no
    # class features at all at L1, and Berserker's +1 Speed / Might-Jump / +2 AD did nothing). Canon
    # ledgers are untouched: they carry their own hand-authored rows (cf. bonan.yaml).
    rows = class_feature_rows(cfcat or {}, cls, 1)
    if rows:
        entry = {'slot': 'class_features', 'picks': [f['name'] for f in rows],
                 'note': 'L1 class features (auto from class_features.yaml). ' + BUILDER_NOTE}
        g = class_feature_grants(rows, unarmored=True)
        if g:
            entry['grants'] = g
            if any(f.get('grants_unarmored') for f in rows):
                entry['note'] += ' Includes an unarmoured-only bonus; drop it if you wear armour.'
        cg.setdefault('class_choices', []).append(entry)
    sc = ccat.get('spellcasting') or {}
    if sc.get('model') == 'schools':
        cg['spell_schools'] = [UNDECIDED] * sc.get('schools_chosen', 0)
    # the L1 choice pickers APPEND (the class-features row above may already be there)
    if ccat.get('disciplines_pick_l1'):
        cg.setdefault('class_choices', []).append(
            {'slot': 'spellblade_disciplines',
             'picks': [UNDECIDED] * ccat['disciplines_pick_l1']})
    elif ccat.get('pact_boons_pick_l1'):
        cg.setdefault('class_choices', []).append(
            {'slot': 'pact_boons', 'picks': [UNDECIDED] * ccat['pact_boons_pick_l1']})
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
            self.ledger = blank_ledger(CLASS_NAMES[key], self.cat[key],
                                       self.cat.get('class_features'))
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
        self._undo = []   # a STACK: one snapshot per add_level, so every
                          # level added this session can be undone in turn
        self._resync_all_granted_effects()   # BUG-34: derived data, rebuilt on load

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
                if row.get('targets') == 'attributes':
                    # emit per-attribute variants; a target-less pick is meaningless to
                    # the engine (and used to crash its '(target)' parse). CH-5 (2026-07-28):
                    # driven by the catalog row's `targets`, not by matching the name
                    # 'Attribute Increase', so Attribute Decrease gets the same treatment
                    # from data alone. Anti-mirror: one flag, no per-name list here.
                    for a in ATTRS:
                        nm = '%s (%s)' % (row['name'], a)
                        opts.append({'name': nm, 'cost': row['cost'], 'group': lst,
                                     'label': '%s (%s, cost %s)' % (nm, lst, row['cost'])})
                    continue
                opts.append({'name': row['name'], 'cost': row['cost'], 'group': lst,
                             'label': '%s (%s, cost %s)' % (row['name'], lst, row['cost'])})
        return opts

    def _anc_budget(self):
        # FR-9: ancestry points spent vs the granted budget. Feeds the live "Ancestry points:
        # N of M spent" readout and gates the auto empty-slot in _decisions. Only counts levels
        # <= current (planned-level ancestry picks, if any, are speculative like the rest of a
        # plan), which is also what eng.ancestry_budget's `level` argument enforces.
        # BUG-36 (2026-07-28): the budget half USED to be re-derived here as 5 + 2 per class-table
        # feature, a hand-maintained copy of the engine's version that never read `ancestry_points`
        # grants, so Ancestry Increase ({ancestry_points: 4}) did nothing at all. It now calls the
        # engine, which owns the one definition (trap 2: two copies of a list always drift).
        cg = self.ledger['chargen']
        cur = self.ledger['current_level']
        spent = sum(int(t.get('cost', 0) or 0) for t in (cg.get('ancestry_traits') or []))
        for lvl, es in (self.ledger.get('levels') or {}).items():
            if int(lvl) > cur:
                continue
            for e in es or []:
                if e.get('slot') == 'ancestry_trait':
                    spent += int(e.get('cost', 0) or 0)
        return spent, eng.ancestry_budget(self.ledger, cur, self.ccat['spine'])

    def _anc_has_undecided(self):
        # FR-9: is there already an open (undecided) ancestry-trait slot anywhere? If so, the
        # auto empty-slot is suppressed so at most ONE ready slot ever shows. This is also what
        # keeps the harness safe: every test that builds ancestry adds a real undecided slot via
        # add_trait() before reading, so the auto slot never appears mid-build.
        if any(str(t.get('name')) == UNDECIDED for t in self.ledger['chargen'].get('ancestry_traits') or []):
            return True
        return any(e.get('slot') == 'ancestry_trait' and str(e.get('pick')) == UNDECIDED
                   for es in (self.ledger.get('levels') or {}).values() for e in es or [])

    def _anc_grant_levels(self):
        # Every level (<= current) that GAVE ancestry points. L1 always gives 5, L4/L8 add
        # '2 Ancestry Points', and BUG-36 adds any level whose pick declares an ancestry_points
        # grant. Owned by the engine so this and the state() 'anc_levels' dropdown are one list,
        # not two copies of it. Read by _anc_ready_level (max) and by state().
        return eng.ancestry_grant_levels(self.ledger, self.ledger['current_level'],
                                         self.ccat['spine'])

    def _anc_ready_level(self):
        # BUG-18: the level at which to render the ready ancestry slot = the highest level
        # (<= current) that granted ancestry points. Points are pooled, so after L4 the ready
        # slot belongs in the L4 block where the user just gained them, not back at chargen.
        # BUG-36: taking Ancestry Increase at L2 likewise surfaces its 4 points at L2.
        return max(self._anc_grant_levels())

    def _anc_minor_count(self):
        # count of chosen Minor (0-cost) ancestry traits (excluding undecided ready slots).
        return sum(1 for t in self._traits()
                   if str(t.get('name')) != UNDECIDED and int(t.get('cost', 0) or 0) == 0)

    def _anc_minor_room(self):
        # BUG-17: True when the one free Minor Trait has not been taken AND a 0-cost option is
        # still available to pick. Lets the ready slot show even at 0 points remaining.
        if self._anc_minor_count() >= 1:
            return False
        chosen = {base_name(str(t.get('name'))) for t in self._traits()}
        return any(int(o.get('cost', 0) or 0) == 0 and base_name(str(o['name'])) not in chosen
                   for o in self._anc_options())

    # ---------- grants-only maneuver/spell auto-heal (2026-07-19) ----------
    # The maneuver/spell analog of the FR-9 ancestry ready-slot. Model: the engine derives
    # "Maneuvers/Spells known" as a BUDGET (class table + path + all grants); the flat pool
    # (free-choice picks) + the granted_<resource> lists (FIXED grants, e.g. pact-boon
    # maneuvers) must supply that many NAMED picks. When fewer are named than the budget, a
    # gap exists (e.g. Scaletrix's unrecorded Arcane spells) and self-heals via a ready slot.
    def _res_slot(self, resource):
        return 'maneuver' if resource == 'maneuvers' else 'spell'

    def _res_budget(self, resource):
        # engine-derived known count = single source of truth for the budget.
        cur = self.ledger['current_level']
        lbl = 'Maneuvers known' if resource == 'maneuvers' else 'Spells known'
        try:
            return int(eng.replay(self.ledger, cur).derived.get(lbl) or 0)
        except Exception:
            return 0

    def _res_have(self, resource):
        # named picks filling the budget: decided flat free picks (chargen + per-level, at/below
        # current) + the fixed-grant names in granted_<resource> lists. Undecided / composite
        # entries do not count as filled.
        cur = self.ledger['current_level']
        gkey = 'granted_%s' % resource
        slot = self._res_slot(resource)
        have = sum(1 for x in (self.ledger['chargen'].get(resource) or [])
                   if str(x) != UNDECIDED and not is_composite(x))
        for c in (self.ledger['chargen'].get('class_choices') or []):
            have += sum(1 for g in (c.get(gkey) or []) if str(g) != UNDECIDED)
        for t in (self.ledger['chargen'].get('ancestry_traits') or []):   # FR-13a: spells childed on an ancestry trait
            if isinstance(t, dict):
                have += sum(1 for g in (t.get(gkey) or []) if str(g) != UNDECIDED)
        for lvl, es in (self.ledger.get('levels') or {}).items():
            if int(lvl) > cur:
                continue
            for e in es or []:
                if e.get('slot') == slot and str(e.get('pick')) != UNDECIDED and not is_composite(e.get('pick')):
                    have += 1
                have += sum(1 for g in (e.get(gkey) or []) if str(g) != UNDECIDED)
        return have

    def _res_has_undecided_at(self, resource, lvl):
        # an already-open undecided slot AT THIS LEVEL suppresses the level's ready slot, so at most ONE
        # ready slot ever shows per level (chaining on each pick, the FR-9 pattern) and the trips/scratch
        # harness stays safe. An undecided grant-child (e.g. a freshly re-picked pact boon's maneuver
        # slot) is itself the ready slot, so it suppresses the flat auto slot too.
        slot = self._res_slot(resource)
        gkey = 'granted_%s' % resource
        if lvl == 1:
            if any(str(x) == UNDECIDED for x in (self.ledger['chargen'].get(resource) or [])):
                return True
            for c in (self.ledger['chargen'].get('class_choices') or []):
                if any(str(x) == UNDECIDED for x in (c.get(gkey) or [])):
                    return True
            for t in (self.ledger['chargen'].get('ancestry_traits') or []):   # FR-13a childed grant
                if isinstance(t, dict) and any(str(x) == UNDECIDED for x in (t.get(gkey) or [])):
                    return True
        for e in ((self.ledger.get('levels') or {}).get(lvl) or []):
            if e.get('slot') == slot and str(e.get('pick')) == UNDECIDED:
                return True
            if any(str(x) == UNDECIDED for x in (e.get(gkey) or [])):
                return True
        return False

    def _res_has_undecided(self, resource):
        # any open undecided slot at or below the current level.
        return any(self._res_has_undecided_at(resource, lvl)
                   for lvl in range(1, self.ledger['current_level'] + 1))

    def _res_have_at(self, resource, lvl):
        # named picks RECORDED at one level: chargen (lvl 1) = the flat chargen list + the fixed-grant
        # names childed on chargen class choices / ancestry traits; lvl > 1 = that level's flat entries
        # + their grant children. Summed over 1..cur this equals _res_have.
        gkey = 'granted_%s' % resource
        slot = self._res_slot(resource)
        n = 0
        if lvl == 1:
            n += sum(1 for x in (self.ledger['chargen'].get(resource) or [])
                     if str(x) != UNDECIDED and not is_composite(x))
            for c in (self.ledger['chargen'].get('class_choices') or []):
                n += sum(1 for g in (c.get(gkey) or []) if str(g) != UNDECIDED)
            for t in (self.ledger['chargen'].get('ancestry_traits') or []):
                if isinstance(t, dict):
                    n += sum(1 for g in (t.get(gkey) or []) if str(g) != UNDECIDED)
        for e in ((self.ledger.get('levels') or {}).get(lvl) or []):
            if e.get('slot') == slot and str(e.get('pick')) != UNDECIDED and not is_composite(e.get('pick')):
                n += 1
            n += sum(1 for g in (e.get(gkey) or []) if str(g) != UNDECIDED)
        return n

    def _res_gained_at(self, resource, lvl):
        # how many of this resource the level GRANTED = the engine budget delta across it. Any source
        # counts (class table, path rider, talent, subclass, ancestry trait) with no per-feature data.
        lbl = 'Maneuvers known' if resource == 'maneuvers' else 'Spells known'

        def budget(l):
            if l < 1:
                return 0
            try:
                return int(eng.replay(self.ledger, l).derived.get(lbl) or 0)
            except Exception:
                return 0
        return budget(lvl) - budget(lvl - 1)

    def _prune_level_overflow(self, lvl):
        # BUG-28 (2026-07-27): a re-picked grant-bearing entry can SHRINK a level's maneuver/spell grant
        # (talent Remarkable Repertoire {spells:2} -> Wild Form {}). The flat picks it funded carry no
        # provenance (the deliberate flat-pool boundary), so the level was left holding spells it no
        # longer earns, silently: the readout only speaks when UNDER budget. Drop the builder-ADDED flat
        # picks at that level, newest first, until the level is back inside its own grant.
        # Two guards keep this from eating real data: it only runs while the character is GLOBALLY
        # over-recorded (so a mis-attributed level never loses a legitimately picked spell), and it never
        # touches hand-authored/canon rows or path-rider rows (a path rider is owned by its path pick and
        # regenerated by _sync_path_rider). Anything it cannot resolve stays visible as the
        # over-recorded advisory in builder_problems.
        for resource in ('maneuvers', 'spells'):
            slot = self._res_slot(resource)
            ents = (self.ledger.get('levels') or {}).get(lvl) or []
            while self._res_have(resource) > self._res_budget(resource) \
                    and self._res_have_at(resource, lvl) > self._res_gained_at(resource, lvl):
                victim = next((e for e in reversed(ents)
                               if e.get('slot') == slot
                               and str(e.get('pick')) != UNDECIDED
                               and BUILDER_NOTE in str(e.get('note', ''))
                               and not str(e.get('source', '')).startswith('path rider')), None)
                if victim is None:
                    break
                ents.remove(victim)

    def _res_ready_level(self, resource):
        # BUG-23 (2026-07-27): the maneuver/spell analog of _anc_ready_level. The ready slot belongs
        # at the level where the gap actually IS, not always back at chargen L1. A Barbarian who takes
        # MC Bard Remarkable Repertoire at L2 gains 2 spells there; rendering its ready slot in the L1
        # block (where the Barbarian table grants none) read as "not granting the spells" - the same
        # mis-placement BUG-18 fixed for ancestry points.
        # Attribution is data-free: the engine budget DELTA per level says how many that level granted,
        # and _res_have_at says how many are recorded there, so the slot lands at the LOWEST level that
        # is short. Works for ANY grant source (class table, path rider, talent, subclass, trait) with
        # no per-feature knowledge. A genuinely unattributable gap falls back to chargen, which is also
        # the audit case (a canon ledger missing an old L1 pick) and keeps that slot where it belongs.
        # BUG-29 (2026-07-27): suppression is PER LEVEL, so a short level still gets its ready slot while
        # another level has an open slot of its own. A Spellblade taking Remarkable Repertoire at L2 has
        # two undecided L1 spell pickers; suppressing globally meant the 2 talent spells appeared in the
        # budget ("0 of 4") with nowhere to pick them, which reads as the grant not working.
        # Returns None when no level can host a ready slot right now.
        # Only called when a shortfall exists, so the extra replays stay off the hot path.
        blocked = False
        for lvl in range(1, self.ledger['current_level'] + 1):
            gained = self._res_gained_at(resource, lvl)
            if gained > 0 and self._res_have_at(resource, lvl) < gained:
                if not self._res_has_undecided_at(resource, lvl):
                    return lvl
                blocked = True   # this level is short but its own open slot IS the ready slot
        if blocked:
            return None
        # no level is attributably short (the gap sits somewhere the deltas cannot place, e.g. a canon
        # ledger recording a level-granted pick at chargen): fall back to chargen if IT can host a slot.
        # That is the audit case, which is why chargen stays the fallback.
        return 1 if not self._res_has_undecided_at(resource, 1) else None

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

    def _spell_grant_tag(self, parent):
        # FR-8 slice 5: if PARENT is a subclass whose catalog subclass_grants entry carries a
        # spell_access tag AND grants spells, return that tag (e.g. 'Psychic' for Warlock Eldritch's
        # Otherworldly Gift: "learn 1 Spell with the Psychic Tag"). This is the ONE gate that turns a
        # tag-constrained spell grant into a constrained child picker - plain 'spells' is deliberately
        # NOT in GRANT_CHILD_SLOTS, so the other five {spells:N} budget grants stay on the flat pool.
        if parent.get('slot') != 'subclass':
            return None
        if int((parent.get('grants') or {}).get('spells', 0) or 0) <= 0:
            return None
        sg = (self.ccat.get('subclass_grants') or {}).get(base_name(parent.get('pick'))) or {}
        return (sg.get('spell_access') or {}).get('tag')

    def _spell_grant_source(self, parent):
        # FR-13a: if PARENT carries a spell_access.source constraint AND grants spells, return
        # (source, schools|None) so the {spells:N} grant renders as SOURCE-filtered child pickers
        # (e.g. Scaletrix's Innate Power / Intuitive Magic -> 2 Arcane spells). Data-driven: the
        # constraint lives on the ledger entry itself (spell_access: {source, schools}), so no
        # catalog talent table is needed for the walked case. This is the source-based sibling of
        # the tag-based _spell_grant_tag (subclass_grants) - together they cover the two ways a
        # feature reaches spells outside the character's own class list.
        if int((parent.get('grants') or {}).get('spells', 0) or 0) <= 0:
            return None
        sa = parent.get('spell_access') or {}
        # FR-13a slice 2: when the parent models an explicit Sorcerous Origin node, its chosen
        # source is the source of truth (the node DRIVES this filter, so re-picking it re-filters
        # the spell children); otherwise fall back to a static spell_access.source. Schools (if any)
        # still come from spell_access.
        src = ((parent.get('sorcerous_origin') or {}).get('chosen_source')) or sa.get('source')
        if not src or str(src) == UNDECIDED:
            return None
        return src, (sa.get('schools') or None)

    def _talent_rows(self):
        # BUG-33 (2026-07-27, found by the CH-5 Tier-1 probe): ONE list of every talent row this
        # character can actually pick, so a lookup can never see fewer rows than _talent_options
        # offers. `class_talents` was missing from both talent lookups (this one and the set_decision
        # branch), so the six class talents that carry a real effect were offered, picked, and then
        # applied NOTHING: Unfathomable Strength {jump:1}, Expanded Meta Magic {mp:2}, Greater Innate
        # Power {mp:1}, Expanded Disciplines {disciplines:2} (which should spawn two discipline
        # child-pickers), Pact Bane {spells:1} and Expanded Spell School {spells:2}. Same
        # duplicate-list root cause as BUG-31/32: two hand-maintained readers of one catalog.
        t = self.cat['talents']
        return (list(t['mc_features']) + list(t['general'])
                + list((t.get('class_talents') or {}).get(self.cls, [])))

    def _any_list_defs(self):
        # catalog defs whose spell grant reaches ANY Spell List (`spell_access: {any: true}`); today
        # just MC Bard's Remarkable Repertoire / Magical Secrets. Data-driven, so a second one is a
        # catalog edit.
        return {t['name']: t for t in self._talent_rows()
                if (t.get('spell_access') or {}).get('any')}

    def _spell_grant_any(self, parent):
        # BUG-30: does THIS entry carry an any-list spell grant? The any-list sibling of
        # _spell_grant_tag / _spell_grant_source: it turns the entry's {spells: N} into N unfiltered
        # spell child-slots glued under it, so the reach belongs to the spells the feature pays for
        # instead of leaking into every other picker. Ledgers write a multiclass feature either bare
        # (what the picker sets) or in the documented "MC <Class>: <Feature>" long form, so match both.
        if int((parent.get('grants') or {}).get('spells', 0) or 0) <= 0:
            return False
        nm = base_name(str(parent.get('pick') or parent.get('name') or ''))
        defs = self._any_list_defs()
        return bool(defs.get(nm)
                    or (defs.get(nm.split(':', 1)[-1].strip()) if nm.startswith('MC ') else None))

    def _any_list_slots(self):
        # BUG-30: how many spells this character may take from ANY Spell List, i.e. the sum of the
        # `spells` grants on held features whose catalog def carries `spell_access: {any: true}`
        # (today: MC Bard's Remarkable Repertoire / Magical Secrets). Data-driven off the catalog,
        # the same way _spell_grant_tag reads subclass_grants, so a second any-list feature is a
        # data edit. Only counts DECIDED picks at or below the current level.
        n = 0
        for lvl in sorted(self.ledger.get('levels') or {}):
            if lvl > self.ledger['current_level']:
                continue
            for e in self.ledger['levels'][lvl] or []:
                if self._spell_grant_any(e):
                    n += int((e.get('grants') or {}).get('spells', 0) or 0)
        return n

    def _spell_access(self):
        # -> (options set, describe(name) -> why-legal string or None) for the character's OWN access
        # (class schools/source + tag and school grants). An any-list grant (BUG-30) deliberately does
        # NOT widen this: its spells are picked in their own child-slots under the granting feature
        # (see _grant_children), so every other picker stays honestly filtered. This set is also what
        # catalog_problems counts hand-authored off-list flat picks against.
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

    def _spell_any_options(self):
        # BUG-30: options for an ANY-LIST spell child-slot = every spell in spells.md, grouped by
        # school. No filtering is needed because the grant itself reaches every list ("any 2 Spells of
        # your choice from any Spell List"); the point of the child-slot is that this reach applies to
        # the 2 spells the feature pays for and to nothing else.
        return [{'name': n, 'group': (self.meta.get(n) or {}).get('school', '?'),
                 'label': '%s (%s)' % (n, (self.meta.get(n) or {}).get('school', '?'))}
                for n in sorted(self.meta.keys())]

    def _spell_tagged_options(self):
        # FR-8 slice 5: options for a tag-constrained spell child-slot = accessible spells that carry
        # the character's granted spell tag (Eldritch -> Psychic). _spell_access already widens the
        # accessible set to every tag-granted spell, so this yields exactly the Psychic-tag spells
        # (e.g. Tendrils from Beyond, legal via the tag though its Conjuration school is not chosen).
        tags = self._grant_tags()
        if not tags:
            return []
        names, _why = self._spell_access()
        out = [n for n in names if set((self.meta.get(n) or {}).get('tags') or []) & tags]
        return [{'name': n, 'group': (self.meta.get(n) or {}).get('school', '?'),
                 'label': '%s (%s)' % (n, (self.meta.get(n) or {}).get('school', '?'))}
                for n in sorted(out)]

    def _all_sources(self):
        # FR-13a slice 2: the set of CANONICAL spell sources (Arcane / Divine / Primal), harvested
        # from the baked spell metadata (spells.md "Source:" lines). Used to tell a real source name
        # apart from a free-text provenance string on a ledger spell entry. Cached.
        if getattr(self, '_all_src_cache', None) is None:
            s = set()
            for m in self.meta.values():
                s |= set(m.get('sources') or [])
            self._all_src_cache = s
        return self._all_src_cache

    def _spell_sourced_options(self, source, schools=None):
        # FR-13a: options for a SOURCE-constrained spell child-slot = every spell in spells.md whose
        # Source list includes `source` (optionally narrowed to `schools`). Independent of the
        # character's own class source, since the grant reaches outside it (e.g. a Druid's Arcane
        # grants via Innate Power). Uses the spell metadata baked from spells.md.
        out = []
        for n, m in self.meta.items():
            if source in (m.get('sources') or []):
                if schools and m.get('school') not in schools:
                    continue
                out.append(n)
        return [{'name': n, 'group': (self.meta.get(n) or {}).get('school', '?'),
                 'label': '%s (%s)' % (n, (self.meta.get(n) or {}).get('school', '?'))}
                for n in sorted(out)]

    def _maneuver_options(self):
        return [{'name': m, 'group': typ, 'label': '%s (%s)' % (m, typ)}
                for typ, lst in self.cat['maneuvers']['maneuvers'].items() for m in lst]

    def _talent_options(self, restrict=None):
        # BUG-35: `restrict='class_talents'` narrows the picker to THIS class's class talents, which
        # is what a Paragon subclass grant owes ("a Class Talent of your choice from your Class").
        # Same rows _talent_rows() resolves against, just a narrower offer, so the anti-mirror (CT)
        # check still covers it.
        t = self.cat['talents']
        if restrict == 'class_talents':
            return [{'name': r['name'], 'group': self.cls + ' talents',
                     'label': '%s (%s talent)' % (r['name'], self.cls)}
                    for r in (t.get('class_talents') or {}).get(self.cls, [])]
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

    def _chosen_names(self, slot):
        # FR-7: base names already chosen for this slot across chargen + every level,
        # so a picker can hide them. Composite / undecided entries are skipped.
        out = set()
        cg = self.ledger['chargen']
        namekey = slot in ('spell', 'maneuver', 'talent')

        def add(v):
            if v is None:
                return
            s = str(v)
            if s == UNDECIDED or is_composite(s):
                return
            out.add(base_name(s) if namekey else s)
        if slot == 'spell':
            for x in cg.get('spells') or []:
                add(x)
        elif slot == 'maneuver':
            for x in cg.get('maneuvers') or []:
                add(x)
        elif slot == 'spell_school':
            for x in cg.get('spell_schools') or []:
                add(x)
        elif slot == 'discipline':
            # BUG-21: disciplines are held in three places - the L1 chargen picker, flat level rows,
            # and (new) a subclass grant-child. All three count as "already known", which is what
            # Paladin's "if you already know that Discipline" clause turns on.
            for c in cg.get('class_choices') or []:
                if 'disciplin' in str(c.get('slot')):
                    for x in c.get('picks') or []:
                        add(x)
                for x in c.get('granted_disciplines') or []:
                    add(x)
            for lvl in self.ledger.get('levels') or {}:
                for e in self.ledger['levels'][lvl] or []:
                    for x in e.get('granted_disciplines') or []:
                        add(x)
        for lvl in self.ledger.get('levels') or {}:
            for e in self.ledger['levels'][lvl] or []:
                if e.get('slot') == slot:
                    add(e.get('pick'))
        if slot == 'spell':   # FR-8 slice 5: a tag-constrained granted spell (Eldritch Psychic) is also
            # "chosen", so the flat spell picker hides it (no double-pick across the two slots).
            for c in cg.get('class_choices') or []:
                for x in c.get('granted_spells') or []:
                    add(x)
            for t in cg.get('ancestry_traits') or []:   # FR-13a: spells childed on an ancestry trait
                if isinstance(t, dict):
                    for x in t.get('granted_spells') or []:
                        add(x)
            for lvl in self.ledger.get('levels') or {}:
                for e in self.ledger['levels'][lvl] or []:
                    for x in e.get('granted_spells') or []:
                        add(x)
        return out

    # ---------- FR-3 slice 2: planned-level skill picks (Hybrid, reusing the FR-8 backbone) ----
    def _parse_skill_pick(self, v):
        # a planned skill pick is stored as "<Skill>: <resulting tier>" (e.g. "Awareness: Expert").
        # A colon does not trip is_composite (that gate only fires on a colon in a "4th ..." head),
        # so the value round-trips cleanly. A bare name defaults to Novice (defensive / hand-authored).
        s = str(v)
        if ':' in s:
            a, b = s.rsplit(':', 1)
            return a.strip(), b.strip()
        return s.strip(), 'Novice'

    def _parse_plan_pick(self, v):
        # FR-17: a planned skill/trade pick may carry a " (cap+)" suffix (a Mastery-Limit purchase).
        # Return (name, tier, cap_raised). A bare CAPARM ("(cap+)") = armed-but-empty: no name/tier.
        s = str(v)
        cap = False
        m = re.search(r'\s*\(cap\+\)\s*$', s)
        if m:
            cap = True
            s = s[:m.start()].strip()
        if not s or s == UNDECIDED:
            return '', None, cap        # empty / a bare CAPARM sentinel: armed but not yet a pick
        name, tier = self._parse_skill_pick(s)
        return name, tier, cap

    @staticmethod
    def _plan_pick_cost(v):
        # FR-17: a cap+ pick spends 2 points (tier step + limit raise); a normal pick spends 1.
        return 2 if re.search(r'\(cap\+\)\s*$', str(v)) else 1

    def _plan_decided(self, v):
        # a granted skill/trade slot counts as filled only if it names a real skill/trade
        # (UNDECIDED and a bare CAPARM sentinel are both "not yet picked").
        return str(v) != UNDECIDED and bool(self._parse_plan_pick(v)[0])

    def _mastery_cap_idx(self, level):
        # the DC20 Mastery Limit as a MASTERIES index (None<Novice<Adept<Expert): Novice <L5,
        # Adept L5-9, Expert at L10. The builder ladder tops out at Expert, which is the L10 cap,
        # so no plan (<=L10) is ever clipped by the ladder. Mirrors build_engine.mastery_limit.
        if level >= 10:
            return MASTERIES.index('Expert')
        if level >= 5:
            return MASTERIES.index('Adept')
        return MASTERIES.index('Novice')

    def _plan_catalog_names(self, kind):
        # every catalog skill (across governing-attribute lists) or trade for a plan point-buy.
        stc = self.cat.get('skills_trades') or {}
        if kind == 'skills':
            return sorted({n for lst in (stc.get('skills') or {}).values() for n in lst})
        return sorted(stc.get('trades') or [])

    def _plan_running_state(self, kind, level):
        # FR-3/FR-17: the running mastery of each skill/trade AS OF just before `level`: the flat
        # kind.masteries aggregate (kept as source of truth by the Hybrid decision) plus any raises
        # from PLAN levels strictly below `level`. Within-level picks do not chain (each of a level's
        # slots is a distinct one-step allocation).
        gkey = 'granted_%s' % kind
        st = {}
        for name, m in ((self.ledger.get(kind) or {}).get('masteries') or {}).items():
            if m.get('mastery'):
                st[name] = m.get('mastery')
        cur = self.ledger['current_level']
        for L in sorted(self.ledger.get('levels') or {}):
            if L <= cur or L >= level:
                continue
            for e in self.ledger['levels'][L] or []:
                for v in e.get(gkey) or []:
                    sk, tier, _cap = self._parse_plan_pick(v)
                    if sk:
                        st[sk] = tier
        return st

    def _plan_running_caps(self, kind, level):
        # FR-17: per skill/trade, how many Mastery-Limit raises are in effect just before `level`:
        # +1 for a flat-aggregate limit_raise (a point purchase OR an Expertise cap+level bump, both
        # lift the ceiling by 1), plus +1 for each cap+ pick in a PLAN level strictly below `level`.
        gkey = 'granted_%s' % kind
        caps = {}
        for name, m in ((self.ledger.get(kind) or {}).get('masteries') or {}).items():
            if m.get('limit_raise'):
                caps[name] = caps.get(name, 0) + 1
        cur = self.ledger['current_level']
        for L in sorted(self.ledger.get('levels') or {}):
            if L <= cur or L >= level:
                continue
            for e in self.ledger['levels'][L] or []:
                for v in e.get(gkey) or []:
                    sk, _t, capd = self._parse_plan_pick(v)
                    if sk and capd:
                        caps[sk] = caps.get(sk, 0) + 1
        return caps

    # kept for back-compat with any older references
    def _skill_running_state(self, level):
        return self._plan_running_state('skills', level)

    def _plan_options(self, kind, level, capraise=False):
        # FR-3/FR-17: legal picks for a skill/trade child-slot on a planned `level`. For every catalog
        # name offer the ONE next tier up from its running state (add-new = None->Novice, raise = one
        # tier). In NORMAL mode the tier must be within the level's Mastery Limit + any carried raises;
        # in cap+ mode the ceiling is +1 (a new limit purchase) and every option carries the " (cap+)"
        # marker so selecting it records the 2-point purchase. The picker only ever offers legal options.
        base = self._plan_running_state(kind, level)
        capb = self._plan_running_caps(kind, level)
        lvlcap = self._mastery_cap_idx(level)
        marker = ' ' + CAPARM if capraise else ''
        out = []
        for n in self._plan_catalog_names(kind):
            cur_tier = base.get(n)
            cur_idx = MASTERIES.index(cur_tier) if cur_tier in MASTERIES else 0
            nxt = cur_idx + 1
            eff_cap = lvlcap + capb.get(n, 0) + (1 if capraise else 0)
            if nxt >= len(MASTERIES) or nxt > eff_cap:
                continue
            tier = MASTERIES[nxt]
            verb = 'new' if cur_idx == 0 else 'raise from %s' % cur_tier
            if capraise:
                verb += ', cap+'
            out.append({'name': '%s: %s%s' % (n, tier, marker), 'group': kind.title(),
                        'label': '%s -> %s (%s)' % (n, tier, verb)})
        return out

    def _skill_plan_options(self, level):
        return self._plan_options('skills', level)

    def _child_pool(self, singular):
        # BUG-34: the ONE place that answers "which catalog rows sit behind this pickable option
        # kind". _options_for renders its labels from this, the chargen class-choice aggregate sums
        # its grants from this, and _sync_granted_effects reads the grants of a CHOSEN child from
        # this. Three readers, one list, so the offer and the effect cannot diverge (the rule that
        # came out of BUG-31/32/33). Keyed by the SINGULAR slot name, i.e. the values in
        # GRANT_CHILD_SLOTS, plus pact_boon which is a parent-only pick.
        if singular == 'discipline':
            return list(self.ccat.get('disciplines') or [])
        if singular == 'pact_boon':
            return list(self.ccat.get('pact_boons') or [])
        if singular == 'rune':
            return list(self.ccat.get('runes') or [])
        if singular == 'metamagic':
            return list((self.cat.get('metamagic') or {}).get('options') or [])
        return []

    def _options_for(self, slot, restrict=None):
        if slot == 'ancestry_trait':
            return self._anc_options()
        if slot == 'spell':
            return self._spell_options()
        if slot == 'spell':
            return self._spell_options()
        if slot == 'maneuver':
            return self._maneuver_options()
        if slot == 'talent':
            return self._talent_options(restrict)   # BUG-35: Paragon's rider is class-talents-only
        if slot == 'attribute':
            # BUG-5: capitalise for display only; value (name) stays lower-case as stored.
            return [{'name': a, 'group': '', 'label': a.title()} for a in ATTRS]
        if slot == 'path':
            return [{'name': p, 'group': '', 'label': p} for p in self.ccat['paths']]
        if slot == 'subclass':
            return [{'name': s, 'group': '', 'label': s} for s in self.ccat['subclasses']]
        if slot == 'discipline':
            return [{'name': d['name'], 'group': '',
                     'label': d['name'] + _fmt_grants(d.get('grants'))}
                    for d in self._child_pool('discipline')]
        if slot == 'pact_boon':
            return [{'name': b['name'], 'group': '',
                     'label': b['name'] + _fmt_grants(b.get('grants'))}
                    for b in self._child_pool('pact_boon')]
        if slot == 'spell_school':
            return [{'name': s, 'group': '', 'label': s}
                    for s in self.cat['spell_schools']['schools']]
        if slot == 'rune':   # FR-8 slice 3 grant-child pickers (class-scoped: Spellblade runes in ccat)
            return [{'name': r['name'], 'group': '',
                     'label': r['name'] + _fmt_grants(r.get('grants'))}
                    for r in self._child_pool('rune')]
        if slot == 'metamagic':   # FR-8 slice 4 grant-child pickers (cat-level, cross-class: reached via MC Sorcerer)
            return [{'name': r['name'], 'group': '',
                     'label': r['name'] + _fmt_grants(r.get('grants'))}
                    for r in self._child_pool('metamagic')]
        if slot == 'spell_tagged':   # FR-8 slice 5 constrained spell grant-child (Eldritch Psychic-only)
            return self._spell_tagged_options()
        if slot == 'spell_any':      # BUG-30 any-list spell grant-child (MC Bard Magical Secrets)
            return self._spell_any_options()
        if slot == 'spell_sourced':  # FR-13a source-constrained spell grant-child; options are per-
            return []                # parent (the source constraint), so _grant_children sets them
        if slot == 'ancestry_origin':  # BUG-24: per-ancestry Origin damage type; options are per-
            return []                    # ancestry (Dragonborn vs Fiendborn), so _origin_decisions sets them
        if slot == 'source_choice':  # FR-13a slice 2: the Sorcerous Origin node = the chosen Sorcerer
            # Source. The three magic Sources (classes.md l.2530-2551: Sorcerers draw from Arcane,
            # Divine, or Primal); narrowed to the sources actually present in the baked metadata.
            return [{'name': s, 'group': '', 'label': s}
                    for s in ('Arcane', 'Divine', 'Primal') if s in self._all_sources()]
        if slot in ('skill', 'trade'):   # FR-3/FR-17 planned-level skill/trade child-slot: options are
            return []                      # level-aware, so _grant_children overrides d['options'].
        return []

    # ---------- catalog-level legality (the layer the engine does not do) ----------
    def catalog_problems(self):
        probs = []
        # BUG-30: an any-list grant's own spells are childed under the granting feature and are legal by
        # construction (their picker offers every spell), so they never reach this flat sweep. What this
        # DOES cover is a hand-authored / received ledger that left such spells in the flat pool (the
        # shape bonan.yaml had before the BUG-30 migration): those off-list picks are tolerated up to the
        # number of any-list slots the character holds, and flagged beyond it. Same shape as the
        # off-source / Arcane-grant-slot count below.
        names, why = self._spell_access()
        anyslots = self._any_list_slots()
        off_any = 0
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
                if anyslots:
                    off_any += 1        # legal IF an any-list slot covers it; counted below
                else:
                    probs.append('catalog: spell %s not legal for this %s (%s)'
                                  % (s, self.cls, self.meta[s]['school']))
            elif model == 'source' and why(s) == 'Arcane grant slot':
                off_source += 1
        if off_any > anyslots:
            probs.append('catalog: %d spell(s) from outside this %s\'s own lists vs %d any-list '
                         'grant slot(s)' % (off_any, self.cls, anyslots))
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
        # ancestry-trait prerequisites (e.g. Superior Darkvision requires Darkvision).
        # "any ... Trait" category requirements are recorded in the catalog but not
        # enforced here (no single name to resolve, so no false positives).
        present = {base_name(t.get('name')) for t in self._traits()
                   if str(t.get('name')) != UNDECIDED and base_name(t.get('name'))}
        for t in self._traits():
            nm = t.get('name')
            if str(nm) == UNDECIDED:
                continue
            row = self._anc_find(nm)[1]
            req = (row or {}).get('requires')
            if req and 'any ' not in str(req).lower() and base_name(req) not in present:
                probs.append('catalog: %s requires %s, which this character has not taken'
                             % (base_name(nm), req))
        # FR-3 slice 2 / FR-17: planned-level skill AND trade picks legality (the enforcement the engine
        # skips on plans). Each decided pick must be a known catalog skill/trade, exactly ONE mastery
        # step up from its running state (aggregate + lower plan levels), within the level's Mastery
        # Limit PLUS any carried raises PLUS its own cap+ purchase, and distinct within the level. The
        # picker only offers legal options, so this defends against stale / hand-authored values.
        cur = self.ledger['current_level']
        for kind in PLAN_POINTBUY:
            allnames = set(self._plan_catalog_names(kind))
            label = 'skill' if kind == 'skills' else 'trade'
            for lvl in sorted(self.ledger.get('levels') or {}):
                if lvl <= cur:
                    continue
                base = self._plan_running_state(kind, lvl)
                capb = self._plan_running_caps(kind, lvl)
                lvlcap = self._mastery_cap_idx(lvl)
                seen = set()
                for e in self.ledger['levels'][lvl] or []:
                    for v in e.get('granted_%s' % kind) or []:
                        if not self._plan_decided(v):
                            continue   # UNDECIDED or an armed-but-empty cap+ slot: not yet a pick
                        sk, tier, capd = self._parse_plan_pick(v)
                        if sk not in allnames:
                            probs.append('catalog: planned %s %r (L%d) is not a known %s'
                                         % (label, sk, lvl, label))
                            continue
                        if tier not in MASTERIES or tier is None:
                            probs.append('catalog: planned %s %s has an invalid tier %r (L%d)'
                                         % (label, sk, tier, lvl))
                            continue
                        base_idx = MASTERIES.index(base.get(sk)) if base.get(sk) in MASTERIES else 0
                        if MASTERIES.index(tier) != base_idx + 1:
                            probs.append('catalog: planned %s %s -> %s (L%d) is not a single step up from %s'
                                         % (label, sk, tier, lvl, base.get(sk) or 'none'))
                        eff_cap = lvlcap + capb.get(sk, 0) + (1 if capd else 0)
                        if MASTERIES.index(tier) > eff_cap:
                            probs.append('catalog: planned %s %s -> %s (L%d) exceeds the mastery limit %s'
                                         ' (tick cap+ to raise it)'
                                         % (label, sk, tier, lvl, MASTERIES[min(eff_cap, len(MASTERIES) - 1)]))
                        if sk in seen:
                            probs.append('catalog: planned %s %s picked twice at L%d' % (label, sk, lvl))
                        seen.add(sk)
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
            for _res, _sing in GRANT_CHILD_SLOTS.items():   # FR-8 slice 2 grant-child slots
                if _res in PLAN_POINTBUY:   # FR-17: skill/trade carriers are points-based, handled below
                    continue
                _n = int((c.get('grants') or {}).get(_res, 0) or 0)
                _lst = c.get('granted_%s' % _res) or []
                for _k in range(_n):
                    if _k >= len(_lst) or str(_lst[_k]) == UNDECIDED:
                        probs.append('builder: L1 %s undecided' % _sing)
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
                for _res, _sing in GRANT_CHILD_SLOTS.items():   # FR-8 slice 2 grant-child slots
                    if _res in PLAN_POINTBUY:   # FR-17: skill/trade carriers are points-based, handled below
                        continue
                    _n = int((e.get('grants') or {}).get(_res, 0) or 0)
                    _lst = e.get('granted_%s' % _res) or []
                    for _k in range(_n):
                        if _k >= len(_lst) or str(_lst[_k]) == UNDECIDED:
                            probs.append('builder: L%d %s undecided' % (lvl, _sing))
                if self._spell_grant_tag(e):   # FR-8 slice 5 constrained spell grant-child
                    _n = int((e.get('grants') or {}).get('spells', 0) or 0)
                    _lst = e.get('granted_spells') or []
                    for _k in range(_n):
                        if _k >= len(_lst) or str(_lst[_k]) == UNDECIDED:
                            probs.append('builder: L%d spell (tag) undecided' % lvl)
                if self._spell_grant_any(e):   # BUG-30 any-list spell grant-child
                    _n = int((e.get('grants') or {}).get('spells', 0) or 0)
                    _lst = e.get('granted_spells') or []
                    for _k in range(_n):
                        if _k >= len(_lst) or str(_lst[_k]) == UNDECIDED:
                            probs.append('builder: L%d spell (any list) undecided' % lvl)
        # FR-3 slice 2 / FR-17: planned levels ENFORCE their skill AND trade point budgets (Darryl's
        # call), POINTS-based rather than per-slot, because a cap+ pick costs 2 points. So a level with
        # N points is under-spent while decided picks total < N, and over-spent if they total > N (only
        # reachable by cap+ overshoot). This is the deliberate divergence from Slice 1's "a plan raises
        # no problems", scoped to the point-buy carriers; runes / metamagic / tagged spells stay
        # speculative and are NOT flagged on a plan level.
        for lvl in sorted(self.ledger.get('levels') or {}):
            if lvl <= cur:
                continue
            for e in self.ledger['levels'][lvl] or []:
                for kind in PLAN_POINTBUY:
                    _n = int((e.get('grants') or {}).get(kind, 0) or 0)
                    if _n <= 0:
                        continue
                    _lst = e.get('granted_%s' % kind) or []
                    spent = sum(self._plan_pick_cost(v) for v in _lst if self._plan_decided(v))
                    if spent < _n:
                        probs.append('builder: L%d planned %s: %d of %d point(s) unspent'
                                     % (lvl, kind, _n - spent, _n))
                    elif spent > _n:
                        probs.append('builder: L%d planned %s over budget (%d points, %d spent)'
                                     % (lvl, kind, _n, spent))
        # BUG-28: over-recorded maneuvers/spells must never be silent. _prune_level_overflow clears the
        # builder-added ones a shrunken grant left behind; anything left (hand-authored rows, a path
        # rider whose path is still chosen) is a real data question, so say so instead of hiding it
        # behind a readout that only speaks when under budget.
        for _res in ('maneuvers', 'spells'):
            _have, _bud = self._res_have(_res), self._res_budget(_res)
            if _have > _bud:
                probs.append('builder: %d %s recorded but only %d granted (remove %d)'
                             % (_have, _res, _bud, _have - _bud))
        if self.scratch and not str(self.ledger.get('ancestry') or '').strip():
            probs.append('builder: ancestry not chosen')
        return probs

    # ---------- the decision model ----------
    def _origin_decisions(self):
        # BUG-24 (option-effects, 2026-07-25): Dragonborn/Fiendborn each require a single per-ancestry
        # Origin (a damage type) that "all future choices within this Ancestry must use" (ancestries.md
        # l.525/696). It is ENGINE-NEUTRAL (records a type, no derived-stat effect), so it lives in the
        # ledger at chargen.ancestry_origins[<source>] and is NOT a grant. Render ONE picker per present
        # origin-ancestry (a trait of that source has been taken), so a scratch pick can record it - the
        # gap the bug named. Shared value = consistency across that ancestry's typed traits for free.
        origins = (self.cat['ancestries'].get('origins') or {})
        if not origins:
            return []
        present = []
        for t in self._traits():
            src = str(t.get('source') or '')
            if src in origins and src not in present:
                present.append(src)
        store = self.ledger['chargen'].get('ancestry_origins') or {}
        out = []
        for src in present:
            cur = store.get(src, UNDECIDED)
            d = self._dec('AO#%s' % src, 1, 'ancestry_origin', cur, None, False, True)
            d['options'] = [{'name': x, 'group': '', 'label': x} for x in origins[src]]
            d['current'] = cur if cur else UNDECIDED
            if cur and cur != UNDECIDED and not any(o['name'] == cur for o in d['options']):
                d['options'].insert(0, {'name': cur, 'label': '%s (off-list)' % cur})
            d['slotlabel'] = '%s origin' % src.lower()
            out.append(d)
        return out

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
            # FR-13a slice 2: an ancestry trait can itself GRANT a source-constrained spell (Scaletrix's
            # Fiendish Magic "Arcane Spell" -> Command). Materialise its grant-child(ren) right after the
            # trait row so they glue under it (FR-20). Reuses the same source branch as class/level grants;
            # traits without a spell grant (Mana Increase, Jumper, ...) produce nothing.
            ds.extend(self._grant_children(t, 'cgtrait:%d' % i, 1, not ph))
        ds.extend(self._origin_decisions())   # BUG-24: per-ancestry Origin damage-type picker(s)
        for ci, c in enumerate(cg.get('class_choices') or []):
            opt_slot = ('discipline' if c['slot'] == 'spellblade_disciplines'
                        else 'pact_boon' if c['slot'] in ('pact_boons', 'pact_boon') else None)
            if opt_slot:
                for pi, p in enumerate(c.get('picks') or []):
                    ds.append(self._dec('cg:choice:%d:%d' % (ci, pi), 1, opt_slot, p,
                                        None, False, not is_composite(p)))
            else:
                ds.append({'id': None, 'level': 1, 'slot': c['slot'],
                           'pick': ', '.join(str(x) for x in c['picks']),
                           'widget': 'fixed', 'editable': False, 'cost': None, 'inferred': False})
            ds.extend(self._grant_children(c, 'cg:%d' % ci, 1, True))   # FR-8 slice 2
        for i, s in enumerate(cg.get('spells') or []):
            ds.append(self._dec('cg:spell:%d' % i, 1, 'spell', s, None, False, not is_composite(s)))
        for i, m in enumerate(cg.get('maneuvers') or []):
            ds.append(self._dec('cg:man:%d' % i, 1, 'maneuver', m, None, False, not is_composite(m)))
        for lvl in sorted(self.ledger.get('levels') or {}):
            is_plan = lvl > cur
            for i, e in enumerate(self.ledger['levels'][lvl] or []):
                slot_ok = e.get('slot') in EDITABLE_SLOTS and not is_composite(e.get('pick'))
                # FR-3: a builder-generated plan row (plan_edit flag) is an editable picker so
                # the plan can be filled in; a hand-authored locked plan row (Tanrielle) is not.
                plan_edit = is_plan and bool(e.get('plan_edit')) and slot_ok
                editable = (lvl <= cur and slot_ok) or plan_edit
                ds.append(self._dec('L%d:%d' % (lvl, i), lvl, e.get('slot'), e.get('pick'),
                                    e.get('cost'), bool(e.get('inferred')), editable,
                                    note=e.get('note'), plan=is_plan, plan_editable=plan_edit,
                                    spell_source=e.get('source'),   # FR-13a slice 2: source-filter flat path spells
                                    restrict=e.get('restrict'),     # BUG-35: Paragon's class-talents-only rider
                                    # BUG-16: maneuver/spell budget slots are NOT removable. They are a
                                    # fixed-count pool (base class table + path riders + grants) that the
                                    # engine budgets but does NOT count entry-by-entry, and nothing
                                    # regenerates a deleted one (there is no "+ maneuver" and re-picking
                                    # Path/Pact Boon only rebuilds path-rider / grant-child slots). A stray
                                    # x let a required slot be deleted into a silent, unrecoverable
                                    # shortfall. They are edit-only now: change the pick via the dropdown.
                                    # Ancestry traits stay removable - they DO self-heal (FR-9 auto-slot +
                                    # the "+ ancestry trait" button re-add against the point budget).
                                    removable=(e.get('slot') == 'ancestry_trait'
                                               and (self.scratch or BUILDER_NOTE in str(e.get('note', ''))))))
                ds.extend(self._grant_children(e, 'L%d:%d' % (lvl, i), lvl,
                                               (lvl <= cur) or bool(e.get('plan_edit'))))   # FR-8 slice 2 / FR-3
        # FR-9: while ancestry points are unspent AND no open slot already exists, show ONE
        # ready empty ancestry-trait picker so the common case (spend your points) needs no
        # button - matching the skills allocator's always-ready feel. It flows through the
        # normal decision renderer; set_decision materialises a real trait on pick.
        # BUG-17 (2026-07-19): also show the slot when the single free Minor (0-cost) Trait has
        # not been taken yet, even at 0 points left (a Minor Trait costs 0 and is a separate
        # one-only allowance, ancestries.md l.~2568). So the gate is "points remain OR a minor
        # is still available".
        # BUG-18 (2026-07-19): render the ready slot at the level that most recently granted
        # ancestry points (L4 / L8 give '2 Ancestry Points'), not always at chargen L1 - so
        # after levelling to L4 the extra points spawn slots AT L4, where the user is looking,
        # instead of silently appearing back in the L1 block.
        spent, budget = self._anc_budget()
        if (spent < budget or self._anc_minor_room()) and not self._anc_has_undecided() \
                and self._anc_options():
            # BUG-18: unspent POINTS surface at the level that most recently granted them (L4/L8);
            # BUG-17: the free MINOR trait is a chargen allowance, so it surfaces at L1.
            tl = self._anc_ready_level() if spent < budget else 1
            sid = 'cg:trait:+' if tl == 1 else 'L%d:trait:+' % tl
            auto = self._dec(sid, tl, 'ancestry_trait', UNDECIDED, None, False, True)
            auto['auto'] = True
            ds.append(auto)
        # grants-only auto-heal (2026-07-19): the maneuver/spell analog of the FR-9 ready-slot.
        # When fewer NAMED picks fill the budget than the engine derives (e.g. Scaletrix's
        # unrecorded Arcane spells), show ONE ready picker so the gap self-heals on pick,
        # chaining one at a time. Advisory only - being under the known count is legal-but-
        # unfinished (surfaced by the readout + this row), not an illegal state, so it raises
        # no problem and leaves the baseline clean.
        # BUG-23 (2026-07-27): and it renders at the level that is short (_res_ready_level), not always
        # at chargen - the BUG-18 treatment for maneuvers/spells. _res_ready_level also owns the
        # per-level suppression (BUG-29) and returns None when no level can host a slot right now.
        for resource in ('maneuvers', 'spells'):
            if self._res_have(resource) < self._res_budget(resource) \
                    and self._options_for(self._res_slot(resource)):
                rl = self._res_ready_level(resource)
                if rl is None:
                    continue
                short = 'man' if resource == 'maneuvers' else 'spell'
                sid = 'cg:%s:+' % short if rl == 1 else 'L%d:%s:+' % (rl, short)
                auto = self._dec(sid, rl, self._res_slot(resource), UNDECIDED, None, False, True)
                auto['auto'] = True
                ds.append(auto)
        return self._reorder_decisions(ds)

    def _reorder_decisions(self, ds):
        # FR-20: reorder the pickers WITHIN each level to chargen flow -
        # attributes -> class/subclass -> ancestry -> resources (FR20_CAT). Cross-level
        # order is untouched (levels already ascending). Grant-child rows (GC#...) are
        # glued to their parent: a child inherits the anchor (preceding non-GC top-level
        # row)'s category rank AND block sequence, so e.g. a subclass's rune/metamagic
        # pickers stay directly under the subclass rather than migrating to resources.
        # Stable within a rank: same-rank blocks keep their original relative order, and
        # rows within a block keep their original order (the (blk, idx) tie-breakers).
        meta = []
        blk_ctr = {}    # per level: running block counter (original block order)
        anchor = {}     # per level: (rank, block) of the current anchor row
        for idx, d in enumerate(ds):
            lvl = d['level']
            if str(d.get('id') or '').startswith('GC#'):
                rank, blk = anchor.get(lvl, (FR20_DEFAULT_RANK, 0))
            else:
                blk = blk_ctr.get(lvl, 0) + 1
                blk_ctr[lvl] = blk
                rank = FR20_CAT.get(d.get('slot'), FR20_DEFAULT_RANK)
                anchor[lvl] = (rank, blk)
            # FR-36 / FR-21: persist the category rank on the row so the page can colour
            # its left accent by category and group long levels under category sub-headers.
            # GC children inherit the anchor rank, so a block (e.g. a subclass + its runes)
            # is one colour / one group.
            d['cat'] = rank
            meta.append((lvl, rank, blk, idx, d))
        meta.sort(key=lambda t: (t[0], t[1], t[2], t[3]))
        return [t[4] for t in meta]

    def _dec(self, did, lvl, slot, pick, cost, inferred, editable, note=None, plan=False,
             removable=False, plan_editable=False, spell_source=None, restrict=None):
        # FR-3: a builder-generated PLAN row (a level above current_level) is an editable
        # picker so a player can fill in the plan; a hand-authored locked plan (e.g.
        # Tanrielle's L5/L6) has no plan_editable flag and stays a read-only preview.
        # Non-plan rows are unaffected (eff_edit reduces to the old editable-and-not-plan).
        eff_edit = editable and (not plan or plan_editable)
        d = {'id': did, 'level': lvl, 'slot': slot, 'pick': pick, 'cost': cost,
             'inferred': inferred, 'editable': eff_edit, 'plan': plan,
             'widget': 'picker' if eff_edit else 'fixed',
             'removable': removable}
        if restrict:
            d['restrict'] = restrict   # BUG-35: surfaced so the harness can assert the narrowing
        if note:
            d['note'] = note
            if str(note).startswith('Replaced composite') or 'Overflow' in str(note):
                d['was_note'] = note   # provenance shown even on the (now editable) picker row
        # escape hatch: a composite/invalid entry at/below current level in a clean
        # single-value slot keeps its text but gets a "replace" picker (see the page JS)
        if (not plan) and not (editable and not plan) and slot in REPLACEABLE_SLOTS \
                and str(pick) != UNDECIDED and is_composite(pick):
            d['replaceable'] = True
            d['options'] = self._options_for(slot, restrict)
            # (The old one-click "expand into per-level slots" reconcile that lived here was
            # RETIRED 2026-07-19: it flattened FIXED grants (pact-boon maneuvers) into the flat
            # pool alongside their granted_ list, which is exactly the double-count the grants-only
            # unification removed. Missing maneuver/spell slots now self-heal via the auto ready-slot
            # in _decisions, and a genuine composite still gets the single-value replace dropdown.)
        if d['widget'] == 'picker':
            if slot == 'spell' and spell_source and spell_source in self._all_sources():
                # FR-13a slice 2: a flat spell entry carrying a CANONICAL source (e.g. a Spellcaster-
                # path spell "source: Arcane" on a Druid) renders source-filtered to that source
                # instead of the class list, so an off-class-source pick (Dispel Magic / Telekinesis)
                # is a legal picker rather than a "(current, off-list)" row. Free-text provenance
                # sources ("class table +1", "Spellcaster path +1 spell") are NOT canonical and fall
                # through to the class options unchanged.
                opts = self._spell_sourced_options(spell_source)
            else:
                # BUG-35: an entry can NARROW its own picker (Paragon's rider talent is restricted
                # to this class's class talents). Only the talent slot reads it today; the plumbing
                # is generic so the next constrained grant is a data edit.
                opts = self._options_for(slot, restrict)
            if slot in FR7_FILTER_SLOTS:  # FR-7: hide options already taken elsewhere
                mine = base_name(pick) if slot in ('spell', 'maneuver', 'talent') else str(pick)
                taken = self._chosen_names(slot) - ({mine} if str(pick) != UNDECIDED else set())
                opts = [o for o in opts if o['name'] not in taken]
            d['options'] = opts
            if str(pick) == UNDECIDED:
                d['current'] = UNDECIDED
                return d
            d['current'] = (base_name(pick) if slot in ('ancestry_trait', 'talent', 'spell',
                                                        'maneuver', 'subclass', 'spell_tagged',
                                                        'spell_sourced') else str(pick))
            if slot == 'ancestry_trait':
                lst, row = self._anc_find(pick)
                if lst is not None:
                    d['current_group'] = lst   # dedupe same-named traits across lists
                if row is not None and row.get('targets') == 'attributes':
                    # a targeted trait's <select> value is the decorated variant (CH-5)
                    m = re.search(r'\(([^)]+)\)', str(pick))
                    d['current'] = '%s (%s)' % (row['name'],
                                                m.group(1).strip().lower() if m else ATTRS[0])
                elif row is not None:
                    d['current'] = row['name']   # resolve ledger aliases (e.g. Arcane Spell)
            if slot == 'talent':
                m = re.match(r'MC \w+(?: \((?:Novice|Adept|Expert|Master)\))?:\s*(.*)', str(pick))
                d['current'] = base_name((m.group(1) if m else str(pick)).split(':')[0])
            # A <select> must contain its current value or the browser renders it blank/locked.
            # An inferred/off-list pick (e.g. Scaletrix's guessed "Dispel Magic", not in his
            # school-filtered options) is kept selectable by prepending it as an "(off-list)" option
            # so it shows and can be corrected. UNDECIDED already returned above.
            cur = d.get('current')
            if cur and cur != UNDECIDED and not any(o.get('name') == cur for o in (d.get('options') or [])):
                d.setdefault('options', []).insert(
                    0, {'name': cur, 'label': '%s (current, off-list)' % cur})
        return d

    def _grant_children(self, parent, parentref, level, editable):
        # FR-8 slice 2: a grant-bearing parent (boon / discipline / talent / subclass) auto-
        # materialises typed child picker-slots for each PICKABLE grant resource (GRANT_CHILD_SLOTS:
        # runes, metamagic, ...). The picks live in a granted_<resource> list ON the parent, so the
        # link is structural: the child id encodes the parent (GC#<parentref>#<resource>#<k>), and
        # re-picking or removing the parent rebuilds/drops them. Maneuvers/spells are excluded (they
        # keep the flat-pool + expand_composite model - the surgical slice-2 boundary).
        out = []
        grants = parent.get('grants') or {}
        cur = self.ledger['current_level']
        for resource, singular in GRANT_CHILD_SLOTS.items():
            n = int(grants.get(resource, 0) or 0)
            if n <= 0:
                continue
            lst = parent.get('granted_%s' % resource) or []
            if resource in PLAN_POINTBUY:
                # FR-3 slice 2 / FR-17: skill & trade child-slots are POINT-BUY. Each slot offers the
                # ONE next tier up from the running state (sibling-distinct within the level). A cap+
                # slot (Mastery-Limit purchase) offers the tier one above the cap and costs 2 points,
                # so the level's N points are consumed as we go: once spent >= N the trailing empty
                # slot is dropped (no dangling picker). Cost is 2 per cap+ pick, 1 otherwise.
                sing = 'skill' if resource == 'skills' else 'trade'
                sib = {self._parse_plan_pick(lst[j])[0]
                       for j in range(min(n, len(lst))) if self._plan_decided(lst[j])}
                spent = 0
                for k in range(n):
                    raw = lst[k] if k < len(lst) else UNDECIDED
                    capd = str(raw) == CAPARM or (self._plan_decided(raw)
                                                  and self._parse_plan_pick(raw)[2])
                    decided = self._plan_decided(raw)
                    if not decided and spent >= n:
                        continue   # budget exhausted (a cap+ pick ate an extra point): drop empty slot
                    pick = raw if decided else UNDECIDED   # a bare CAPARM shows as undecided + cap+ on
                    d = self._dec('GC#%s#%s#%d' % (parentref, resource, k), level, sing,
                                  pick, None, False, editable,
                                  plan=level > cur, plan_editable=editable and level > cur)
                    d['plan_pointbuy'] = resource   # JS: render the cap+ control on this row
                    d['capraise'] = bool(capd)
                    mine = self._parse_plan_pick(pick)[0] if decided else None
                    opts = self._plan_options(resource, level, capraise=bool(capd))
                    d['options'] = [o for o in opts
                                    if self._parse_plan_pick(o['name'])[0] == mine
                                    or self._parse_plan_pick(o['name'])[0] not in sib]
                    out.append(d)
                    if decided:
                        spent += self._plan_pick_cost(raw)
                continue
            for k in range(n):
                pick = lst[k] if k < len(lst) else UNDECIDED
                d = self._dec('GC#%s#%s#%d' % (parentref, resource, k), level, singular,
                              pick, None, False, editable,
                              plan=level > self.ledger['current_level'],
                              plan_editable=editable and level > self.ledger['current_level'])
                if resource == 'disciplines' and d.get('options'):
                    # BUG-21: "if you already know that Discipline, you gain another one of your
                    # choice" - so an already-held Discipline is not a legal pick here. Filter them
                    # out (keeping this slot's own current value selectable, the _dec off-list rule).
                    held = self._chosen_names('discipline') - {str(pick)}
                    d['options'] = [o for o in d['options'] if o['name'] not in held]
                out.append(d)
        # FR-8 slice 5: a TAG-CONSTRAINED spell grant (Eldritch Otherworldly Gift) materialises one
        # constrained spell child-slot. The child id uses resource 'spells' so _set_grant_child writes
        # granted_spells; the slot type 'spell_tagged' filters options to the granted tag. The {spells:1}
        # grant is CONSUMED by this pick (it is already counted by the spell budget via grant totals,
        # exactly like granted_maneuvers), so it does not stack - the flat spell count is unchanged.
        if self._spell_grant_tag(parent):
            n = int(grants.get('spells', 0) or 0)
            lst = parent.get('granted_spells') or []
            for k in range(n):
                pick = lst[k] if k < len(lst) else UNDECIDED
                out.append(self._dec('GC#%s#spells#%d' % (parentref, k), level, 'spell_tagged',
                                     pick, None, False, editable,
                                     plan=level > self.ledger['current_level'],
                                     plan_editable=editable and level > self.ledger['current_level']))
        # BUG-30: an ANY-LIST spell grant (MC Bard Magical Secrets: "any 2 Spells of your choice from
        # any Spell List") materialises N UNFILTERED spell child-slots glued under the granting feature.
        # Same shape as the tag / source branches (resource 'spells' -> granted_spells, consumed by the
        # budget, so the flat count is unchanged). Doing it here rather than widening the flat pool is
        # what keeps every OTHER picker honestly filtered to the character's own lists, and it shows
        # the player which 2 spells the talent is paying for.
        if self._spell_grant_any(parent):
            n = int(grants.get('spells', 0) or 0)
            lst = parent.get('granted_spells') or []
            opts = self._spell_any_options()
            for k in range(n):
                pick = lst[k] if k < len(lst) else UNDECIDED
                d = self._dec('GC#%s#spells#%d' % (parentref, k), level, 'spell_any',
                              pick, None, False, editable,
                              plan=level > cur, plan_editable=editable and level > cur)
                d['options'] = list(opts)
                out.append(d)
        # FR-13a: a SOURCE-constrained spell grant (e.g. Innate Power / Intuitive Magic -> N spells
        # of the chosen Sorcerer Source) materialises source-filtered spell child-slots. Same shape
        # as the tag branch (resource 'spells' -> granted_spells, consumed by the budget), options
        # filtered to the source (+ optional schools). Guarded off the tag case so the two never
        # double-render a parent that (hypothetically) had both.
        # FR-13a slice 2: an EXPLICIT Sorcerous Origin node. A parent carrying a sorcerous_origin dict
        # (MC Sorcerer Innate Power) renders ONE 'source_choice' picker for the chosen Sorcerer Source
        # (Arcane/Divine/Primal). Emitted BEFORE the source-spell children so it reads top-down, and its
        # value DRIVES their source filter (via _spell_grant_source, which reads chosen_source first), so
        # re-picking it re-filters + resets the spell children (see _set_grant_child).
        if isinstance(parent.get('sorcerous_origin'), dict):
            cur_src = parent['sorcerous_origin'].get('chosen_source', UNDECIDED)
            out.append(self._dec('GC#%s#sorcerous_origin#0' % parentref, level, 'source_choice',
                                 cur_src, None, False, editable,
                                 plan=level > cur, plan_editable=editable and level > cur))
        gsrc = self._spell_grant_source(parent)
        if gsrc and not self._spell_grant_tag(parent) and not self._spell_grant_any(parent):
            src, schools = gsrc
            n = int(grants.get('spells', 0) or 0)
            lst = parent.get('granted_spells') or []
            opts = self._spell_sourced_options(src, schools)
            for k in range(n):
                pick = lst[k] if k < len(lst) else UNDECIDED
                d = self._dec('GC#%s#spells#%d' % (parentref, k), level, 'spell_sourced',
                              pick, None, False, editable,
                              plan=level > cur, plan_editable=editable and level > cur)
                d['options'] = list(opts)
                curv = d.get('current')
                if curv and curv != UNDECIDED and not any(o.get('name') == curv for o in d['options']):
                    d['options'].insert(0, {'name': curv, 'label': '%s (current, off-list)' % curv})
                out.append(d)
        # grants-only display (2026-07-19): a PACT BOON grants "N Maneuvers of your choice"
        # (classes.md l.3244 Pact Weapon = Attack, l.3269 Pact Armor = Defensive), so the granted
        # maneuvers are player-CHOICE picks tied to the boon - the exact shape of the slice-5
        # Eldritch spell grant. Render them as EDITABLE grant-child pickers (stored in
        # granted_maneuvers, re-picking the boon rebuilds them via _apply_grants), NOT read-only
        # rows and NOT flat-pool dups. Gated to pact-boon parents so a CHOICE grant that uses the
        # flat pool (Martial Expansion {maneuvers:2}, MC Bard {spells:2}) is untouched.
        if parent.get('slot') in ('pact_boon', 'pact_boons'):
            n = int(grants.get('maneuvers', 0) or 0)
            lst = parent.get('granted_maneuvers') or []
            # the boon constrains the maneuver TYPE (Pact Weapon = Attack, Pact Armor = Defense,
            # classes.md l.3244/3269), sourced from the catalog boon's maneuver_type. Each option
            # carries its type in 'group' (from _maneuver_options), so filter to that type - keeping
            # the current pick selectable even if off-type (mirrors the _dec off-list guard).
            bname = base_name(parent.get('pick')
                              or (parent.get('picks') or [''])[0] or '')
            brow = next((b for b in (self.ccat.get('pact_boons') or []) if b.get('name') == bname), {})
            mtype = brow.get('maneuver_type')
            for k in range(n):
                pick = lst[k] if k < len(lst) else UNDECIDED
                d = self._dec('GC#%s#maneuvers#%d' % (parentref, k), level, 'maneuver',
                              pick, None, False, editable,
                              plan=level > cur, plan_editable=editable and level > cur)
                if mtype and d.get('options'):
                    d['options'] = [o for o in d['options']
                                    if o.get('group') == mtype or o.get('name') == d.get('current')]
                out.append(d)
        return out

    def _apply_grants(self, entry, grants, changed):
        # FR-8 slice 2: one home for "a re-picked grant-bearing parent rebuilds its grants and its
        # granted child-slots". Sets/pops the grants dict; clears stale maneuver/spell provenance on
        # a real option change (mirrors the level pact_boon branch, now applied to discipline / talent
        # / the chargen cg:choice path too); resizes each pickable granted_<resource> list to the new
        # count (all UNDECIDED on change; kept then padded/truncated when the option is unchanged).
        grants = dict(grants or {})
        if grants:
            entry['grants'] = grants
        else:
            entry.pop('grants', None)
        if changed:
            entry.pop('granted_maneuvers', None)
            entry.pop('granted_spells', None)
        for resource in GRANT_CHILD_SLOTS:
            gkey = 'granted_%s' % resource
            n = int(grants.get(resource, 0) or 0)
            if n <= 0:
                entry.pop(gkey, None)
                continue
            prev = [] if changed else list(entry.get(gkey) or [])
            entry[gkey] = (prev + [UNDECIDED] * n)[:n]
        # FR-8 slice 5: a tag-constrained spell grant (Eldritch Psychic) resizes granted_spells like a
        # child resource. Plain {spells:N} grants (the other five) are NOT tag-constrained, so this is a
        # no-op for them and they keep the flat-pool model. (On a real change the granted_spells pop
        # above already fired; here we rebuild it to the new count, all UNDECIDED.)
        # BUG-30: an any-list spell grant (MC Bard Magical Secrets) resizes granted_spells the same way.
        if self._spell_grant_tag(entry) or self._spell_grant_any(entry):
            n = int(grants.get('spells', 0) or 0)
            if n <= 0:
                entry.pop('granted_spells', None)
            else:
                prev = [] if changed else list(entry.get('granted_spells') or [])
                entry['granted_spells'] = (prev + [UNDECIDED] * n)[:n]
        # grants-only (2026-07-19): a pact boon's "N Maneuvers of your choice" are editable
        # grant-children in granted_maneuvers, so resize that list like a child resource (the
        # other {maneuvers:N} grant, Martial Expansion, uses the flat pool and is not a pact_boon).
        if entry.get('slot') in ('pact_boon', 'pact_boons'):
            n = int(grants.get('maneuvers', 0) or 0)
            if n <= 0:
                entry.pop('granted_maneuvers', None)
            else:
                prev = [] if changed else list(entry.get('granted_maneuvers') or [])
                entry['granted_maneuvers'] = (prev + [UNDECIDED] * n)[:n]
        self._sync_granted_effects(entry)   # BUG-34: children just changed, redo their derived total

    def _sync_granted_effects(self, entry):
        # BUG-34 (2026-07-27, Darryl in Chrome; shape (a), his call). The FR-8 child machinery
        # assumed every grant-child is a LEAF: _set_grant_child writes the pick as a bare name
        # string into granted_<resource>, and the engine's sum_grants only walks `grants` dicts. That
        # holds for spells / maneuvers / runes / metamagic, and is false for DISCIPLINES, which carry
        # their own grants. So a Magus picked as a child of Expanded Disciplines moved neither MP nor
        # Spells, while the same Magus picked first-class moved both.
        #
        # The fix keeps the DECLARED grant and the DERIVED total in separate keys. The parent keeps
        # `grants: {disciplines: 2}` (what the option promises: two picks), and gains
        # `granted_effects: {mp: 1, spells: 1, maneuvers: 1}` (what the chosen children add up to),
        # which the engine sums alongside `grants`. Re-picking a child just rebuilds the derived
        # dict from scratch, so it can never drift, and no already-exported player ledger changes
        # shape. `granted_training` is the same idea for the non-numeric half: Warrior's
        # `training: [Heavy Armor, Heavy Shield]`, which never flowed from a picked discipline on
        # ANY path (see _sync_training for the first-class half).
        eff, trained = {}, []
        for resource, singular in GRANT_CHILD_SLOTS.items():
            if resource in PLAN_POINTBUY:
                continue   # skill/trade point-buy children are "Name: Tier" strings, not catalog rows
            pool = {r['name']: r for r in self._child_pool(singular)}
            for pick in entry.get('granted_%s' % resource) or []:
                row = pool.get(base_name(str(pick)))
                if not row:
                    continue   # undecided, or a name the catalog does not know
                for key, val in (row.get('grants') or {}).items():
                    if isinstance(val, bool) or not isinstance(val, (int, float)):
                        eff[key] = val          # a non-numeric flag (jump_from: might): last wins
                    else:
                        eff[key] = eff.get(key, 0) + val
                for t in row.get('training') or []:
                    if t not in trained:
                        trained.append(t)
        for key, val in (('granted_effects', eff), ('granted_training', trained)):
            if val:
                entry[key] = val
            else:
                entry.pop(key, None)

    def _sync_training(self, entry, row):
        # BUG-34, the first-class half. A discipline's combat training (Warrior -> Heavy Armor,
        # Heavy Shield) did not flow on ANY path, including a discipline picked normally, because
        # _apply_grants copies `grants` and nothing else. Kept beside the grants copy rather than
        # folded into it: training is a named list, not a number, so the engine unions it instead of
        # summing it (see build_engine.combat_training).
        t = list((row or {}).get('training') or [])
        if t:
            entry['training'] = t
        else:
            entry.pop('training', None)

    def _resync_all_granted_effects(self):
        # BUG-34: granted_effects is DERIVED, so rebuild it for every grant-bearing parent on load.
        # A ledger written before this change (or hand-authored) then behaves the same as one edited
        # in the builder, instead of quietly under-counting until the child happens to be re-picked.
        # Provably a no-op on all six canon ledgers today: none of them carries granted_disciplines,
        # and every rune / metamagic row is declared no_effect, which is why PARTY_DERIVED does not
        # move. The harness baselines are the guard.
        cg = self.ledger.get('chargen') or {}
        for e in list(cg.get('class_choices') or []) + list(cg.get('ancestry_traits') or []):
            self._sync_granted_effects(e)
        for lvl in (self.ledger.get('levels') or {}):
            for e in self.ledger['levels'][lvl] or []:
                self._sync_granted_effects(e)

    def _set_grant_child(self, did, value):
        # write a grant-child pick into its parent's granted_<resource> list (see _grant_children).
        # did = GC#<parentref>#<resource>#<k>; parentref = 'cgtrait:<i>' (chargen ancestry trait),
        # 'cg:<ci>' (chargen class choice), or 'L<lvl>:<idx>' (level entry).
        _, parentref, resource, k = did.split('#')
        k = int(k)
        entry = self._grant_child_entry(parentref)
        if resource == 'sorcerous_origin':
            # FR-13a slice 2: the explicit Sorcerous Origin node writes the chosen Sorcerer Source.
            # If the source actually changed, reset the source-filtered spell children to UNDECIDED
            # (their old picks may be illegal under the new source), mirroring _apply_grants' clear.
            so = entry.setdefault('sorcerous_origin', {})
            if str(so.get('chosen_source')) != str(value):
                so['chosen_source'] = value
                n = int((entry.get('grants') or {}).get('spells', 0) or 0)
                if n > 0:
                    entry['granted_spells'] = [UNDECIDED] * n
            return self.state()
        n = int((entry.get('grants') or {}).get(resource, 0) or 0)
        lst = list(entry.get('granted_%s' % resource) or [])
        lst = (lst + [UNDECIDED] * n)[:max(n, k + 1)]
        lst[k] = value
        entry['granted_%s' % resource] = lst
        # BUG-34: a grant-child can itself be grant-bearing (a discipline), so rebuild the parent's
        # derived total. Harmless for leaf kinds, which contribute nothing.
        self._sync_granted_effects(entry)
        return self.state()

    def _grant_child_entry(self, parentref):
        if parentref.startswith('cgtrait:'):   # FR-13a slice 2: chargen ancestry-trait grant parent
            return self.ledger['chargen']['ancestry_traits'][int(parentref.split(':')[1])]
        if parentref.startswith('cg:'):
            return self.ledger['chargen']['class_choices'][int(parentref.split(':')[1])]
        lvl, idx = parentref[1:].split(':')
        return self.ledger['levels'][int(lvl)][int(idx)]

    def set_plan_capraise(self, did, on):
        # FR-17: toggle the cap+ (Mastery-Limit purchase) on a planned skill/trade child-slot. On an
        # EMPTY slot this arms cap+ (a bare CAPARM sentinel), which switches the slot's picker to the
        # cap+ option set (offering the tier one above the level cap). On a DECIDED slot it just adds/
        # removes the " (cap+)" suffix (the tier itself is fixed by the single-step rule; the marker
        # records the extra point spent). Only planned skill/trade slots carry this control.
        _, parentref, resource, k = str(did).split('#')
        if resource not in PLAN_POINTBUY:
            return self.state()
        k = int(k)
        entry = self._grant_child_entry(parentref)
        gkey = 'granted_%s' % resource
        n = int((entry.get('grants') or {}).get(resource, 0) or 0)
        lst = list(entry.get(gkey) or [])
        lst = (lst + [UNDECIDED] * n)[:max(n, k + 1)]
        want = str(on) in ('1', 'true', 'True', 'on', 'yes')
        name, tier, _cap = self._parse_plan_pick(lst[k])
        if name:                       # a real pick: rewrite its marker, keep the tier
            lst[k] = '%s: %s%s' % (name, tier, ' ' + CAPARM if want else '')
        else:                          # empty slot: arm / disarm cap+
            lst[k] = CAPARM if want else UNDECIDED
        entry[gkey] = lst
        return self.state()

    def _alloc(self):
        out = []
        for kind in ('skills', 'trades'):
            for name, m in ((self.ledger.get(kind) or {}).get('masteries') or {}).items():
                lr = m.get('limit_raise')
                purchase = 'skill_point_purchase' if kind == 'skills' else 'trade_point_purchase'
                out.append({'id': '%s:%s' % (kind, name), 'kind': kind, 'name': name,
                            'mastery': m.get('mastery'), 'limit_raise': lr,
                            'options': [str(x) for x in MASTERIES],
                            'purchasable': (not lr) or lr == purchase,
                            'purchased': lr == purchase,
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

    def _language_options(self):
        lc = (self.cat.get('languages') or {}).get('languages') or {}
        have = {str(l.get('name')) for l in (self.ledger.get('languages') or [])}
        return [{'name': n, 'group': g} for g, lst in lc.items()
                for n in lst if n not in have]

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

    def _level_grant(self, lvl):
        # FR-10: format ONE class-spine row's grants for that level's section header -
        # the numeric per-level deltas plus the named features (dropping the generic
        # L1 'Class Features' label). Shared by next_level_info (the sidebar next-level
        # strip) and state()'s level_grants map (every rendered level's header).
        row = self.ccat['spine'].get(lvl, {})
        bits = []
        for k, lab in (('hp', 'HP'), ('sp', 'SP'), ('mp', 'MP'), ('spells', 'spell'),
                       ('maneuvers', 'maneuver'), ('attribute_points', 'attribute pt'),
                       ('skill_points', 'skill pt'), ('trade_points', 'trade pt')):
            v = row.get(k, 0)
            if v:
                bits.append('+%d %s' % (v, lab))
        return {'summary': ', '.join(bits),
                'features': [f for f in row.get('features', []) if f != 'Class Features']}

    def next_level_info(self):
        cur = self.ledger['current_level']
        if cur >= 10:
            return None
        g = self._level_grant(cur + 1)
        return {'level': cur + 1, 'summary': g['summary'], 'features': g['features'],
                'has_plan': bool((self.ledger.get('levels') or {}).get(cur + 1))}

    def state(self):
        cur = self.ledger['current_level']
        rep = eng.replay(self.ledger, cur)
        stats, budgets = self._sections(rep.lines)
        planned = [l for l in sorted(self.ledger.get('levels') or {}) if l > cur]
        # FR-10: per-level grant summaries for EVERY rendered level (1..current +
        # planned), for all characters - so each level's collapsible header can show
        # what it grants without expanding. Keyed by level (JSON stringifies the keys;
        # the JS render loop indexes level_grants[lvl]). Supersedes the old cur+1-only
        # next-level echo. L1 (chargen starting kit) is included by design.
        level_grants = {l: self._level_grant(l) for l in list(range(1, cur + 1)) + planned}
        anc_levels = self._anc_grant_levels()   # BUG-36: was a second copy of _anc_ready_level's list
        # FR-3: the next level a plan block can be appended to = one above the highest
        # existing level (completed, current, or already-planned), capped at the L10 ceiling.
        plan_level = max([cur] + list((self.ledger.get('levels') or {}).keys())) + 1
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
            'level_grants': level_grants,
            'undo_level': (self._undo[-1]['added']) if self._undo else None,
            'can_plan': plan_level <= 10,          # FR-3: room to add a planned level
            'plan_level': plan_level if plan_level <= 10 else None,
            'anc_levels': anc_levels,
            'anc_spent': self._anc_budget()[0],     # FR-9: live "N of M spent" readout
            'anc_budget': self._anc_budget()[1],
            # grants-only auto-heal: live "N of M recorded" readout for maneuvers/spells
            'man_have': self._res_have('maneuvers'), 'man_budget': self._res_budget('maneuvers'),
            'spell_have': self._res_have('spells'), 'spell_budget': self._res_budget('spells'),
            'anc_lists_all': sorted(self.cat['ancestries']['ancestries'].keys()),
            'skill_trade_options': self._skill_trade_options(),
            'decisions': self._decisions(),
            'alloc': self._alloc(),
            'languages': self._langs(),
            'language_options': self._language_options(),
            'stats': stats, 'budgets': budgets,
            'advisories': [b for b in budgets if 'SPARE' in b],
            'problems': rep.problems,
            'catalog_problems': self.catalog_problems(),
            'builder_problems': self.builder_problems(),
        })

    def sheet(self):
        import math
        s = json.loads(self.state())
        st = {r[0]: r[1] for r in s['stats']}
        def num(x):
            try:
                return int(str(x))
            except Exception:
                return 0
        attrs = {}
        for part in str(st.get('Attributes', '')).split(' / '):
            part = part.strip()
            if not part:
                continue
            ab, val = part.rsplit(' ', 1)
            key = {'Mig': 'Might', 'Agi': 'Agility', 'Cha': 'Charisma', 'Int': 'Intelligence'}.get(ab, ab)
            attrs[key] = num(val)
        prime = num(st.get('Prime'))
        cmv = num(st.get('Combat Mastery'))
        hp = num(st.get('HP'))
        MB = {'Novice': 2, 'Adept': 4, 'Expert': 6, 'Master': 8, 'Grandmaster': 10}
        skmap = (self.cat.get('skills_trades') or {}).get('skills') or {}
        attr_of = {}
        for a, lst in skmap.items():
            for nm in lst:
                attr_of[nm] = a
        skills, trades = [], []
        for a in s['alloc']:
            tier = a.get('mastery')
            mb = MB.get(tier, 0)
            if a['kind'] == 'skills':
                gov = attr_of.get(a['name'], 'Prime')
                amod = prime if gov == 'Prime' else attrs.get(gov, 0)
                skills.append({'name': a['name'], 'attr': gov, 'tier': tier, 'bonus': amod + mb})
            else:
                trades.append({'name': a['name'], 'tier': tier, 'mb': mb})  # FR-15: mastery bonus only
        cur = s['level']
        eder = eng.replay(self.ledger, cur).derived
        groups = {}
        for d in s['decisions']:
            lv = d.get('level')
            if lv and lv > cur:
                continue
            pick = d.get('pick')
            if not pick or str(pick) == 'None':
                continue
            slot = SHEET_SLOT_ALIAS.get(d.get('slot'), d.get('slot'))   # BUG-32
            lst = groups.setdefault(slot, [])
            if not any(x['pick'] == pick for x in lst):
                lst.append({'level': lv, 'pick': pick})
        spells = []
        # BUG-12(b): tag-constrained granted spells (FR-8 slice 5, e.g. Runt's Psychic
        # Tendrils from Beyond) live under the 'spell_tagged' slot, so pull those in too or
        # they drop off the sheet's spell list. Skip any still-undecided grant.
        for e in groups.get('spell', []) + groups.get('spell_tagged', []) + groups.get('spell_sourced', []):
            if str(e['pick']) == UNDECIDED:
                continue
            m = self.meta.get(e['pick']) or {}
            spells.append({'name': e['pick'], 'school': m.get('school'), 'tags': m.get('tags') or []})
        # The char sheet is the "all my spells in one place" reference view (provenance/grant-source
        # lives in the builder decision list, colour-coded by category). So sort the sheet list
        # ALPHABETICALLY by name for findability, not by the internal slot-kind harvest order
        # (flat -> tagged -> sourced), which would otherwise leak grant provenance into the sheet.
        spells.sort(key=lambda s: str(s['name']).lower())
        equipment = [{'name': it.get('name'), 'pd': it.get('pd'), 'ad': it.get('ad'), 'mods': it.get('mods')}
                     for it in (self.ledger.get('equipment') or [])]
        return json.dumps({
            'character': s['character'], 'player': s['player'], 'klass': s['klass'],
            'subclass': s['subclass'], 'ancestry': s['ancestry'], 'background': s['background'],
            'level': cur, 'cm': cmv, 'prime': prime, 'attrs': attrs,
            'core': {k: st.get(k) for k in ('Attack/Spell Check', 'Save DC', 'Initiative', 'Grit',
                                            'HP', 'SP', 'MP', 'Spells known', 'Maneuvers known', 'PD', 'AD')},
            'derived': {'bloodied': math.ceil(hp / 2), 'well_bloodied': math.ceil(hp / 4),
                        'death_threshold': prime + cmv, 'rest_points': hp,
                        'saves': eder.get('saves', {}), 'move': eder.get('move'),
                        'jump': eder.get('jump'), 'spend_limit': eder.get('spend_limit'),
                        'dr': eder.get('dr', {})},
            'skills': skills, 'trades': trades, 'languages': s['languages'],
            'abilities': groups,   # kept for the harness / any caller that wants it raw
            # BUG-32: the RENDERED ability groups, in SHEET_GROUPS order, so the page cannot
            # drop a slot by forgetting to list it.
            'ability_groups': [{'label': lbl, 'items': groups[sl]}
                               for sl, lbl in SHEET_GROUPS if groups.get(sl)],
            'spells': spells, 'equipment': equipment,
            # FR-23: Stamina Regen trigger(s), derived catalog-driven by the shared engine helper.
            'stamina_regen': eng.stamina_regen(self.ledger, self.cat.get('stamina_regen') or {}),
            # BUG-34: Combat Training, base + anything an option granted. It had no home on the
            # sheet at all, which is why nobody noticed Warrior's Heavy Armor / Heavy Shield never
            # arriving. Assert the artifact, not just the model (trap 3).
            'combat_training': eng.combat_training(self.ledger, cur),
        })

    # ---------- edits ----------
    def set_decision(self, did, value):
        did = str(did)
        value = str(value)
        if did.startswith('GC#'):
            return self._set_grant_child(did, value)   # FR-8 slice 2 grant-child pick
        if did.startswith('AO#'):   # BUG-24: per-ancestry Origin damage-type choice (engine-neutral)
            src = did.split('#', 1)[1]
            self.ledger['chargen'].setdefault('ancestry_origins', {})[src] = value
            return self.state()
        if did.startswith('L') and did.endswith(':trait:+'):
            # BUG-18: the ready ancestry slot rendered at a level (L4/L8) - materialise a real
            # level ancestry_trait entry, then set it (the level analog of cg:trait:+). Handled
            # before the generic 'L<lvl>:<idx>' branch, which cannot parse this sentinel id.
            lvl = int(did[1:].split(':')[0])
            self.ledger.setdefault('levels', {}).setdefault(lvl, []).append(
                {'slot': 'ancestry_trait', 'pick': UNDECIDED, 'cost': 0, 'note': BUILDER_NOTE})
            self._set_trait(self.ledger['levels'][lvl][-1], value, entry=True)
            return self.state()
        if did == 'cg:trait:+':
            # FR-9: the auto empty-slot - materialise a real chargen ancestry trait, then set it
            # (add_trait + _set_trait in one step). Next state() re-derives whether another auto
            # slot is warranted (still under budget) exactly like the skills allocator chains.
            self.ledger['chargen'].setdefault('ancestry_traits', []).append(
                {'name': UNDECIDED, 'cost': 0, 'note': BUILDER_NOTE})
            self._set_trait(self.ledger['chargen']['ancestry_traits'][-1], value)
            return self.state()
        if did.startswith('L') and (did.endswith(':man:+') or did.endswith(':spell:+')):
            # BUG-23: the ready maneuver/spell slot rendered at the level that granted the budget
            # (the level analog of cg:man:+ / cg:spell:+, mirroring the BUG-18 trait sentinel).
            # Materialise a real LEVEL entry so the pick is recorded where it was earned, which is
            # also how the six canon ledgers record level-granted picks (see bonan.yaml L2 spells).
            # Handled before the generic 'L<lvl>:<idx>' branch, which cannot parse this sentinel.
            lvl = int(did[1:].split(':')[0])
            slot = 'maneuver' if did.endswith(':man:+') else 'spell'
            if value != UNDECIDED:
                self.ledger.setdefault('levels', {}).setdefault(lvl, []).append(
                    {'slot': slot, 'pick': value, 'note': BUILDER_NOTE})
            return self.state()
        if did in ('cg:man:+', 'cg:spell:+'):
            # grants-only auto-heal: materialise a real chargen maneuver/spell from the ready
            # slot (mirrors cg:trait:+). Next state() re-derives whether another ready slot is
            # warranted (still under the known count), chaining one at a time.
            key = 'maneuvers' if did == 'cg:man:+' else 'spells'
            if value != UNDECIDED:
                self.ledger['chargen'].setdefault(key, []).append(value)
            return self.state()
        if did.startswith('cg:'):
            parts = did.split(':')
            kind = parts[1]
            cg = self.ledger['chargen']
            if kind == 'choice':
                ci, pi = int(parts[2]), int(parts[3])
                row_ch = cg['class_choices'][ci]
                changed = base_name(row_ch['picks'][pi]) != value
                row_ch['picks'][pi] = value
                # aggregate grants across picks (Magus mp/spells, Pact Weapon maneuvers, ...)
                # BUG-34: pools come from _child_pool, the single source the pickers render from,
                # so this aggregate can never be offered an option it does not know how to score.
                pool = (self._child_pool('discipline') + self._child_pool('pact_boon')
                        + self._child_pool('rune'))
                agg, trained = {}, []
                for p in row_ch['picks']:
                    r = next((d for d in pool if d['name'] == p), None)
                    for k2, v2 in ((r or {}).get('grants') or {}).items():
                        agg[k2] = agg.get(k2, 0) + v2
                    for t in ((r or {}).get('training') or []):   # BUG-34: first-class training
                        if t not in trained:
                            trained.append(t)
                self._sync_training(row_ch, {'training': trained})
                # FR-8 slice 2: apply grants + rebuild grant children, and clear stale
                # granted_maneuvers/granted_spells on a real change - the chargen path did NOT do
                # this before (the known slice-1 gap), now symmetric with the level pact_boon branch.
                self._apply_grants(row_ch, agg, changed)
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
            _old_pick = e.get('pick')
            _was_composite = is_composite(_old_pick) and str(_old_pick) != value
            if slot == 'ancestry_trait':
                self._set_trait(e, value, entry=True)
            elif slot == 'discipline':
                row = next((d for d in self._child_pool('discipline')
                            if d['name'] == value), {})
                e['pick'] = value
                self._apply_grants(e, row.get('grants'), base_name(_old_pick) != value)   # FR-8 slice 2
                self._sync_training(e, row)   # BUG-34: Warrior's Heavy Armor / Heavy Shield
                self._edited(e)
            elif slot == 'talent':
                # BUG-33: one lookup over _talent_rows (general + mc_features + THIS class's
                # class_talents). The old two-branch lookup omitted class_talents entirely.
                row = next((t for t in self._talent_rows() if t['name'] == value), None)
                e['pick'] = value
                self._apply_grants(e, (row or {}).get('grants'), base_name(_old_pick) != value)   # FR-8 slice 2
                self._edited(e)
                self._sync_talent_rider(int(lvl), e)
            elif slot == 'subclass':
                # FR-8 slice 3: the subclass is a grant-bearing parent (the one branch slice 2 left
                # un-wired). Look up its grants in the catalog subclass_grants side-map and route
                # through _apply_grants so re-picking rebuilds/clears its rune child-slots (e.g. Rune
                # Knight grants runes: 2), symmetric with the discipline / pact_boon / talent branches.
                sg = (self.ccat.get('subclass_grants') or {}).get(value) or {}
                changed = base_name(e.get('pick')) != value
                e['pick'] = value
                self.ledger['subclass'] = value
                self._apply_grants(e, sg.get('grants'), changed)   # FR-8 slice 3
                # BUG-21: a subclass grant can name the thing it gives (Paladin -> the Acolyte
                # Discipline). Pre-fill it, unless the character already holds it, in which case the
                # rules say "you gain another one of your choice" so the slot stays an open pick.
                for _res, _want in (sg.get('prefer') or {}).items():
                    _lst = e.get('granted_%s' % _res)
                    if not _lst or str(_lst[0]) != UNDECIDED:
                        continue
                    if _want not in self._chosen_names(GRANT_CHILD_SLOTS.get(_res, _res)):
                        _lst[0] = _want
                self._edited(e)
                # BUG-35: a subclass can owe REAL sibling entries at named levels (Paragon's Class
                # Talent at L3/L7/L10). Sweep after the pick so switching away from Paragon takes
                # its rider with it.
                self._sync_subclass_rider(e)
            elif slot == 'pact_boon':
                changed = base_name(e.get('pick')) != value
                row = next((b for b in (self.ccat.get('pact_boons') or []) if b['name'] == value), {})
                e['pick'] = value
                self._apply_grants(e, row.get('grants'), changed)   # FR-8 slice 2 (clears stale granted_* on change)
                self._edited(e)
            else:
                e['pick'] = value
                self._edited(e)
                if slot == 'path' and BUILDER_NOTE in str(e.get('note', '')):
                    self._sync_path_rider(int(lvl), value)
            if _was_composite:
                e['note'] = 'Replaced composite/placeholder entry in builder (was: %s).' % _old_pick
            # BUG-28: if this re-pick shrank the level's maneuver/spell grant, drop the builder-added
            # flat picks it was funding (guarded; see _prune_level_overflow).
            self._prune_level_overflow(int(lvl))
        return self.state()

    def _set_trait(self, t, value, entry=False):
        lst, row = self._anc_find(value)
        key = 'pick' if entry else 'name'
        # FR-13a slice 2: a trait can carry a source-constrained spell grant (Fiendish Magic ->
        # Command). If it is re-picked to a DIFFERENT trait, drop that spell-grant provenance so a
        # stale grant-child (and a phantom spell in the engine count) cannot linger (mirrors
        # _apply_grants' changed-clear).
        changed = base_name(str(t.get(key))) != base_name(str(value))
        if changed:
            t.pop('granted_spells', None)
            t.pop('spell_access', None)
            t.pop('sorcerous_origin', None)
            if isinstance(t.get('grants'), dict):
                t['grants'].pop('spells', None)
                if not t['grants']:
                    t.pop('grants', None)
        t[key] = value
        if row is not None:
            t['cost'] = row['cost']
            t['source'] = lst
            # Scratch-mode option-effects layer (2026-07-25): copy the catalog option's mechanical
            # effect onto the ledger entry so a picked trait actually APPLIES its effect (previously a
            # scratch pick applied its cost but nothing else - BUG-27 etc). On a real change the spell
            # provenance was cleared just above, so replacing grants with the new trait's catalog
            # grants is safe; an UNCHANGED re-pick leaves the entry (and any hand-authored childed
            # spell grant) untouched.
            # BUG-25 (2026-07-27): the copy now carries CHOICE spell grants too. A def with
            # `grants: {spells: N}` + `spell_access: {source, schools}` (Fiendish Magic, Celestial
            # Magic) becomes a source-constrained grant parent on pick, so the existing FR-13a
            # cgtrait child machinery renders N filtered spell pickers under the trait. Previously
            # those two traits granted nothing in scratch mode because the pair was hand-authored
            # per ledger entry (Scaletrix only).
            # CH-5 Tier-1 (2026-07-27): an ancestry trait may also carry `grants_unarmored`, the
            # conditional-defence shape class features already use (Thick-Skinned / Quick Reactions
            # +1 AD / +1 PD "while you aren't wearing Armor", ancestries.md l.365/396; Hard Shell
            # pairs it with an unconditional {speed: -1}). Same documented heuristic as BUG-22: the
            # equipment model carries no armour TYPE, so is_unarmored() name-matches the items, and
            # the row's note says which way it resolved. Merged INTO grants (not stored separately)
            # so the engine's sum_grants picks it up with no engine change.
            if changed:
                cat_grants = dict(row.get('grants') or {})
                # CH-5 (2026-07-28): a `targets: attributes` row declares the placeholder
                # {attribute: N}; the chosen target is carried in the decorated variant name
                # the picker emitted, so rewrite the key to the engine's attr_<name> here.
                # Resolving it once, at copy time, is what keeps the ENGINE free of a name
                # parse. An unresolved key surviving to the ledger is reported by the engine
                # rather than ignored, so this path cannot fail silently.
                if row.get('targets') == 'attributes' and 'attribute' in cat_grants:
                    _m = re.search(r'\(([^)]+)\)', str(value))
                    _tgt = (_m.group(1).strip().lower() if _m else ATTRS[0])
                    if _tgt in ATTRS:
                        cat_grants['attr_' + _tgt] = cat_grants.pop('attribute')
                cat_unarm = dict(row.get('grants_unarmored') or {})
                if cat_unarm and is_unarmored(self.ledger):
                    for _k, _v in cat_unarm.items():
                        cat_grants[_k] = ((cat_grants.get(_k, 0) + _v)
                                          if isinstance(_v, (int, float)) else _v)
                if cat_grants:
                    t['grants'] = cat_grants
                else:
                    t.pop('grants', None)
                cat_access = row.get('spell_access')
                if cat_access and int(cat_grants.get('spells', 0) or 0) > 0:
                    t['spell_access'] = dict(cat_access)
        was_added = BUILDER_NOTE in str(t.get('note', ''))
        t['note'] = ('%s; cost %s from catalog (%s).'
                     % (BUILDER_NOTE if was_added else 'Edited in builder',
                        row['cost'] if row else '?', lst))
        if row and row.get('grants_unarmored'):
            t['note'] += (' Includes an unarmoured-only bonus.' if is_unarmored(self.ledger)
                          else ' Unarmoured-only bonus NOT applied (armour worn).')
        t.pop('inferred', None)

    def _edited(self, e):
        note = str(e.get('note', ''))
        if BUILDER_NOTE not in note and not note.startswith('Replaced composite'):
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

    def _sync_subclass_rider(self, e=None):
        # BUG-35: a subclass can owe entries the grants dict cannot express. Paragon owes "a Class
        # Talent of your choice from your Class" at L3, L7 and L10 (character-creation.md
        # l.757-780), and a Class Talent carries its own grants, so it has to be a REAL sibling
        # entry rather than a grant-child (a grant-child is stored as a bare name and treated as a
        # leaf, which is BUG-34). The catalog declares them as `level_riders: {level: [{slot,
        # restrict}]}`, so a second subclass with the same shape is a data edit.
        #
        # Rebuild-from-scratch, like the path/talent riders: drop every builder-added subclass
        # rider across ALL levels first, then re-add for the CURRENT subclass. So re-picking
        # Paragon -> Rune Knight removes the talent slot, and levelling to 7 with Paragon already
        # held picks up the next one (add_level calls this too). Canon-recorded picks are never
        # touched: the rider only fires for a builder-touched subclass entry, because a
        # hand-authored ledger already records the talent it chose as its own entry.
        levels = self.ledger.get('levels') or {}
        held = {}   # (level, slot) -> [detached rider entries, in order]
        for lvl in list(levels):
            for r in list(levels[lvl] or []):
                if str(r.get('source', '')).startswith('subclass rider') \
                        and BUILDER_NOTE in str(r.get('note', '')):
                    levels[lvl].remove(r)
                    held.setdefault((int(lvl), r.get('slot')), []).append(r)
        if e is None:
            e = next((x for lv in sorted(levels) for x in (levels[lv] or [])
                      if x.get('slot') == 'subclass'), None)
        if e is None or 'in builder' not in str(e.get('note', '')):
            return
        name = base_name(str(e.get('pick') or ''))
        sg = (self.ccat.get('subclass_grants') or {}).get(name) or {}
        cur = self.ledger['current_level']
        for rlvl, riders in (sg.get('level_riders') or {}).items():
            rlvl = int(rlvl)
            if rlvl not in levels:
                continue   # that level does not exist yet; add_level re-syncs when it does
            for rider in riders or []:
                # Re-attach the SAME entry when one was just detached for this level+slot, so a
                # re-sync (levelling up, re-picking the same subclass) keeps a talent the player
                # already chose, along with its grants and any child slots. Only a genuine change
                # of subclass leaves it detached, which is the intended clear.
                pool = held.get((rlvl, rider['slot'])) or []
                d = pool.pop(0) if pool else {'slot': rider['slot'], 'pick': UNDECIDED,
                                              'note': BUILDER_NOTE}
                d['source'] = 'subclass rider (%s)' % name
                if rider.get('restrict'):
                    d['restrict'] = rider['restrict']
                else:
                    d.pop('restrict', None)
                if rlvl > cur:
                    d['plan_edit'] = True   # FR-3: a rider on a PLANNED level is still fillable
                else:
                    d.pop('plan_edit', None)
                levels[rlvl].append(d)

    def _sync_talent_rider(self, lvl, e):
        # the Attribute Increase General Talent grants Attribute Points; spawn that many
        # attribute pick slots so they can be allocated (mirrors the path rider). Only for
        # builder-touched talent entries, so canon-recorded picks are never duplicated.
        ents = self.ledger['levels'][lvl]
        for r in list(ents):
            if str(r.get('source', '')).startswith('talent rider') \
                    and BUILDER_NOTE in str(r.get('note', '')):
                ents.remove(r)
        n = int((e.get('grants') or {}).get('attribute_points', 0) or 0)
        if n and 'in builder' in str(e.get('note', '')):
            for _ in range(n):
                ents.append({'slot': 'attribute', 'pick': UNDECIDED,
                             'source': 'talent rider (%s)' % e.get('pick'),
                             'note': BUILDER_NOTE})
        # Expanded Boon grants an extra Pact Boon - model it as a first-class boon pick
        # (grants flow from the chosen boon's catalog row), not a conflated talent grant.
        has_boon = any(x.get('slot') == 'pact_boon' for x in ents)
        if base_name(e.get('pick')) == 'Expanded Boon' and not has_boon \
                and 'in builder' in str(e.get('note', '')):
            ents.append({'slot': 'pact_boon', 'pick': UNDECIDED,
                         'source': 'talent rider (Expanded Boon)', 'note': BUILDER_NOTE})

    # (The reconcile cluster _granted_at_level / _parse_picks / _total_granted / expand_composite
    # was RETIRED 2026-07-19 with the grants-only unification. Its one-click "expand into per-level
    # slots" flattened FIXED grants into the flat pool alongside their granted_ lists, which is the
    # double-count this change removed. Missing maneuver/spell slots now self-heal via the auto
    # ready-slot in _decisions; a genuine composite still gets the single-value replace dropdown.)

    def set_attr(self, name, value):
        self.ledger['chargen']['attributes'][str(name)] = int(value)
        return self.state()

    def set_mastery(self, did, value):
        kind, name = str(did).split(':', 1)
        m = self.ledger[kind]['masteries'][name]
        m['mastery'] = None if value in ('None', '', 'null') else str(value)
        return self.state()

    def set_limit_raise(self, did, on):
        # buy a Skill/Trade Mastery Limit raise with 1 point (core-rules.md: spend 1 point
        # to raise the Mastery Limit of a Skill/Trade by 1). The engine counts the extra
        # point and stops flagging the mastery as over the normal level cap.
        kind, name = str(did).split(':', 1)
        m = self.ledger[kind]['masteries'][name]
        purchase = 'skill_point_purchase' if kind == 'skills' else 'trade_point_purchase'
        if str(on) in ('1', 'true', 'True', 'on', 'yes'):
            m['limit_raise'] = purchase
        elif m.get('limit_raise') in ('skill_point_purchase', 'trade_point_purchase'):
            m.pop('limit_raise', None)   # never clobber a non-purchase (Expertise) raise
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

    def dismiss_note(self, did):
        # clear the verbose "Replaced composite ... (was: ...)" provenance once the
        # user has finished re-picking; keep the generic edited marker (hidden on pickers)
        did = str(did)
        if did.startswith('L'):
            lvl, idx = did[1:].split(':')
            e = self.ledger['levels'][int(lvl)][int(idx)]
            note = str(e.get('note', ''))
            if note.startswith('Replaced composite'):
                e['note'] = 'Edited in builder (%s).' % self.handle
            elif 'Overflow' in note:
                e['note'] = '%s (expanded from composite).' % BUILDER_NOTE
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
    def _gen_level_slots(self, new, plan=False):
        # FR-3: build the decision slots a level grants, from the class spine. Shared by
        # add_level (advance) and add_planned_level (append a future plan). When plan=True
        # each generated slot carries plan_edit:True, so a builder-created plan renders as
        # editable pickers (a hand-authored locked plan has no such flag and stays a
        # read-only preview - see _decisions / _dec).
        row = self.ccat['spine'].get(new, {})
        ents = []

        def add(d):
            if plan:
                d['plan_edit'] = True
            ents.append(d)
        for _ in range(row.get('attribute_points', 0)):
            add({'slot': 'attribute', 'pick': UNDECIDED, 'note': BUILDER_NOTE})
        for f in row.get('features', []):
            if f == 'Talent':
                add({'slot': 'talent', 'pick': UNDECIDED, 'note': BUILDER_NOTE})
            elif f == 'Path':
                add({'slot': 'path', 'pick': UNDECIDED, 'note': BUILDER_NOTE})
            elif f == 'Subclass':
                add({'slot': 'subclass', 'pick': UNDECIDED, 'note': BUILDER_NOTE})
            elif f == '2 Ancestry Points':
                add({'slot': 'ancestry_trait', 'pick': UNDECIDED, 'cost': 0,
                     'note': BUILDER_NOTE})
            elif f == 'Class Features':
                pass
            else:
                # BUG-19: the class table prints a generic "Class Feature"; show the REAL feature
                # name(s) for this level from class_features.yaml, one row each, and apply any
                # numeric effect (BUG-22). Outside the curated level range we fall back to the
                # generic label rather than inventing one.
                rows = class_feature_rows(self.cat.get('class_features') or {}, self.cls, new)
                if rows:
                    unarm = is_unarmored(self.ledger)
                    for fr in rows:
                        d = {'slot': 'class_feature', 'pick': fr['name'],
                             'note': ((fr.get('note') + '. ') if fr.get('note') else '')
                                     + ('flavor feature. ' if fr.get('flavor') else '')
                                     + BUILDER_NOTE}
                        g = class_feature_grants([fr], unarmored=unarm)
                        if g:
                            d['grants'] = g
                            if fr.get('grants_unarmored'):
                                d['note'] += (' Includes an unarmoured-only bonus.' if unarm
                                              else ' Unarmoured-only bonus NOT applied (armour worn).')
                        add(d)
                else:
                    add({'slot': 'class_feature', 'pick': f,
                         'note': 'auto - see classes.md. ' + BUILDER_NOTE})
        for _ in range(row.get('spells', 0)):
            add({'slot': 'spell', 'pick': UNDECIDED,
                 'source': 'class table L%d' % new, 'note': BUILDER_NOTE})
        for _ in range(row.get('maneuvers', 0)):
            add({'slot': 'maneuver', 'pick': UNDECIDED,
                 'source': 'class table L%d' % new, 'note': BUILDER_NOTE})
        # FR-3 slice 2: a PLAN level carries its own skill picks. Emit ONE carrier entry whose
        # {skills:N} grant materialises N editable skill child-slots via the FR-8 backbone (N = the
        # class-spine skill_points). Only for plans - a real advance (add_level) leaves skills in the
        # flat aggregate, so completed/current levels are untouched (the Hybrid split; no ledger reshape).
        sp = int(row.get('skill_points', 0) or 0)
        if plan and sp:
            add({'slot': 'skills', 'grants': {'skills': sp},
                 'pick': '%d skill point%s' % (sp, '' if sp == 1 else 's'),
                 'note': 'plan: fill the skill picks below. ' + BUILDER_NOTE})
        # FR-17: a PLAN level also carries its own trade picks, the same way (carrier {trades:M},
        # M = class-spine trade_points). Skills and trades are the two plan point-buy carriers.
        tp = int(row.get('trade_points', 0) or 0)
        if plan and tp:
            add({'slot': 'trades', 'grants': {'trades': tp},
                 'pick': '%d trade point%s' % (tp, '' if tp == 1 else 's'),
                 'note': 'plan: fill the trade picks below. ' + BUILDER_NOTE})
        return ents

    def add_level(self):
        cur = self.ledger['current_level']
        if cur >= 10:
            return self.state()
        new = cur + 1
        levels = self.ledger.setdefault('levels', {})
        # FR-3: the undo snapshot now records the exact level added (added) and whether
        # this was an advance (advanced) vs an appended plan, so undo restores correctly
        # for both and the undo link labels the real level. Snapshot BEFORE mutating.
        self._undo.append({'cur': cur, 'added': new, 'advanced': True,
                           'expected': copy.deepcopy(self.ledger.get('expected')),
                           'had_block': new in levels, 'block': copy.deepcopy(levels.get(new))})
        if new not in levels:
            levels[new] = self._gen_level_slots(new)   # generate slots from the class spine
        # else: PROMOTE the existing plan level - its entries simply become current
        self.ledger['current_level'] = new
        # BUG-35: a subclass rider owed at THIS level (Paragon's Class Talent at L7/L10) only
        # becomes placeable once the level block exists. Re-syncing keeps any rider pick already
        # made on a promoted plan level (see _sync_subclass_rider).
        self._sync_subclass_rider()
        if self.ledger.get('expected') is not None:
            # the sheet totals documented the OLD level; keep them as history, the new
            # level's numbers now come FROM the builder
            self.ledger['expected_at_L%d' % cur] = self.ledger.pop('expected')
        return self.state()

    def add_planned_level(self):
        # FR-3: append the next FUTURE (planned) level as an editable plan block, WITHOUT
        # advancing current_level - so any character can build a multi-level plan the way
        # Tanrielle's L5/L6 were hand-authored. The new plan level stacks above the highest
        # existing level (completed, current, or already-planned) and renders as a dashed,
        # editable plan group. Undo shares the add_level stack, so its undo link never
        # vanishes and unwinds correctly (advanced=False: only the block is removed).
        cur = self.ledger['current_level']
        levels = self.ledger.setdefault('levels', {})
        top = max([cur] + list(levels.keys()))
        new = top + 1
        if new > 10:
            return self.state()
        self._undo.append({'cur': cur, 'added': new, 'advanced': False,
                           'expected': copy.deepcopy(self.ledger.get('expected')),
                           'had_block': new in levels, 'block': copy.deepcopy(levels.get(new))})
        levels[new] = self._gen_level_slots(new, plan=True)
        self._sync_subclass_rider()   # BUG-35: a planned L7/L10 owes Paragon's next Class Talent
        return self.state()

    def undo_add_level(self):
        if not self._undo:
            return self.state()
        u = self._undo.pop()
        new = u['added']
        levels = self.ledger.get('levels') or {}
        if u.get('had_block'):
            levels[new] = u['block']
        else:
            levels.pop(new, None)
        if u.get('advanced'):   # only an advance changed current_level / demoted expected
            self.ledger['current_level'] = u['cur']
            self.ledger.pop('expected_at_L%d' % u['cur'], None)
            if u['expected'] is not None:
                self.ledger['expected'] = u['expected']
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
