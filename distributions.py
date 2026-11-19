"""Сравнение теоретических CDF на групповых контрольных блоках."""

from dataclasses import dataclass
import numpy as np
import pandas as pd
from scipy import stats
from scipy.optimize import brentq
from scipy.special import logsumexp
from sklearn.mixture import GaussianMixture
from threadpoolctl import threadpool_limits

from .analysis import COLUMNS, NAMES


CANDIDATES = {
    "alcohol": ("lognorm", "gamma", "skewnorm", "mix_norm"),
    "density": ("norm", "t", "mix_norm"),
    "residual sugar": ("lognorm", "gamma", "burr12", "mix_lognorm"),
}
LABELS = {
    "norm": "Нормальное",
    "t": "Стьюдента",
    "lognorm": "Логнормальное",
    "gamma": "Гамма",
    "skewnorm": "Асимметричное нормальное",
    "burr12": "Бёрра XII",
    "mix_norm": "Смесь 2 нормальных",
    "mix_lognorm": "Смесь 2 логнормальных",
}
LEVELS = np.array([.05, .25, .5, .75, .95, .99])
SCORE_LEVELS = LEVELS[:-1]
NEAR_TIE = .005


@dataclass(frozen=True)
class Mixture:
    weights: np.ndarray
    components: tuple

    def cdf(self, x):
        return sum(w * d.cdf(x) for w, d in zip(self.weights, self.components))

    def pdf(self, x):
        return sum(w * d.pdf(x) for w, d in zip(self.weights, self.components))

    def logpdf(self, x):
        return logsumexp([np.log(w) + d.logpdf(x)
                          for w, d in zip(self.weights, self.components)], axis=0)

    def ppf(self, p):
        def quantile(level):
            points = [d.ppf(level) for d in self.components]
            lo, hi = min(points), max(points)
            margin = max(hi - lo, 1e-10) * 1e-6
            return brentq(lambda x: self.cdf(x) - level, lo - margin, hi + margin)
        return np.array([quantile(q) for q in np.atleast_1d(p)])


@dataclass(frozen=True)
class Model:
    key: str
    distribution: object
    n_params: int
    parameters: dict

    @property
    def label(self):
        return LABELS[self.key]


@dataclass
class FitReport:
    baseline: Model
    selected: Model
    scores: pd.DataFrame
    quantiles: pd.DataFrame
    jump_floor: float


def grouped_blocks(wine, n_blocks=5):
    """Полные повторы в одном блоке; детерминированная балансировка по n."""
    index = pd.MultiIndex.from_frame(wine)
    group, _ = pd.factorize(index, sort=False)
    sizes = np.bincount(group)
    hashes = pd.util.hash_pandas_object(wine, index=False).to_numpy()
    representatives = np.unique(group, return_index=True)[1]
    order = np.lexsort((hashes[representatives], -sizes))
    totals = np.zeros(n_blocks, dtype=int)
    block = np.empty(len(sizes), dtype=int)
    for g in order:
        b = np.argmin(totals)
        block[g] = b
        totals[b] += sizes[g]
    return block[group]


def fit_family(key, sample):
    x = np.asarray(sample, dtype=float)
    if key in ("mix_norm", "mix_lognorm"):
        # Подгоняем смесь на исходной шкале или на логарифмах.
        y = np.log(x) if key == "mix_lognorm" else x
        center, scale = y.mean(), y.std(ddof=0)
        z = ((y - center) / scale).reshape(-1, 1)
        gm = GaussianMixture(n_components=2, n_init=5, max_iter=500,
                             init_params="k-means++",
                             tol=1e-6, reg_covar=1e-4, random_state=42)
        with threadpool_limits(limits=1):
            gm.fit(z)
        if not gm.converged_:
            raise RuntimeError("Не сошлась подгонка двухкомпонентной смеси.")
        means = center + scale * gm.means_.ravel()
        sigma = scale * np.sqrt(gm.covariances_.ravel())
        order = np.argsort(means)
        means, sigma, weights = means[order], sigma[order], gm.weights_[order]
        if key == "mix_lognorm":
            parts = tuple(stats.lognorm(s, loc=0, scale=np.exp(m)) for m, s in zip(means, sigma))
        else:
            parts = tuple(stats.norm(loc=m, scale=s) for m, s in zip(means, sigma))
        parameters = {
            "w₁": weights[0], "μ₁": means[0], "σ₁": sigma[0],
            "μ₂": means[1], "σ₂": sigma[1],
        }
        return Model(key, Mixture(weights, parts), 5, parameters)

    family = getattr(stats, key)
    if key in ("lognorm", "gamma", "burr12"):
        fitted = family.fit(x, floc=0)
        names = {
            "lognorm": ("σ_log", "loc", "scale"),
            "gamma": ("shape", "loc", "scale"),
            "burr12": ("c", "d", "loc", "scale"),
        }[key]
        count = len(fitted) - 1
    else:
        fitted = family.fit(x)
        names = {"norm": ("μ", "σ"), "t": ("ν", "loc", "scale"),
                 "skewnorm": ("α", "loc", "scale")}[key]
        count = len(fitted)
    return Model(key, family(*fitted), count, dict(zip(names, fitted)))


def cdf_gap(x, model):
    """Проверяет левую и правую стороны каждого эмпирического скачка."""
    x = np.sort(np.asarray(x, dtype=float))
    n = len(x)
    p = model.distribution.cdf(x)
    right = np.arange(1, n + 1) / n
    left = right - 1 / n
    return float(max(np.max(right - p), np.max(p - left)))


def _choose_key(scores):
    # Если разница меньше 0.5 п. п. CDF, выбираем меньше параметров.
    near = scores.loc[scores["D_CV"] <= scores["D_CV"].min() + NEAR_TIE]
    return near.sort_values(["Параметров", "D_CV"]).index[0]


def compare_models(wine, blocks):
    results = {}
    per_block = []
    for c in COLUMNS:
        x = wine[c].to_numpy()
        models, rows = {}, []
        for key in CANDIDATES[c]:
            model = fit_family(key, x)
            models[key] = model
            gaps, q_errors = [], []
            for b in np.unique(blocks):
                train, check = x[blocks != b], x[blocks == b]
                fitted = fit_family(key, train)
                gap = cdf_gap(check, fitted)
                q_real = np.quantile(check, SCORE_LEVELS)
                q_model = fitted.distribution.ppf(SCORE_LEVELS)
                iqr = np.diff(np.quantile(train, [.25, .75]))[0]
                q_error = np.mean(np.abs(q_model - q_real)) / iqr
                gaps.append(gap)
                q_errors.append(q_error)
                per_block.append({"Величина": NAMES[c], "Модель": model.label, "Блок": b + 1,
                                  "n обучения": len(train), "n проверки": len(check),
                                  "D": gap, "MAE квантилей / IQR": q_error})
            loglik = model.distribution.logpdf(x).sum()
            if not np.isfinite([loglik, *gaps, *q_errors]).all():
                raise ValueError(f"Некорректная подгонка для {c}: {key}")
            outside = model.distribution.cdf(0)
            if c == "alcohol":
                outside += model.distribution.sf(100) if key != "mix_norm" else (
                    1 - model.distribution.cdf(100)
                )
            rows.append({
                "key": key, "Модель": model.label, "Параметров": model.n_params,
                "D_CV": np.mean(gaps), "SD D по блокам": np.std(gaps, ddof=1),
                "MAE квантилей / IQR": np.mean(q_errors),
                "D на всех строках": cdf_gap(x, model),
                "BIC": model.n_params * np.log(len(x)) - 2 * loglik,
                "P вне физ. области": outside,
            })
        score = pd.DataFrame(rows).set_index("key")
        best_key = _choose_key(score)
        baseline, chosen = models[CANDIDATES[c][0]], models[best_key]
        score["Выбор"] = np.where(score.index == best_key, "да", "")
        score = score.sort_values("D_CV").reset_index(drop=True)
        q_real = np.quantile(x, LEVELS)
        q_base = baseline.distribution.ppf(LEVELS)
        q_best = chosen.distribution.ppf(LEVELS)
        quantiles = pd.DataFrame({
            "Квантиль": LEVELS, "Эмпирический": q_real, "Исходная модель": q_base,
            "Выбранная модель": q_best, "Δ выбранной": q_best - q_real,
        })
        floor = np.unique(x, return_counts=True)[1].max() / (2 * len(x))
        results[c] = FitReport(baseline, chosen, score, quantiles, floor)
    return results, pd.DataFrame(per_block)
