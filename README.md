# NLNAS

![Python 3](https://img.shields.io/badge/python-3-blue?logo=python)
[![License](https://img.shields.io/badge/license-MIT-green)](https://choosealicense.com/licenses/mit/)
[![Code style](https://img.shields.io/badge/style-black-black)](https://pypi.org/project/black)

## Installation

```sh
pip install -r requirements.txt -r requirements.dev.txt
pip install --extra-index-url https://pypi.nvidia.com -r requirements.cuda12.txt
```

## Usage

- Pretty-print a model structure: run `./pretty-print.sh HF_MODEL_NAME`, e.g. `./pretty-print.sh microsoft/resnet-18`
- Fine-tuning: modify and run `finetune.sh`
- Latent cluster correction: modify and run `correct.sh`

## Contributing

### Dependencies

- `python3.10`;
- `requirements.txt` for runtime dependencies;
- `requirements.dev.txt` for development dependencies.
- `make` (optional);

Simply run

```sh
virtualenv venv -p python3.10
. ./venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements.dev.txt
python -m pip install --no-cache-dir --extra-index-url https://pypi.nvidia.com -r requirements.cuda12.txt
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
