import numpy as np


def polar_standard(n, rng):
    """n стандартных нормальных чисел полярным методом."""
    if n < 0:
        raise ValueError("Размер выборки должен быть неотрицательным.")
    result = np.empty(n)
    filled = 0
    while filled < n:
        pair_count = (n - filled + 1) // 2
        pairs = rng.uniform(-1, 1, size=(pair_count, 2))
        s = (pairs**2).sum(axis=1)
        inside = (s > 0) & (s < 1)
        s_good = s[inside]
        factor = np.sqrt(-2 * np.log(s_good) / s_good)
        values = (pairs[inside] * factor[:, None]).ravel()
        take = min(len(values), n - filled)
        result[filled:filled + take] = values[:take]
        filled += take
    return result


def generate_normal(n, mean, sigma, rng):
    if not np.isfinite(mean) or not np.isfinite(sigma) or sigma <= 0:
        raise ValueError("Нужны конечное среднее и положительное стандартное отклонение.")
    return mean + sigma * polar_standard(n, rng)


def generate_mixture(n, weights, means, sigmas, rng):
    """Сначала выбирает компоненту, затем генерирует её нормальное значение."""
    weights, means, sigmas = (np.asarray(a, dtype=float) for a in (weights, means, sigmas))
    if any(a.shape != (2,) or not np.isfinite(a).all() for a in (weights, means, sigmas)):
        raise ValueError("Ожидаются параметры двух конечных компонент.")
    if (weights < 0).any() or not np.isclose(weights.sum(), 1) or (sigmas <= 0).any():
        raise ValueError("Веса должны суммироваться в 1, а масштабы — быть положительными.")
    if n < 0:
        raise ValueError("Размер выборки должен быть неотрицательным.")
    component = (rng.random(n) >= weights[0]).astype(int)
    z = polar_standard(n, rng)
    return means[component] + sigmas[component] * z, component


def fit_empirical(x):
    if len(x) == 0 or not np.isfinite(x).all():
        raise ValueError("Нужна непустая выборка из конечных значений.")
    values, counts = np.unique(x, return_counts=True)
    probabilities = counts / counts.sum()
    cumulative = np.cumsum(counts) / counts.sum()
    return values, probabilities, cumulative


def inverse_lookup(values, cumulative, u):
    # Ищем первый накопленный порог, который строго больше u.
    index = np.searchsorted(cumulative, u, side="right")
    return values[index]


def generate_empirical(n, values, cumulative, rng):
    if n < 0:
        raise ValueError("Размер выборки должен быть неотрицательным.")
    return inverse_lookup(values, cumulative, rng.random(n))
