#!/bin/bash
# Mutation test for the FR-46 option round-trip, the (RT) section of tools/builder_verify.py.
#
# WHY THIS EXISTS. A harness that only ever passes is worthless, and FR-46 is a harness whose
# whole claim is "it would have caught BUG-19/22/24/25/27/30/33". That claim needs evidence.
# Each case below breaks exactly ONE thing and asserts builder_verify now FAILS, via the
# specific check that is supposed to notice. If a case stops being caught, the round-trip has
# developed a blind spot and the (RT) section is no longer worth the runtime it costs.
#
# It also caught a real defect in FR-46 itself on the first pass: case 4 is the string-vs-int
# catalog-key bug the section shipped with, where three fixed class features silently asserted
# nothing at all and the suite still said PASS.
#
# USAGE
#   bash tools/fr46_mutate.sh              # all cases (~2m, 7 cases)
#   CASES=1,4 bash tools/fr46_mutate.sh    # just those cases, by number
#
# Each case runs in a throwaway copy of the tree under $TMPDIR, so the working tree is never
# mutated. Exits 0 only when every selected case was caught.
#
# A NOTE ON WHAT IS DELIBERATELY *NOT* TESTED. Mutating the CATALOG is not caught, and must not
# be: the assertions read each expected amount FROM the catalog row, so the catalog IS the
# specification. Changing it moves the spec and correctly still passes. Only an implementation
# that fails to honour the spec is a bug, so every mutation below breaks the ENGINE, the API,
# or the harness. Case 3 is the one exception and it is not a counter-example: it adds an
# unknown grant KEY, which is a spec the harness cannot interpret rather than a changed amount.
#
# Runs one section via `builder_verify.py --only fr46` (~11s) rather than the full ~45s suite,
# which is what keeps the whole sweep inside a constrained sandbox's process budget.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$HERE")"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/fr46_mutate.XXXXXX")"
SEED="$TMP/seed"
WORK="$TMP/work"
trap 'rm -rf "$TMP"' EXIT

pass=0; fail=0; n=0
WANT="${CASES:-all}"

# Seed from the working tree, minus .git (a 7.5M copy per case is pure latency).
mkdir -p "$SEED"
( cd "$REPO" && tar cf - --exclude=.git . ) | ( cd "$SEED" && tar xf - )

run_case () {
  local name="$1"; local want="$2"; local setup="$3"
  n=$((n+1))
  if [ "$WANT" != "all" ] && ! echo ",$WANT," | grep -q ",$n,"; then return; fi
  rm -rf "$WORK"; cp -r "$SEED" "$WORK"
  if ! ( cd "$WORK" && eval "$setup" ); then
    echo "SETUP BROKE  [$n] $name"; fail=$((fail+1)); return
  fi
  out=$(cd "$WORK" && timeout 300 python3 tools/builder_verify.py --only fr46 2>&1)
  code=$?
  if [ "$code" -eq 0 ]; then
    echo "NOT CAUGHT   [$n] $name  (builder_verify still exited 0)"
    fail=$((fail+1))
  elif echo "$out" | grep -q -- "$want"; then
    echo "caught       [$n] $name"
    echo "               -> $(echo "$out" | grep -m1 -- "$want" | sed 's/^ *//' | cut -c1-100)"
    pass=$((pass+1))
  else
    echo "CAUGHT WRONG [$n] $name (it failed, but not via '$want')"
    echo "$out" | grep -m3 -- "FAIL " | sed 's/^/               /'
    fail=$((fail+1))
  fi
}

echo "=== FR-46 mutation tests (repo: $REPO) ==="

# 1. A declared numeric grant that no longer ARRIVES: the BUG-19/22/24/25/27/30 family shape,
#    and the single most important thing this section claims to catch.
run_case "engine drops numeric grants (sum_grants returns 0 for hp)" \
  "moves HP by +1" \
  "python3 -c \"
p='tools/build_engine.py'
t=open(p,encoding='utf-8').read()
old='''def sum_grants(ledger, level, key):
    total = 0'''
new='''def sum_grants(ledger, level, key):
    if key == 'hp':
        return 0
    total = 0'''
assert t.count(old)==1, 'anchor moved: sum_grants'
open(p,'w',encoding='utf-8').write(t.replace(old,new,1))
\""

# 2. The RT_KNOWN_FAIL registry must be load-bearing rather than decorative. Until 2026-07-28 this
#    case proved that by DROPPING the BUG-36 entry so the real bug resurfaced. BUG-36 is now fixed
#    and the registry is empty, which is trap 4 waiting to happen: an empty collection passes every
#    assertion about its members, so the reverse-assertion at the bottom of _rt_check_option ("it
#    now WORKS, retire the entry") would sit there with zero coverage and rot. So the mutation was
#    inverted: ADD an entry for an option that demonstrably works, and the guard must fire.
#    This one case buys two things. It exercises the registry machinery, and because the guard only
#    trips when the budget genuinely MOVES, it also proves the BUG-36 fix is still live. That makes
#    it a whole-budget grant assertion (nothing spawns, no stat changes), a shape no other case
#    covers. If a future bug repopulates RT_KNOWN_FAIL, swap the entry here for one that is still
#    broken and flip the expectation back to the old "must resurface" form.
run_case "RT_KNOWN_FAIL entry added for a WORKING option (guard must fire)" \
  "it now WORKS" \
  "python3 -c \"
p='tools/builder_verify.py'
t=open(p,encoding='utf-8').read()
old='RT_KNOWN_FAIL = {}'
new='''RT_KNOWN_FAIL = {'Ancestry Increase': 'BUG-36'}'''
assert t.count(old)==1, 'anchor moved: RT_KNOWN_FAIL (repopulated? see the note above)'
open(p,'w',encoding='utf-8').write(t.replace(old,new,1))
\""

# 3. A brand-new grant key must not ship unasserted. This is trap 2 (never hand-maintain a list
#    that mirrors another list) applied to the harness's own assertion tables.
run_case "new unrecognised grant key appears in the catalog" \
  "every grant key the catalog uses has an assertion table" \
  "python3 -c \"
p='builds/catalog/ancestries.yaml'
t=open(p,encoding='utf-8').read()
old='- {name: Tough, cost: 1, grants: {hp: 1}}'
i=t.index('Dwarf:'); j=t.index(old,i)
t=t[:j]+'- {name: Tough, cost: 1, grants: {hp: 1, sanity_points: 3}}'+t[j+len(old):]
open(p,'w',encoding='utf-8').write(t)
\""

# 4. The bug this section SHIPPED with. class_features.yaml keys its levels as integers, so a
#    string-only path walk resolves the three fixed class features to {}, runs zero assertions,
#    prints nothing, and the suite still says PASS. The silence guard must fire.
run_case "_rt_catalog_row regressed to string-only keys (silent-pass trap)" \
  "produced at least one assertion" \
  "python3 -c \"
p='tools/builder_verify.py'
t=open(p,encoding='utf-8').read()
old='''        if part in node:
            node = node[part]
        else:
            try:                                  # class_features.yaml keys levels as ints
                node = node[int(part)]
            except (ValueError, KeyError):
                return {}'''
new='''        node = node.get(part)
        if node is None:
            return {}'''
assert t.count(old)==1, 'anchor moved: _rt_catalog_row key walk'
open(p,'w',encoding='utf-8').write(t.replace(old,new,1))
\""

# 5. CH-5 (2026-07-28) REPLACED the old "name-matched todo goes inert" case, which mutated the
#    engine's `startswith("Speed Increase")` branch. That branch no longer exists: Speed Increase
#    and the per-attribute deltas are data now. The mutation target moved to the seam the refactor
#    INTRODUCED, which is the builder's target resolution: a `targets: attributes` row declares the
#    placeholder {attribute: N} and _set_trait rewrites the key to attr_<chosen>. Break that and the
#    grant reaches the ledger unresolved, so it applies nothing, which is the exact failure mode of
#    the whole BUG-19/22/24/25/27/30/36 family in a brand-new place. Note this mutates the API, not
#    the catalog: the catalog still declares the right thing, the implementation stops honouring it.
run_case "builder stops resolving a targeted grant to attr_<target>" \
  "moves Charisma by +1" \
  "python3 -c \"
p='tools/builder_build.py'
t=open(p,encoding='utf-8').read()
old='if _tgt in ATTRS:'
assert t.count(old)==1, 'anchor moved: _set_trait target resolution'
open(p,'w',encoding='utf-8').write(t.replace(old,'if False:',1))
\""

# 6. The reachability guard: an RT_UNREACHABLE entry that becomes reachable must be RETIRED, not
#    left to rot. Simulated by claiming a plainly reachable option is unreachable.
run_case "stale RT_UNREACHABLE entry (the option is actually reachable)" \
  "now reachable via" \
  "python3 -c \"
p='tools/builder_verify.py'
t=open(p,encoding='utf-8').read()
old='RT_UNREACHABLE = {'
new='RT_UNREACHABLE = {\n    \\\"Innate Power\\\": \\\"deliberately wrong, for the mutation test\\\",'
assert t.count(old)==1, 'anchor moved: RT_UNREACHABLE'
open(p,'w',encoding='utf-8').write(t.replace(old,new,1))
\""

# 7. The other half of the same seam: the ENGINE must apply the per-attribute keys it is handed.
#    Case 1 proves this for a summed derived stat (hp); an attribute is a different code path (it
#    feeds Prime, saves, jump and the Attributes row rather than a single total), and it is the one
#    CH-5 added, so it gets its own case rather than being assumed covered.
run_case "engine ignores per-attribute grants (attribute_deltas returns zeros)" \
  "moves Might by -1" \
  "python3 -c \"
p='tools/build_engine.py'
t=open(p,encoding='utf-8').read()
old='    return {a: sum_grants(ledger, level, ATTR_GRANT_PREFIX + a) for a in ATTRIBUTES}'
new='    return {a: 0 for a in ATTRIBUTES}'
assert t.count(old)==1, 'anchor moved: attribute_deltas'
open(p,'w',encoding='utf-8').write(t.replace(old,new,1))
\""

echo
echo "=== caught $pass / $((pass+fail)) ==="
[ "$fail" -eq 0 ]
