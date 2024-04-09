"""A custom dataset sample that samples class-balanced batches"""

from typing import Any, Iterator

import numpy as np
import torch
import torch.distributed
from torch import Tensor
from torch.utils.data import IterableDataset, Sampler


def get_generator(seed: int | None = None) -> torch.Generator:
    """
    Returns a seeded (either manually or automatically) `torch.Generator`.

    Args:
        seed (int | None, optional):
    """
    generator = torch.Generator()
    if seed is None:
        generator.seed()
    else:
        generator.manual_seed(seed)
    return generator


def _choice(
    a: Tensor,
    n: int | None = None,
    generator: torch.Generator | None = None,
) -> Tensor:
    """
    Analogous to
    [`numpy.random.choice`](https://numpy.org/doc/stable/reference/random/generated/numpy.random.choice.html)
    except the selection is without replacement the selection distribution is
    uniform.

    Args:
        a (Tensor): Tensor to sample from.
        n (int | None, optional): Number of samples to draw. If `None`, returns
            a permutation of `a`
        generator (torch.Generator | None, optional):
    """
    idx = torch.randperm(len(a), generator=generator)
    return a[idx if n is None else idx[:n]]


class _Iterator(Iterator[list[int]]):
    """Iterator class for `BalancedBatchSampler`"""

    batch_size: int
    classes: Tensor
    generator: torch.Generator
    n_batches: int  # Number of batches **left** to generate
    n_classes_per_batch: int
    y: Tensor

    _idx: Tensor
    """
    Indices of entries of the dataset that are available to this sampler. In
    the non-distributed case, this is just `torch.arange(len(y))`. In the
    distributed case, this is `torch.arange(rank, len(y), world_size)`.
    """

    def __init__(
        self,
        y: Tensor,
        batch_size: int,
        n_classes_per_batch: int,
        n_batches: int,
        seed: int | None = None,
        world_size: int | None = None,
        rank: int | None = None,
    ):
        """
        Args:
            y (Tensor):
            batch_size (int):
            n_classes_per_batch (int):
            n_batches (int | None, optional): Defaults to
                `len(y) // batch_size`
            seed (int | None, optional):
            world_size (int | None, optional): Set this for distributed
                balanced sampling. You can find out the world size by calling
                `torch.distributed.get_world_size()`. If set, so should
                `rank`, otherwise both will be ignored.
            rank (int | None, optional): Set this for distributed
                balanced sampling. You can find out the global rank of the
                current node by calling `torch.distributed.get_global_rank()`.
                If set, so should `world_size`, otherwise both will be ignored.
        """
        self.batch_size = batch_size
        self.n_classes_per_batch = n_classes_per_batch
        self.generator = get_generator(seed)
        if world_size is not None and rank is not None:
            self._idx = torch.arange(rank, len(y), world_size)
        else:
            self._idx = torch.arange(len(y))
        self.y = y[self._idx]
        self.classes = torch.unique(self.y)
        self.n_batches = n_batches or (len(self._idx) // batch_size)
        if len(self.classes) < n_classes_per_batch:
            raise ValueError(
                "The number of classes per batch cannot exceed the actual "
                f"number of classes ({len(self.classes)})"
            )

    def __iter__(self) -> Iterator[list[int]]:
        return self

    def __next__(self) -> list[int]:
        """
        Returns:
            list[int]: A list of indices of length `self.batch_size`
        """
        if self.n_batches <= 0:
            raise StopIteration
        self.n_batches -= 1
        classes = _choice(
            self.classes, self.n_classes_per_batch, self.generator
        )
        idx = [
            _choice(
                self._idx[self.y == i],
                self.batch_size // self.n_classes_per_batch,
                self.generator,
            )
            for i in classes
        ]
        # If there's room left, add extra samples from the first class
        if reminder := self.batch_size % len(self.classes):
            idx += [
                _choice(
                    self._idx[self.y == classes[0]], reminder, self.generator
                )
            ]
        return torch.concat(idx).int().tolist()


class BalancedBatchSampler(Sampler[list[int]]):
    """
    A batch sampler where the classes are represented (roughly) equally in each
    batch.

        dataloader = DataLoader(
            dataset,
            batch_sampler=BalancedBatchSampler(
                dataset, batch_size=200, n_classes_per_batch=5
            ),
        )

    This sampler can't run in distributed mode (yet). If using with Pytorch
    Lightning, don't forget to construct your trainer with
    `use_distributed_sampler=False`.
    """

    batch_size: int
    n_batches: int
    n_classes_per_batch: int
    seed: int | None
    y: Tensor

    def __init__(
        self,
        y: IterableDataset | Tensor | np.ndarray,
        batch_size: int,
        n_classes_per_batch: int,
        n_batches: int | None = None,
        seed: int | None = None,
        label_key: Any = 1,
    ):
        """
        Args:
            y (IterableDataset | Tensor | np.ndarray): Either the whole dataset
                (in which case you might want to set `label_key` to make sure
                the labels are retrieved correctly) or the labels themselves.
            batch_size (int):
            n_classes_per_batch (int):
            n_batches (int | None, optional):
            seed (int | None, optional):
            label_key (Any, optional): Only needed if `y` is a dataset.
        """
        super().__init__()
        if isinstance(y, np.ndarray):
            self.y = Tensor(y)
        elif isinstance(y, IterableDataset):
            self.y = Tensor([e[label_key] for e in y])
        else:
            self.y = y
        self.batch_size = batch_size
        self.n_classes_per_batch = n_classes_per_batch
        self.seed = seed
        self.n_batches = n_batches or (len(self.y) // batch_size)

    def __len__(self) -> int:
        return self.n_batches

    def __iter__(self) -> Iterator[list[int]]:
        if torch.distributed.is_initialized():
            return _Iterator(
                self.y,
                batch_size=self.batch_size,
                n_classes_per_batch=self.n_classes_per_batch,
                n_batches=self.n_batches,
                seed=self.seed,
                world_size=torch.distributed.get_world_size(),
                rank=torch.distributed.get_rank(),
            )
        return _Iterator(
            self.y,
            batch_size=self.batch_size,
            n_classes_per_batch=self.n_classes_per_batch,
            n_batches=self.n_batches,
            seed=self.seed,
        )
