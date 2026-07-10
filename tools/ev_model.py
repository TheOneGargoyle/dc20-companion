#!/usr/bin/env python3
"""DC20 EV model — the script behind the numbers in workshop files 08/10/11/12/13.

Conventions (rules/house-rules.md + 08): 65% to-hit vs an equal-level target
=> on a d20+5 the die thresholds are: hit 8+, Heavy 13+ (+1 dmg), Brutal 18+ (+2),
nat 20 = crit (auto-hit, +2, stacks with the tier reached). "Beyond Brutal"
(+15 over) is unreachable at +5 vs equal defence. ADV/DisADV = keep max/min of
(1+|adv|) d20s; they cancel 1:1. MCP: 2nd/3rd/4th same-type check on your own
turn = DisADV 1/2/3 (reactions on others' turns exempt; Dual Wielding exempts
the next attack with the *other* weapon, once/turn).

Usage: import or run; edit the __main__ examples. Keep assumptions cited when
pasting results into the workshop files, and re-verify vs rules/ after each
DC20 version bump.
"""

def die_probs(adv: int):
    """P(kept die = k) for k=1..20 under ADV (adv>0) / DisADV (adv<0)."""
    n = abs(adv) + 1
    if adv >= 0:
        return [(k/20)**n - ((k-1)/20)**n for k in range(1, 21)]
    return [((21-k)/20)**n - ((20-k)/20)**n for k in range(1, 21)]


def ev(D, adv=0, impact=False, dbl=False):
    """EV of one attack with on-hit damage D at the 65% benchmark.

    impact: +1 dmg on Heavy+ hits (Impact property / Staff of Lightning rider).
    dbl:    Heavy/Brutal/Crit bonuses doubled (Disintegrate).
    """
    P = die_probs(adv)
    e = 0.0
    imp = 1 if impact else 0
    heavy = (2 if dbl else 1) + imp
    brutal = (4 if dbl else 2) + imp
    crit = 4 if dbl else 2
    for k in range(1, 21):
        p = P[k-1]
        if k == 20:
            e += p * (D + brutal + crit)   # brutal tier + crit bonus
        elif k >= 18:
            e += p * (D + brutal)
        elif k >= 13:
            e += p * (D + heavy)
        elif k >= 8:
            e += p * D
    return e


def ev_tiers(tiers, atk, defense, adv=0):
    """General form: tiers = dict(hit=, heavy=, brutal=, crit=) absolute damage
    per tier; explicit attack bonus vs an explicit defense (used for the Bonan
    soak table and melee weapon profiles, e.g. 2H Heavy/Impact:
    tiers = {'hit':2,'heavy':4,'brutal':5,'crit':7})."""
    P = die_probs(adv)
    e = 0.0
    for k in range(1, 21):
        p = P[k-1]
        over = atk + k - defense
        if k == 20:
            e += p * tiers['crit']
        elif over >= 10:
            e += p * tiers['brutal']
        elif over >= 5:
            e += p * tiers['heavy']
        elif over >= 0:
            e += p * tiers['hit']
    return e


def contested(my_bonus, their_bonus, adv=0, their_adv=0):
    """P(my d20+bonus > their d20+bonus); ties -> defender (used for Runt's
    grapple/throw lines in 10: Athletics +7 vs an equal-level +3)."""
    P_me, P_them = die_probs(adv), die_probs(their_adv)
    return sum(P_me[a-1] * P_them[b-1]
               for a in range(1, 21) for b in range(1, 21)
               if a + my_bonus > b + their_bonus)


def p_hit_check(bonus, defense, adv=0):
    """P(d20+bonus >= defense), nat 20 auto-hits (throw-at-target vs PD)."""
    P = die_probs(adv)
    return sum(P[k-1] for k in range(1, 21) if k == 20 or k + bonus >= defense)


def help_die_gain(tiers, atk, defense, die=8, adv=0):
    """EV gain from adding a Help Die (avg die/2+0.5 shift on the check) —
    approximated by shifting the effective attack bonus (used in 11)."""
    shift = die/2 + 0.5
    return ev_tiers(tiers, atk + shift, defense, adv) - ev_tiers(tiers, atk, defense, adv)


if __name__ == "__main__":
    print("Runt mega-bolt D9 + Hasty ADV:            %.2f" % ev(9, adv=1))
    print("  … Lightning Bolt w/ Staff Impact:       %.2f" % ev(9, adv=1, impact=True))
    print("Runt Chain-bolt D7 x2 (pass 2 headline):  %.2f" % (2 * ev(7, adv=1, impact=True)))
    print("Runt grapple, Ath +7 size-ADV vs +3:      %.3f" % contested(7, 3, adv=1))
    print("Runt same-turn throw (MCP net-flat):      %.3f" % contested(7, 3, adv=0))
    print("Runt FK-Disintegrate D7 + Hasty (dbl):    %.2f" % ev(7, adv=1, dbl=True))
    print("AoE per target, D4 (Fireball/Torrent):    %.2f" % ev(4))
    melee = {'hit': 2, 'heavy': 4, 'brutal': 5, 'crit': 7}
    print("Called melee basic (ADV), 11's engine:    %.2f" % ev_tiers(melee, 5, 13, adv=1))
    rage = {'hit': 3, 'heavy': 5, 'brutal': 6, 'crit': 8}
    print("Bonan raging mace + ADV:                  %.2f" % ev_tiers(rage, 5, 13, adv=1))
