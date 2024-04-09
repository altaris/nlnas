# NLNAS

![Python 3](https://img.shields.io/badge/python-3-blue?logo=python)
[![License](https://img.shields.io/badge/license-MIT-green)](https://choosealicense.com/licenses/mit/)
[![Code style](https://img.shields.io/badge/style-black-black)](https://pypi.org/project/black)

## Usage

### Fine-tuning

```sh
python3.10 -m nlnas finetune \
    microsoft/resnet-18 cifar100 out.local/ft \
    --train-split 'train[:80%]' \
    --val-split 'train[80%:]' \
    --test-split test \
    --image-key img \
    --label-key fine_label \
    --head-name classifier.1
```

### Fine-tuning with latent clustering correction

```sh
python3.10 -m nlnas finetune \
    microsoft/resnet-18 cifar100 out.local/ftc \
    --train-split 'train[:80%]' \
    --val-split 'train[80%:]' \
    --test-split test \
    --image-key img \
    --label-key fine_label \
    --head-name classifier.1 \
    --correction-weight 0.001 \
    --correction-submodules model.resnet.encoder.stages.3 \
    --batch-size 128
```


### Latent clustering correction

The correction command uses a `BalancedBatchSampler`.

```sh
python3.10 -m nlnas correct \
    out.local/ft/cifar100/microsoft-resnet-18/results.json out.local/c \
    model.resnet.encoder.stages.0,model.resnet.encoder.stages.1,model.resnet.encoder.stages.2,model.resnet.encoder.stages.3 0.001 \
    --batch-size 200 \
    --n-classes-per-batch 5
```

## Contributing

### Dependencies

- `python3.10` or newer;
- `requirements.txt` for runtime dependencies;
- `requirements.dev.txt` for development dependencies.
- `make` (optional);

Simply run

```sh
virtualenv venv -p python3.10
. ./venv/bin/activate
python3.10 -m pip install --upgrade pip
python3.10 -m pip install -r requirements.txt
python3.10 -m pip install -r requirements.dev.txt
python3.10 -m pip install --no-cache-dir --extra-index-url https://pypi.nvidia.com -r requirements.cuda12.txt
```

### Documentation

Simply run

```sh
make docs
```

This will generate the HTML doc of the project, and the index file should be at
`docs/index.html`. To have it directly in your browser, run

```sh
make docs-browser
```

### Code quality

Don't forget to run

```sh
make
```

to format the code following [black](https://pypi.org/project/black/),
typecheck it using [mypy](http://mypy-lang.org/), and check it against coding
standards using [pylint](https://pylint.org/).
