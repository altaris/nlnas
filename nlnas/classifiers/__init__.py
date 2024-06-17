"""Classifier models and related stuff"""

from .base import BaseClassifier, full_dataset_latent_clustering
from .huggingface import HuggingFaceClassifier
from .torchvision import TorchvisionClassifier
from .wrapped import WrappedClassifier
