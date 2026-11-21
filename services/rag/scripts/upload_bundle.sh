#!/usr/bin/env bash
# Upload dist/rag_bundle.tar.gz (+ its listing) to the private Hugging Face dataset repo.
#
#   hf auth login                                      # once, with your own token
#   export RAG_ASSETS_REPO=<hf-user>/ns-vqa-rag-assets   # created on huggingface.co as PRIVATE
#   bash scripts/upload_bundle.sh
#
# Refuses a repo that is missing or public: the bundle holds course-dataset images and
# files derived from them, so it is shared privately only.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${RAG_ASSETS_REPO:?set RAG_ASSETS_REPO, e.g. user/ns-vqa-rag-assets}"
[ -f dist/rag_bundle.tar.gz ] || { echo "no bundle: run python scripts/make_bundle.py first"; exit 1; }
PY=${PY:-python3}
"$PY" - "$RAG_ASSETS_REPO" <<'EOF'
import sys
from huggingface_hub import HfApi
api, repo = HfApi(), sys.argv[1]
info = api.repo_info(repo, repo_type="dataset")
if not info.private:
    sys.exit(f"refusing: {repo} is public; make it private first")
for name in ("rag_bundle.json", "rag_bundle.tar.gz"):
    api.upload_file(path_or_fileobj=f"dist/{name}", path_in_repo=name, repo_id=repo, repo_type="dataset",
                    commit_message=f"Upload {name}")
    print("uploaded", name)
EOF
