"""Steady-state 2.5D finite-volume heat conduction for a two-layer board model.

Each grid cell inside the outline has a top node (F.Cu side) and a bottom node
(B.Cu side). Per cell and layer:

  sheet conductance  S = k_cu * t_cu * copper_fraction + k_xy * t_board / 2   [W/K]
  lateral link       G = harmonic_mean(S_i, S_j)  (square cells)
  vertical link      G = k_z * A / t_board + k_cu * pi * d * t_plating / t_board per barrel
  convection         G = h * A to ambient on each face

which discretizes  div(S grad T) - h (T - T_amb) + q = 0  per layer. Results are
estimates of board temperatures under stated assumptions, not measurements.
"""

from tools.thermal.geometry import _np


def solve(mask, sheet_top, sheet_bottom, vertical, h_top, h_bottom, power_top, power_bottom, cell_m, ambient):
    """Solve for (T_top, T_bottom) in °C; arrays shaped like `mask` (NaN outside).

    sheet_*: W/K per cell, vertical: W/K per cell, h_*: W/(m²K), power_*: W per cell.
    """
    np = _np()
    from scipy.sparse import coo_matrix
    from scipy.sparse.linalg import spsolve

    ny, nx = mask.shape
    idx = -np.ones(mask.shape, dtype=np.int64)
    n = int(mask.sum())
    idx[mask] = np.arange(n)
    area = cell_m * cell_m
    rows, cols, vals = [], [], []
    diag = np.zeros(2 * n)

    def couple(a, b, g):
        rows.extend([a, b])
        cols.extend([b, a])
        vals.extend([-g, -g])
        np.add.at(diag, a, g)
        np.add.at(diag, b, g)

    for layer, sheet in ((0, sheet_top), (1, sheet_bottom)):
        off = layer * n
        for axis in (0, 1):  # neighbours along y, then x
            a_sl = (slice(0, ny - 1), slice(None)) if axis == 0 else (slice(None), slice(0, nx - 1))
            b_sl = (slice(1, ny), slice(None)) if axis == 0 else (slice(None), slice(1, nx))
            both = mask[a_sl] & mask[b_sl]
            s1, s2 = sheet[a_sl][both], sheet[b_sl][both]
            couple(idx[a_sl][both] + off, idx[b_sl][both] + off, 2 * s1 * s2 / (s1 + s2))
    couple(np.arange(n), np.arange(n) + n, vertical[mask])
    conv = np.concatenate([np.full(n, h_top * area), np.full(n, h_bottom * area)])
    diag += conv
    rows.append(np.arange(2 * n))
    cols.append(np.arange(2 * n))
    vals.append(diag)
    A = coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
                   shape=(2 * n, 2 * n)).tocsr()
    p = np.concatenate([power_top[mask], power_bottom[mask]])
    rise = spsolve(A, p)
    residual = float(np.abs(A @ rise - p).max())
    out = []
    for layer in (0, 1):
        field = np.full(mask.shape, np.nan)
        field[mask] = ambient + rise[layer * n:(layer + 1) * n]
        out.append(field)
    lost = float((conv * rise).sum())
    return {"top": out[0], "bottom": out[1], "residual_w": residual, "power_in_w": float(p.sum()),
            "power_out_w": lost, "unknowns": 2 * n}
