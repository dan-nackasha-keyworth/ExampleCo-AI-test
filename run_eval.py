"""
Eval-as-CI: a small, fixed set of "known-answer" messages, run through
the real pipeline against the real API, with hard pass/fail assertions.

This is the answer to "how do you know the next prompt change won't
reintroduce a bug you already fixed" - both real false positives this
build caught (msg_017, msg_085) are encoded here as regression cases
that must never fire again, alongside the messages that must still be
caught correctly. Run this before shipping any prompt change, or let
CI run it automatically on every push (see .github/workflows/eval.yml).

Exits non-zero on any failure, so it's usable as a CI gate, not just a
manual sanity check.
"""

import json
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from config import CONFIG
from pipeline import classify_and_extract

DATA_PATH = Path(__file__).parent / "data" / "sample_messages.json"

# Each case: message id, and the specific assertion(s) it must satisfy -
# one classify_and_extract call per unique message id, all assertions for
# that id checked against the same extraction (not re-queried per check).
# "must_flag_sensitive" / "must_not_flag_sensitive" check sensitive_topic_flags.
# "must_flag_retention" / "must_not_flag_retention" check retention_risk_language.
# "must_be_category" checks the predicted category outright.
CASES = [
    # Sensitive-topic true positives - recall must hold.
    {"id": "msg_095", "must_flag_sensitive": True},
    {"id": "msg_096", "must_flag_sensitive": True},
    {"id": "msg_097", "must_flag_sensitive": True},
    {"id": "msg_098", "must_flag_sensitive": True},
    {"id": "msg_099", "must_flag_sensitive": True},
    {"id": "msg_100", "must_flag_sensitive": True},
    {"id": "msg_118", "must_flag_sensitive": True},
    # Real false positive #1 (fixed): routine return-to-sender must NOT
    # be misread as a customs seizure.
    {"id": "msg_017", "must_not_flag_sensitive": True},
    # Routine near-misses that must stay unflagged (the original bug
    # class - substring/near-miss matching on "customs").
    {"id": "msg_004", "must_not_flag_sensitive": True},
    {"id": "msg_010", "must_not_flag_sensitive": True},
    {"id": "msg_018", "must_not_flag_sensitive": True},
    {"id": "msg_024", "must_not_flag_sensitive": True},
    # Retention-risk true positives - recall must hold.
    {"id": "msg_083", "must_flag_retention": True},
    {"id": "msg_092", "must_flag_retention": True},
    {"id": "msg_117", "must_flag_retention": True},
    # Real false positive #2 (fixed): anger about a billing issue, with
    # no actual leaving/switching language, must NOT be flagged as
    # retention risk. Also both a sensitive-topic true positive and a
    # retention-risk regression case in the same message - one call.
    {"id": "msg_085", "must_flag_sensitive": True, "must_not_flag_retention": True},
    # Basic classification sanity check - a clean, unambiguous message
    # should still land in the right category.
    {"id": "msg_002", "must_be_category": "Service"},
]


def load_message(all_messages, msg_id):
    for m in all_messages:
        if m["id"] == msg_id:
            return m
    raise KeyError(f"message {msg_id} not found in sample_messages.json")


def main():
    load_dotenv()
    client = anthropic.Anthropic(max_retries=3, timeout=60.0)

    with open(DATA_PATH, encoding="utf-8") as f:
        all_messages = json.load(f)

    failures = []
    for case in CASES:
        msg = load_message(all_messages, case["id"])
        extraction, _ = classify_and_extract(
            client, msg["text"], CONFIG, entry_channel=msg.get("entry_channel"),
        )

        is_sensitive = bool(extraction["sensitive_topic_flags"])
        is_retention = extraction["retention_risk_language"]
        category = extraction["category"]

        if case.get("must_flag_sensitive") and not is_sensitive:
            failures.append(f"{case['id']}: expected sensitive_topic_flags to fire, got none")
        if case.get("must_not_flag_sensitive") and is_sensitive:
            failures.append(f"{case['id']}: expected NO sensitive flag, got {extraction['sensitive_topic_flags']}")
        if case.get("must_flag_retention") and not is_retention:
            failures.append(f"{case['id']}: expected retention_risk_language=True, got False")
        if case.get("must_not_flag_retention") and is_retention:
            failures.append(f"{case['id']}: expected retention_risk_language=False, got True")
        if case.get("must_be_category") and category != case["must_be_category"]:
            failures.append(f"{case['id']}: expected category={case['must_be_category']}, got {category}")

        status = "FAIL" if any(case["id"] in f for f in failures) else "pass"
        print(f"  [{status}] {case['id']}")

    print()
    if failures:
        print(f"{len(failures)} regression(s) found:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print(f"All {len(CASES)} eval cases passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
