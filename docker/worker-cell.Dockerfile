# Worker cell layer (see specs/04-worker-cell.md).
#
# Thin layer on top of the local sandbox base image
# (docker/openshell-sandbox-image/Dockerfile — CentOS Stream 10 port of
# upstream NVIDIA/OpenShell-Community sandboxes/base). The base provides
# runtimes (Node 22, Python 3.14 via uv), agent CLIs (opencode, codex,
# copilot, claude), gh, git, skills, and the default policy. This layer
# adds only the Ralph-loop contract: prompt, harness command.
#
# Build base first (from docker/openshell-sandbox-image/):
#   podman build -t openshell-base:centos-stream10 .
# Then this layer:
#   podman build -t worker-cell:latest -f docker/worker-cell.Dockerfile .

ARG BASE_IMAGE=openshell-base:centos-stream10
FROM ${BASE_IMAGE}

# Contract prompt (source: prompts/worker_contract.txt in repo).
COPY prompts/worker_contract.txt /etc/prompts/worker_contract.txt

# Harness command (source: harness/wrapper.py in repo).
# Python-only (no jq in base image — stdlib json suffices).
# Invoked explicitly per attempt via `sandbox exec` (see specs/04-worker-cell.md).
# Entrypoint stays the base default (/bin/bash); the task keepalive is the
# trailing `sleep infinity` in the create command — the wrapper is never PID 1.
COPY harness/wrapper.py /usr/local/bin/cell-harness
RUN chmod +x /usr/local/bin/cell-harness

WORKDIR /sandbox
