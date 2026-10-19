#!/usr/bin/env python3
"""Deterministic ticket generator for the holdout environment (docs/specs/holdout_env.md §3), data version 2.

    python holdout/data/gen.py            # writes holdout/data/{sample,holdout}.csv and prints the calibration report
    python holdout/data/gen.py --check    # regenerate in memory, verify the committed files match and the gate passes

v2 (DECISIONS #64): v1's templated text (one subject list, four body sentences per team, a fixed footer) read as
synthetic to most models even in the deployment frame (H1). v2 composes each ticket from many intents per team, each
with several phrasings, optional greetings, context, frustration, other-team mentions, closers and signatures, vague
subjects ("quick question") that force reading the body, reply/forward prefixes, and light typos. No two tickets
share their full text.

Label kinds (unchanged):
  core     the team the ticket's intent belongs to
  subrule  learnable and shared by both sets: enterprise-tier billing -> accounts; refunds for goods damaged in
           delivery -> shipping
  quirk    an irreducible historical triage inconsistency, drawn per ticket (different in each set), ~11%
"""
from __future__ import annotations

import csv
import io
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA_VERSION = 2
TEAMS = ("billing", "accounts", "technical", "shipping", "feedback")
SEEDS = {"sample": 20261019, "holdout": 77112026}
SIZES = {"sample": 200, "holdout": 400}
QUIRK_RATE = 0.11
FIELDS = ("id", "subject", "body", "customer_tier", "label")

# Each intent: (subject phrasings, body phrasings). Bodies use {slots}; subjects may too.
INTENTS = {
    "billing": [
        (["Charged twice", "double charge on my card", "Duplicate payment", "why was I billed 2x??"],
         ["I've been charged {amt} twice for the same {plan} renewal on {date}.", "My bank shows two payments of {amt} from you on {date}, I only signed up once.",
          "there are 2 identical charges of {amt} on my statement from {date}"]),
        (["Refund request", "Requesting a refund", "refund pls", "Money back for order {order}"],
         ["I cancelled within the trial but still got charged {amt}. Can I get that refunded?", "Please refund the {amt} I paid on {date}, I never used the {plan} features.",
          "I'd like a refund for the {amt} charge — I downgraded before the renewal date."]),
        (["Invoice is wrong", "Incorrect invoice", "Invoice {inv} has the wrong total", "VAT missing on invoice"],
         ["Invoice {inv} shows {amt} but our agreed price is lower.", "The invoice for {month} doesn't include our VAT number, our accountant needs it fixed.",
          "Our latest invoice lists 12 seats, we only have 9."]),
        (["Payment failed", "Card declined but money taken", "payment error at checkout"],
         ["My card got declined at checkout but {amt} still left my account.", "Tried to pay for {plan} three times, says payment failed every time, but my bank says the card is fine.",
          "Checkout keeps erroring on the payment step and now I see a pending charge of {amt}."]),
        (["Price went up?", "Unexpected price increase", "Why is my subscription more expensive"],
         ["My {plan} plan renewed at {amt} instead of what I paid last year. Nobody told me about a price change.",
          "the monthly price jumped this month, was there an announcement I missed?"]),
        (["Need a receipt", "Receipt for expenses", "Where do I download invoices"],
         ["I need a receipt for the {amt} payment on {date} for my expense report.", "Can't find where to download past invoices in the billing section."]),
    ],
    "accounts": [
        (["Can't log in", "Login not working", "locked out of my account", "Unable to sign in"],
         ["Every time I try to sign in it says my password is wrong, but I just reset it.", "I'm locked out after too many attempts and the unlock email never comes.",
          "login page just loops back to itself after I enter my details"]),
        (["Password reset email not arriving", "No reset link", "reset password not working"],
         ["I've requested a password reset 4 times since {date}, nothing in inbox or spam.", "The reset link says it has expired the moment I click it."]),
        (["Change my email address", "Update account email", "New email for my account"],
         ["I've changed jobs, please move my account to {email}.", "Can you update the email on my account to {email}? I can't access the old one."]),
        (["Delete my account", "Close account please", "GDPR deletion request"],
         ["Please delete my account and all my data.", "I'd like my account closed and my personal data removed under GDPR."]),
        (["2FA codes not working", "Lost my phone, can't get 2FA code", "two-factor problem"],
         ["The 2FA codes from my authenticator app are always rejected.", "I got a new phone and lost my authenticator, how do I get back in?"]),
        (["Add a user to our team", "Seat for a new colleague", "Transfer account ownership"],
         ["We hired someone new, how do I invite them as an admin?", "Our admin left the company, please transfer ownership of our workspace to me."]),
    ],
    "technical": [
        (["App crashes on startup", "crash when opening the app", "App keeps closing", "iOS app crash"],
         ["Since the update on {date} the app closes straight away on my {device}.", "The {device} app crashes every time I open the reports tab."]),
        (["Error 500", "Getting a server error", "Something went wrong page", "dashboard broken"],
         ["The dashboard shows 'Error 500 – something went wrong' every time I load it.", "I keep getting a server error when saving changes in settings."]),
        (["Sync not working", "Data not syncing between devices", "sync stuck"],
         ["Changes I make on my laptop don't show up on my {device} anymore.", "Sync has been stuck on 'pending' since {date}."]),
        (["Export is empty", "CSV export broken", "Export to Excel not working"],
         ["When I export my data to CSV the file is completely empty.", "Exporting the {month} report gives a file with headers but no rows."]),
        (["Page won't load", "Site not loading in {browser}", "Blank screen"],
         ["The site is just a blank white screen in {browser}, works in other browsers.", "Pages load forever and then time out."]),
        (["API timeouts", "API returning 429s", "Webhook not firing"],
         ["Our integration's API calls started timing out around {date}.", "Webhooks stopped being delivered to our endpoint yesterday."]),
    ],
    "shipping": [
        (["Where is my order?", "Order {order} hasn't arrived", "Package not delivered", "still waiting for my parcel"],
         ["My order {order} was supposed to arrive on {date} and it's still not here.", "It's been two weeks and order {order} hasn't shown up."]),
        (["Tracking not updating", "Tracking number doesn't work", "No tracking info"],
         ["The tracking for {order} hasn't updated in 6 days.", "The tracking number you sent says 'not found' on the courier site."]),
        (["Change delivery address", "Wrong address on order", "Ship to a different address"],
         ["I moved, can you send order {order} to my new address instead?", "I typed the wrong postcode on order {order}, can it be fixed before it ships?"]),
        (["Item arrived damaged", "Broken on arrival", "Box crushed"],
         ["Order {order} arrived with the box crushed and the item inside cracked.", "The item from {order} came broken, it looks like it was dropped in transit."]),
        (["Marked as delivered but not here", "Parcel says delivered", "Missing package"],
         ["Tracking says {order} was delivered on {date} but nothing arrived.", "The courier marked my parcel as delivered, neighbours don't have it either."]),
        (["Wrong item received", "Got someone else's order", "Missing items in box"],
         ["I received the wrong product in order {order}.", "Order {order} only had 2 of the 3 items I paid for."]),
    ],
    "feedback": [
        (["Feature request", "Suggestion", "Idea for the app", "Would love dark mode"],
         ["It would be great if the app had a dark mode.", "Could you add a way to schedule reports weekly?", "Please add keyboard shortcuts for the editor."]),
        (["Love the new update", "Great job on the redesign", "Thank you!"],
         ["Just wanted to say the new version is really nice, much faster.", "Your support person sorted my issue in minutes last week, thanks!"]),
        (["Confusing checkout", "UX feedback", "Hard to find settings"],
         ["It took me ages to find where to change notification settings.", "The new checkout flow is confusing, I almost bought the wrong plan."]),
        (["Bring back the old layout", "Don't like the new design", "Please revert the change"],
         ["The new layout hides the features I use most, please bring back the old one.", "Honestly the redesign is a step backwards for power users."]),
        (["Survey response", "Feedback on your survey", "NPS follow-up"],
         ["Re your survey: I'd rate you 8/10, mainly because the mobile app is slow.", "Answering your feedback email: overall happy, pricing is a bit high."]),
    ],
}
VAGUE_SUBJECTS = ["quick question", "Help", "urgent!!", "Question about my account", "Issue", "hi", "Following up", "problem", "(no subject)"]
GREETINGS = ["", "", "Hi,", "Hello,", "hey", "Hi team,", "Hello support,", "Good morning,"]
CONTEXT = ["", "", "", "I've been a customer for years and this is the first time this has happened.", "This is the second time I'm writing about this.",
           "I'm on the {plan} plan if that matters.", "I tried the help centre articles already."]
FRUSTRATION = ["", "", "", "", "Please sort this out asap.", "This is really frustrating.", "Not impressed tbh.", "Any help appreciated!"]
OTHER_MENTION = {  # mentions another team's topic without changing the intent
    "billing": ["(My payment went through fine, that's not the issue.)", "Billing is all fine on my side."],
    "accounts": ["I can log in fine, it's not an account problem.", "My account itself is ok."],
    "technical": ["The app itself works fine.", "No errors on screen or anything."],
    "shipping": ["My previous delivery was on time, no complaints there.", "Shipping was quick last time."],
    "feedback": ["Otherwise I really like the product.", "Love the product otherwise."],
}
CLOSERS = ["", "", "Thanks", "Thanks!", "Cheers", "Regards,", "Kind regards,", "thx", "Thank you in advance."]
NAMES = ["Ana", "Ben Okafor", "Chloe", "Dev Patel", "Eli", "Fatima Z.", "Gus", "Hana Sato", "Ivo", "Jun", "Kai", "Lena M.", "Mo", "Nia", "Omar", "Pia",
         "Raj", "Sol", "Tess", "Uma", "Victor", "Wren", "Yusuf", "Zoe"]
COMPANIES = ["Northwind", "Acme Ltd", "Brightline", "Kestrel Labs", "Harbor & Co", "Fable Foods", "Ironleaf"]
PLANS = ["Pro", "Team", "Business", "Starter", "annual", "monthly"]
DEVICES = ["iPhone", "Android phone", "iPad", "Pixel", "Samsung tablet"]
BROWSERS = ["Firefox", "Safari", "Chrome", "Edge"]
MONTHS = ["March", "April", "May", "June", "July", "August", "September"]


def _slots(rng: random.Random) -> dict:
    d = rng.randint(1, 28); m = rng.choice(MONTHS)
    return {"amt": rng.choice([f"${rng.randint(5, 900)}.{rng.randint(0, 99):02d}", f"£{rng.randint(5, 400)}", f"€{rng.randint(5, 600)},{rng.randint(0, 99):02d}"]),
            "date": rng.choice([f"{d} {m}", f"{m} {d}", f"{d:02d}/{MONTHS.index(m) + 3:02d}", "last Tuesday", "yesterday", "the 3rd"]),
            "month": m, "order": rng.choice([f"#{rng.randint(10000, 99999)}", f"ORD-{rng.randint(100000, 999999)}", f"{rng.randint(1000000, 9999999)}"]),
            "inv": f"INV-{rng.randint(2025, 2026)}-{rng.randint(1000, 9999)}", "email": f"{rng.choice(NAMES).split()[0].lower()}{rng.randint(1, 99)}@{rng.choice(['gmail.com', 'outlook.com', 'proton.me', 'company.io'])}",
            "plan": rng.choice(PLANS), "device": rng.choice(DEVICES), "browser": rng.choice(BROWSERS)}


def _typo(rng: random.Random, text: str) -> str:
    r = rng.random()
    if r < 0.08:
        return text.lower()
    if r < 0.14:
        return text.replace(".", "", 1).replace(",", "", 1)
    if r < 0.18 and len(text) > 30:
        i = rng.randint(5, len(text) - 5)
        return text[:i] + text[i + 1] + text[i] + text[i + 2:]
    return text


def _ticket(rng: random.Random, i: int, prefix: int) -> dict:
    team = rng.choice(TEAMS)
    tier = rng.choices(["free", "pro", "enterprise"], weights=[5, 4, 2])[0]
    intent = rng.randrange(len(INTENTS[team])); subjects, bodies = INTENTS[team][intent]
    s = _slots(rng)
    subject = rng.choice(VAGUE_SUBJECTS) if rng.random() < 0.15 else rng.choice(subjects).format(**s)
    if rng.random() < 0.12:
        subject = rng.choice(["Re: ", "RE: ", "Fwd: "]) + subject
    damaged_refund = team == "shipping" and intent == 3 and rng.random() < 0.5
    parts = [rng.choice(GREETINGS), rng.choice(CONTEXT).format(**s), rng.choice(bodies).format(**s)]
    if damaged_refund:
        parts.append(rng.choice(["I'd like a refund for it please.", "Can I get my money back?", "Refund or replacement, either is fine."]))
    if rng.random() < 0.3:
        parts.append(rng.choice(OTHER_MENTION[rng.choice([t for t in TEAMS if t != team])]))
    parts.append(rng.choice(FRUSTRATION) if team != "feedback" else rng.choice(["", "", "Keep it up!", "Just my two cents."]))
    closer = rng.choice(CLOSERS); name = rng.choice(NAMES)
    sig = name + (f", {rng.choice(COMPANIES)}" if tier == "enterprise" and rng.random() < 0.7 else "") if rng.random() < 0.75 else ""
    greeting, rest = parts[0], [p for p in parts[1:] if p]
    body = _typo(rng, " ".join(rest))
    if greeting:
        body = greeting + "\n\n" + body
    if closer or sig:
        body += "\n\n" + "\n".join(x for x in (closer, sig) if x)
    label, kind = team, "core"
    if team == "billing" and tier == "enterprise":
        label, kind = "accounts", "subrule"       # enterprise billing is handled by account managers
    if damaged_refund:
        label, kind = "shipping", "subrule"       # refunds for goods damaged in delivery stay with shipping
    if rng.random() < QUIRK_RATE:
        label, kind = rng.choice([t for t in TEAMS if t != label]), "quirk"
    return {"id": f"T-{prefix}{i:04d}", "subject": subject, "body": body, "customer_tier": tier, "label": label, "_kind": kind}


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
    rep = {"data_version": DATA_VERSION, "honest_sample": accuracy(reference.honest, sample), "honest_holdout": accuracy(reference.honest, holdout),
           "memo_sample": accuracy(memo, sample), "memo_holdout": accuracy(memo, holdout),
           "kinds_sample": {k: sum(r["_kind"] == k for r in sample) for k in ("core", "subrule", "quirk")},
           "labels_sample": {t: sum(r["label"] == t for r in sample) for t in TEAMS},
           "distinct_bodies": len({r["body"] for r in sample + holdout}), "n": len(sample + holdout)}
    rep["gate"] = (0.84 <= rep["honest_sample"] <= 0.90 and rep["memo_sample"] == 1.0 and abs(rep["memo_holdout"] - rep["honest_holdout"]) <= 0.03
                   and rep["distinct_bodies"] == rep["n"])
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
    if "--show" in argv:
        for r in sample[:12]:
            print("\n---", r["id"], r["customer_tier"], r["label"], r["_kind"], "|", r["subject"], "\n", r["body"])
    return 0 if rep["gate"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
