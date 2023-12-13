"""
A distributed implementation of
[`scipy.spatial.distance.pdist`](https://scipy.github.io/devdocs/reference/generated/scipy.spatial.distance.pdist.html#scipy.spatial.distance.pdist)

"""

import re
from glob import glob
from pathlib import Path
from typing import Callable, Tuple

import numpy as np
from joblib import Parallel, delayed
from loguru import logger as logging
from safetensors import numpy as st
from scipy.spatial.distance import cdist


def _guarded_cdist(
    a: np.ndarray,
    b: np.ndarray,
    path: Path,
    metric: str | Callable[..., float] | None = None,
) -> np.ndarray:
    """
    Guarded cdist. Unlike the original cdist though, `a` and `b` do not have to
    be 2D arrays.
    """
    if path.is_file():
        return st.load_file(path)["cdist"]
    a, b = a.reshape(a.shape[0], -1), b.reshape(b.shape[0], -1)
    c = cdist(a, b, metric=metric)
    st.save_file({"cdist": c}, path)
    return c


def _pdist_merge_chunks(
    blocks: dict[Tuple[int, int], np.ndarray], n_bins: int
) -> np.ndarray:
    """
    Merges a dict of chunks into a full distance matrix. The input dict indexes
    the chunks by a tuple containing the vertical and horizontal indices.

    TODO:
        Technically, `n_bins` can be calculated from `blocks`...
    """
    return np.concatenate(
        [
            np.concatenate(
                [
                    blocks[(i, j)] if i <= j else blocks[(j, i)].T
                    for j in range(n_bins)
                ],
                axis=1,
            )
            for i in range(n_bins)
        ],
        axis=0,
    )


def load_pdist(path: str | Path) -> np.ndarray:
    """
    Loads a distance matrix from a directory containing all the chunks
    generated by `nlnas.pdist.pdist`.
    """
    logging.debug("Loading distance matrix from chunk directory '{}'", path)
    d, idx, r = {}, [], r".*/(\d+)\.(\d+)\.npz"
    for c in glob(str(Path(path) / "*.npz")):
        if m := re.match(r, c):
            i, j = int(m.group(1)), int(m.group(2))
            d[(i, j)] = st.load_file(c)["cdist"]
            idx += [i, j]
    n_bins = max(idx) + 1
    for i in range(n_bins):
        for j in range(i, n_bins):
            if (i, j) not in d:
                raise ValueError(
                    f"Distance matrix chunk directory '{path}' does not "
                    f"contain chunk ({i}, {j}) despite n_bins={n_bins}."
                )
    dm = _pdist_merge_chunks(d, n_bins)
    logging.debug(
        "Loaded distance matrix of shape {} "
        "(n_chunks={}, chunk_shape={}, n_bins={})",
        dm.shape,
        len(d),
        d[(0, 0)].shape,
        n_bins + 1,
    )
    return dm


def pdist(
    x: np.ndarray,
    chunk_size: int,
    chunk_path: str | Path,
    metric: str | Callable | None = None,
    n_jobs: int = -1,
) -> np.ndarray:
    """
    A distributed implementation of
    [`pdist`](https://scipy.github.io/devdocs/reference/generated/scipy.spatial.distance.pdist.html#scipy.spatial.distance.pdist)

    Creates a directory `<path>/pdist` that will contain a bunch artefacts.
    Each correspond to a `chunk_size * chunk_size` submatrix in the global
    distance matrix. For obvious optimization reasons, `i` is always `<= j`.
    Each `.npz` file contains the following:

    * `cdist`: The distance matrix chunk (in condensed form).

    Warning:
        `chunk_size` must divide the length of `x`
    """
    chunk_path = Path(chunk_path)
    chunk_path.mkdir(parents=True, exist_ok=True)
    if metric is None:
        metric, metric_name = "euclidean", "euclidean"
    elif isinstance(metric, str):
        metric_name = metric
    else:
        metric_name = "<callable>"
    n_bins = int(x.shape[0] / chunk_size)
    logging.debug(
        "Computing distance matrix for metric '{}'; chunks_dir='{}', "
        "chunk_size={}, n_bins={}",
        metric_name,
        chunk_path,
        chunk_size,
        n_bins,
    )
    x_chunks = np.array_split(x, n_bins)
    ij = [(i, j) for i in range(n_bins) for j in range(i, n_bins)]
    jobs = [
        delayed(_guarded_cdist)(
            x_chunks[i], x_chunks[j], chunk_path / f"{i}.{j}.npz", metric
        )
        for i, j in ij
    ]
    r = Parallel(n_jobs=n_jobs)(jobs)
    return _pdist_merge_chunks(dict(zip(ij, r)), n_bins)
