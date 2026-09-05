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

And a third, found while hardening this tool itself on Windows:

  3. `Path.write_text()` opens its target in *text* mode, which silently
     translates `\n` to the OS line ending on write — on Windows that means
     every mutate/restore cycle flipped `engine.py` from LF to CRLF, leaving
     `git status` dirty after every run even though the content never changed.
     Worse, `write_text()` truncates the file before writing, in two separate
     steps with no atomicity — if the process is interrupted between them (a
     killed terminal, an antivirus scan grabbing the file mid-write), the file
     is left at 0 bytes, permanently, until someone notices and restores it
     from git. Fixed below: read and write raw bytes (no newline translation),
     and write via a temp file + atomic replace, so a file is either the old
     content or the new content, never neither.

Run:  python tools/mutation_check.py

Every mutation must report CAUGHT. A SURVIVED row means the suite has a blind
spot at exactly the place a fine or a compliance breach would come from.
"""

import pathlib
import subprocess
import sys
import tempfile
import os

RULES = pathlib.Path("due/core/policy/rules.yaml")
ENGINE = pathlib.Path("due/core/policy/engine.py")


def _read_bytes(path: pathlib.Path) -> bytes:
    return path.read_bytes()


def _atomic_write(path: pathlib.Path, data: bytes) -> None:
    """Write bytes so the target is always fully-old or fully-new, never empty."""
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        pathlib.Path(tmp_name).unlink(missing_ok=True)
        raise


ORIG_RULES = _read_bytes(RULES)
ORIG_ENGINE = _read_bytes(ENGINE)

# A "pattern not found" SKIP looks identical whether a rule was genuinely
# renamed or the file underneath it was corrupted by something outside this
# script entirely. Silently reporting SKIP either way is the wrong failure
# mode for a safety tool — it should refuse to run on a file it doesn't
# recognise, not guess quietly.
if b"class PolicyEngine" not in ORIG_ENGINE or len(ORIG_ENGINE) < 5000:
    sys.exit(
        f"ABORT: {ENGINE} looks corrupted or truncated ({len(ORIG_ENGINE)} bytes, "
        "missing 'class PolicyEngine'). Not running mutations against it.\n"
        "Fix: git checkout -- due/core/policy/engine.py due/core/policy/rules.yaml"
    )
if b"max_retries" not in ORIG_RULES or len(ORIG_RULES) < 1000:
    sys.exit(
        f"ABORT: {RULES} looks corrupted or truncated ({len(ORIG_RULES)} bytes, "
        "missing 'max_retries'). Not running mutations against it.\n"
        "Fix: git checkout -- due/core/policy/engine.py due/core/policy/rules.yaml"
    )

MUTATIONS = [
    ("retry cap 3 -> 99",        RULES,  b"      max_retries: 3",  b"      max_retries: 99"),
    ("24h network cap 9 -> 999", RULES,  b"      max_attempts: 9", b"      max_attempts: 999"),
    ("contact cap 2 -> 50",      RULES,  b"      max_contacts: 2", b"      max_contacts: 50"),
    ("RBI notice 24h -> 0",      RULES,  b"      notice_hours: 24",b"      notice_hours: 0"),
    ("AFA threshold -> huge",    RULES,  b"      threshold: 15000",b"      threshold: 99999999"),
    ("consent gate disabled",    ENGINE, b'return (not event.consent_active), (', b'return False, ('),
    ("terminal gate disabled",   ENGINE, b"if cause in TERMINAL_FOR_RETRY:", b"if False:"),
    ("obligation gate disabled", ENGINE, b"return (not event.obligation_valid), (", b'return False, ('),
]

results = []
for name, path, old, new in MUTATIONS:
    orig = ORIG_RULES if path == RULES else ORIG_ENGINE
    if old not in orig:
        results.append((name, "SKIP (pattern not found)")); continue
    _atomic_write(path, orig.replace(old, new, 1))
    r = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q", "-x", "--no-header"],
                       capture_output=True, text=True)
    caught = r.returncode != 0
    line = [l for l in r.stdout.splitlines() if "failed" in l or "passed" in l]
    results.append((name, ("CAUGHT   " if caught else "SURVIVED ") + (line[-1] if line else "")))
    _atomic_write(path, orig)

_atomic_write(RULES, ORIG_RULES)
_atomic_write(ENGINE, ORIG_ENGINE)
print("mutation            result")
print("-" * 72)
for name, res in results:
    print(f"{name:26s} {res}")
