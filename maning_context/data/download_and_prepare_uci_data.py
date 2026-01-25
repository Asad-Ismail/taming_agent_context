"""Download and prepare UCI Adult Income Dataset for Manus replication."""
import csv
import random
import urllib.request
from pathlib import Path
from io import StringIO

WORKSPACE = Path(__file__).parent.parent / "workspace"
DATA_URL = "https://archive.ics.uci.edu/ml/machine-learning-databases/adult/adult.data"


def download_uci_data():
    response = urllib.request.urlopen(DATA_URL)
    data = response.read().decode("utf-8")
    return data


def transform_to_schema(raw_data: str) -> list[dict]:
    reader = csv.reader(StringIO(raw_data))
    rows = []
    for i, row in enumerate(reader):
        if len(row) < 15:
            continue
        age = int(row[0].strip())
        workclass = row[1].strip()
        fnlwgt = row[2].strip()
        education = row[3].strip()
        education_num = row[4].strip()
        marital_status = row[5].strip()
        occupation = row[6].strip()
        relationship = row[7].strip()
        race = row[8].strip()
        sex = row[9].strip()
        capital_gain = row[10].strip()
        capital_loss = row[11].strip()
        hours_per_week = row[12].strip()
        native_country = row[13].strip()
        income_str = row[14].strip()

        income_value = 80000 if ">50K" in income_str else 30000

        rows.append({
            "id": i,
            "age": age,
            "income": income_value,
            "country": native_country if native_country != "?" else "Unknown"
        })

    return rows


def introduce_data_quality_issues(rows: list[dict]) -> list[dict]:
    random.seed(42)

    for row in rows:
        if random.random() < 0.10:
            row["age"] = ""
        if random.random() < 0.10:
            row["income"] = ""
        if random.random() < 0.05:
            row["country"] = ""

    for i in range(min(10, len(rows))):
        if random.random() < 0.5:
            rows[i]["age"] = 101 + random.randint(0, 20)
        if random.random() < 0.3:
            rows[i]["income"] = 301000 + random.randint(0, 50000)

    return rows


def write_csv(rows: list[dict], output_path: Path):
    with open(output_path, "w") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "age", "income", "country"])
        writer.writeheader()
        writer.writerows(rows)


def main():
    output_path = WORKSPACE / "data" / "raw.csv"
    if output_path.exists():
        print(f"Data already exists at {output_path}")
        return

    print("Downloading UCI Adult Income Dataset...")
    raw_data = download_uci_data()

    print("Transforming to required schema...")
    rows = transform_to_schema(raw_data)
    print(f"Processed {len(rows)} rows")

    print("Introducing data quality issues...")
    rows = introduce_data_quality_issues(rows)

    write_csv(rows, output_path)

    print(f"Created {output_path}")
    print(f"Total rows: {len(rows)}")
    print("\nFirst 10 rows:")
    with open(output_path) as f:
        for i, line in enumerate(f):
            if i >= 11:
                break
            print(line.strip())


if __name__ == "__main__":
    main()
