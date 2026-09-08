# backend-api — the image that carries the method and the three harnesses (AD-16, AD-10).
#
# Built from the repository root, because it needs two trees: `backend-api/` and the shared
# `scripts/harness/`. See `docker-compose.yml`.
#
# Configuration is the environment (AD-20), so nothing here reads `.env`: the only values
# baked in are version pins, and every one of them is an ARG with a literal default. No
# credential is a build argument — `docker history` shows those — and `.dockerignore` keeps
# a filled `.env` out of the build context entirely (hard rule 5, AD-5).
#
# The layer order is deliberate: system packages, then Node, then the locked Python
# dependencies, then the source, then the harness installs. The harness installs are last
# because they are the slow ones and they change only when a pinned version does.

# syntax=docker/dockerfile:1

ARG PYTHON_IMAGE=python:3.14-slim-trixie
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.12.9

FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE}

# Pins nothing outside this file reads at runtime, so they are not contract variables.
ARG NODE_VERSION=24.20.0
ARG GH_VERSION=2.100.0
# Defaults matching `.env.example`; compose passes the real values through `env_file`.
ARG AGENT_HOME=/home/agent
ARG WORK_DIR=/work

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    AGENT_HOME=${AGENT_HOME} \
    WORK_DIR=${WORK_DIR} \
    HOME=${AGENT_HOME} \
    # npm's global prefix sits outside every named volume on purpose: `agent-home` is
    # seeded from the image only while it is empty, so a CLI installed under HOME would
    # go stale the first time the image was rebuilt.
    NPM_CONFIG_PREFIX=/opt/npm-global \
    NPM_CONFIG_UPDATE_NOTIFIER=false \
    NPM_CONFIG_FUND=false \
    PATH=/app/backend-api/.venv/bin:/opt/npm-global/bin:/usr/local/bin:/usr/local/sbin:/usr/bin:/usr/sbin:/bin:/sbin

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      git \
      xz-utils \
 && rm -rf /var/lib/apt/lists/*

# Node 24 from the official distribution, checksum-verified. The NodeSource script would
# pull whatever 24.x is current on the day the image is built.
RUN set -eux; \
    case "$(dpkg --print-architecture)" in \
      amd64) node_arch=x64 ;; \
      arm64) node_arch=arm64 ;; \
      *) echo "unsupported architecture: $(dpkg --print-architecture)" >&2; exit 1 ;; \
    esac; \
    archive="node-v${NODE_VERSION}-linux-${node_arch}.tar.xz"; \
    curl -fsSLO "https://nodejs.org/dist/v${NODE_VERSION}/${archive}"; \
    curl -fsSLO "https://nodejs.org/dist/v${NODE_VERSION}/SHASUMS256.txt"; \
    grep " ${archive}\$" SHASUMS256.txt | sha256sum -c -; \
    tar -xJf "${archive}" -C /usr/local --strip-components=1 --no-same-owner \
        --exclude=CHANGELOG.md --exclude=LICENSE --exclude=README.md; \
    rm -f "${archive}" SHASUMS256.txt; \
    node --version; npm --version

# gh: the git host client the `git.push` / `pr.link` step kinds shell out to (AD-14).
# Checksum-verified against the release's own manifest, like Node above: this binary is
# handed GITHUB_TOKEN at run time, so a silently substituted download would matter.
RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    archive="gh_${GH_VERSION}_linux_${arch}.tar.gz"; \
    base="https://github.com/cli/cli/releases/download/v${GH_VERSION}"; \
    curl -fsSL -o "${archive}" "${base}/${archive}"; \
    curl -fsSL -o gh_checksums.txt "${base}/gh_${GH_VERSION}_checksums.txt"; \
    grep " ${archive}\$" gh_checksums.txt | sha256sum -c -; \
    tar -xzf "${archive}" -C /usr/local --strip-components=1 --no-same-owner \
        "gh_${GH_VERSION}_linux_${arch}/bin/gh"; \
    rm -f "${archive}" gh_checksums.txt; \
    gh --version

COPY --from=uv /uv /usr/local/bin/uv

# One non-root user for the process and for every harness it spawns (NFR-3). `work` and
# `agent-home` are mounted here, and a named volume takes its ownership from the image.
RUN set -eux; \
    useradd --create-home --home-dir "${AGENT_HOME}" --shell /bin/bash --uid 1000 agent; \
    mkdir -p "${WORK_DIR}" /opt/npm-global /app; \
    chown -R agent:agent "${WORK_DIR}" "${AGENT_HOME}" /opt/npm-global /app

USER agent
WORKDIR /app/backend-api

# Dependencies before source, so editing a module does not re-resolve the environment.
COPY --chown=agent:agent backend-api/pyproject.toml backend-api/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY --chown=agent:agent backend-api/ ./
RUN uv sync --locked --no-dev

# The shared scripts live beside the component, exactly as the repository lays them out, so
# `docker compose exec backend-api scripts/harness/claude.sh doctor` reads the same file a
# reviewer reads.
COPY --chown=agent:agent scripts/harness /app/scripts/harness
COPY --chown=agent:agent scripts/readiness_fixture.sh /app/scripts/readiness_fixture.sh
COPY --chown=agent:agent backend-api/docker-entrypoint.sh /app/docker-entrypoint.sh

# The shipped Templates (SPEC CAP-3): `seed_shipped` reads this path at start-up
# (`TEMPLATES_DIR=/app/templates`, story 3.3). Repository-root, like `scripts/harness` above.
COPY --chown=agent:agent templates /app/templates

# The readiness fixture (SPEC CAP-8): `scripts/readiness_fixture.sh` copies this, never
# edits it in place. Repository-root, like `templates` above.
COPY --chown=agent:agent fixtures /app/fixtures

WORKDIR /app

# Each harness installs its CLI at its pinned version and copies the BMAD skill stubs into
# the global skill directory it reads (AD-16). Run as `agent`, so the stubs land under
# AGENT_HOME owned by the user that will read them.
RUN scripts/harness/claude.sh install \
 && scripts/harness/codex.sh install \
 && scripts/harness/opencode.sh install

# Informational: the published port comes from BACKEND_API_PORT in `.env`.
EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
