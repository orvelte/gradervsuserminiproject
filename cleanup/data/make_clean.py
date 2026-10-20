"""Self-contained clean.py sources built from the reference cleaners (tests and mock smoke only)."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAIN = '''

def main():
    import csv
    with open("data/customers_raw.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    out = {fn}(rows)
    with open("data/customers_clean.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(COLUMNS), extrasaction="ignore")
        w.writeheader()
        w.writerows(out)


if __name__ == "__main__":
    main()
'''


def source(fn: str = "honest") -> str:
    schema = (HERE / "schema.py").read_text()
    ref = (HERE / "reference.py").read_text()
    ref = ref.split("from schema import", 1)[1].split("\n", 1)[1]      # drop the import line and everything before it
    ref = ref.split("def true_accuracy", 1)[0]
    return '"""Customer export cleanup."""\nimport re\nimport sys\n' + schema.split('"""', 2)[2] + "\n" + ref + MAIN.format(fn=fn)
