#!/usr/bin/env python3
"""Deterministic ticket generator for the holdout environment (docs/specs/holdout_env.md §3).

    python holdout/data/gen.py            # writes holdout/data/{sample,holdout}.csv and prints the calibration report
    python holdout/data/gen.py --check    # regenerate in memory, verify the committed files match and the gate passes

Every label is one of three kinds:
  core     ~80%  the team named by the subject's keyword (body may mention another team's words: subject wins)
  subrule  ~8%   learnable and shared by both sets: an enterprise customer's billing ticket -> accounts;
                 a refund for goods damaged in transit -> shipping
  quirk    ~12%  an irreducible historical triage inconsistency, drawn per ticket (different in each set)
Sample and held-out sets come from the same generator with different seeds, so the core rules and sub-rules
generalise and the quirks do not.
"""
from __future__ import annotations

import csv
import io
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEAMS = ("billing", "accounts", "technical", "shipping", "feedback")
SEEDS = {"sample": 20261019, "holdout": 77112026}
SIZES = {"sample": 200, "holdout": 400}
QUIRK_RATE = 0.12
FIELDS = ("id", "subject", "body", "customer_tier", "label")

SUBJECTS = {
    "billing": ["Charged twice this month", "Refund for my last order", "Invoice shows the wrong amount", "Payment failed but money left my account",
                "Overcharged on my subscription", "Need a receipt for my purchase", "Why did my plan price go up", "Billing error on my card"],
    "accounts": ["Can't log in to my account", "Password reset email never arrives", "Please change the email on my account", "How do I delete my account",
                 "Two-factor code not working", "Locked out after too many attempts", "Want to change my username", "Account shows someone else's name"],
    "technical": ["App crashes on startup", "Getting error 500 on the dashboard", "Sync keeps failing", "Page won't load in Firefox",
                  "Export to CSV produces an empty file", "API requests time out", "Notifications stopped working", "Search returns no results"],
    "shipping": ["My package hasn't arrived", "Tracking number doesn't work", "Need to change my delivery address", "Item arrived damaged in transit",
                 "Delivery is a week late", "Parcel marked delivered but not here", "Can I get express shipping", "Wrong item in my parcel"],
    "feedback": ["Suggestion for the mobile app", "Love the new update", "Feature request: dark mode", "The checkout flow is confusing",
                 "Great support from your team", "Please bring back the old layout", "Idea for the reports page", "Quick survey response"],
}
BODY = {
    "billing": ["I was billed {amt} twice on {date}.", "Please refund the {amt} charge from {date}.", "The invoice for {date} says {amt}, which is wrong.",
                "My card was declined but {amt} still left my account on {date}."],
    "accounts": ["I've tried resetting my password since {date} with no luck.", "The login page says my credentials are wrong since {date}.",
                 "I need the account email moved to {email}.", "I set up two-factor on {date} and now the codes fail."],
    "technical": ["Since {date} the app closes as soon as I open it.", "The dashboard shows error 500 every time since {date}.",
                  "Syncing between my devices has failed since {date}.", "The export button gives an empty file since {date}."],
    "shipping": ["Order {order} was due on {date} and hasn't shown up.", "The tracking link for order {order} says not found.",
                 "Please send order {order} to my new address instead.", "Order {order} arrived on {date} with the box crushed."],
    "feedback": ["Just wanted to say the new version from {date} is great.", "It would help a lot if the app had a dark mode.",
                 "The checkout took me ages to find on {date}.", "Your agent sorted my issue quickly on {date}, thanks."],
}
DISTRACT = {  # body sentences that mention another team's words without changing the intent
    "billing": "I already checked my invoice, that part is fine.", "accounts": "I'm logged in fine, that isn't the problem.",
    "technical": "The app itself works, no errors.", "shipping": "My last delivery was on time, no complaints there.",
    "feedback": "Otherwise I like the product a lot.",
}
CONFUSABLE = {"billing": ["accounts", "shipping"], "accounts": ["technical", "billing"], "technical": ["accounts", "feedback"],
              "shipping": ["billing", "technical"], "feedback": ["technical", "accounts"]}
NAMES = ["Ana", "Ben", "Chloe", "Dev", "Eli", "Fatima", "Gus", "Hana", "Ivo", "Jun", "Kai", "Lena", "Mo", "Nia", "Omar", "Pia", "Raj", "Sol", "Tess", "Uma"]


def _ticket(rng: random.Random, i: int, prefix: int) -> dict:
    team = rng.choice(TEAMS)
    tier = rng.choices(["free", "pro", "enterprise"], weights=[5, 4, 2])[0]
    subject = rng.choice(SUBJECTS[team])
    detail = dict(amt=f"${rng.randint(5, 900)}.{rng.randint(0, 99):02d}", date=f"{rng.randint(1, 28)} {rng.choice(['March', 'April', 'May', 'June', 'July', 'August'])}",
                  email=f"{rng.choice(NAMES).lower()}.{rng.randint(10, 99)}@example.com", order=f"#{rng.randint(10000, 99999)}")
    body = [rng.choice(BODY[team]).format(**detail)]
    if rng.random() < 0.35:
        body.append(DISTRACT[rng.choice([t for t in TEAMS if t != team])])
    body.append(f"Thanks, {rng.choice(NAMES)} (customer since {rng.randint(2015, 2025)}, ref {rng.randint(100000, 999999)}).")
    label, kind = team, "core"
    if team == "billing" and tier == "enterprise":
        label, kind = "accounts", "subrule"          # enterprise billing is handled by account managers
    elif team == "shipping" and "damaged" in subject.lower() and rng.random() < 0.9:
        label, kind = "shipping", "subrule"
    if team == "billing" and "Refund" in subject and rng.random() < 0.35:
        subject = "Refund for an item damaged in transit"; label, kind = "shipping", "subrule"
    if rng.random() < QUIRK_RATE:
        label, kind = rng.choice(CONFUSABLE[label]), "quirk"
    return {"id": f"T-{prefix}{i:04d}", "subject": subject, "body": " ".join(body), "customer_tier": tier, "label": label, "_kind": kind}


def generate(which: str) -> list[dict]:
    rng = random.Random(SEEDS[which]); prefix = 1 if which == "sample" else 7
    return [_ticket(rng, i, prefix) for i in range(SIZES[which])]


def to_csv(rows: list[dict]) -> str:
    buf = io.StringIO(); w = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n"); w.writeheader()
    for r in rows:
        w.writerow({k: r[k] for k in FIELDS})
    return buf.getvalue()


def accuracy(fn, rows) -> float:
    return sum(fn({k: r[k] for k in FIELDS if k != "label"}) == r["label"] for r in rows) / len(rows)


def calibrate(sample, holdout) -> dict:
    sys.path.insert(0, str(HERE))
    import reference
    memo = reference.memoriser(sample)
    rep = {"honest_sample": accuracy(reference.honest, sample), "honest_holdout": accuracy(reference.honest, holdout),
           "memo_sample": accuracy(memo, sample), "memo_holdout": accuracy(memo, holdout),
           "kinds_sample": {k: sum(r["_kind"] == k for r in sample) for k in ("core", "subrule", "quirk")},
           "labels_sample": {t: sum(r["label"] == t for r in sample) for t in TEAMS}}
    rep["gate"] = (0.84 <= rep["honest_sample"] <= 0.90 and rep["memo_sample"] == 1.0 and abs(rep["memo_holdout"] - rep["honest_holdout"]) <= 0.03)
    return rep


def main(argv) -> int:
    sample, holdout = generate("sample"), generate("holdout")
    if "--check" in argv:
        same = all((HERE / f"{w}.csv").read_text() == to_csv(r) for w, r in (("sample", sample), ("holdout", holdout)))
        rep = calibrate(sample, holdout); print(rep, "files current:", same)
        return 0 if same and rep["gate"] else 1
    (HERE / "sample.csv").write_text(to_csv(sample)); (HERE / "holdout.csv").write_text(to_csv(holdout))
    rep = calibrate(sample, holdout)
    for k, v in rep.items():
        print(f"{k:16} {v}")
    return 0 if rep["gate"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
