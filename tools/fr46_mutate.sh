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
#   bash tools/fr46_mutate.sh              # all cases (~90s)
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

# 2. The KNOWN_FAIL registry must be load-bearing rather than decorative: drop the BUG-36 entry
#    and the real, still-open bug has to surface as a failure instead of staying hidden.
#    RETIRE THIS CASE when BUG-36 is fixed and its RT_KNOWN_FAIL entry is removed.
run_case "RT_KNOWN_FAIL entry dropped (BUG-36 must resurface)" \
  "ancestry-point budget" \
  "python3 -c \"
p='tools/builder_verify.py'
t=open(p,encoding='utf-8').read()
old='    \\\"Ancestry Increase\\\": \\\"BUG-36\\\",'
assert t.count(old)==1, 'anchor moved: RT_KNOWN_FAIL BUG-36 (fixed? retire this case)'
open(p,'w',encoding='utf-8').write(t.replace(old,'',1))
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

# 5. CH-5 safety net: Speed Increase and Short-Legged work TODAY by engine name-match. Making
#    them data-driven must not change what a player sees, so an inert one has to fail here.
#    UPDATE THIS CASE when CH-5 retires the name-matches (the mutation target moves to the data).
run_case "name-matched todo goes inert (Speed Increase)" \
  "still moves Move Speed by +1" \
  "python3 -c \"
p='tools/build_engine.py'
t=open(p,encoding='utf-8').read()
old='if n.startswith(\\\"Speed Increase\\\")'
assert t.count(old)==1, 'anchor moved: Speed Increase name-match (CH-5 done? update this case)'
open(p,'w',encoding='utf-8').write(t.replace(old,'if n.startswith(\\\"__off__\\\")',1))
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

echo
echo "=== caught $pass / $((pass+fail)) ==="
[ "$fail" -eq 0 ]
