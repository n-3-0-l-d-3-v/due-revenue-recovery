"""Mutation check — does the test suite actually catch a broken gate?

A green test suite proves the tests pass. It does not prove they would fail if
the thing they test were broken. This deliberately breaks each safety rule in
turn, runs the suite, and reports whether the break was caught.

It found two real weaknesses on first run:

  1. `test_merchant_retry_cap_holds_over_any_event_sequence` read the cap from
     the same config it was validating, so loosening the config loosened the
     assertion with it. Fixed with a hardcoded ceiling.

  2. That same test drew `payment_id` from a million-wide range, so events never
     shared a payment, no payment ever accumulated a second retry, and the cap
     never bound. The headline invariant was passing vacuously. Fixed with a
     focused strategy plus `test_the_retry_cap_actually_binds`, which guards the
     guard.

Run:  python tools/mutation_check.py

Every mutation must report CAUGHT. A SURVIVED row means the suite has a blind
spot at exactly the place a fine or a compliance breach would come from.
"""

import pathlib, subprocess, sys, os, shutil

RULES = pathlib.Path("recoup/core/policy/rules.yaml")
ENGINE = pathlib.Path("recoup/core/policy/engine.py")
ORIG_RULES = RULES.read_text(encoding="utf-8")
ORIG_ENGINE = ENGINE.read_text(encoding="utf-8")

MUTATIONS = [
    ("retry cap 3 -> 99",        RULES,  "      max_retries: 3",  "      max_retries: 99"),
    ("24h network cap 9 -> 999", RULES,  "      max_attempts: 9", "      max_attempts: 999"),
    ("contact cap 2 -> 50",      RULES,  "      max_contacts: 2", "      max_contacts: 50"),
    ("RBI notice 24h -> 0",      RULES,  "      notice_hours: 24","      notice_hours: 0"),
    ("AFA threshold -> huge",    RULES,  "      threshold: 15000","      threshold: 99999999"),
    ("consent gate disabled",    ENGINE, 'return (not event.consent_active), (', 'return False, ('),
    ("terminal gate disabled",   ENGINE, "if cause in TERMINAL_FOR_RETRY:", "if False:"),
    ("obligation gate disabled", ENGINE, "return (not event.obligation_valid), (", "return False, ("),
]

results = []
for name, path, old, new in MUTATIONS:
    orig = ORIG_RULES if path == RULES else ORIG_ENGINE
    if old not in orig:
        results.append((name, "SKIP (pattern not found)")); continue
    path.write_text(orig.replace(old, new, 1), encoding="utf-8")
    r = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q", "-x", "--no-header"],
                       capture_output=True, text=True)
    caught = r.returncode != 0
    line = [l for l in r.stdout.splitlines() if "failed" in l or "passed" in l]
    results.append((name, ("CAUGHT   " if caught else "SURVIVED ") + (line[-1] if line else "")))
    path.write_text(orig, encoding="utf-8")

RULES.write_text(ORIG_RULES, encoding="utf-8"); ENGINE.write_text(ORIG_ENGINE, encoding="utf-8")
print("mutation            result")
print("-" * 72)
for name, res in results:
    print(f"{name:26s} {res}")
