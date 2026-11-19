"""Графики для полного набора и проверки по блокам."""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import FormatStrFormatter

from lab01_tools.analysis import frequency_table
from .protocol import EVENT_THRESHOLD, LIMITS


DATA = "#26384a"
MIX = "#795372"
BASE = "#7e8b96"


def _cdf(ax, data, left, right, label, color, style="-"):
    f = frequency_table(data)
    ax.step(np.r_[left, f["x"], right], np.r_[0, f["F(x)"], 1], where="post",
            label=label, color=color, linestyle=style, linewidth=1.65)


def _density_axis(ax, left, right):
    ax.set(xlim=(left, right), xlabel="Плотность, г/см³")
    ax.xaxis.set_major_formatter(FormatStrFormatter("%.4f"))
    ax.grid(alpha=.19)
    ax.spines[["top", "right"]].set_visible(False)


def plot_full_density(real, draws):
    mix, normal = draws["mixture"], draws["normal"]
    left = min(real.min(), mix.min(), normal.min()) - .00015
    right = max(real.max(), mix.max(), normal.max()) + .00015
    bins = np.linspace(left, right, 33)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.2, 6.6), constrained_layout=True)
    ax1.hist(real, bins=bins, density=True, color=DATA, alpha=.42, label="Исходные записи")
    ax1.hist(mix, bins=bins, density=True, histtype="step", linewidth=2,
             color=MIX, label="Генерация смеси")
    ax1.hist(normal, bins=bins, density=True, histtype="step", linewidth=1.6,
             linestyle="--", color=BASE, label="Генерация одной нормальной")
    ax1.set(title="Полная таблица: одинаковые интервалы гистограмм",
            ylabel="Плотность вероятности, см³/г")
    ax1.legend(frameon=False, fontsize=9)

    _cdf(ax2, real, left, right, "Исходные записи", DATA)
    _cdf(ax2, mix, left, right, "Генерация смеси", MIX, "--")
    _cdf(ax2, normal, left, right, "Генерация одной нормальной", BASE, ":")
    ax2.set(title="Эмпирические функции распределения", ylabel="F(x)", ylim=(-.02, 1.02))
    ax2.legend(loc="upper left", frameon=False, fontsize=9)
    for ax in (ax1, ax2):
        _density_axis(ax, left, right)
    return fig


def plot_block_check(scores, examples):
    worst = int(scores.loc[scores["cdf_gap"].idxmax(), "Блок"])
    real, draws = examples[worst]
    left = min(real.min(), draws.min()) - .00015
    right = max(real.max(), draws.max()) + .00015
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.2, 6.9), constrained_layout=True)
    _cdf(ax1, real, left, right, f"Контроль, n={len(real)}", DATA)
    _cdf(ax1, draws, left, right, "Генерация смеси", MIX, "--")
    ax1.axvline(EVENT_THRESHOLD, color=BASE, linestyle=":", label="Порог 0.997")
    ax1.set(title=f"Блок {worst}: наибольшее расхождение CDF смеси",
            ylabel="F(x)", ylim=(-.02, 1.02))
    ax1.legend(loc="upper left", frameon=False, fontsize=9)
    _density_axis(ax1, left, right)

    short = {"mean": "Среднее", "sd": "Разброс", "w1": "W₁",
             "tails": "Квантили", "event": "Вероятность порога"}
    colors = ["#397c8c", "#5e6183", "#8a7750", "#a64f6b", "#b36c30"]
    for (key, limit), color in zip(LIMITS.items(), colors):
        ax2.plot(scores["Блок"], scores[key] / limit, ".-", color=color,
                 linewidth=1.45, markersize=7, label=short[key])
    ax2.axhline(1, color=DATA, linestyle="--", linewidth=1, label="Допуск")
    ax2.set(title="Ошибки смеси по блокам", xlabel="Контрольный блок",
            ylabel="Ошибка / допуск", xticks=sorted(scores["Блок"]), ylim=(0, None))
    ax2.grid(alpha=.19)
    ax2.spines[["top", "right"]].set_visible(False)
    ax2.legend(ncols=3, loc="upper center", bbox_to_anchor=(.5, -.17),
               frameon=False, fontsize=9)
    return fig
