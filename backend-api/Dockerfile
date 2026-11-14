# backend-api — the image that carries the method and the three harnesses (AD-16, AD-10).
#
# Built from the repository root, because it needs two trees: `backend-api/` and the shared
# `scripts/harness/`. See `docker-compose.yml`.
#
# Configuration is the environment (AD-20), so nothing here reads `.env`: the only values
# baked in are version pins. The toolchain pins are ARGs with a literal default; the three
# harness CLI pins are valueless ARGs that compose fills from `.env` (`build.args`); unset,
# the `: "${X:=default}"` line in `scripts/harness/<name>.sh` applies, which equals
# `.env.example`. No
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
ARG PLAYWRIGHT_VERSION=1.62.1
# The docker client equals the `docker` service's `docker:<version>-dind` in both compose files.
ARG DOCKER_VERSION=29.4.3
ARG DOCKER_SHA256_AMD64=bc9734a89d3edd15eeca8620961f6499ba69948814c85d7ac3488e34b3e16d01
ARG DOCKER_SHA256_ARM64=fdde3dbedbd8dc9e9e54a3172e682b4e69e740296e580542ea9ceacebbbf4f4c
ARG DOCKER_COMPOSE_VERSION=5.6.1
ARG DOCKER_COMPOSE_SHA256_AMD64=47737f4236e6d3ccea7291995203f8f018058783b4c3a9469119811a0b5db8c0
ARG DOCKER_COMPOSE_SHA256_ARM64=42cfa75f51ad0ccf290bad37899e0038a8c10a0069e85233ecc1d53e3ff1347d
ARG DOCKER_BUILDX_VERSION=0.38.1
ARG DOCKER_BUILDX_SHA256_AMD64=e25d5cd675092bb5d1d03632fdc46cdf3fede7b514dc5f023a105e00d3ce5ad4
ARG DOCKER_BUILDX_SHA256_ARM64=3b83b3731916ba433feccaaa689fe5bcdc81c641d92c8e6c2ea865dfa141c97a
# The code-analysis tools (epic 5): versions are literals; each downloaded binary is pinned to a
# sha256 per architecture, copied from the release's own checksum file.
ARG GITLEAKS_VERSION=8.30.1
# gitleaks_8.30.1_checksums.txt, entry gitleaks_8.30.1_linux_x64.tar.gz
ARG GITLEAKS_SHA256_AMD64=551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb
# gitleaks_8.30.1_checksums.txt, entry gitleaks_8.30.1_linux_arm64.tar.gz
ARG GITLEAKS_SHA256_ARM64=e4a487ee7ccd7d3a7f7ec08657610aa3606637dab924210b3aee62570fb4b080
ARG OSV_SCANNER_VERSION=2.7.1
# osv-scanner_SHA256SUMS, entry osv-scanner_linux_amd64
ARG OSV_SCANNER_SHA256_AMD64=fb7dab19a8bd9bbe5c3189f09d4b7ee1820c9553a23bac202648a56efd2f6ee8
# osv-scanner_SHA256SUMS, entry osv-scanner_linux_arm64
ARG OSV_SCANNER_SHA256_ARM64=983d22fbad9724514e3fcc6acc83b5fa64c5ffa6b0d9f510028f22c1b223ff81
ARG LIZARD_VERSION=1.26.0
ARG JSCPD_VERSION=5.4.3
ARG OPENGREP_VERSION=2.0.0
# opengrep v2.0.0 release asset opengrep_linux_x86 (the release's digest for the asset)
ARG OPENGREP_SHA256_AMD64=37e93f4da5fd04a18c5c1febbdd12f7e98dfccd4d0c9cf2593bcb25eeb462da0
# opengrep v2.0.0 release asset opengrep_linux_aarch64 (the release's digest for the asset)
ARG OPENGREP_SHA256_ARM64=6257b65423a744b704af2ff9beeb8f222c2f6925236af386b56b031d4c06d6d8
# Defaults matching `.env.example`; compose passes the real values through `env_file`.
ARG AGENT_HOME=/home/agent
ARG WORK_DIR=/work

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    AGENT_HOME=${AGENT_HOME} \
    WORK_DIR=${WORK_DIR} \
    HOME=${AGENT_HOME} \
    # npm's global prefix sits outside every named volume on purpose: it holds the corepack
    # shims, which must follow the image. The harness CLIs live apart, in /opt/harness-cli
    # (the `harness-bin` volume, reconciled against the `*_VERSION` pins at every start), and
    # come first on PATH; /opt/harness-image, the build's own copy, is on no PATH.
    NPM_CONFIG_PREFIX=/opt/npm-global \
    NPM_CONFIG_UPDATE_NOTIFIER=false \
    NPM_CONFIG_FUND=false \
    COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
    PATH=/app/backend-api/.venv/bin:/opt/harness-cli/bin:/opt/npm-global/bin:/usr/local/bin:/usr/local/sbin:/usr/bin:/usr/sbin:/bin:/sbin

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      git \
      make \
      sudo \
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

# The docker CLI with its compose and buildx plugins, for a target repository whose commands
# run `docker compose`. Client only: the daemon is the optional `docker` service
# (`VERIFY_DOCKER`, deploy/README.md § Docker for Runs); without it every docker command
# here answers `Cannot connect to the Docker daemon`. download.docker.com publishes no
# checksum file for the static archive, so all three are pinned to a literal sha256 per
# architecture, and a version bump without its checksums fails the build.
RUN set -eux; \
    case "$(dpkg --print-architecture)" in \
      amd64) docker_arch=x86_64; plugin_arch=amd64; \
             docker_sha="${DOCKER_SHA256_AMD64}"; \
             compose_sha="${DOCKER_COMPOSE_SHA256_AMD64}"; \
             buildx_sha="${DOCKER_BUILDX_SHA256_AMD64}" ;; \
      arm64) docker_arch=aarch64; plugin_arch=arm64; \
             docker_sha="${DOCKER_SHA256_ARM64}"; \
             compose_sha="${DOCKER_COMPOSE_SHA256_ARM64}"; \
             buildx_sha="${DOCKER_BUILDX_SHA256_ARM64}" ;; \
      *) echo "unsupported architecture: $(dpkg --print-architecture)" >&2; exit 1 ;; \
    esac; \
    plugins=/usr/local/libexec/docker/cli-plugins; \
    mkdir -p "${plugins}"; \
    curl -fsSL -o docker.tgz \
        "https://download.docker.com/linux/static/stable/${docker_arch}/docker-${DOCKER_VERSION}.tgz"; \
    echo "${docker_sha}  docker.tgz" | sha256sum -c -; \
    tar -xzf docker.tgz -C /usr/local/bin --strip-components=1 --no-same-owner docker/docker; \
    rm -f docker.tgz; \
    curl -fsSL -o "${plugins}/docker-compose" \
        "https://github.com/docker/compose/releases/download/v${DOCKER_COMPOSE_VERSION}/docker-compose-linux-${docker_arch}"; \
    echo "${compose_sha}  ${plugins}/docker-compose" | sha256sum -c -; \
    curl -fsSL -o "${plugins}/docker-buildx" \
        "https://github.com/docker/buildx/releases/download/v${DOCKER_BUILDX_VERSION}/buildx-v${DOCKER_BUILDX_VERSION}.linux-${plugin_arch}"; \
    echo "${buildx_sha}  ${plugins}/docker-buildx" | sha256sum -c -; \
    chmod 0755 /usr/local/bin/docker "${plugins}/docker-compose" "${plugins}/docker-buildx"; \
    docker --version; docker compose version; docker buildx version

# Chromium's shared system libraries, for the UI gate (`make e2e-ui`) a harness runs in a
# target repository's worktree. Libraries only, as root — the browser itself needs no root
# and comes from `make install-e2e`, onto the persistent `agent-home` volume.
RUN set -eux; \
    export HOME=/root; \
    apt-get update; \
    npx -y "playwright@${PLAYWRIGHT_VERSION}" install-deps chromium; \
    rm -rf /var/lib/apt/lists/* /root/.npm

COPY --from=uv /uv /usr/local/bin/uv

# The tools a Run's analysis runs on a repository's change (AD-14, RM-5): gitleaks (secrets),
# osv-scanner (known vulnerabilities), lizard (function complexity), jscpd (duplication; it
# writes SARIF itself), and the Opengrep engine (possible findings). No rule pack is installed:
# each repository declares its own (`sast.rules`). Installed as root onto the agent's PATH,
# before the user exists.
RUN set -eux; \
    case "$(dpkg --print-architecture)" in \
      amd64) gitleaks_arch=x64; osv_arch=amd64; \
             gitleaks_sha="${GITLEAKS_SHA256_AMD64}"; osv_sha="${OSV_SCANNER_SHA256_AMD64}" ;; \
      arm64) gitleaks_arch=arm64; osv_arch=arm64; \
             gitleaks_sha="${GITLEAKS_SHA256_ARM64}"; osv_sha="${OSV_SCANNER_SHA256_ARM64}" ;; \
      *) echo "unsupported architecture: $(dpkg --print-architecture)" >&2; exit 1 ;; \
    esac; \
    archive="gitleaks_${GITLEAKS_VERSION}_linux_${gitleaks_arch}.tar.gz"; \
    curl -fsSL -o "${archive}" \
        "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/${archive}"; \
    echo "${gitleaks_sha}  ${archive}" | sha256sum -c -; \
    tar -xzf "${archive}" -C /usr/local/bin --no-same-owner gitleaks; \
    rm -f "${archive}"; \
    curl -fsSL -o /usr/local/bin/osv-scanner \
        "https://github.com/google/osv-scanner/releases/download/v${OSV_SCANNER_VERSION}/osv-scanner_linux_${osv_arch}"; \
    echo "${osv_sha}  /usr/local/bin/osv-scanner" | sha256sum -c -; \
    chmod 0755 /usr/local/bin/osv-scanner; \
    UV_TOOL_DIR=/opt/uv-tools UV_TOOL_BIN_DIR=/usr/local/bin \
        uv tool install --python /usr/local/bin/python3 "lizard==${LIZARD_VERSION}"; \
    npm install -g "jscpd@${JSCPD_VERSION}"; \
    gitleaks version; osv-scanner --version; lizard --version; jscpd --version; \
    rm -rf /root/.npm /root/.cache/uv

RUN set -eux; \
    case "$(dpkg --print-architecture)" in \
      amd64) og_asset=opengrep_linux_x86; og_sha="${OPENGREP_SHA256_AMD64}" ;; \
      arm64) og_asset=opengrep_linux_aarch64; og_sha="${OPENGREP_SHA256_ARM64}" ;; \
      *) echo "unsupported architecture: $(dpkg --print-architecture)" >&2; exit 1 ;; \
    esac; \
    curl -fsSL -o /usr/local/bin/opengrep \
        "https://github.com/opengrep/opengrep/releases/download/v${OPENGREP_VERSION}/${og_asset}"; \
    echo "${og_sha}  /usr/local/bin/opengrep" | sha256sum -c -; \
    chmod 0755 /usr/local/bin/opengrep; \
    opengrep --version

# One non-root user for the process and for every harness it spawns (NFR-3). `work` and
# `agent-home` are mounted here, and a named volume takes its ownership from the image.
RUN set -eux; \
    useradd --create-home --home-dir "${AGENT_HOME}" --shell /bin/bash --uid 1000 agent; \
    echo 'agent ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/agent; \
    chmod 0440 /etc/sudoers.d/agent; \
    mkdir -p "${WORK_DIR}" /opt/npm-global/bin /opt/harness-image /opt/harness-cli /opt/bmad /app; \
    corepack enable --install-directory /opt/npm-global/bin; \
    # Node's default global location is also agent-owned: `corepack enable` and any tool
    # that ignores NPM_CONFIG_PREFIX writes here, and the agent user must install freely.
    chown -R agent:agent "${WORK_DIR}" "${AGENT_HOME}" /opt/npm-global /opt/harness-image /opt/harness-cli /opt/bmad /app \
        /usr/local/bin /usr/local/lib/node_modules

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
COPY --chown=agent:agent scripts/docker_context.sh /app/scripts/docker_context.sh
COPY --chown=agent:agent scripts/setup /app/scripts/setup
COPY --chown=agent:agent backend-api/docker-entrypoint.sh /app/docker-entrypoint.sh

# The shipped Templates (SPEC CAP-3): `seed_shipped` reads this path at start-up
# (`TEMPLATES_DIR=/app/templates`, story 3.3). Repository-root, like `scripts/harness` above.
COPY --chown=agent:agent templates /app/templates

# The readiness fixture (SPEC CAP-8): `scripts/readiness_fixture.sh` copies this, never
# edits it in place. Repository-root, like `templates` above.
COPY --chown=agent:agent fixtures /app/fixtures

# Operator skills (story 4-1, AD-16): installed into every harness by install_operator_skills
# in _common.sh. Repository-root, like `templates` and `fixtures` above.
COPY --chown=agent:agent ia-agents-skills /app/ia-agents-skills

WORKDIR /app

# BMAD is carried as a package under /opt/bmad (never mounted), at `_common.sh`'s
# BMAD_VERSION default; no BMAD skill reaches a harness home from the image — the setup runner
# installs it. Before the harness ARGs, so a harness pin change does not re-run it.
RUN bash -c 'source scripts/harness/_common.sh && install_bmad_package'

# Each harness installs its CLI at its pinned version and the operator skills into the global
# skill directory it reads (AD-16). Run as `agent`.
#
# The pins are valueless ARGs: compose passes `.env`'s value, and unset, the script default
# installs. Declared here, not with the others, because a changed ARG busts the cache of
# every RUN after it, and only these installs read them.
ARG CLAUDE_CODE_VERSION
ARG CODEX_VERSION
ARG OPENCODE_VERSION
#
# `install` writes the CLIs to /opt/harness-image, which is never mounted: each start's
# `ensure` copies from it whenever it is at the pin, so a release's CLIs reach an existing
# `harness-bin` volume without the registry. The copy into /opt/harness-cli seeds a volume
# created from this image.
RUN scripts/harness/claude.sh install \
 && scripts/harness/codex.sh install \
 && scripts/harness/opencode.sh install \
 && cp -a /opt/harness-image/. /opt/harness-cli/

# The client install, entire (agent-delivery-kit plan §1): `docker run --rm <image> kit
# bootstrap | tar x` hands a machine `install.sh`, the compose file, the env contract,
# the product manifest, the shipped examples and kit/ straight out of the image it will run
# (`llm-platform/` stays in the image for the repository's development; bootstrap leaves it
# out), and `GET /api/v1/kit/*`
# serves kit/ to project repositories (`KIT_DIR=/app/deploy/kit`). `.dockerignore` keeps
# every filled `.env` and `llm-platform/backups/` out of the context (hard rule 5). `VERSION`
# sits at /app as it sits at the repository root: `/api/v1/version` reads it there, and the
# bootstrap archive carries it so install.sh knows which tag it came from. Last, after the
# harness installs above: a kit edit must not re-run three `npm install`s.
COPY --chown=agent:agent deploy /app/deploy
COPY --chown=agent:agent VERSION /app/VERSION
COPY --chown=agent:agent guide /app/guide
RUN python -m orchestrator.tools.build_guide --source /app/guide --out /app/guide-build --version-file /app/VERSION
COPY --chown=agent:agent templates/*.yaml /app/deploy/templates/shipped/
COPY --chown=agent:agent scripts/product_manifest.py /app/scripts/product_manifest.py
RUN python3 /app/scripts/product_manifest.py /app/deploy /app/VERSION > /app/deploy/product-files.json

# Informational: the published port comes from BACKEND_API_PORT in `.env`.
EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
