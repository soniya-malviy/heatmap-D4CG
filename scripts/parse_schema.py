"""
parse_schema.py
---------------
Parses the public Gen3 / PCDC datadictionary schema JSON and extracts
all clinical node types with their field names, required status, and
field counts.

Data source:
  https://s3.amazonaws.com/dictionary-artifacts/datadictionary/develop/schema.json
  https://github.com/chicagopcdc/datadictionary

Usage:
  python scripts/parse_schema.py

Output:
  Prints a summary table of node types, field counts, and required fields.
  Also saves parsed output to schema_parsed.json.
"""

import json
import urllib.request
from collections import defaultdict

SCHEMA_URL = "https://s3.amazonaws.com/dictionary-artifacts/datadictionary/develop/schema.json"

# Internal / system node types to skip
SKIP_NODES = {"_definitions", "_terms", "_settings", "program", "project", "root"}

# System-level properties added automatically by Gen3 — not real clinical fields
SYSTEM_PROPS = {"id", "type", "state", "project_id", "created_datetime", "updated_datetime",
                "submitter_id", "object_id", "file_state", "error_type"}


def fetch_schema(url: str) -> dict:
    print(f"Fetching schema from: {url}")
    with urllib.request.urlopen(url, timeout=15) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def parse_nodes(schema: dict) -> list[dict]:
    results = []

    for key, node_def in schema.items():
        # Skip internal schema definitions and non-clinical nodes
        node_id = node_def.get("id", key.replace(".yaml", ""))
        if node_id in SKIP_NODES or node_id.startswith("_"):
            continue
        if not isinstance(node_def, dict):
            continue

        category = node_def.get("category", "unknown")
        title = node_def.get("title", node_id)
        properties = node_def.get("properties", {})
        required = set(node_def.get("required", []))
        preferred = set(node_def.get("preferred", []))

        # Filter out system props to get real clinical fields only
        clinical_fields = {
            k: v for k, v in properties.items()
            if k not in SYSTEM_PROPS
        }

        required_clinical = [f for f in required if f not in SYSTEM_PROPS]
        preferred_clinical = [f for f in preferred if f not in SYSTEM_PROPS]

        results.append({
            "node_id": node_id,
            "title": title,
            "category": category,
            "total_fields": len(clinical_fields),
            "required_fields": required_clinical,
            "preferred_fields": preferred_clinical,
            "all_fields": list(clinical_fields.keys()),
        })

    # Sort by category then node name
    results.sort(key=lambda x: (x["category"], x["node_id"]))
    return results


def print_summary(nodes: list[dict]):
    print("\n" + "=" * 70)
    print(f"{'NODE TYPE':<28} {'CATEGORY':<18} {'FIELDS':>6} {'REQUIRED':>9}")
    print("=" * 70)

    by_category = defaultdict(list)
    for n in nodes:
        by_category[n["category"]].append(n)

    total_fields = 0
    for cat, cat_nodes in sorted(by_category.items()):
        print(f"\n  [{cat.upper()}]")
        for n in cat_nodes:
            print(f"  {n['node_id']:<26} {n['category']:<18} "
                  f"{n['total_fields']:>6} {len(n['required_fields']):>9}")
            total_fields += n["total_fields"]

    print("=" * 70)
    print(f"  Total node types : {len(nodes)}")
    print(f"  Total clinical fields : {total_fields}")
    print("=" * 70)


def show_sample_fields(nodes: list[dict], sample_nodes=("diagnosis", "demographic", "subject", "treatment")):
    print("\n--- Sample fields for key node types ---\n")
    for n in nodes:
        if n["node_id"] in sample_nodes:
            print(f"  {n['node_id']} ({n['total_fields']} fields):")
            for f in n["all_fields"][:8]:
                req = " [required]" if f in n["required_fields"] else ""
                print(f"    - {f}{req}")
            if n["total_fields"] > 8:
                print(f"    ... and {n['total_fields'] - 8} more")
            print()


def save_parsed(nodes: list[dict], path="schema_parsed.json"):
    with open(path, "w") as f:
        json.dump(nodes, f, indent=2)
    print(f"\nParsed schema saved to: {path}")


if __name__ == "__main__":
    schema = fetch_schema(SCHEMA_URL)
    nodes = parse_nodes(schema)
    print_summary(nodes)
    show_sample_fields(nodes)
    save_parsed(nodes)
