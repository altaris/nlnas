"""Latent clustering correction"""

# pylint: disable=duplicate-code

from datetime import datetime, timedelta
from pathlib import Path

import turbo_broccoli as tb

from .classifiers import HuggingFaceClassifier
from .datasets import HuggingFaceDataset
from .finetune import make_trainer
from .logging import r0_info
from .training import checkpoint_ves


def correct(
    model_name: str,
    ckpt_path: Path,
    dataset_name: str,
    output_dir: Path,
    correction_submodules: list[str],
    correction_weight: float = 1e-3,
    max_epochs: int = 100,
    batch_size: int = 64,
    train_split: str = "train",
    val_split: str = "val",
    test_split: str = "test",
    image_key: str = "image",
    label_key: str = "label",
    logit_key: str = "logits",
    head_name: str | None = None,
):
    """
    Performs latent clustering correction on a pretrained model.

    Args:
        model_name (str):
        ckpt_path (Path):
        dataset_name (str):
        output_dir (Path):
        correction_submodules (list[str]):
        correction_weight (float, optional):
        max_epochs (int, optional):
        batch_size (int, optional):
        train_split (str, optional):
        val_split (str, optional):
        test_split (str, optional):
        image_key (str, optional):
        label_key (str, optional):
        logit_key (str, optional):
        head_name (str | None, optional):
    """
    _dataset_name = dataset_name.replace("/", "-")
    _model_name = model_name.replace("/", "-")
    _output_dir = output_dir / _dataset_name / _model_name
    _output_dir.mkdir(parents=True, exist_ok=True)

    dataset = HuggingFaceDataset(
        dataset_name=dataset_name,
        fit_split=train_split,
        val_split=val_split,
        test_split=test_split,
        label_key=label_key,
        image_processor=model_name,
        train_dl_kwargs={
            "batch_size": batch_size,
            "num_workers": 16,
            "persistent_workers": True,
            "pin_memory": False,
        },
    )
    n_classes = dataset.n_classes()

    model = HuggingFaceClassifier(
        model_name=model_name,
        n_classes=n_classes,
        head_name=head_name,
        image_key=image_key,
        label_key=label_key,
        logit_key=logit_key,
        optimizer="adam",
        optimizer_kwargs={
            "lr": 5e-5,
            "weight_decay": 0,
            "betas": (0.9, 0.999),
            "eps": 1e-8,
        },
        scheduler="linearlr",
        cor_weight=correction_weight,
        cor_submodules=correction_submodules,
    )
    # pylint: disable=no-value-for-parameter
    model.model = HuggingFaceClassifier.load_from_checkpoint(ckpt_path).model
    r0_info("Loaded checkpoint '{}'", ckpt_path)

    trainer = make_trainer(_model_name, _output_dir, max_epochs)
    start = datetime.now()
    trainer.fit(model, dataset)
    fit_time = datetime.now() - start
    r0_info("Finished correction in {}", fit_time)

    ckpt = Path(trainer.checkpoint_callback.best_model_path)  # type: ignore
    ckpt = ckpt.relative_to(output_dir)
    v, e, s = checkpoint_ves(ckpt)
    r0_info("Best checkpoint path: '{}'", ckpt)
    r0_info("version={}, best_epoch={}, n_steps={}", v, e, s)

    test_results = trainer.test(model, dataset)

    document = {
        "model": {"name": model_name},
        "dataset": {
            "name": dataset_name,
            "n_classes": n_classes,
            "train_split": train_split,
            "val_split": val_split,
            "test_split": test_split,
            "image_key": image_key,
            "label_key": label_key,
            "batch_size": batch_size,
        },
        "correction": {
            "hparams": dict(model.hparams),
            "epochs": max_epochs,
            "correction_submodules": correction_submodules,
            "correction_weight": correction_weight,
            "best_checkpoint": {
                "path": str(ckpt),
                "version": v,
                "best_epoch": e,
                "n_steps": s,
            },
            "time": fit_time / timedelta(seconds=1),
            "test": test_results,
        },
    }
    tb.save_json(document, _output_dir / "results.json")
