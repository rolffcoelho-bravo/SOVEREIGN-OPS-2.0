#!/usr/bin/env python3
"""Generate publication-quality figures for SOVEREIGN-OPS-2.0.

Produces SVG and PNG figures suitable for:
- The project dashboard (docs/ folder)
- The technical report
- The scientific paper

All figures use a cohesive colour scheme with accessibility in mind
(WCAG-safe contrasts, colorblind-friendly palettes).

Usage:
    python -I scripts/generate_figures.py [--output-dir docs/figures]
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Final, TypedDict

import matplotlib
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.figure import Figure

matplotlib.use("Agg")  # headless rendering

# ---------------------------------------------------------------------------
# Design system — cohesive palette
# ---------------------------------------------------------------------------

# Primary palette (colorblind-safe, WCAG AA compliant)
SLATE: Final = "#1e293b"
STONE_600: Final = "#57534e"
BLUE_600: Final = "#2563eb"
BLUE_400: Final = "#60a5fa"
EMERALD_500: Final = "#10b981"
AMBER_500: Final = "#f59e0b"
ROSE_500: Final = "#f43f5e"
VIOLET_500: Final = "#8b5cf6"
CYAN_500: Final = "#06b6d4"
GRAY_100: Final = "#f3f4f6"
GRAY_200: Final = "#e5e7eb"
GRAY_300: Final = "#d1d5db"
GRAY_400: Final = "#9ca3af"
GRAY_700: Final = "#374151"
WHITE: Final = "#ffffff"

# Categorical palette (8 hues, colorblind-safe ordering)
CAT_PALETTE: Final = [
    BLUE_600,
    EMERALD_500,
    AMBER_500,
    ROSE_500,
    VIOLET_500,
    CYAN_500,
    "#d97706",
    "#6366f1",
]

# Sequential palette (blue ramp)
SEQ_BLUES: Final = ["#dbeafe", "#bfdbfe", "#93c5fd", "#60a5fa", "#3b82f6", "#2563eb", "#1d4ed8"]


def _apply_style(fig: Figure) -> None:
    """Apply publication typography and layout to a figure."""
    for ax in fig.get_axes():
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color(GRAY_300)
        ax.spines["bottom"].set_color(GRAY_300)
        ax.tick_params(colors=GRAY_700, labelsize=9)
        ax.xaxis.label.set_color(GRAY_700)
        ax.yaxis.label.set_color(GRAY_700)
        ax.title.set_color(SLATE)


def _save(fig: Figure, name: str, output_dir: Path) -> None:
    """Save figure as both SVG (web) and PNG (print)."""
    for fmt in ("svg", "png"):
        path = output_dir / f"{name}.{fmt}"
        fig.savefig(
            path,
            format=fmt,
            dpi=300,
            bbox_inches="tight",
            facecolor=WHITE,
            edgecolor="none",
        )
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 1: Gated Development Progress
# ---------------------------------------------------------------------------


def fig_gate_progress(output_dir: Path) -> None:
    """Horizontal bar chart showing gate progression with test counts."""
    gates = ["G0", "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9"]
    tests = [38, 72, 110, 169, 199, 365, 0, 0, 0, 0]
    status = ["COMPLETE"] * 5 + ["IN PROGRESS"] + ["PLANNED"] * 4
    colors = []
    for s in status:
        if s == "COMPLETE":
            colors.append(EMERALD_500)
        elif s == "IN PROGRESS":
            colors.append(BLUE_600)
        else:
            colors.append(GRAY_300)

    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.barh(
        gates[::-1],
        tests[::-1],
        color=colors[::-1],
        height=0.6,
        edgecolor=WHITE,
        linewidth=0.5,
    )

    # Annotate test counts
    for bar_obj, t, s in zip(bars, tests[::-1], status[::-1], strict=False):
        if t > 0:
            ax.text(
                bar_obj.get_width() + 5,
                bar_obj.get_y() + bar_obj.get_height() / 2,
                f"{t} tests" if s != "PLANNED" else "",
                va="center",
                ha="left",
                fontsize=9,
                color=GRAY_700,
                fontweight="medium",
            )
        if s == "PLANNED":
            ax.text(
                15,
                bar_obj.get_y() + bar_obj.get_height() / 2,
                "PLANNED",
                va="center",
                ha="left",
                fontsize=8,
                color=GRAY_400,
                style="italic",
            )

    ax.set_xlabel("Cumulative Test Count", fontsize=10, fontweight="medium")
    ax.set_title("DARP Gated Development Progress", fontsize=14, fontweight="bold", pad=15)
    ax.set_xlim(0, max(tests) * 1.2)

    # Legend
    legend_elements = [
        mpatches.Patch(facecolor=EMERALD_500, label="Complete"),
        mpatches.Patch(facecolor=BLUE_600, label="In Progress"),
        mpatches.Patch(facecolor=GRAY_300, label="Planned"),
    ]
    ax.legend(handles=legend_elements, loc="lower right", fontsize=9, frameon=False)

    _apply_style(fig)
    _save(fig, "gate_progress", output_dir)


# ---------------------------------------------------------------------------
# Figure 2: Test Growth Over Gates (area chart)
# ---------------------------------------------------------------------------


def fig_test_growth(output_dir: Path) -> None:
    """Stacked area showing test growth across gate milestones."""
    gates = ["G0", "G1", "G2", "G3", "G4", "G5"]
    total = [38, 72, 110, 169, 199, 365]
    added = [38, 34, 38, 59, 30, 166]

    fig, ax = plt.subplots(figsize=(10, 5))

    # Area fill
    ax.fill_between(range(len(gates)), total, alpha=0.15, color=BLUE_600)
    ax.plot(
        range(len(gates)),
        total,
        color=BLUE_600,
        linewidth=2.5,
        marker="o",
        markersize=8,
        zorder=5,
    )

    # Annotate each point
    for i, (t, a) in enumerate(zip(total, added, strict=False)):
        ax.annotate(
            f"{t}\n(+{a})",
            (i, t),
            textcoords="offset points",
            xytext=(0, 14),
            ha="center",
            fontsize=9,
            fontweight="bold",
            color=SLATE,
        )

    ax.set_xticks(range(len(gates)))
    ax.set_xticklabels(gates, fontsize=10, fontweight="medium")
    ax.set_ylabel("Cumulative Tests", fontsize=10, fontweight="medium")
    ax.set_title(
        "Test Suite Growth Across Development Gates",
        fontsize=14,
        fontweight="bold",
        pad=15,
    )
    ax.set_ylim(0, max(total) * 1.3)
    ax.grid(axis="y", alpha=0.3, linestyle="--")

    _apply_style(fig)
    _save(fig, "test_growth", output_dir)


# ---------------------------------------------------------------------------
# Figure 3: Source Architecture Treemap
# ---------------------------------------------------------------------------


class _CategoryInfo(TypedDict):
    modules: list[str]
    lines: int
    color: str


def fig_source_architecture(output_dir: Path) -> None:
    """Treemap-style horizontal bars showing codebase composition."""
    categories: dict[str, _CategoryInfo] = {
        "API & Parsers": {
            "modules": ["api", "edp_parser", "esa_parser"],
            "lines": 1584,
            "color": BLUE_600,
        },
        "ML & Statistics": {
            "modules": [
                "statistics",
                "detectors",
                "comparative",
                "evaluation",
                "pipeline",
                "decision_engine",
            ],
            "lines": 2380,
            "color": EMERALD_500,
        },
        "Contracts & Schemas": {
            "modules": ["contracts", "schemas"],
            "lines": 741,
            "color": VIOLET_500,
        },
        "Data Quality": {
            "modules": ["quality_profiler", "source_verifier", "splits"],
            "lines": 502,
            "color": AMBER_500,
        },
        "Research Modules": {
            "modules": [
                "edp_source_audit",
                "edp_view_comparison",
                "edp_exposure",
                "edp_source_schemas",
                "edp_acquisition",
                "edp_events",
                "edp_duplicates",
                "edp_version_audit",
                "esa_acquisition",
            ],
            "lines": 1135,
            "color": CYAN_500,
        },
        "Infrastructure": {
            "modules": ["adapters", "audit", "__init__"],
            "lines": 69,
            "color": GRAY_400,
        },
    }

    total_lines = sum(c["lines"] for c in categories.values())

    fig, ax = plt.subplots(figsize=(12, 5))
    names = list(categories.keys())
    lines: list[int] = [categories[n]["lines"] for n in names]
    colors: list[str] = [categories[n]["color"] for n in names]
    pcts = [loc / total_lines * 100 for loc in lines]

    bars = ax.barh(
        names[::-1],
        lines[::-1],
        color=colors[::-1],
        height=0.6,
        edgecolor=WHITE,
        linewidth=0.5,
    )

    for bar_obj, l_val, p in zip(bars, lines[::-1], pcts[::-1], strict=False):
        ax.text(
            bar_obj.get_width() + 20,
            bar_obj.get_y() + bar_obj.get_height() / 2,
            f"{l_val:,} lines ({p:.0f}%)",
            va="center",
            ha="left",
            fontsize=9,
            color=GRAY_700,
            fontweight="medium",
        )

    ax.set_xlabel("Lines of Code", fontsize=10, fontweight="medium")
    ax.set_title(
        f"Source Architecture — {total_lines:,} Total Lines Across {len(categories)} Domains",
        fontsize=14,
        fontweight="bold",
        pad=15,
    )
    ax.set_xlim(0, int(max(lines) * 1.4))

    _apply_style(fig)
    _save(fig, "source_architecture", output_dir)


# ---------------------------------------------------------------------------
# Figure 4: DARP Statistical Pipeline (Methodology Diagram)
# ---------------------------------------------------------------------------


def fig_methodology_pipeline(output_dir: Path) -> None:
    """Flow diagram of the 5-layer confirmatory evaluation pipeline."""
    fig, ax = plt.subplots(figsize=(14, 6))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 6)
    ax.axis("off")

    # Title
    ax.text(
        7,
        5.6,
        "DARP Confirmatory Evaluation Pipeline",
        ha="center",
        va="center",
        fontsize=16,
        fontweight="bold",
        color=SLATE,
    )

    # Pipeline boxes
    layers = [
        ("INPUT", "N detectors × K splits\n→ metric matrix", GRAY_400, 0.5),
        ("L1", "Pairwise Wilcoxon\nSigned-Rank Tests", BLUE_600, 2.8),
        ("L2", "Holm–Bonferroni\nFWER Correction", BLUE_400, 5.1),
        ("L3", "Cliff's δ Effect Size\n+ BCa Bootstrap CI", EMERALD_500, 7.4),
        ("L4", "Kendall's W\nRank Concordance", AMBER_500, 9.7),
        ("L5", "ComparisonReport\n(Immutable, SHA-256)", VIOLET_500, 12.0),
    ]

    box_w, box_h = 2.0, 1.4
    y_center = 2.8

    for label, desc, color, x_pos in layers:
        rect = mpatches.FancyBboxPatch(
            (x_pos, y_center - box_h / 2),
            box_w,
            box_h,
            boxstyle="round,pad=0.1",
            facecolor=color,
            edgecolor="none",
            alpha=0.9,
        )
        ax.add_patch(rect)
        ax.text(
            x_pos + box_w / 2,
            y_center + 0.15,
            label,
            ha="center",
            va="center",
            fontsize=11,
            fontweight="bold",
            color=WHITE,
        )
        ax.text(
            x_pos + box_w / 2,
            y_center - 0.3,
            desc,
            ha="center",
            va="center",
            fontsize=8,
            color=WHITE,
            style="italic",
            linespacing=1.4,
        )

    # Arrows between boxes
    for i in range(len(layers) - 1):
        x_start = layers[i][3] + box_w
        x_end = layers[i + 1][3]
        ax.annotate(
            "",
            xy=(x_end, y_center),
            xytext=(x_start, y_center),
            arrowprops={"arrowstyle": "->", "color": GRAY_400, "lw": 1.5},
        )

    # Annotations below
    annotations = [
        (1.5, 1.0, "Non-parametric\npaired comparison"),
        (3.8, 1.0, "Step-down\np-value correction"),
        (6.1, 1.0, "Practical\nsignificance"),
        (8.4, 1.0, "Stability across\nchronological splits"),
        (10.7, 1.0, "Cryptographic\nprovenance chain"),
    ]
    for x, y, text in annotations:
        ax.text(
            x + 1.0,
            y,
            text,
            ha="center",
            va="center",
            fontsize=8,
            color=GRAY_700,
            style="italic",
        )

    # Domain isolation badge
    badge = mpatches.FancyBboxPatch(
        (4.5, 4.4),
        5.0,
        0.6,
        boxstyle="round,pad=0.15",
        facecolor=ROSE_500,
        edgecolor="none",
        alpha=0.85,
    )
    ax.add_patch(badge)
    ax.text(
        7.0,
        4.7,
        "✦ Domain Isolation Enforced — Cross-domain comparison structurally prohibited",
        ha="center",
        va="center",
        fontsize=9,
        fontweight="bold",
        color=WHITE,
    )

    _apply_style(fig)
    _save(fig, "methodology_pipeline", output_dir)


# ---------------------------------------------------------------------------
# Figure 5: Decision Envelope Taxonomy
# ---------------------------------------------------------------------------


def fig_decision_envelope(output_dir: Path) -> None:
    """Radar/priority chart of the 5-outcome decision taxonomy."""
    outcomes = [
        ("BLOCK_DATA_INTEGRITY", "P1", ROSE_500, 100),
        ("DEGRADED_SERVICE", "P2", AMBER_500, 85),
        ("ABSTAIN_INSUFFICIENT", "P3", VIOLET_500, 70),
        ("SUPPORTED_ALERT", "P4", EMERALD_500, 55),
        ("INVESTIGATE", "P5", BLUE_600, 40),
    ]

    fig, ax = plt.subplots(figsize=(10, 6))

    for i, (_name, priority, color, severity) in enumerate(outcomes):
        ax.barh(
            i,
            severity,
            color=color,
            height=0.6,
            edgecolor=WHITE,
            linewidth=0.5,
            alpha=0.9,
        )
        ax.text(
            severity + 2,
            i,
            f"{severity}%",
            va="center",
            ha="left",
            fontsize=10,
            fontweight="bold",
            color=color,
        )
        ax.text(
            -2,
            i,
            f"{priority}",
            va="center",
            ha="right",
            fontsize=10,
            fontweight="bold",
            color=GRAY_700,
        )

    ax.set_yticks(range(len(outcomes)))
    ax.set_yticklabels([o[0].replace("_", "\n") for o in outcomes], fontsize=9, fontweight="medium")
    ax.set_xlabel("Decision Confidence Threshold (%)", fontsize=10, fontweight="medium")
    ax.set_title(
        "DARP Decision Envelope — 5-Outcome Taxonomy",
        fontsize=14,
        fontweight="bold",
        pad=15,
    )
    ax.set_xlim(0, 115)
    ax.invert_yaxis()

    _apply_style(fig)
    _save(fig, "decision_envelope", output_dir)


# ---------------------------------------------------------------------------
# Figure 6: CI Pipeline (Verification Chain)
# ---------------------------------------------------------------------------


def fig_ci_pipeline(output_dir: Path) -> None:
    """Linear flow of the CI verification stages."""
    stages = [
        ("ruff\ncheck", BLUE_600),
        ("ruff\nformat", BLUE_400),
        ("mypy\n--strict", VIOLET_500),
        ("pytest\n(365)", EMERALD_500),
        ("smoke\nHTTP", CYAN_500),
        ("secrets\nscan", AMBER_500),
        ("pip\naudit", ROSE_500),
    ]

    fig, ax = plt.subplots(figsize=(14, 3))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 3)
    ax.axis("off")

    ax.text(
        7,
        2.6,
        "Continuous Integration Pipeline",
        ha="center",
        va="center",
        fontsize=14,
        fontweight="bold",
        color=SLATE,
    )

    box_w, box_h = 1.5, 1.2
    spacing = 1.8
    start_x = (14 - len(stages) * spacing + (spacing - box_w)) / 2

    for i, (label, color) in enumerate(stages):
        x = start_x + i * spacing
        rect = mpatches.FancyBboxPatch(
            (x, 0.5),
            box_w,
            box_h,
            boxstyle="round,pad=0.1",
            facecolor=color,
            edgecolor="none",
            alpha=0.9,
        )
        ax.add_patch(rect)
        ax.text(
            x + box_w / 2,
            0.5 + box_h / 2,
            label,
            ha="center",
            va="center",
            fontsize=9,
            fontweight="bold",
            color=WHITE,
            linespacing=1.3,
        )

        if i < len(stages) - 1:
            ax.annotate(
                "",
                xy=(x + spacing, 0.5 + box_h / 2),
                xytext=(x + box_w, 0.5 + box_h / 2),
                arrowprops={"arrowstyle": "->", "color": GRAY_300, "lw": 1.5},
            )

    # Green checkmark at end
    ax.text(
        start_x + (len(stages) - 1) * spacing + box_w + 0.3,
        0.5 + box_h / 2,
        "✓",
        fontsize=20,
        color=EMERALD_500,
        fontweight="bold",
        va="center",
    )

    _save(fig, "ci_pipeline", output_dir)


# ---------------------------------------------------------------------------
# Figure 7: Statistical Methodology Comparison Matrix
# ---------------------------------------------------------------------------


def fig_methodology_comparison(output_dir: Path) -> None:
    """Heatmap comparing DARP statistical approach vs. standard practices."""
    methods = [
        "Significance Testing",
        "FWER Control",
        "Effect Size",
        "Bootstrap CI",
        "Rank Stability",
        "Cryptographic Provenance",
        "Domain Isolation",
        "Abstention-Aware Eval",
    ]
    approaches = ["Standard\nPractice", "Advanced\nML Eval", "DARP\n(This Work)"]

    # 0=absent, 1=partial, 2=full
    matrix = np.array(
        [
            [2, 2, 2],  # Significance
            [0, 1, 2],  # FWER
            [0, 2, 2],  # Effect size
            [0, 1, 2],  # Bootstrap CI
            [0, 0, 2],  # Rank stability
            [0, 0, 2],  # Crypto provenance
            [0, 0, 2],  # Domain isolation
            [0, 0, 2],  # Abstention-aware
        ]
    )

    fig, ax = plt.subplots(figsize=(8, 7))

    cmap = matplotlib.colors.ListedColormap([GRAY_200, AMBER_500, EMERALD_500])
    bounds = [-0.5, 0.5, 1.5, 2.5]
    norm = matplotlib.colors.BoundaryNorm(bounds, cmap.N)

    ax.imshow(matrix, cmap=cmap, norm=norm, aspect="auto")

    ax.set_xticks(range(len(approaches)))
    ax.set_xticklabels(approaches, fontsize=10, fontweight="medium")
    ax.set_yticks(range(len(methods)))
    ax.set_yticklabels(methods, fontsize=9)

    # Cell labels
    labels = {0: "—", 1: "partial", 2: "✓"}
    for i in range(len(methods)):
        for j in range(len(approaches)):
            color = WHITE if matrix[i, j] == 2 else (WHITE if matrix[i, j] == 1 else GRAY_400)
            ax.text(
                j,
                i,
                labels[matrix[i, j]],
                ha="center",
                va="center",
                fontsize=10,
                fontweight="bold",
                color=color,
            )

    ax.set_title(
        "Methodological Comparison — DARP vs. Standard Approaches",
        fontsize=13,
        fontweight="bold",
        pad=15,
    )

    # Legend
    legend_elements = [
        mpatches.Patch(facecolor=GRAY_200, label="Absent", edgecolor=GRAY_300),
        mpatches.Patch(facecolor=AMBER_500, label="Partial"),
        mpatches.Patch(facecolor=EMERALD_500, label="Full Support"),
    ]
    ax.legend(
        handles=legend_elements,
        loc="upper left",
        bbox_to_anchor=(0, -0.08),
        ncol=3,
        fontsize=9,
        frameon=False,
    )

    ax.tick_params(top=True, bottom=False, labeltop=True, labelbottom=False)
    for edge in ["top", "bottom", "left", "right"]:
        ax.spines[edge].set_visible(False)
    ax.set_xticks([x - 0.5 for x in range(1, len(approaches))], minor=True)
    ax.set_yticks([y - 0.5 for y in range(1, len(methods))], minor=True)
    ax.grid(which="minor", color=WHITE, linewidth=2)
    ax.tick_params(which="minor", size=0)

    fig.tight_layout()
    _save(fig, "methodology_comparison", output_dir)


# ---------------------------------------------------------------------------
# Figure 8: Donut — Module Architecture Distribution
# ---------------------------------------------------------------------------


def fig_module_donut(output_dir: Path) -> None:
    """Donut chart of codebase distribution by functional area."""
    labels = [
        "API & Parsers",
        "ML & Statistics",
        "Contracts & Schemas",
        "Research Modules",
        "Data Quality",
        "Infrastructure",
    ]
    sizes = [1584, 2380, 741, 1135, 502, 69]
    colors = [BLUE_600, EMERALD_500, VIOLET_500, CYAN_500, AMBER_500, GRAY_400]

    total = sum(sizes)

    fig, ax = plt.subplots(figsize=(8, 8))

    wedges, _texts, _autotexts = ax.pie(
        sizes,
        labels=None,
        colors=colors,
        autopct="",
        startangle=90,
        pctdistance=0.82,
        wedgeprops={
            "width": 0.35,
            "edgecolor": WHITE,
            "linewidth": 2,
        },
    )

    # Custom labels outside
    for wedge, label, size in zip(wedges, labels, sizes, strict=False):
        angle = (wedge.theta2 - wedge.theta1) / 2 + wedge.theta1
        x = math.cos(math.radians(angle))
        y = math.sin(math.radians(angle))
        ha = "left" if x >= 0 else "right"
        ax.annotate(
            f"{label}\n{size:,} lines ({size / total * 100:.0f}%)",
            xy=(0.68 * x, 0.68 * y),
            xytext=(1.15 * x, 1.15 * y),
            ha=ha,
            va="center",
            fontsize=9,
            fontweight="medium",
            color=GRAY_700,
            arrowprops={"arrowstyle": "-", "color": GRAY_300, "lw": 0.8},
        )

    # Center text
    ax.text(
        0,
        0.05,
        f"{total:,}",
        ha="center",
        va="center",
        fontsize=24,
        fontweight="bold",
        color=SLATE,
    )
    ax.text(
        0,
        -0.1,
        "total lines",
        ha="center",
        va="center",
        fontsize=10,
        color=GRAY_400,
    )

    ax.set_title("Source Architecture Distribution", fontsize=14, fontweight="bold", y=1.02)
    _save(fig, "module_donut", output_dir)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate SOVEREIGN-OPS figures")
    parser.add_argument("--output-dir", default="docs/figures", help="Output directory for figures")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    generators = [
        ("Gate progress", fig_gate_progress),
        ("Test growth", fig_test_growth),
        ("Source architecture", fig_source_architecture),
        ("Methodology pipeline", fig_methodology_pipeline),
        ("Decision envelope", fig_decision_envelope),
        ("CI pipeline", fig_ci_pipeline),
        ("Methodology comparison", fig_methodology_comparison),
        ("Module donut", fig_module_donut),
    ]

    for name, func in generators:
        print(f"  Generating {name}...", end=" ", flush=True)
        func(output_dir)
        print("done")

    print(f"\n  {len(generators)} figures saved to {output_dir}/")
    print("  Formats: SVG (web/dashboard) + PNG (print/report)")


if __name__ == "__main__":
    main()
