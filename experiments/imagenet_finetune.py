from pathlib import Path

import pytorch_lightning as pl
from loguru import logger as logging
from torchvision.models import AlexNet_Weights, ResNet18_Weights

from nlnas.classifier import TorchvisionClassifier
from nlnas.imagenet import ImageNet
from nlnas.logging import setup_logging
from nlnas.training import train_model_guarded
from nlnas.utils import best_device

# IMAGENET_DOWNLOAD_PATH = Path.home() / "torchvision" / "datasets" / "imagenet"
IMAGENET_DOWNLOAD_PATH = Path.home() / "torchvision" / "imagenet"


def main():
    pl.seed_everything(0)
    experiments = [
        {
            "model_name": "resnet18",
            "weights": ResNet18_Weights.IMAGENET1K_V1,
            "correction_submodules": [
                "model.0.layer3",
                "model.0.layer4",
                # "model.0.fc",
            ],
        },
        {
            "model_name": "alexnet",
            "weights": AlexNet_Weights.IMAGENET1K_V1,
            "correction_submodules": [
                "model.0.classifier.1",
                "model.0.classifier.4",
                "model.0.classifier.6",
            ],
        },
        # {
        #     "model_name": "vit_b_16",
        #     "weights": ViT_B_16_Weights.IMAGENET1K_SWAG_E2E_V1,
        #     "correction_submodules": [
        #         # "model.0.encoder.layers.encoder_layer_0.mlp",
        #         # "model.0.encoder.layers.encoder_layer_1.mlp",
        #         # "model.0.encoder.layers.encoder_layer_2.mlp",
        #         # "model.0.encoder.layers.encoder_layer_3.mlp",
        #         # "model.0.encoder.layers.encoder_layer_4.mlp",
        #         # "model.0.encoder.layers.encoder_layer_5.mlp",
        #         # "model.0.encoder.layers.encoder_layer_6.mlp",
        #         # "model.0.encoder.layers.encoder_layer_7.mlp",
        #         # "model.0.encoder.layers.encoder_layer_8.mlp",
        #         # "model.0.encoder.layers.encoder_layer_9.mlp",
        #         "model.0.encoder.layers.encoder_layer_10.mlp",
        #         "model.0.encoder.layers.encoder_layer_11.mlp",
        #         # "model.0.heads",
        #     ],
        # },
    ]
    weight_exponent, batch_size, k = 3, 2048, 5
    for exp in experiments:
        try:
            exp_name = (
                exp["model_name"]
                + f"_finetune_l{k}_b{batch_size}_1e-{weight_exponent}"
            )
            output_dir = Path("out") / exp_name / "imagenet"
            datamodule = ImageNet(
                transform=exp["weights"].transforms(),
                download_path=IMAGENET_DOWNLOAD_PATH,
            )
            model = TorchvisionClassifier(
                exp["model_name"],
                n_classes=1000,
                model_config={"weights": exp["weights"]},
                cor_type="louvain",
                cor_weight=10 ** (-weight_exponent),
                cor_submodules=exp["correction_submodules"],
                cor_kwargs={"k": k},
            )
            model = model.to(best_device())
            train_model_guarded(
                model,
                datamodule,
                output_dir / "model",
                name=exp_name,
                max_epochs=512,
            )
        # except:
        #     raise
        except (KeyboardInterrupt, SystemExit):
            return
        except:
            logging.exception(":sad trombone:")


if __name__ == "__main__":
    setup_logging()
    main()
