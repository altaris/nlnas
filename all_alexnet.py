from itertools import product
from pathlib import Path

import pytorch_lightning as pl
import torchvision.transforms as tvtr
from loguru import logger as logging

from nlnas.classifier import TorchvisionClassifier
from nlnas.logging import setup_logging
from nlnas.nlnas import train_and_analyse_all
from nlnas.training import best_checkpoint_path, train_model_guarded
from nlnas.tv_dataset import DEFAULT_DATALOADER_KWARGS, TorchvisionDataset
from nlnas.transforms import cifar10_normalization


def main():
    pl.seed_everything(0)
    model_names = ["alexnet"]
    analysis_submodules = [
        "model.0.features.0",
        "model.0.features.3",
        "model.0.features.6",
        "model.0.features.8",
        "model.0.features.10",
        # "model.0.features",
        "model.0.classifier.1",
        "model.0.classifier.4",
        "model.0.classifier.6",
        # "model.0.classifier",
    ]
    dataset_names = [
        # "mnist",
        # "kmnist",
        # "fashionmnist",
        "cifar10",
        "cifar100",
    ]
    transform = tvtr.Compose(
        [
            tvtr.RandomCrop(32, padding=4),
            tvtr.RandomHorizontalFlip(),
            tvtr.ToTensor(),
            cifar10_normalization(),
            tvtr.Resize([64, 64], antialias=True),
        ]
    )
    for m, d in product(model_names, dataset_names):
        try:
            output_dir = Path("out") / m / d
            dataloader_kwargs = DEFAULT_DATALOADER_KWARGS.copy()
            dataloader_kwargs["batch_size"] = 2048
            datamodule = TorchvisionDataset(
                d,
                transform=transform,
                dataloader_kwargs=dataloader_kwargs,
            )
            model = TorchvisionClassifier(
                model_name=m,
                n_classes=datamodule.n_classes,
                input_shape=datamodule.image_shape,
            )
            train_and_analyse_all(
                model=model,
                submodule_names=analysis_submodules,
                dataset=datamodule,
                output_dir=output_dir,
                model_name=m,
            )
        except KeyboardInterrupt:
            return
        except:
            logging.exception(":sad trombone:")


if __name__ == "__main__":
    setup_logging()
    main()
