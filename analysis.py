"""Загрузка данных, критерии отбора и описательная статистика."""

from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


COLUMNS = ("alcohol", "density", "residual sugar")
NAMES = {"alcohol": "Спирт", "density": "Плотность", "residual sugar": "Остаточный сахар"}
UNITS = {"alcohol": "% об.", "density": "г/см³", "residual sugar": "г/л"}
COLORS = {"alcohol": "#75445b", "density": "#327c83", "residual sugar": "#b47832"}
GROUPS = {"3–4": (3, 4), "5–6": (5, 6), "7–8": (7, 8)}
GROUP_COLORS = {"3–4": "#2b7991", "5–6": "#7e5175", "7–8": "#b16b25"}
THRESHOLDS = {"alcohol": 11, "density": 0.997, "residual sugar": 3}
EVENT_LABELS = {"alcohol": "A > 11 % об.", "density": "D > 0.997 г/см³", "residual sugar": "S > 3 г/л"}
LIMITS = {"mean": 0.10, "variance_pct": 10, "cdf": 0.05, "q95_iqr": 0.25}


def load_wine(path=None):
    """Чтение неизменённого красного набора из комплекта лабораторной."""
    if path is None:
        path = Path(__file__).resolve().parent.parent / "data" / "winequality-red.csv"
    wine = pd.read_csv(path, sep=";")
    if wine.shape != (1599, 12):
        raise ValueError("Ожидается красный набор Wine Quality: 1599 строк и 12 столбцов.")
    if not np.isfinite(wine.to_numpy(dtype=float)).all():
        raise ValueError("В файле обнаружены пропуски или бесконечные значения.")
    if not (wine[list(COLUMNS)] > 0).all().all():
        raise ValueError("В выбранных столбцах есть неположительные измерения.")
    if set(wine["quality"]) != set(range(3, 9)):
        raise ValueError("В исходном красном наборе ожидаются оценки от 3 до 8.")
    return wine


def frequency_table(series):
    values, counts = np.unique(series, return_counts=True)
    return pd.DataFrame({
        "x": values,
        "Частота": counts,
        "p": counts / counts.sum(),
        "F(x)": np.cumsum(counts) / counts.sum(),
    })


def ecdf_at(values, points):
    ordered = np.sort(np.asarray(values, dtype=float))
    return np.searchsorted(ordered, points, side="right") / ordered.size


def empirical_gap(a, b):
    """Максимальное различие двух ступенчатых CDF; без p-значения."""
    points = np.union1d(a, b)
    return float(np.max(np.abs(ecdf_at(a, points) - ecdf_at(b, points))))


def describe_values(series):
    x = pd.Series(series, dtype=float)
    q05, q1, med, q3, q95, q99 = x.quantile([.05, .25, .5, .75, .95, .99])
    return pd.Series({
        "Количество": x.size,
        "Уникальных значений": x.nunique(),
        "Сумма": x.sum(),
        "Среднее": x.mean(),
        "Медиана": med,
        "Мода": ", ".join(f"{v:g}" for v in x.mode()),
        "Минимум": x.min(),
        "Максимум": x.max(),
        "Размах": x.max() - x.min(),
        "Дисперсия, ddof=0": x.var(ddof=0),
        "Дисперсия, ddof=1": x.var(ddof=1),
        "Ст. отклонение, ddof=1": x.std(ddof=1),
        "Q05": q05,
        "Q1": q1,
        "Q3": q3,
        "Q95": q95,
        "Q99": q99,
        "IQR": q3 - q1,
        "Асимметрия": x.skew(),
        "Эксцесс": x.kurt(),
    }, name="Значение")


def normalizations(wine):
    numeric = wine[list(COLUMNS)]
    z = (numeric - numeric.mean()) / numeric.std(ddof=1)
    unit = (numeric - numeric.min()) / (numeric.max() - numeric.min())
    return pd.DataFrame({
        "Среднее z": z.mean(),
        "Ст. отклонение z": z.std(ddof=1),
        "Минимум min–max": unit.min(),
        "Максимум min–max": unit.max(),
    }).rename(index=NAMES)


def criterion_groups(wine):
    return {label: wine.loc[wine["quality"].between(lo, hi)]
            for label, (lo, hi) in GROUPS.items()}


def _comparison(group, full):
    sigma = full.std(ddof=0)
    iqr = full.quantile(.75) - full.quantile(.25)
    return {
        "Δ среднего / σ": (group.mean() - full.mean()) / sigma,
        "Δ дисперсии, %": 100 * (group.var(ddof=0) / full.var(ddof=0) - 1),
        "D между CDF": empirical_gap(group, full),
        "Δ Q95": group.quantile(.95) - full.quantile(.95),
        "Δ Q95 / IQR": (group.quantile(.95) - full.quantile(.95)) / iqr,
    }


def quality_comparison(wine):
    groups = criterion_groups(wine)
    sizes = pd.DataFrame({
        "Строк": {label: len(frame) for label, frame in groups.items()},
        "Доля, %": {label: 100 * len(frame) / len(wine) for label, frame in groups.items()},
    }).rename_axis("Оценка качества")

    summaries, comparisons = [], []
    for c in COLUMNS:
        for label, part in {"Все строки": wine, **groups}.items():
            s = part[c]
            summaries.append({
                "Величина": NAMES[c], "Ед.": UNITS[c], "Качество": label,
                "n": len(s), "Среднее": s.mean(), "Медиана": s.median(),
                "Дисперсия": s.var(ddof=0), "Q95": s.quantile(.95),
            })
            if label == "Все строки":
                continue
            metrics = _comparison(s, wine[c])
            passed = [
                abs(metrics["Δ среднего / σ"]) <= LIMITS["mean"],
                abs(metrics["Δ дисперсии, %"]) <= LIMITS["variance_pct"],
                metrics["D между CDF"] <= LIMITS["cdf"],
                abs(metrics["Δ Q95 / IQR"]) <= LIMITS["q95_iqr"],
            ]
            comparisons.append({
                "Величина": NAMES[c], "Качество": label, **metrics,
                "В допуске": f"{sum(passed)} из {len(passed)}",
            })
    return sizes, pd.DataFrame(summaries), pd.DataFrame(comparisons)


def criterion_expansion(wine):
    """Те же признаки на вложенных множествах оценок."""
    stages = [("5", 5, 5), ("5–6", 5, 6), ("4–7", 4, 7), ("3–8", 3, 8)]
    rows = []
    for label, lo, hi in stages:
        part = wine.loc[wine["quality"].between(lo, hi)]
        for c in COLUMNS:
            rows.append({
                "Качество": label, "n": len(part), "Охват, %": 100 * len(part) / len(wine),
                "Величина": NAMES[c], **_comparison(part[c], wine[c]),
            })
    return pd.DataFrame(rows)


def weighted_reconstruction(wine):
    """Среднее, дисперсия и CDF из полных групп с их исходными весами."""
    groups = criterion_groups(wine)
    result = []
    for c in COLUMNS:
        weights = np.array([len(frame) / len(wine) for frame in groups.values()])
        means = np.array([frame[c].mean() for frame in groups.values()])
        variances = np.array([frame[c].var(ddof=0) for frame in groups.values()])
        mu = weights @ means
        variance = weights @ (variances + (means - mu)**2)
        points = np.unique(wine[c])
        mixture_cdf = sum(w * ecdf_at(frame[c], points)
                          for w, frame in zip(weights, groups.values()))
        result.append({
            "Величина": NAMES[c], "Среднее из групп": mu,
            "Среднее таблицы": wine[c].mean(), "Дисперсия из групп": variance,
            "Дисперсия таблицы": wine[c].var(ddof=0),
            "Макс. ошибка CDF": np.max(np.abs(mixture_cdf - ecdf_at(wine[c], points))),
        })
    return pd.DataFrame(result)


def outlier_report(wine):
    fences, summaries = [], []
    for c in COLUMNS:
        x = wine[c]
        q1, q3 = x.quantile([.25, .75])
        iqr = q3 - q1
        for label, k in [("Все строки", None), ("В пределах 1.5 IQR", 1.5),
                         ("В пределах 3 IQR", 3.0)]:
            if k is None:
                part = x
            else:
                lo, hi = q1 - k * iqr, q3 + k * iqr
                below, above = int((x < lo).sum()), int((x > hi).sum())
                part = x.loc[x.between(lo, hi)]
                fences.append({
                    "Величина": NAMES[c], "Ед.": UNITS[c], "k": k, "Нижняя": lo,
                    "Верхняя": hi, "Ниже": below, "Выше": above,
                    "За границами, %": 100 * (below + above) / len(x),
                })
            summaries.append({
                "Величина": NAMES[c], "Ед.": UNITS[c], "Данные": label,
                "n": len(part), "Среднее": part.mean(), "Медиана": part.median(),
                "Ст. отклонение": part.std(ddof=1), "Q95": part.quantile(.95),
                "Эксцесс": part.kurt(),
            })
    return pd.DataFrame(fences), pd.DataFrame(summaries)


def dependence_report(wine):
    """Прежние три проверки χ² на различных строках с поправкой Бонферрони."""
    unique = wine.drop_duplicates()
    levels = {c: pd.qcut(unique[c], 3, labels=False) for c in COLUMNS}
    events = {c: wine[c] > THRESHOLDS[c] for c in COLUMNS}
    prob, corr, hypotheses = [], [], []
    for a, b in combinations(COLUMNS, 2):
        label = NAMES[a] + " — " + NAMES[b]
        p_a, p_b = events[a].mean(), events[b].mean()
        p_both = (events[a] & events[b]).mean()
        prob.append({
            "B": EVENT_LABELS[a], "C": EVENT_LABELS[b], "P(B)": p_a, "P(C)": p_b,
            "P(B∩C)": p_both, "P(B)P(C)": p_a * p_b, "P(C|B)": p_both / p_a,
        })
        corr.append({
            "Пара": label, "Пирсон, все": wine[a].corr(wine[b]),
            "Спирмен, все": wine[a].corr(wine[b], method="spearman"),
            "Пирсон, без полных повторов": unique[a].corr(unique[b]),
        })
        counts = pd.crosstab(levels[a], levels[b])
        chi2, p, dof, expected = stats.chi2_contingency(counts, correction=False)
        v = np.sqrt(chi2 / (len(unique) * (min(counts.shape) - 1)))
        p_adj = min(3 * p, 1.0)
        hypotheses.append({
            "Пара": label, "χ²": chi2, "df": dof, "min E": expected.min(),
            "p": p, "p с поправкой": p_adj, "V Крамера": v,
            "Независимость": "отвергается" if p_adj < .05 else "не отвергается",
        })
    return pd.DataFrame(prob), pd.DataFrame(corr), pd.DataFrame(hypotheses)
