"""Проверка генераторов из командной строки: python -m research.validate_models."""

import numpy as np

from lab01_tools import load_wine
from .protocol import (
    SEED, N_SIM, METHODS, fit_density, mixture_parameters, sample_density,
    score_full, implementation_checks, evaluate_blocks, block_overview,
    tolerance_table,
)


def main():
    wine = load_wine()
    real = wine["density"].to_numpy()
    fit = fit_density(real)
    draws = {key: sample_density(fit, key, N_SIM, SEED + j)
             for j, key in enumerate(METHODS)}
    checks, theory = implementation_checks(fit, draws)
    assert checks["Пройдена"].all() and theory["Пройдена"].all()
    summary, full_scores = score_full(real, fit, draws)
    blocks, scores, _ = evaluate_blocks(wine)
    print("Групповые блоки:", np.bincount(blocks))
    print("Параметры смеси:", mixture_parameters(fit))
    print("Проверки алгоритма:\n", checks.to_string())
    print("Сопоставление с законом:\n", theory.to_string(index=False))
    print("Полная таблица:\n", summary.to_string())
    print("Расхождения на полном наборе:\n", full_scores.to_string(index=False))
    print("Средние по блокам:\n", block_overview(scores).to_string())
    print("Смесь на контрольных блоках:\n", scores.query("Метод == 'mixture'").to_string(index=False))
    print("Допуски:\n", tolerance_table(scores.query("Метод == 'mixture'")).to_string(index=False))


if __name__ == "__main__":
    main()
