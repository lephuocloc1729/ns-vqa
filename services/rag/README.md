# Vietnamese Legal RAG

A multimodal retrieval-augmented QA project for Vietnamese traffic-law questions. The main experiment workflow is **Natural QA**: retrieve relevant legal passages and similar training examples, then answer with a vision-language model. A separate data utility supports the VLSP2025-MLQA-TSR dataset.

## Start here: run a Natural QA experiment

Run all commands from the project root (the folder containing `pyproject.toml`). You may place this folder anywhere; no `/Users/...` or `/root/...` path is required. The example below reuses transferred embedding artifacts and runs Qwen3.5-9B Q4 through llama.cpp.

**About `inference.py`:** `src/text_based_rag/inference.py`, which `natural_qa_runner` imports for prompts and law lookup, was missing from an earlier checkout. It was restored from its compiled bytecode and compiles to the same bytecode as the original; the original comments could not be recovered. Installing a third-party package named `inference` is not a substitute for this module.

### Supported machines and execution modes

| Machine | What the current code supports |
| --- | --- |
| Linux with NVIDIA CUDA GPU | Intended environment for embedding, captioning and answer generation, once all source files and assets are present. |
| Windows with NVIDIA CUDA GPU | Python utilities and Windows llama.cpp executable paths are supported in source; a full run still needs verification. WSL2 with a CUDA-enabled Linux environment can follow the Linux commands. |
| macOS, CPU-only, or AMD GPU | Data utilities and CLI help can run. Full embedding generation currently uses hard-coded CUDA; there is no CPU, MPS or ROCm device option. Use a separate NVIDIA GPU machine for the full experiment. |

Reusing embeddings avoids recomputing those vectors; it does not establish support for full inference on every device. BGE-M3 embedding explicitly requires CUDA with BF16 support and at least 5 GiB free VRAM. That is an embedding-stage check, **not** a memory estimate for the complete pipeline. Model weights, images and the context window also consume memory; the 65,536-token example is not a low-memory preset. Hardware changes can change timings and numerical outputs.

### 1. Prepare the Python environment

The project requires Python 3.10–3.12. Its `pyproject.toml` does not yet declare all runtime packages.

```bash
# Linux / macOS (Python 3.10, 3.11 or 3.12)
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools
python -m pip install -e .
python -m pip install numpy requests pillow
```

On native Windows, use PowerShell to create and activate the environment:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools
python -m pip install -e .
python -m pip install numpy requests pillow
```

If activation is unavailable, invoke `.venv/bin/python` (Linux/macOS) or `.\.venv\Scripts\python.exe` (Windows) directly. Do not copy another machine's `.venv`: recreate it on the destination. A new virtual environment does not automatically inherit packages from a GPU image.

For embedding or Transformers generation, install a CUDA-enabled PyTorch build compatible with the destination NVIDIA driver, then install the additional Python dependencies:

```bash
python -m pip install transformers sentence-transformers accelerate huggingface-hub sentencepiece safetensors
python -m pip check
```

These are dependency names, not a validated version lock. In particular, the Transformers backend needs a version exposing `Qwen3_5ForConditionalGeneration` for Qwen3.5. When reproducing a run, obtain the original dependency versions together with its artifacts and save the destination environment with `python -m pip freeze > environment.txt`. Hugging Face downloads need network access and, for restricted models, an account with model access. No API key is needed by the local llama.cpp HTTP server.

Verify the device before a GPU run (the Python check is safe even without CUDA):

```bash
nvidia-smi
python -c "import torch; ok = torch.cuda.is_available(); print('CUDA:', ok); print(torch.cuda.get_device_name(0) if ok else 'No CUDA device'); print('BF16:', torch.cuda.is_bf16_supported() if ok else False)"
```

### 2. Check required files

The Natural dataset root must contain the train, public-test, private-test, and law-corpus directories:

```text
data/raw/VLSP2025-MLQA-Natural/dataset/
├── train data/
├── public_test data/
├── private_test data (post submission)/
└── law_db/
```

For the example below, these cache paths must also exist:

```text
artifacts/experiments/text_based_rag/natural_qa/t768_o64/f2llm-v2-0.6b/train/
artifacts/experiments/text_based_rag/natural_qa/query_embeddings/f2llm-v2-0.6b/
artifacts/public-test/text_based_rag/natural_qa/query_embeddings/f2llm-v2-0.6b/
```

For image-enabled Qwen Q4 runs, the runner expects these files relative to the project root:

```text
models/huggingface/Qwen3.5-9B-GGUF/Qwen3.5-9B-Q4_K_M.gguf
models/huggingface/Qwen3.5-9B-GGUF/mmproj-F16.gguf
.venv/tools/llama.cpp-b11624/llama-server
```

The runner's answer-model choice is `qwen3.5-9b-gguf`. The runner does not download the model files automatically. The files used for the saved results are published in the Hugging Face repository `unsloth/Qwen3.5-9B-GGUF`; check their SHA-256 after downloading, because a different file is a different experiment:

| File | SHA-256 |
| --- | --- |
| `Qwen3.5-9B-Q4_K_M.gguf` | `03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8` |
| `mmproj-F16.gguf` | `f70dc3509053962b0d0d3ee8a7eacebf5d60aa560cad78254ae8698516ae029f` |

Install a llama.cpp b11624 executable built for the destination OS, CPU architecture and CUDA runtime at the path above. On Linux x64, the official ggml-org release assets `llama-b11624-bin-ubuntu-cuda-12.8-x64.tar.gz` and `cudart-llama-b11624-bin-ubuntu-cuda-12.8-x64.tar.gz` match the runtime recorded by the saved runs; extract both into `.venv/tools/llama.cpp-b11624/` so the CUDA libraries sit beside `llama-server`. On Windows the filename is `llama-server.exe`; retain the required runtime DLLs beside it. On Linux the file must be executable. Do not copy a Linux executable to Windows/macOS.

The three embedding directories above are only part of the required assets. Transfer the matching corpus preparation/index directories under `artifacts/experiments/text_based_rag/corpus/`, Natural QA caption directories, and any tokenizer snapshots used by the selected workflow. Keep directory structure, manifests, JSONL records and NumPy arrays together; copying only `run_config.json` is insufficient. The runner also checks the TSR law source at `data/raw/VLSP2025-MLQA-TSR/dataset/law_db/vlsp2025_law.json` against the Natural law corpus. Obtain datasets and image files from their authorized provider or project maintainer; they are not installed by `pip`.

Paths under `data/`, `models/` and `.venv/` are excluded by `.gitignore`, so a source copy/clone alone does not provide these assets. Copy only the splits needed for your workflow, including train for the example bank. For external storage, quote `--dataset-root`, `--corpus-chunks`, `--caption-dir` and `--output-dir` paths containing spaces. Other model/corpus/cache paths are defined in source relative to the project root; these are not configurable through `.env` or a general `--device`/`--model-path` option. Preserve their expected layout.

Before a full run, check imports and executable compatibility:

```bash
python -c "import numpy, requests; from PIL import Image; from text_based_rag import inference, query_image_captioning; print('Runtime imports OK')"
.venv/tools/llama.cpp-b11624/llama-server --version
python -m text_based_rag.natural_qa_runner --help
```

On Windows use `.\.venv\tools\llama.cpp-b11624\llama-server.exe --version`.

### 3. Run

After preparing the assets, use a new output directory for each run. This example uses five image few-shot examples and retrieval configuration C. The multiline examples use Bash syntax: in PowerShell replace each trailing `\` with a backtick, or put the entire command on one line.

```bash
python -m text_based_rag.natural_qa_runner \
  --dataset-root data/raw/VLSP2025-MLQA-Natural/dataset \
  --split public_test \
  --output-dir artifacts/experiments/text_based_rag/natural_qa/my_public_c_5shot \
  --embedding-model f2llm-v2-0.6b \
  --embedding-dtype bf16 \
  --answer-model qwen3.5-9b-gguf \
  --corpus-chunks artifacts/experiments/text_based_rag/natural_qa/t768_o64/f2llm-v2-0.6b/train \
  --reuse-precomputed-embeddings \
  --fresh-captions --allow-incomplete-captions \
  --fewshot-k 5 --answer-with-images \
  --context-size 65536 --current-context-budget 20000 --answer-max-tokens 2048 \
  --corpus-k 5 --examples-k 4 --high-examples-k 3 \
  --gate-low 0.70 --gate-high 0.7835 \
  --weight-high 0.87 --weight-middle 0.05 --weight-low 0.40
```

`--reuse-precomputed-embeddings` reuses the corpus, train-bank, and query embeddings when their metadata and hashes match. The chunk path must be the encoder's completed `train` cache. If a cache is missing or does not match, stop and inspect the error rather than silently treating a new embedding run as equivalent.

The answer model is independent of the embedding model. For GGUF choices (`qwen3.5-9b-gguf`, `qwen3.5-9b-gguf-bf16`, `gemma-3-12b-it-gguf-f16`), answers run through llama.cpp. Only `qwen3.5-9b-transformers` and `gemma-3-12b-it` load Transformers for answer generation.

### 4. Find the outputs

The selected `--output-dir` is the run's root. Inspect its `run_config.json` and the split folder's `predictions.jsonl` to confirm settings and answers. Retrieval artifacts are saved alongside the run. Keep the command line and output directory together in experiment notes so reruns can be compared.

The runner protects completed output folders. If settings change, choose a different `--output-dir`; do not delete a prior run to make a new configuration fit.

## Change the experiment

Common options:

| Goal | Option |
| --- | --- |
| Choose validation, public, or private split | `--split validation\|public_test\|private_test`; `train` is accepted only with `--embedding-only` |
| Set demonstrations | `--fewshot-k 0\|1\|3\|5\|7` |
| Pass query and demonstration images to the answer model | `--answer-with-images` |
| Change answer model context window | `--context-size N` |
| Limit current-law/caption/question context | `--current-context-budget N` |
| Change maximum answer length | `--answer-max-tokens N` |
| Save retrieval without generating answers | `--retrieval-only` |
| Prepare the train example bank only | `--prepare-bank-only` |

For another chunk setup, point `--corpus-chunks` at that setup's encoder-specific `train` cache. For another encoder, change `--embedding-model` and use that encoder's matching cache paths. Do not compare runs if the data split, prompt, images, retrieval settings, or context budgets differ unintentionally.

## Build or refresh Natural QA artifacts

The fast path above assumes the matching cache and model files already exist. Use the preparation commands only when those inputs are absent or intentionally being rebuilt.

### Law corpus preparation

```bash
python -m text_based_rag.corpus_normalization --help
python -m text_based_rag.corpus_normalization
python -m text_based_rag.corpus_image_captioning --help
python -m text_based_rag.corpus_image_captioning
```

Normalization defaults to the TSR law JSON and processed law-image directory. Corpus image captioning requires its configured Qwen GGUF, multimodal projector, and llama.cpp runtime. Review the CLI help before using `--overwrite`.

### Chunking and embedding

```bash
python -m text_based_rag.corpus_chunking --help
python -m text_based_rag.corpus_chunking --max-tokens 768 --overlap-tokens 64
python -m text_based_rag.corpus_embedding download
python -m text_based_rag.corpus_embedding index --batch-size 4
```

Chunking needs the local tokenizer. Embedding needs CUDA PyTorch and GPU memory; lower `--batch-size` if necessary. These corpus-preparation commands are distinct from the Natural QA per-encoder train/query caches consumed by `natural_qa_runner`.

## Dataset utility: VLSP2025-MLQA-TSR

Validate the local TSR source, inspect counts, extract images, or generate a train/dev split:

```bash
python -m multimodal_legal_rag.data validate
python -m multimodal_legal_rag.data stats
python -m multimodal_legal_rag.data prepare
python -m multimodal_legal_rag.data split --seed 2025 --dev-ratio 0.2
```

The source defaults to `data/raw/VLSP2025-MLQA-TSR`; prepared images and splits default to `data/processed/`. This utility is separate from the Natural QA inference command above.

## Tuning and help

Tune retrieval with train/dev data and reserve public/private test for final evaluation. Check current parameters before a run:

```bash
python -m text_based_rag.natural_qa_tuning --help
python -m text_based_rag.natural_qa_runner --help
```

Other CLI help:

```bash
python -m multimodal_legal_rag.data --help
python -m text_based_rag.corpus_normalization --help
python -m text_based_rag.corpus_image_captioning --help
python -m text_based_rag.corpus_chunking --help
python -m text_based_rag.corpus_embedding --help
```

## Troubleshooting on a new machine

| Symptom | Action |
| --- | --- |
| `No module named text_based_rag` | Use the newly created environment and run `python -m pip install -e .` from the project root. Keep the source tree in place for this editable installation. |
| Cannot import `inference` from `text_based_rag` | Check that `src/text_based_rag/inference.py` exists in your copy and that `python -m pip install -e .` was run from the project root. If the error names another module, such as `requests`, install that package. |
| CUDA unavailable / BF16 unsupported | Check the NVIDIA driver and installed PyTorch build. CPU/MPS fallback is not implemented; BGE-M3 always enforces BF16 even if `--embedding-dtype fp16` is supplied. |
| Missing model, tokenizer, DLL or executable | Check the expected relative path and install assets built for the destination OS. `pip install -e .` does not install llama.cpp or model weights. |
| Missing data, captions, law index or embeddings | Obtain the complete matching asset bundle, or prepare the required artifacts with the appropriate commands. The corpus commands alone do not recreate every Natural QA cache. |
| Cache hash or configuration mismatch | Use matching source/data/model versions or rebuild intentionally into a new directory. Do not edit hashes or manifests to bypass validation. Moving assets may expose saved absolute paths; inspect the reported mismatch. |
| Out of memory / context overflow | Free GPU memory; for embedding lower batch size where supported. For generation reduce context, few-shot count or image use and use a new output directory. Record changed settings because this is a different experiment. |

Verification scope: the README commands and paths were checked against the source and CLI help.
