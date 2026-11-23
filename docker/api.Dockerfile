# The backend API: FastAPI + the rules pipeline (Python) + SWI-Prolog (janus).
#
# FROM the SignCite base (docker/base.Dockerfile, built by .github/workflows/base-image.yml):
# Ubuntu 24.04, Python 3.12, SWI-Prolog 11.0.0 from its PPA, and the venv /opt/venv. It is pinned by
# its commit tag, so building this image never needs Launchpad, and Prolog or Python change only
# when this line does. To update them: rebuild the base (run the workflow), then change the tag.
ARG BASE=ghcr.io/lephuocloc1729/signcite-base:9d66ff8468c03d44b1d3afd95bb8c4141500c0a5
FROM ${BASE}

ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH

WORKDIR /app
# dependencies first (a cached layer that changes only with pyproject.toml)
COPY pyproject.toml ./
RUN python - <<'PY' > /tmp/req.txt && pip install --no-cache-dir -r /tmp/req.txt
import tomllib
p = tomllib.load(open("pyproject.toml", "rb"))["project"]
print("\n".join(p["dependencies"] + p["optional-dependencies"]["api"]))
PY

# the code: the pipeline finds kb/ and prompts/ next to vqa/, so the tree is kept as in the repo
COPY vqa ./vqa
COPY app ./app
COPY kb ./kb
COPY prompts ./prompts
COPY web/e2e/fake_api.py ./web/e2e/fake_api.py
COPY docker/api-entrypoint.sh /usr/local/bin/api-entrypoint
RUN pip install --no-cache-dir --no-deps -e . \
 && swipl -q -g "consult('kb/load.pl'), halt" -t "halt(1)" \
 && useradd --create-home --uid 10001 vqa \
 && mkdir -p var/uploads cache/scenes logs /run/signcite-auth \
 && chown -R vqa:vqa var cache logs /run/signcite-auth \
 && chmod +x /usr/local/bin/api-entrypoint

USER vqa
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1
ENTRYPOINT ["api-entrypoint"]
