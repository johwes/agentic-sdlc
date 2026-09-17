# Worker cell image (see specs/04-worker-cell.md).
# Skeleton: full package versions and registry flow are TBD.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl jq python3 python3-venv ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Node.js LTS (placeholder: pin major + install via nodesource in full build)
# OpenCode CLI + Claude Code CLI installed here in the full build.

# Contract prompt + harness entrypoint (sources: prompts/, harness/ in repo).
COPY prompts/worker_contract.txt /etc/prompts/worker_contract.txt
COPY harness/wrapper.py /usr/local/bin/cell-harness
RUN chmod +x /usr/local/bin/cell-harness

WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/cell-harness"]
