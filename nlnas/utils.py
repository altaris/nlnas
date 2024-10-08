"""Useful stuff."""

import os
from typing import Any, Callable, Literal

import numpy as np
import torch
from torch import Tensor, nn


def get_reasonable_n_jobs() -> int:
    """
    Gets a reasonable number of jobs for parallel processing. Reasonable means
    it's not going to slam your system (hopefully). See the implementation for
    the exact scheme.
    """
    n = os.cpu_count()
    if n is None:
        return 1
    if n <= 8:
        return n // 2
    return int(n * 2 / 3)


def make_tqdm(
    style: Literal["notebook", "console", "none"] | None = "console",
) -> Callable:
    """
    Returns the appropriate tqdm factory function based on the style. Note that
    if the style is `"none"` or `None`, a fake tqdm function is returned that is
    just the identity function. In particular, the usual `tqdm` methods like
    `set_postfix` cannot be used.

    Args:
        style (Literal['notebook', 'console', 'none'] | None, optional):
            Defaults to "console".
    """

    def _fake_tqdm(x: Any, *_, **__):
        return x

    if style is None or style == "none":
        f = _fake_tqdm
    elif style == "console":
        from tqdm import tqdm as f  # type: ignore
    elif style == "notebook":
        from tqdm.notebook import tqdm as f  # type: ignore
    else:
        raise ValueError(
            f"Unknown TQDM style '{style}'. Available styles are 'notebook', "
            "'console', or None"
        )
    return f


def pretty_print_submodules(
    module: nn.Module,
    exclude_non_trainable: bool = False,
    max_depth: int | None = None,
    _prefix: str = "",
    _current_depth: int = 0,
):
    """
    Recursively prints a module and its submodule in a hierarchical manner.

        >>> pretty_print_submodules(model, max_depth=4)
        model -> ResNetForImageClassification
        |-----resnet -> ResNetModel
        |     |------embedder -> ResNetEmbeddings
        |     |      |--------embedder -> ResNetConvLayer
        |     |      |        |--------convolution -> Conv2d
        |     |      |        |--------normalization -> BatchNorm2d
        |     |      |        |--------activation -> ReLU
        |     |      |--------pooler -> MaxPool2d
        |     |------encoder -> ResNetEncoder
        |     |      |-------stages -> ModuleList
        |     |      |       |------0 -> ResNetStage
        |     |      |       |------1 -> ResNetStage
        |     |      |       |------2 -> ResNetStage
        |     |      |       |------3 -> ResNetStage
        |     |------pooler -> AdaptiveAvgPool2d
        |-----classifier -> Sequential
        |     |----------0 -> Flatten
        |     |----------1 -> Linear

    Args:
        module (nn.Module):
        exclude_non_trainable (bool, optional): Defaults to `True`.
        max_depth (int | None, optional): Defaults to `None`, which means no
            depth cap.
        _prefix (str, optional): Don't use.
        _current_depth (int, optional): Don't use.
    """
    if max_depth is not None and _current_depth > max_depth:
        return
    for k, v in module.named_children():
        if exclude_non_trainable and len(list(v.parameters())) == 0:
            continue
        print(_prefix + k, "->", v.__class__.__name__)
        p = _prefix.replace("-", " ") + "|" + ("-" * len(k))
        pretty_print_submodules(
            module=v,
            exclude_non_trainable=exclude_non_trainable,
            max_depth=max_depth,
            _prefix=p,
            _current_depth=_current_depth + 1,
        )


def to_array(x: Any, **kwargs) -> np.ndarray:
    """
    Converts an array-like object to a numpy array. If the input is a tensor,
    it is detached and moved to the CPU first
    """
    if isinstance(x, Tensor):
        return x.detach().cpu().numpy()
    return x if isinstance(x, np.ndarray) else np.array(x, **kwargs)


def to_tensor(x: Any, **kwargs) -> Tensor:
    """
    Converts an array-like object to a torch tensor. If `x` is already a tensor,
    then it is returned as is. In particular, if `x` is a tensor this method is
    differentiable and its derivative is the identity function.
    """
    return x if isinstance(x, Tensor) else torch.tensor(x, **kwargs)
