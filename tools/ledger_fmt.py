#!/usr/bin/env python3
"""FR-50: rewrite the six canon ledgers in the house format, i.e. exactly as the builder's
export prints them, so an untouched export is byte-identical and an edit diffs as only its own
lines. builder_verify (45) asserts the fixed point; run this after any hand edit to a ledger.

    python3 tools/ledger_fmt.py           rewrite builds/<pc>.yaml in place where it drifted
    python3 tools/ledger_fmt.py --check   report drift, exit 1, write nothing

Refuses to write a file whose data would change (yaml.safe_load before == after).
"""
import os
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import builder_build  # noqa: E402
import builder_verify  # noqa: E402

REPO = os.path.dirname(HERE)


def main():
    check = "--check" in sys.argv
    tmp = builder_verify.stage()
    os.chdir(tmp)
    sys.path.insert(0, tmp)
    import builder_api
    cat = {c: c + ".yaml" for c in builder_build.CATALOG}
    chars = list(builder_build.CHARS)
    assert chars, "no ledgers found"
    drift = []
    for c in chars:
        path = os.path.join(REPO, "builds", c + ".yaml")
        src = open(path, encoding="utf-8").read()
        out = builder_api.BuilderAPI(c, cat, ledger_text=src).export_yaml()
        if yaml.safe_load(out) != yaml.safe_load(src):
            sys.exit("REFUSED %s: export would change the ledger's data" % c)
        if "anchor was edited away" in out:
            sys.exit("REFUSED %s: a comment lost its anchor" % c)
        if out == src:
            continue
        drift.append(c)
        if not check:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(out)
    verb = "drifted" if check else "rewritten"
    print("%s: %s" % (verb, ", ".join(drift)) if drift else "all %d ledgers in house format" % len(chars))
    sys.exit(1 if (check and drift) else 0)


if __name__ == "__main__":
    main()
