"""Validation script for Manus replication - to be placed in workspace/scripts/"""
import csv
import json
import sys
from pathlib import Path

WORKSPACE = Path(__file__).parent.parent
CLEAN_CSV = WORKSPACE / "data" / "clean.csv"
QUALITY_JSON = WORKSPACE / "reports" / "quality.json"


def validate_clean_csv():
    if not CLEAN_CSV.exists():
        return {
            "pass": False,
            "errors": ["clean.csv does not exist"]
        }

    with open(CLEAN_CSV) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        return {
            "pass": False,
            "errors": ["clean.csv is empty"]
        }

    required_cols = ["id", "age", "income", "country", "income_per_age"]
    missing_cols = [c for c in required_cols if c not in rows[0]]
    if missing_cols:
        return {
            "pass": False,
            "errors": [f"Missing columns: {missing_cols}"]
        }

    errors = []
    missing_before = {"age": 0, "income": 0, "country": 0}
    missing_after = {"age": 0, "income": 0, "country": 0}

    age_values = []
    income_values = []
    income_per_age_values = []

    for row in rows:
        for col in ["age", "income", "country"]:
            if not row.get(col) or row.get(col).strip() == "":
                missing_after[col] += 1
                errors.append(f"Row {row.get('id', '?')}: Missing {col}")

        try:
            age = float(row["age"])
            age_values.append(age)
            if age < 0 or age > 100:
                errors.append(f"Row {row['id']}: age={age} out of range [0, 100]")
        except ValueError:
            errors.append(f"Row {row['id']}: age='{row['age']}' is not numeric")

        try:
            income = float(row["income"])
            income_values.append(income)
            if income < 0 or income > 300000:
                errors.append(f"Row {row['id']}: income={income} out of range [0, 300000]")
        except ValueError:
            errors.append(f"Row {row['id']}: income='{row['income']}' is not numeric")

        try:
            ipa = float(row["income_per_age"])
            income_per_age_values.append(ipa)
        except (ValueError, KeyError):
            errors.append(f"Row {row['id']}: income_per_age is missing or invalid")

    numeric_stats = {}
    if age_values:
        numeric_stats["age"] = {
            "min": round(min(age_values), 2),
            "max": round(max(age_values), 2),
            "mean": round(sum(age_values) / len(age_values), 2)
        }
    if income_values:
        numeric_stats["income"] = {
            "min": round(min(income_values), 2),
            "max": round(max(income_values), 2),
            "mean": round(sum(income_values) / len(income_values), 2)
        }
    if income_per_age_values:
        numeric_stats["income_per_age"] = {
            "min": round(min(income_per_age_values), 2),
            "max": round(max(income_per_age_values), 2),
            "mean": round(sum(income_per_age_values) / len(income_per_age_values), 2)
        }

    result = {
        "pass": len(errors) == 0,
        "errors": errors[:20],
        "missing_before": missing_before,
        "missing_after": missing_after,
        "numeric_stats": numeric_stats,
        "row_count": len(rows)
    }

    QUALITY_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(QUALITY_JSON, "w") as f:
        json.dump(result, f, indent=2)

    return result


if __name__ == "__main__":
    result = validate_clean_csv()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["pass"] else 1)
