"""
mock_density.py
---------------
Generates a mock Data Density Heatmap using real node types and field names
from the chicagopcdc/datadictionary (Gen3 PCDC schema).

This script simulates the final GSoC tool's output — once connected to the
live GraphQL endpoint, real density scores replace the simulated ones here.

Density formula:
  density_score = (non_null_count / total_record_count) × 100

Usage:
  python scripts/mock_density.py

Output:
  public/heatmap_output.png
"""

import os
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import LinearSegmentedColormap

# ── Real node types + real field names from chicagopcdc/datadictionary ────────
# Source: https://github.com/chicagopcdc/datadictionary
# Source: https://s3.amazonaws.com/dictionary-artifacts/datadictionary/develop/schema.json

NODES = {
    "subject / case": [
        "age_at_enrollment", "race", "ethnicity", "sex",
        "vital_status", "disease_type", "primary_site",
        "days_to_birth", "index_date"
    ],
    "diagnosis": [
        "age_at_diagnosis", "primary_diagnosis", "morphology",
        "tumor_stage", "tumor_grade", "vital_status",
        "days_to_last_follow_up", "progression_or_recurrence",
        "classification_of_tumor"
    ],
    "demographic": [
        "gender", "race", "ethnicity",
        "year_of_birth", "year_of_death"
    ],
    "treatment": [
        "treatment_type", "treatment_intent_type",
        "days_to_treatment_start", "days_to_treatment_end",
        "therapeutic_agents", "treatment_outcome"
    ],
    "clinical_test": [
        "biomarker_name", "biomarker_result",
        "biomarker_test_method", "ldh_level_at_diagnosis",
        "ldh_normal_range_upper"
    ],
    "sample": [
        "sample_type", "tissue_type", "preservation_method",
        "days_to_collection", "initial_weight", "composition"
    ],
    "aliquot": [
        "analyte_type", "concentration",
        "aliquot_quantity", "aliquot_volume", "source_center"
    ],
    "follow_up": [
        "days_to_follow_up", "vital_status",
        "disease_response", "progression_or_recurrence",
        "days_to_progression"
    ],
}

# ── Simulated density scores (realistic for pediatric cancer clinical data) ───
# Required fields → 90–99%, preferred → 60–90%, optional → 25–65%
# In the real tool these come from live GraphQL aggregate queries.

DENSITY = {
    "subject / case":  [98, 87, 82, 99, 94, 91, 78, 61, 45],
    "diagnosis":       [96, 99, 72, 85, 68, 94, 88, 44, 55],
    "demographic":     [99, 87, 82, 95, 23],
    "treatment":       [88, 62, 79, 71, 55, 38],
    "clinical_test":   [99, 97, 95, 41, 38],
    "sample":          [94, 91, 67, 85, 32, 48],
    "aliquot":         [98, 72, 61, 58, 29],
    "follow_up":       [91, 88, 54, 47, 33],
}

# ── Colour map: red → orange → yellow → green ─────────────────────────────────
CMAP = LinearSegmentedColormap.from_list(
    "density",
    [
        (0.00, "#C00000"),
        (0.33, "#FF6B35"),
        (0.55, "#FFC000"),
        (0.75, "#92D050"),
        (1.00, "#375623"),
    ],
    N=256
)

BLUE     = "#1F4E79"
MED_BLUE = "#2E75B6"
GREEN    = "#375623"
DARK     = "#1A1A1A"
WHITE    = "#FFFFFF"


def draw_heatmap():
    node_names = list(NODES.keys())
    n_rows = len(node_names)
    max_cols = max(len(v) for v in DENSITY.values())

    fig, ax = plt.subplots(figsize=(15, 6.5))
    fig.patch.set_facecolor("#F8F9FA")
    ax.set_facecolor("#F8F9FA")

    for r, node in enumerate(node_names):
        fields = NODES[node]
        vals   = DENSITY[node]
        y_pos  = n_rows - r - 1

        for c in range(max_cols):
            x_pos = c
            if c < len(vals):
                val   = vals[c]
                color = CMAP(val / 100.0)

                # Cell box
                rect = mpatches.FancyBboxPatch(
                    (x_pos + 0.04, y_pos + 0.04), 0.92, 0.92,
                    boxstyle="round,pad=0.04",
                    linewidth=0, facecolor=color, zorder=2
                )
                ax.add_patch(rect)

                # Percentage label inside cell
                text_color = WHITE if val < 45 or val >= 80 else DARK
                ax.text(
                    x_pos + 0.5, y_pos + 0.5,
                    f"{val}%",
                    ha="center", va="center",
                    fontsize=7.8, fontweight="bold",
                    color=text_color, zorder=3
                )

                # Field name above first row only
                if r == 0:
                    label = fields[c].replace("_", "\n")
                    ax.text(
                        x_pos + 0.5, n_rows + 0.1,
                        label,
                        ha="center", va="bottom",
                        fontsize=5.8, color="#555555",
                    )
            else:
                # Grey placeholder for nodes with fewer fields
                rect = mpatches.FancyBboxPatch(
                    (x_pos + 0.04, y_pos + 0.04), 0.92, 0.92,
                    boxstyle="round,pad=0.04",
                    linewidth=0, facecolor="#E0E0E0", zorder=2
                )
                ax.add_patch(rect)

    # Y-axis node labels
    ax.set_yticks([n_rows - r - 0.5 for r in range(n_rows)])
    ax.set_yticklabels(node_names, fontsize=9.5, fontweight="bold", color=BLUE)
    ax.set_xticks([])
    ax.set_xlim(0, max_cols)
    ax.set_ylim(0, n_rows + 1.4)

    for spine in ax.spines.values():
        spine.set_visible(False)

    # Title
    ax.set_title(
        "Data Density Heatmap — PCDC Gen3 Node Types\n"
        "(Prototype · Node types & fields from chicagopcdc/datadictionary · "
        "Density scores simulated)",
        fontsize=10.5, fontweight="bold", color=BLUE,
        pad=12, loc="left"
    )

    # Legend
    legend_items = [
        mpatches.Patch(color="#C00000", label="0–33%   Sparse / Missing"),
        mpatches.Patch(color="#FFC000", label="34–66%  Partial"),
        mpatches.Patch(color="#375623", label="67–100% Well Populated"),
        mpatches.Patch(color="#E0E0E0", label="N/A     Field not in node"),
    ]
    ax.legend(
        handles=legend_items, loc="lower right",
        fontsize=8, framealpha=0.92,
        edgecolor="#CCCCCC",
        title="Density Score", title_fontsize=8.5
    )

    # Footer note
    fig.text(
        0.01, 0.005,
        "Density = (non-null record count / total record count) × 100%   |   "
        "Real tool queries live GraphQL endpoint via introspection + aggregation   |   "
        "Source: chicagopcdc/datadictionary (Gen3 schema)",
        fontsize=6.5, color="#888888", style="italic"
    )

    plt.tight_layout(rect=[0, 0.03, 1, 1])

    os.makedirs("public", exist_ok=True)
    out_path = "public/heatmap_output.png"
    plt.savefig(out_path, dpi=180, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    print(f"Heatmap saved to: {out_path}")
    plt.close()


if __name__ == "__main__":
    draw_heatmap()
