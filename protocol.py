"""Данные, подгонка и проверки второго спринта."""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from lab01_tools.analysis import ecdf_at, empirical_gap
from lab01_tools.distributions import Model, cdf_gap, fit_family, grouped_blocks

from .generators import (fit_empirical, generate_empirical, generate_mixture,
                         generate_normal, inverse_lookup, polar_standard)


SEED = 20261111
N_SIM = 50_000
EVENT_THRESHOLD = 0.997
DKW_DELTA = 0.001
METHODS = {
    "mixture": "Смесь двух нормальных",
    "normal": "Одна нормальная",
    "empirical": "Эмпирическая инверсия",
}
LIMITS = {
    "mean": 0.15,
    "sd": 0.10,
    "w1": 0.15,
    "tails": 0.35,
    "event": 0.05,
}
METRIC_NAMES = {
    "mean": "Ошибка среднего / σ обучения",
    "sd": "Отн. ошибка ст. отклонения",
    "w1": "W₁ / σ обучения",
    "tails": "Макс. ошибка Q05 и Q95 / σ обучения",
    "event": "Ошибка P(D > 0.997)",
    "cdf_gap": "Макс. разница CDF генерации",
    "theory_gap": "Макс. разница CDF модели",
}


@dataclass(frozen=True)
class DensityFit:
    reference: np.ndarray
    mixture: Model
    normal: Model
    values: np.ndarray
    probabilities: np.ndarray
    cumulative: np.ndarray


def fit_density(data):
    x = np.asarray(data, dtype=float)
    if x.ndim != 1 or len(x) < 2 or not np.isfinite(x).all() or x.std() == 0:
        raise ValueError("Нужен одномерный ряд измерений с ненулевым разбросом.")
    values, probabilities, cumulative = fit_empirical(x)
    return DensityFit(x, fit_family("mix_norm", x), fit_family("norm", x),
                      values, probabilities, cumulative)


def mixture_parameters(fit):
    mixture = fit.mixture.distribution
    means = np.array([d.mean() for d in mixture.components])
    scales = np.array([d.std() for d in mixture.components])
    return mixture.weights, means, scales


def sample_density(fit, method, n, seed):
    rng = np.random.default_rng(seed)
    if method == "mixture":
        return generate_mixture(n, *mixture_parameters(fit), rng)[0]
    if method == "normal":
        return generate_normal(n, fit.normal.distribution.mean(), fit.normal.distribution.std(), rng)
    if method == "empirical":
        return generate_empirical(n, fit.values, fit.cumulative, rng)
    raise ValueError("Неизвестный метод генерации.")


def component_table(fit, component):
    weights, means, sigmas = mixture_parameters(fit)
    return pd.DataFrame({
        "Компонента": [1, 2], "Вес модели": weights,
        "Доля в генерации": np.bincount(component, minlength=2) / len(component),
        "Среднее, г/см³": means, "Ст. отклонение, г/см³": sigmas,
    })


def mixture_moments(fit):
    w, mu, sigma = mixture_parameters(fit)
    mean = float(w @ mu)
    variance = float(w @ (sigma**2 + (mu - mean)**2))
    return mean, variance


def density_summary(x):
    q05, q25, med, q75, q95, q99 = np.quantile(x, [.05, .25, .5, .75, .95, .99])
    return {
        "Количество": len(x), "Среднее": np.mean(x), "Дисперсия": np.var(x),
        "Ст. отклонение": np.std(x), "Q05": q05, "Q25": q25, "Медиана": med,
        "Q75": q75, "Q95": q95, "Q99": q99, "IQR": q75 - q25,
        "Минимум": np.min(x), "Максимум": np.max(x),
        "P(D > 0.997)": np.mean(x > EVENT_THRESHOLD),
    }


def compare_density(real, simulated, scale):
    q_real = np.quantile(real, [.05, .95])
    q_sim = np.quantile(simulated, [.05, .95])
    return {
        "mean": abs(simulated.mean() - real.mean()) / scale,
        "sd": abs(simulated.std() / real.std() - 1),
        "w1": stats.wasserstein_distance(real, simulated) / scale,
        "tails": np.max(np.abs(q_real - q_sim)) / scale,
        "event": abs(np.mean(real > EVENT_THRESHOLD) - np.mean(simulated > EVENT_THRESHOLD)),
        "cdf_gap": empirical_gap(real, simulated),
    }


def model_distance(real, fit, method):
    if method == "mixture":
        return cdf_gap(real, fit.mixture)
    if method == "normal":
        return cdf_gap(real, fit.normal)
    if method == "empirical":
        return empirical_gap(real, fit.reference)
    raise ValueError("Неизвестный метод генерации.")


def score_full(wine_density, fitted, draws):
    metrics = pd.DataFrame({
        "Исходная таблица": density_summary(wine_density),
        **{METHODS[k]: density_summary(x) for k, x in draws.items()},
    })
    scores = pd.DataFrame([
        {"Модель": METHODS[k], **compare_density(wine_density, x, fitted.reference.std()),
         "theory_gap": model_distance(wine_density, fitted, k)}
        for k, x in draws.items()
    ])
    return metrics, scores


def evaluate_blocks(wine, n=N_SIM):
    blocks = grouped_blocks(wine)
    density = wine["density"].to_numpy()
    group = pd.MultiIndex.from_frame(wine)
    if pd.Series(blocks).groupby(group).nunique().max() != 1:
        raise ValueError("Совпадающие строки разделились между блоками.")
    rows, examples = [], {}
    for b in np.unique(blocks):
        train, control = density[blocks != b], density[blocks == b]
        fitted = fit_density(train)
        for j, method in enumerate(METHODS):
            draws = sample_density(fitted, method, n, SEED + 10 * (int(b) + 1) + j)
            metrics = compare_density(control, draws, train.std())
            rows.append({
                "Блок": int(b) + 1, "Метод": method, "Модель": METHODS[method],
                "n обучения": len(train), "n контроля": len(control),
                **metrics, "theory_gap": model_distance(control, fitted, method),
            })
            if method == "mixture":
                examples[int(b) + 1] = (control, draws)
    return blocks, pd.DataFrame(rows), examples


def block_overview(scores):
    return scores.groupby("Модель", sort=False)[list(METRIC_NAMES)].mean().rename(columns=METRIC_NAMES)


def tolerance_table(scores):
    rows = []
    for key, limit in LIMITS.items():
        i = scores[key].idxmax()
        rows.append({
            "Показатель": METRIC_NAMES[key], "Допуск": limit,
            "Макс. ошибка": scores.loc[i, key],
            "Блок с макс. ошибкой": int(scores.loc[i, "Блок"]),
            "В допуске": int((scores[key] <= limit).sum()),
            "Всего блоков": len(scores),
        })
    return pd.DataFrame(rows)


def _known_mixture_draw():
    class FixedRNG:
        def random(self, size):
            return np.array([0.20, 0.80])

        def uniform(self, a, b, size):
            return np.array([[0.30, 0.40]])

    # s=0.25, z≈(0.9991, 1.3321), значения должны идти из разных компонент.
    draw, component = generate_mixture(2, [.3, .7], [1.0, 2.0], [.01, .02], FixedRNG())
    return np.array_equal(component, [0, 1]) and np.allclose(
        draw, [1.0099906553339, 2.0266417475572], rtol=0, atol=1e-10
    )


def implementation_checks(fit, draws):
    toy_x, _, toy_cdf = fit_empirical(np.array([.995, .997, .997, .999]))
    toy_u = np.array([0.0, .249, .25, .60, .75, .999])
    toy_expected = np.array([.995, .995, .997, .997, .999, .999])
    checks = {
        "Полярный метод: корректны пустой и нечётный размеры":
            all(len(polar_standard(n, np.random.default_rng(SEED))) == n for n in (0, 1, 7)),
        "Смесь: контроль выбора компоненты и масштаба": _known_mixture_draw(),
        "Инверсия: контроль точек на границах порогов":
            np.array_equal(inverse_lookup(toy_x, toy_cdf, toy_u), toy_expected),
        "Инверсия: сумма вероятностей равна 1":
            np.isclose(fit.probabilities.sum(), 1) and fit.cumulative[-1] == 1,
        "Инверсия выдаёт только исходные значения":
            np.isin(draws["empirical"], fit.values).all(),
        "Фиксированный seed воспроизводит результат":
            all(np.array_equal(sample_density(fit, k, 11, SEED),
                               sample_density(fit, k, 11, SEED)) for k in METHODS),
        "В генерациях только конечные положительные числа":
            all(np.isfinite(x).all() and (x > 0).all() for x in draws.values()),
    }
    checks = pd.Series(checks, name="Пройдена").to_frame()
    distances = pd.DataFrame([
        {"Модель": METHODS[k], "m": len(x), "Расстояние до заданного закона": model_distance(x, fit, k),
         "Граница ДКВ": np.sqrt(np.log(2 / DKW_DELTA) / (2 * len(x)))}
        for k, x in draws.items()
    ])
    distances["Пройдена"] = distances["Расстояние до заданного закона"] <= distances["Граница ДКВ"]
    return checks, distances
