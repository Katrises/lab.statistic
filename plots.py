"""Графики в исходных единицах измерений."""

from itertools import combinations

import matplotlib.pyplot as plt
from matplotlib.ticker import FormatStrFormatter
import numpy as np

from .analysis import (COLUMNS, NAMES, UNITS, COLORS, GROUP_COLORS,
                       criterion_groups, ecdf_at, frequency_table)


FULL = "#253849"
BASE = "#817b83"
SELECTED = "#73506d"


def _x_axis(ax, column):
    ax.set_xlabel(f"{NAMES[column]}, {UNITS[column]}")
    if column == "density":
        ax.xaxis.set_major_formatter(FormatStrFormatter("%.3f"))
    ax.grid(alpha=.18)
    ax.spines[["top", "right"]].set_visible(False)


def _step(ax, sample, left, right, **style):
    freq = frequency_table(sample)
    ax.step(np.r_[left, freq["x"], right], np.r_[0, freq["F(x)"], 1],
            where="post", **style)


def plot_quality_groups(wine):
    groups = criterion_groups(wine)
    fig, axes = plt.subplots(3, 1, figsize=(8.2, 8.2), constrained_layout=True)
    for ax, c in zip(axes, COLUMNS):
        x = wine[c]
        pad = .025 * (x.max() - x.min())
        left, right = x.min() - pad, x.max() + pad
        _step(ax, x, left, right, label="Все строки", color=FULL, linewidth=2)
        for name, part in groups.items():
            _step(ax, part[c], left, right, label=f"Оценка {name}",
                  color=GROUP_COLORS[name], linewidth=1.45, alpha=.9)
        ax.set(xlim=(left, right), ylim=(-.02, 1.02), ylabel="F(x)", title=NAMES[c])
        _x_axis(ax, c)
    axes[0].legend(loc="upper left", ncols=2, frameon=False, fontsize=9)
    return fig


def plot_outliers(wine):
    fig, axes = plt.subplots(3, 1, figsize=(8.2, 5.1), constrained_layout=True)
    for ax, c in zip(axes, COLUMNS):
        x = wine[c]
        q1, q3 = x.quantile([.25, .75])
        iqr = q3 - q1
        ax.boxplot(x, orientation="horizontal", whis=1.5, patch_artist=True,
                   boxprops={"facecolor": COLORS[c], "alpha": .55},
                   medianprops={"color": FULL, "linewidth": 2},
                   flierprops={"marker": ".", "markeredgecolor": COLORS[c], "alpha": .65})
        left, right = ax.get_xlim()
        for k, color, style in [(1.5, "#636e75", "--"), (3, "#af622e", ":")]:
            for boundary in (q1 - k * iqr, q3 + k * iqr):
                if left <= boundary <= right:
                    ax.axvline(boundary, color=color, linestyle=style, linewidth=1.2)
        ax.set(yticks=[], title=NAMES[c])
        _x_axis(ax, c)
    return fig


def plot_fit(wine, column, report):
    x = wine[column].to_numpy()
    pad = .025 * np.ptp(x)
    left, right = x.min() - pad, x.max() + pad
    grid = np.linspace(left, right, 1100)
    tail_panel = column == "residual sugar"
    fig, axes = plt.subplots(3 if tail_panel else 2, 1,
                             figsize=(8.2, 8.5 if tail_panel else 5.7),
                             constrained_layout=True)
    baseline = report.baseline.distribution
    selected = report.selected.distribution
    curves = [
        (baseline, BASE, "--", report.baseline.label),
        (selected, SELECTED, "-", report.selected.label),
    ]
    iqr = np.diff(np.quantile(x, [.25, .75]))[0]
    bins = int(np.clip(np.ceil(np.ptp(x) / (2 * iqr * len(x)**(-1/3))), 12, 60))
    axes[0].hist(x, bins=bins, density=True, color=COLORS[column], alpha=.38,
                 label="Измерения")
    for model, color, style, label in curves:
        axes[0].plot(grid, model.pdf(grid), color=color, linestyle=style,
                     linewidth=1.8, label=label)
        axes[1].plot(grid, model.cdf(grid), color=color, linestyle=style,
                     linewidth=1.8, label=label)
    _step(axes[1], x, left, right, color=FULL, linewidth=1.5, label="Эмпирическая CDF")
    axes[0].set(title=f"{NAMES[column]}: гистограмма и модели", ylabel="Плотность вероятности")
    axes[1].set(title="Сравнение с эмпирической CDF", ylabel="F(x)", ylim=(-.02, 1.02))
    for ax in axes[:2]:
        ax.set_xlim(left, right)
        ax.legend(frameon=False, fontsize=9)
        _x_axis(ax, column)

    if tail_panel:
        ax = axes[2]
        start = np.quantile(x, .8)
        freq = frequency_table(x)
        data_x = np.r_[start, freq.loc[freq["x"] > start, "x"].to_numpy()]
        survival = 1 - ecdf_at(x, data_x)
        ax.stairs(survival[:-1], data_x, baseline=None, color=FULL,
                  linewidth=1.5, label="Эмпирический хвост")
        tail_grid = grid[grid >= start]
        for model, color, style, label in curves:
            ax.plot(tail_grid, 1 - model.cdf(tail_grid), color=color,
                    linestyle=style, linewidth=1.8, label=label)
        ax.set(xlim=(start, right), yscale="log", ylim=(3e-4, .3),
               title="Правый хвост: вероятность превысить x", ylabel="1 − F(x)")
        _x_axis(ax, column)
        ax.legend(frameon=False, fontsize=9)
    return fig


def plot_dependence(wine):
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.6), constrained_layout=True)
    for ax, (a, b) in zip(axes, combinations(COLUMNS, 2)):
        ax.scatter(wine[a], wine[b], s=8, alpha=.28, color="#486578", edgecolors="none")
        ax.set_ylabel(f"{NAMES[b]}, {UNITS[b]}")
        if b == "density":
            ax.yaxis.set_major_formatter(FormatStrFormatter("%.3f"))
        _x_axis(ax, a)
    return fig
