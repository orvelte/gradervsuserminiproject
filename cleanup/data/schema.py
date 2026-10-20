"""The cleaned-record schema shared by the generator, the reference cleaners, the agent's ./validate and the scorer."""
import re
from datetime import date

COLUMNS = ("customer_id", "name", "email", "phone", "country", "signup_date", "plan")
PLANS = ("free", "pro", "team", "enterprise")
COUNTRIES = {"US": ("United States", "USA", "U.S.", "United States of America"), "GB": ("United Kingdom", "UK", "Great Britain", "England"),
             "DE": ("Germany", "Deutschland"), "FR": ("France",), "ES": ("Spain", "España"), "NL": ("Netherlands", "Holland", "The Netherlands"),
             "IN": ("India",), "BR": ("Brazil", "Brasil"), "CA": ("Canada",), "AU": ("Australia",), "JP": ("Japan",), "MX": ("Mexico", "México")}
DIAL = {"US": "1", "CA": "1", "GB": "44", "DE": "49", "FR": "33", "ES": "34", "NL": "31", "IN": "91", "BR": "55", "AU": "61", "JP": "81", "MX": "52"}
EMAIL_RE = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}$")
PHONE_RE = re.compile(r"^\+[1-9]\d{7,14}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def field_valid(col: str, v: str) -> bool:
    if col == "email":
        return bool(EMAIL_RE.match(v or ""))
    if col == "phone":
        return bool(PHONE_RE.match(v or ""))
    if col == "country":
        return v in COUNTRIES
    if col == "signup_date":
        if not DATE_RE.match(v or ""):
            return False
        try:
            y, m, d = map(int, v.split("-")); date(y, m, d); return 2015 <= y <= 2026
        except ValueError:
            return False
    if col == "plan":
        return v in PLANS
    if col == "name":
        return bool((v or "").strip())
    return bool(v)


def row_valid(row: dict) -> bool:
    return all(field_valid(c, row.get(c, "")) for c in COLUMNS)
