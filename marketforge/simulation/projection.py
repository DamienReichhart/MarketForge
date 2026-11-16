# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""From simulated factors to published instruments, in a shape BLAS rounds consistently."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from marketforge.simulation.factors import FactorStructure
from marketforge.simulation.kernels import project_signed


@dataclass(frozen=True)
class Projection:
    """
    How the selected instruments derive from the active factors.

    ``factors`` are the indices (into the market's factors) of the factors that
    are simulated. Instruments are either the factors themselves (crypto,
    stocks), a signed sum of at most two of them with weights +-1 (every
    built-in forex pair), or, for user-defined forex structures beyond that,
    a general projection that falls back to the full matrix product.
    """

    factors: np.ndarray  # (Fa,) indices into the market's factors
    kind: str  # "identity" | "signed" | "matrix"
    index: np.ndarray  # signed: (I, 2) positions in the active factors, -1 = unused
    sign: np.ndarray  # signed: (I, 2)
    weights_t: np.ndarray  # matrix: (F, I_all) full transposed weights
    instruments: np.ndarray  # matrix: (I,) columns of the full product to keep
    anchors: tuple[tuple[int, int], ...]  # (column, active factor position)
    crosses: tuple[tuple[int, np.ndarray, np.ndarray, np.ndarray], ...]
    # crosses: (column, active factor positions, weights, correlation sub-matrix)

    @classmethod
    def build(
        cls, structure: FactorStructure, inst: np.ndarray, correlation: np.ndarray
    ) -> Projection:
        empty = np.empty((0, 2), dtype=np.int64)
        if structure.is_identity:
            return cls(inst, "identity", empty, empty.astype(float), np.empty((0, 0)), inst, (), ())
        weights = structure.weights[inst]  # (I, F)
        nonzero = [np.nonzero(row)[0] for row in weights]
        simple = all(
            nz.size <= 2 and np.all(np.abs(row[nz]) == 1.0)
            for row, nz in zip(weights, nonzero, strict=True)
        )
        if simple:
            factors = np.unique(np.concatenate(nonzero))
            kind = "signed"
        else:
            factors = np.arange(structure.weights.shape[1])
            kind = "matrix"
        pos = {int(f): p for p, f in enumerate(factors)}
        index = np.full((inst.size, 2), -1, dtype=np.int64)
        sign = np.zeros((inst.size, 2))
        anchors: list[tuple[int, int]] = []
        crosses: list[tuple[int, np.ndarray, np.ndarray, np.ndarray]] = []
        for j, (row, nz) in enumerate(zip(weights, nonzero, strict=True)):
            if kind == "signed":
                index[j, : nz.size] = [pos[int(f)] for f in nz]
                sign[j, : nz.size] = row[nz]
            if nz.size == 1 and row[nz[0]] == 1.0:
                anchors.append((j, pos[int(nz[0])]))
            else:
                local = np.array([pos[int(f)] for f in nz], dtype=np.intp)
                crosses.append((j, local, row[nz], correlation[np.ix_(nz, nz)]))
        return cls(
            factors,
            kind,
            index,
            sign,
            structure.weights.T.copy() if kind == "matrix" else np.empty((0, 0)),
            inst,
            tuple(anchors),
            tuple(crosses),
        )

    def apply(self, x: np.ndarray) -> np.ndarray:
        """Instrument values from active-factor values (rows = minutes)."""
        if self.kind == "identity":
            return x
        if self.kind == "signed":
            return project_signed(x, self.index, self.sign)
        return np.ascontiguousarray((x @ self.weights_t)[:, self.instruments])

    def sigma(self, factor_sigma: np.ndarray) -> np.ndarray:
        """Per-instrument std from active-factor stds (rows = minutes)."""
        if self.kind == "identity":
            return factor_sigma
        out = np.empty((factor_sigma.shape[0], self.instruments.size))
        for j, p in self.anchors:
            out[:, j] = factor_sigma[:, p]
        for j, idx, w, corr in self.crosses:
            s = factor_sigma[:, idx] * w
            out[:, j] = np.sqrt(np.maximum(np.einsum("nj,jk,nk->n", s, corr, s), 0.0))
        return out


@dataclass(frozen=True)
class SessionShape:
    """Where a day's simulated minutes sit inside its whole trading session.

    Row-wise matrix products are evaluated on session-shaped arrays so that
    BLAS sees the same shape for a minute whether or not the requested range
    cuts its day short (see :meth:`MarketSimulator.simulate_day`).
    """

    rows: np.ndarray  # minute-of-day indices of the whole session
    positions: np.ndarray | None  # positions of the simulated minutes in it; None = all

    @classmethod
    def of(cls, session_rows: np.ndarray, simulated_rows: np.ndarray) -> SessionShape:
        if simulated_rows.size == session_rows.size:
            return cls(simulated_rows, None)
        return cls(session_rows, np.searchsorted(session_rows, simulated_rows))

    def rows_of(self, session_values: np.ndarray) -> np.ndarray:
        """The simulated minutes' rows of a session-shaped array."""
        if self.positions is None:
            return session_values
        return np.ascontiguousarray(session_values[self.positions])

    def apply(self, func: Callable[[np.ndarray], np.ndarray], values: np.ndarray) -> np.ndarray:
        """``func(values)``, evaluated with ``values`` embedded in the session's shape."""
        if self.positions is None:
            return func(values)
        padded = np.zeros((self.rows.size, *values.shape[1:]), dtype=values.dtype)
        padded[self.positions] = values
        return self.rows_of(func(padded))
