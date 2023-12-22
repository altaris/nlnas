"""
A torchvision image classifier wrapped inside a
[`LightningModule`](https://lightning.ai/docs/pytorch/stable/common/lightning_module.html)
"""

import warnings
from itertools import chain
from pathlib import Path
from typing import Any, Iterable, Literal

import pytorch_lightning as pl
import torch
import torchmetrics
from loguru import logger as logging
from torch import Tensor, nn
from torch.utils.data import DataLoader
from torch.utils.hooks import RemovableHandle
from torchvision.models import get_model
from tqdm import tqdm

from nlnas.clustering import (
    class_otm_matching,
    louvain_communities,
    louvain_loss,
)

from .separability import gdv, label_variation, mean_ggd
from .utils import best_device


def _make_lazy_linear(*args, **kwargs) -> nn.LazyLinear:
    """
    Constructs a
    [`LazyLinear`](https://pytorch.org/docs/stable/generated/torch.nn.LazyLinear.html)
    layer but hides the following warning:

        [...]torch/nn/modules/lazy.py:180: UserWarning: Lazy modules are a new
        feature under heavy development so changes to the API or functionality
        can happen at any moment.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return nn.LazyLinear(*args, **kwargs)


class Classifier(pl.LightningModule):
    """Classifier model with some extra features"""

    n_classes: int
    sep_submodules: list[str]
    sep_score: Literal["gdv", "lv", "ggd"] | None
    sep_weight: float

    def __init__(
        self,
        n_classes: int,
        sep_submodules: list[str] | None = None,
        sep_score: Literal["gdv", "lv", "ggd"] | None = None,
        sep_weight: float = 1e-1,
        **kwargs: Any,
    ) -> None:
        """
        Args:
            n_classes (int):
            sep_submodules (list[str] | None, optional): Submodules to consider
                for the latent separation score
            sep_score (Literal["gdv", "lv", "gdd"], optional): Type of
                separation score, either
                - `gdv` for the Generalized Discrimination Value (see
                  `nlnas.separability.gdv`),
                - `lv` for Label Variation (see `nlnas.separability.lv`),
                - or `ggd` for Geodesic Grassmanian Distance
                  (see `nlnas.separability.ggd`).
            sep_weight (float, optional): Weight of the separation score.
                Ignored if `sep_submodules` is left to `None`
        """
        super().__init__(**kwargs)
        self.save_hyperparameters()
        self.n_classes = n_classes
        self.sep_submodules = sep_submodules or []
        self.sep_score, self.sep_weight = sep_score, sep_weight

    def _evaluate(self, batch, stage: str | None = None) -> Tensor:
        """Self-explanatory"""
        x, y = batch
        y = y.to(self.device)

        output_dict: dict[str, Tensor] = {}
        logits = self.forward_intermediate(
            x, self.sep_submodules, output_dict, keep_gradients=True
        )
        loss = nn.functional.cross_entropy(logits, y.long())

        if self.sep_score and self.sep_submodules:
            if self.sep_score == "gdv":
                sep_loss = torch.stack(
                    [gdv(v, y) for v in output_dict.values()]
                ).mean()
            elif self.sep_score == "lv":
                sep_loss = torch.stack(
                    [
                        label_variation(
                            v, y.to(v), k=10, n_classes=self.n_classes
                        )
                        for v in output_dict.values()
                    ]
                ).mean()
            elif self.sep_score == "ggd":
                sep_loss = -torch.stack(
                    [mean_ggd(v.flatten(1), y) for v in output_dict.values()]
                ).mean()
            else:
                raise RuntimeError(
                    f"Unknown separation score type '{self.sep_score}'."
                )
        else:
            sep_loss = torch.tensor(0.0)

        if stage:
            self.log(f"{stage}/loss", loss, prog_bar=True, sync_dist=True)
        if stage == "train" and self.sep_score and self.sep_submodules:
            self.log(
                f"{stage}/{self.sep_score}",
                sep_loss,
                prog_bar=True,
                sync_dist=True,
            )
        if stage and best_device() != "mps":
            # NotImplementedError: The operator 'aten::_unique2' is not
            # currently implemented for the MPS device. If you want this op to
            # be added in priority during the prototype phase of this feature,
            # please comment on
            # https://github.com/pytorch/pytorch/issues/77764. As a temporary
            # fix, you can set the environment variable
            # `PYTORCH_ENABLE_MPS_FALLBACK=1` to use the CPU as a fallback for
            # this op. WARNING: this will be slower than running natively on
            # MPS.
            acc = torchmetrics.functional.accuracy(
                torch.argmax(logits, dim=1),
                y,
                "multiclass",
                num_classes=self.n_classes,
                top_k=1,
            )
            self.log(f"{stage}/acc", acc, prog_bar=True, sync_dist=True)
        return loss + self.sep_weight * sep_loss

    def configure_optimizers(self):
        """Override"""
        return torch.optim.Adam(self.parameters())

    def forward_intermediate(
        self,
        x: Tensor,
        submodules: list[str],
        output_dict: dict,
        keep_gradients: bool = False,
    ) -> Tensor:
        """
        Runs the model and collects the output of specified submodules. The
        intermediate outputs are stored in `output_dict` under the
        corresponding submodule name. In particular, this method has side
        effects.

        Args:
            x (Tensor):
            submodules (list[str]):
            output_dict (dict):
            keep_gradients (bool, optional): If `True`, the tensors in
                `output_dict` keep their gradients (if they had some on the
                first place). If `False`, they are detached and moved to the
                CPU.
        """

        def create_hook(key: str):
            def hook(_model: nn.Module, _args: Any, output: Tensor) -> None:
                x = output if keep_gradients else output.detach().cpu()
                output_dict[key] = x

            return hook

        handles: list[RemovableHandle] = []
        for name in submodules:
            submodule = self.get_submodule(name)
            handles.append(submodule.register_forward_hook(create_hook(name)))
        y = self(x)
        for h in handles:
            h.remove()
        return y

    # pylint: disable=arguments-differ
    def test_step(self, batch, *_, **__):
        """Override"""
        return self._evaluate(batch, "test")

    # pylint: disable=arguments-differ
    def training_step(self, batch, *_, **__) -> Any:
        """Override"""
        return self._evaluate(batch, "train")

    def validation_step(self, batch, *_, **__):
        """Override"""
        return self._evaluate(batch, "val")


class TorchvisionClassifier(Classifier):
    """
    A torchvision image classifier with some extra features

    See also:
        https://pytorch.org/vision/stable/models.html#classification
    """

    model: nn.Module

    def __init__(
        self,
        model_name: str,
        n_classes: int,
        input_shape: Iterable[int] | None = None,
        model_config: dict[str, Any] | None = None,
        add_final_fc: bool = False,
        **kwargs,
    ) -> None:
        """
        Args:
            model_name (str): Torchvision model name in lower case. See also
                https://pytorch.org/vision/stable/generated/torchvision.models.list_models.html
            n_classes (int):
            input_shape (Iterable[int], optional): If give, a example run is
                performed after construction. This can be useful to see the
                model's computation graph on tensorboard.
            model_config (dict[str, Any], optional):
            add_final_fc (bool): If true, adds a final dense layer which
                outputs `n_classes` logits
        """
        super().__init__(n_classes=n_classes, **kwargs)
        self.save_hyperparameters()
        modules = [get_model(model_name, **(model_config or {}))]
        if add_final_fc:
            modules.append(_make_lazy_linear(n_classes))
        self.model = nn.Sequential(*modules)

        if input_shape is not None:
            self.example_input_array = torch.zeros([1] + list(input_shape))
            self.model.eval()
            self.forward(self.example_input_array)

    # pylint: disable=arguments-differ
    def forward(self, x: Tensor, *_, **__) -> Tensor:
        """Override"""
        return self.model(x.to(self.device))  # type: ignore


class ClusterCorrectionTorchvisionClassifier(TorchvisionClassifier):
    cc_optimizer: torch.optim.Optimizer

    def __init__(
        self,
        model_name: str,
        n_classes: int,
        input_shape: Iterable[int] | None = None,
        model_config: dict[str, Any] | None = None,
        add_final_fc: bool = False,
        cc_lr: float = 1e-4,
        **kwargs,
    ) -> None:
        super().__init__(
            model_name,
            n_classes,
            input_shape,
            model_config,
            add_final_fc,
            **kwargs,
        )
        self.save_hyperparameters()

    def configure_optimizers(self):
        self.cc_optimizer = torch.optim.SGD(
            list(
                chain(
                    *[
                        self.get_submodule(sm).parameters()
                        for sm in self.sep_submodules
                    ]
                )
            ),
            lr=self.hparams["cc_lr"],
        )
        return super().configure_optimizers()

    def on_train_epoch_end(self) -> None:
        """Override"""
        tdl = self.trainer.train_dataloader
        if tdl is None:
            logging.warning(
                "Module's training does not have a train_dataloader"
            )
            return
        # TODO: use params of tdl
        dl = DataLoader(dataset=tdl.dataset, batch_size=2048)
        progress = tqdm(dl, desc="Cluster correction", leave=False)
        for x, y_true in progress:
            out: dict[str, Tensor] = {}
            self.forward_intermediate(
                x, self.sep_submodules, out, keep_gradients=True
            )
            losses: list[Tensor] = []
            for z in out.values():
                _, y_louvain, _, _ = louvain_communities(
                    z.flatten(1).cpu().detach().numpy()
                )
                # For testing
                # y_louvain = torch.randint_like(y_true, high=15).cpu().numpy()
                matching = class_otm_matching(y_true.numpy(), y_louvain)
                losses.append(
                    louvain_loss(z, y_true.numpy(), y_louvain, matching)
                )
            loss = torch.stack(losses).mean()
            loss.backward()
            self.cc_optimizer.step()
            self.cc_optimizer.zero_grad()
            progress.set_postfix({"train/lou": float(loss.round(decimals=2))})


class TruncatedClassifier(Classifier):
    """
    Given a `Classifier` and the name of one of its submodule, wrapping it in a
    `TruncatedClassifier` produces a "truncated model" that does the following:
    * evaluate an input `x` on the base classifier,
    * take the latent representation outputed by the specified submodule,
    * flatten it and pass it through a final (trainable) head.
    """

    model: TorchvisionClassifier
    fc: nn.Module
    handle: RemovableHandle
    _out: Tensor

    def __init__(
        self,
        model: TorchvisionClassifier | str | Path,
        truncate_after: str,
        freeze_base_model: bool = True,
        **kwargs: Any,
    ) -> None:
        """
        Args:
            model (TorchvisionClassifier | str | Path):
            truncate_after (str): e.g. `model.0.classifier.4`
            freeze_base_model (bool, optional):
        """
        _model = (
            model
            if isinstance(model, nn.Module)
            else TorchvisionClassifier.load_from_checkpoint(str(model))
        )  # Need to make sure the model is loaded to get hparams first
        n_classes = _model.hparams["n_classes"]
        input_shape = _model.hparams["input_shape"]
        kwargs["n_classes"] = n_classes

        super().__init__(**kwargs)
        self.save_hyperparameters()

        self.model = _model
        self.fc = _make_lazy_linear(n_classes).to(self.model.device)
        self.model.requires_grad_(not freeze_base_model)

        def _hook(_model: nn.Module, _args: Any, output: Tensor) -> None:
            self._out = output

        submodule = self.model.get_submodule(truncate_after)
        self.handle = submodule.register_forward_hook(_hook)

        self.example_input_array = torch.zeros([1] + list(input_shape))
        self.model.eval()
        self.forward(self.example_input_array)

    # pylint: disable=arguments-differ
    def forward(self, x: Tensor, *_, **__) -> Tensor:
        """Override"""
        self.model(x.to(self.device))  #  type: ignore
        return self.fc(self._out.flatten(1))
