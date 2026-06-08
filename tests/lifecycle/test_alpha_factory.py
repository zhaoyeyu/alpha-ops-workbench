from datetime import datetime

import pandas as pd
import pytest

from alphaops.lifecycle.factory import AlphaFactory, candidate_id_for_formula, normalize_formula
from alphaops.quant.alpha_dsl import AlphaDslError


def _bars() -> pd.DataFrame:
    rows = []
    prices = {
        "eq:a": [100.0, 110.0, 121.0],
        "eq:b": [100.0, 120.0, 144.0],
        "fut:c": [100.0, 130.0, 169.0],
    }
    for instrument_id, series in prices.items():
        for day, price in enumerate(series, start=1):
            rows.append(
                {
                    "instrument_id": instrument_id,
                    "asset_class": "futures" if instrument_id.startswith("fut") else "equity",
                    "timestamp": datetime(2026, 1, day),
                    "close": price,
                    "adj_close": price,
                    "volume": 1000 + day,
                }
            )
    return pd.DataFrame(rows)


def test_alpha_factory_creates_real_candidate_with_metrics() -> None:
    factory = AlphaFactory()

    candidate = factory.create_candidate(" rank(close) ", _bars())
    payload = candidate.registry_review_payload()

    assert candidate.candidate_id == candidate_id_for_formula("rank(close)")
    assert candidate.formula == "rank(close)"
    assert candidate.state == "registry_review"
    assert candidate.dependencies == ("close",)
    assert candidate.operator_names == ("rank",)
    assert not candidate.factor_preview.empty
    assert payload["lifecycle_state"] == "registry_review"
    assert payload["metrics"]["rank_ic_mean"] == pytest.approx(1.0)
    assert candidate.score > 0


def test_alpha_factory_detects_duplicate_formulas() -> None:
    factory = AlphaFactory()
    first = factory.create_candidate("rank(close)", _bars())
    duplicate = factory.create_candidate("  rank(close)  ", _bars())

    assert duplicate.state == "duplicate"
    assert duplicate.duplicate_of == first.candidate_id
    assert duplicate.registry_review_payload()["duplicate_of"] == first.candidate_id


def test_alpha_factory_invalid_formula_fails_safely() -> None:
    factory = AlphaFactory()

    with pytest.raises(AlphaDslError) as error:
        factory.create_candidate("rank(missing)", _bars())

    assert error.value.code == "unknown_field"


def test_formula_normalization_is_stable() -> None:
    assert normalize_formula(" rank( close ) ") == "rank( close )"
