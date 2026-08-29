"""Append-only, hash-chained audit ledger.

The compliance claim in this project is not "we followed the rules". It is
"here is a record you can independently verify, and if anyone altered it after
the fact, verification fails and tells you exactly where."

Chain structure:

    GENESIS <- entry[0].prev_hash
               entry[0].hash <- entry[1].prev_hash
               entry[1].hash <- entry[2].prev_hash   ...

Each entry's hash covers its own full content, so altering a field breaks that
entry's content hash. Each entry also commits to its predecessor, so deleting or
reordering entries breaks the link. Both failures are localised: verification
reports the sequence number, which is what makes the trail useful in a dispute
rather than merely tamper-evident in the abstract.

Deliberate limitation, stated rather than glossed: this is tamper-EVIDENT, not
tamper-PROOF. Someone with write access to the file can recompute the whole chain
from the point of alteration onward and produce a self-consistent forgery.
Preventing that needs an external anchor — periodically publishing the head hash
somewhere append-only that the same actor does not control. `head` exists for
exactly that purpose, and `compliance_certificate` is where it would be signed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from due.core.models import DecisionRecord, HashChained, RevalidationEntry

GENESIS = "0" * 64

_KINDS: dict[str, type[HashChained]] = {
    "decision": DecisionRecord,
    "revalidation": RevalidationEntry,
}
_KIND_OF: dict[type, str] = {v: k for k, v in _KINDS.items()}


@dataclass
class Violation:
    seq: int
    entry_id: str
    kind: str
    detail: str


@dataclass
class VerificationResult:
    ok: bool
    entries_checked: int
    violations: list[Violation] = field(default_factory=list)

    def __str__(self) -> str:
        if self.ok:
            return f"chain OK — {self.entries_checked} entries verified"
        lines = [f"chain BROKEN — {len(self.violations)} violation(s) in {self.entries_checked} entries"]
        lines.extend(f"  seq {v.seq} [{v.kind}] {v.entry_id}: {v.detail}" for v in self.violations)
        return "\n".join(lines)


class Ledger:
    """In-memory chain with JSONL persistence."""

    def __init__(self) -> None:
        self._entries: list[HashChained] = []

    # -- writing -----------------------------------------------------------

    def append(self, entry: HashChained) -> HashChained:
        """Seal `entry` against the current head and append it.

        Sealing happens here, not at the call site, so an entry cannot be added
        to the chain without being linked to it.
        """
        sealed = entry.seal(self.head)
        self._entries.append(sealed)
        return sealed

    @property
    def head(self) -> str:
        return self._entries[-1].hash if self._entries else GENESIS

    @property
    def entries(self) -> list[HashChained]:
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    # -- verification ------------------------------------------------------

    def verify(self) -> VerificationResult:
        violations: list[Violation] = []
        expected_prev = GENESIS

        for seq, entry in enumerate(self._entries):
            kind = _KIND_OF.get(type(entry), type(entry).__name__)
            entry_id = getattr(entry, "decision_id", None) or getattr(entry, "entry_id", "?")

            recomputed = entry.compute_hash()
            if recomputed != entry.hash:
                violations.append(
                    Violation(
                        seq=seq,
                        entry_id=str(entry_id),
                        kind=kind,
                        detail=(
                            "content hash mismatch — this entry was altered after sealing "
                            f"(stored {entry.hash[:12]}..., recomputed {recomputed[:12]}...)"
                        ),
                    )
                )
            if entry.prev_hash != expected_prev:
                violations.append(
                    Violation(
                        seq=seq,
                        entry_id=str(entry_id),
                        kind=kind,
                        detail=(
                            "broken link — entry does not commit to its predecessor "
                            f"(expected {expected_prev[:12]}..., found {entry.prev_hash[:12]}...). "
                            "An entry was deleted, reordered, or inserted."
                        ),
                    )
                )
            expected_prev = entry.hash

        return VerificationResult(
            ok=not violations, entries_checked=len(self._entries), violations=violations
        )

    # -- persistence -------------------------------------------------------

    def to_jsonl(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            for entry in self._entries:
                fh.write(
                    json.dumps(
                        {
                            "kind": _KIND_OF[type(entry)],
                            "entry": entry.model_dump(mode="json"),
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                )
        return path

    @classmethod
    def from_jsonl(cls, path: Path) -> Ledger:
        ledger = cls()
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                blob = json.loads(line)
                model = _KINDS[blob["kind"]]
                # Bypass append(): loading must preserve the stored hashes exactly,
                # or verification would re-seal a tampered file into a valid one.
                ledger._entries.append(model.model_validate(blob["entry"]))
        return ledger

    # -- reporting ---------------------------------------------------------

    def decisions(self) -> list[DecisionRecord]:
        return [e for e in self._entries if isinstance(e, DecisionRecord)]

    def revalidations(self) -> list[RevalidationEntry]:
        return [e for e in self._entries if isinstance(e, RevalidationEntry)]

    def blocked_actions(self) -> list[tuple[str, list[str]]]:
        """(decision_id, blocking rule ids) for every decision the gate refused."""
        out = []
        for d in self.decisions():
            rules = [g.rule_id for g in d.blocked_by]
            if rules:
                out.append((d.decision_id, sorted(set(rules))))
        return out

    def compliance_certificate(self, generated_at: datetime | None = None) -> dict:
        """Nightly attestation. The head hash is the anchor a third party records."""
        result = self.verify()
        decisions = self.decisions()
        revals = self.revalidations()
        blocked = self.blocked_actions()

        rule_hits: dict[str, int] = {}
        for _, rules in blocked:
            for r in rules:
                rule_hits[r] = rule_hits.get(r, 0) + 1

        return {
            "generated_at": (generated_at or datetime.now()).isoformat(),
            "chain_head": self.head,
            "entries": len(self._entries),
            "chain_verified": result.ok,
            "violations": [v.detail for v in result.violations],
            "decisions": len(decisions),
            "revalidations": len(revals),
            "revalidations_rejected": sum(1 for r in revals if not r.approved),
            "actions_blocked_by_gate": len(blocked),
            "blocks_by_rule": dict(sorted(rule_hits.items(), key=lambda kv: -kv[1])),
        }
