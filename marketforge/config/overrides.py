# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""
TOML override files: change catalog instruments or add new ones without
editing the package.

    # my_instruments.toml
    [instruments.BTCUSD]          # change an existing instrument
    start_price = 42000
    volatility = 0.60

    [instruments.MYCOIN]          # add a new one
    market = "crypto"
    start_price = 1.50
    volatility = 0.90
    drift = 0.0
    volume_base = 20000
    correlations = { BTCUSD = 0.6, ETHUSD = 0.55 }

Keys: market (required for new instruments), start_price, volatility
(annualised), drift (annualised log drift), volume_base (mean volume per
minute: coins for crypto, ticks for forex, shares for stocks),
volume_volatility, spread_bps (typical quoted spread in basis points of the
price; default: the market's rule), correlations (to instruments of the same market;
unspecified pairs of a new instrument default to 0).
"""

from __future__ import annotations

import os
import tomllib
import warnings
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np

from marketforge._warnings import PACKAGE_DIRS
from marketforge.config.catalog.correlation import nearest_correlation
from marketforge.config.catalog.schema import InstrumentParams, MarketConfig
from marketforge.config.factors import FactorStructure, forex_structure
from marketforge.domain.markets import MarketType

_FIELDS = ("start_price", "volatility", "drift", "volume_base", "volume_volatility", "spread_bps")
_KEYS = set(_FIELDS) | {"market", "correlations"}


class OverrideError(ValueError):
    """An override file is malformed or inconsistent with the catalog."""


# What users may pass as overrides: an override file, or the content of its
# [instruments] table as a mapping {SYMBOL: {key: value}}.
Overrides = str | os.PathLike[str] | Mapping[str, Mapping[str, Any]]


def resolve_overrides(overrides: Overrides | None) -> dict[str, dict[str, Any]]:
    """Checked overrides as {SYMBOL: {key: value}}, from a file or a mapping; {} for None."""
    if overrides is None:
        return {}
    if isinstance(overrides, Mapping):
        return _checked(overrides, "overrides")
    return _read(overrides)


def _read(path: str | os.PathLike[str]) -> dict[str, dict[str, Any]]:
    p = Path(path)
    try:
        with open(p, "rb") as fh:
            doc = tomllib.load(fh)
    except FileNotFoundError:
        raise OverrideError(f"Override file not found: {p}") from None
    except tomllib.TOMLDecodeError as e:
        raise OverrideError(f"Invalid TOML in {p}: {e}") from None
    unknown_top = set(doc) - {"instruments"}
    if unknown_top:
        raise OverrideError(
            f"{p}: unknown top-level table(s) {sorted(unknown_top)}; expected [instruments.SYMBOL]"
        )
    return _checked(doc.get("instruments", {}), str(p))


def _checked(entries: Mapping[str, Any], where: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for symbol, body in entries.items():
        if not isinstance(body, Mapping):
            raise OverrideError(f"{where}: [instruments.{symbol}] must be a table")
        bad = set(body) - _KEYS
        if bad:
            raise OverrideError(
                f"{where}: [instruments.{symbol}] has unknown key(s) {sorted(bad)}; "
                f"valid: {sorted(_KEYS)}"
            )
        name = f"{where}: [instruments.{symbol}]"
        for key in _FIELDS:
            if key in body and not _is_number(body[key]):
                raise OverrideError(f"{name}.{key} must be a number, got {body[key]!r}")
        if "correlations" in body:
            correlations = body["correlations"]
            if not isinstance(correlations, Mapping):
                raise OverrideError(
                    f"{name}.correlations must be a table like {{ BTCUSD = 0.6 }}, "
                    f"got {correlations!r}"
                )
            for other, rho in correlations.items():
                if not _is_number(rho):
                    raise OverrideError(
                        f"{name}.correlations.{other} must be a number, got {rho!r}"
                    )
        out[str(symbol).upper()] = dict(body)
    return out


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _imply_new_correlations(
    mat: np.ndarray, i: int, syms: list[str], edits: list[tuple[str, str, float]]
) -> None:
    """
    Fill the correlations a new instrument did not specify.

    The instrument is treated as a regression on the instruments it named:
    x = sum_j beta_j x_j + noise with beta = R_SS^-1 rho_S, which implies
    corr(x, k) = beta . R_Sk for every other instrument k. This keeps the
    matrix valid (a coin 0.6-correlated with BTC is also correlated with ETH)
    instead of defaulting unspecified pairs to 0.
    """
    named = {syms.index(b): rho for a, b, rho in edits if a == syms[i] and syms.index(b) < i}
    named.update({syms.index(a): rho for a, b, rho in edits if b == syms[i] and syms.index(a) < i})
    if not named:
        return
    s_idx = np.array(sorted(named))
    rho_s = np.array([named[j] for j in s_idx])
    beta = np.linalg.lstsq(mat[np.ix_(s_idx, s_idx)], rho_s, rcond=None)[0]
    implied = beta @ mat[s_idx, :i]
    mat[i, :i] = np.clip(implied, -0.99, 0.99)
    mat[:i, i] = mat[i, :i]
    mat[i, s_idx] = mat[s_idx, i] = rho_s


def apply_overrides(
    catalog: dict[MarketType, MarketConfig],
    overrides: dict[str, dict[str, Any]],
) -> dict[MarketType, MarketConfig]:
    """Return a new catalog with the overrides applied (the input is not modified)."""
    owner = {s: m for m, cfg in catalog.items() for s in cfg.symbols}
    instruments = {m: dict(cfg.instruments) for m, cfg in catalog.items()}
    order = {m: list(cfg.symbols) for m, cfg in catalog.items()}
    corr_edits: dict[MarketType, list[tuple[str, str, float]]] = {m: [] for m in catalog}

    for symbol, body in overrides.items():
        market = owner.get(symbol)
        if "market" in body:
            try:
                declared = MarketType(str(body["market"]).lower())
            except ValueError:
                raise OverrideError(f"{symbol}: unknown market {body['market']!r}") from None
            if market is not None and declared != market:
                raise OverrideError(
                    f"{symbol} already exists in the {market.value} market, not {declared.value}"
                )
            market = declared
        if market is None:
            raise OverrideError(
                f'{symbol} is a new instrument: set market = "crypto" | "forex" | "stocks"'
            )
        values: dict[str, Any] = {k: float(body[k]) for k in _FIELDS if k in body}
        try:
            if symbol in instruments[market]:
                instruments[market][symbol] = replace(instruments[market][symbol], **values)
            else:
                missing = [k for k in ("start_price", "volatility") if k not in values]
                if missing:
                    raise OverrideError(f"New instrument {symbol} needs {', '.join(missing)}")
                instruments[market][symbol] = InstrumentParams(symbol=symbol, **values)
                order[market].append(symbol)
                owner[symbol] = market
        except ValueError as e:
            raise OverrideError(f"{symbol}: {e}") from None
        for other, rho in dict(body.get("correlations", {})).items():
            corr_edits[market].append((symbol, other.upper(), float(rho)))

    out: dict[MarketType, MarketConfig] = {}
    for market, cfg in catalog.items():
        syms = order[market]
        if (
            syms == list(cfg.symbols)
            and not corr_edits[market]
            and instruments[market] == cfg.instruments
        ):
            out[market] = cfg
            continue
        n = len(syms)
        mat = np.eye(n)
        k = len(cfg.symbols)
        mat[:k, :k] = cfg.correlation_matrix
        for a, b, rho in corr_edits[market]:
            if b not in syms:
                raise OverrideError(
                    f"{a}: correlation target {b} is not a {market.value} instrument"
                )
            if not -1.0 < rho < 1.0:
                raise OverrideError(
                    f"{a}-{b}: correlation must be strictly between -1 and 1, got {rho}"
                )
        for i in range(k, n):
            _imply_new_correlations(mat, i, syms, corr_edits[market])
        for a, b, rho in corr_edits[market]:
            i, j = syms.index(a), syms.index(b)
            mat[i, j] = mat[j, i] = rho
        # Only the simulated series need a valid matrix: forex crosses are
        # derived from their anchors (ADR 0002), so the full forex matrix is
        # singular by construction.
        structure = (
            forex_structure(syms) if market == MarketType.FOREX else FactorStructure.identity(syms)
        )
        idx = np.array([syms.index(s) for s in structure.factors])
        block = mat[np.ix_(idx, idx)]
        if float(np.min(np.linalg.eigvalsh(block))) < 1e-8:
            # The user's own pairs hold if they can; the rest of the market gives way.
            position = {s: k for k, s in enumerate(structure.factors)}
            edited = np.zeros(block.shape, dtype=bool)
            for a, b, _ in corr_edits[market]:
                if a in position and b in position:
                    edited[position[a], position[b]] = edited[position[b], position[a]] = True
            repaired, kept = nearest_correlation(block, edited)
            moved = float(np.max(np.abs(repaired - block)[edited], initial=0.0))
            warnings.warn(
                f"{market.value}: overridden correlations are not consistent with the rest "
                "of the market; "
                + (
                    "the others were moved to the nearest valid correlation matrix"
                    if kept
                    else f"your values cannot all hold; moved by up to {moved:.2f} to the "
                    "nearest valid correlation matrix"
                ),
                skip_file_prefixes=PACKAGE_DIRS,
            )
            mat[np.ix_(idx, idx)] = repaired
        out[market] = MarketConfig(
            market_type=market,
            instruments={s: instruments[market][s] for s in syms},
            correlation_matrix=mat,
            symbol_order=syms,
        )
    return out
