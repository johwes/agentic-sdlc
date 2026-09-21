# Worker cell layer (see specs/04-worker-cell.md).
#
# Thin layer on top of the local sandbox base image
# (docker/openshell-sandbox-image/Dockerfile — CentOS Stream 10 port of
# upstream NVIDIA/OpenShell-Community sandboxes/base). The base provides
# runtimes (Node 22, Python 3.14 via uv), agent CLIs (opencode, codex,
# copilot, claude), gh, git, skills, and the default policy. This layer
# adds only the Ralph-loop contract: prompt, harness command, OpenCode config.
#
# Build base first (from docker/openshell-sandbox-image/):
#   podman build -t openshell-base:centos-stream10 .
# Then this layer:
#   podman build -t worker-cell:latest -f docker/worker-cell.Dockerfile .

ARG BASE_IMAGE=openshell-base:centos-stream10
FROM ${BASE_IMAGE}

# Contract artifacts (all on read-only-at-runtime paths). The base image
# ends in `USER sandbox`, which cannot mkdir in /etc — so escalate for the
# install and drop back. Files stay root-owned but world-readable, which is
# all the sandbox user needs (read_only mounts are readable, not writable).
USER root
RUN mkdir -p /etc/prompts /etc/opencode
# Contract prompts (source: prompts/* in repo).
COPY prompts/worker_contract.txt /etc/prompts/worker_contract.txt
COPY prompts/triage_contract.txt /etc/prompts/triage_contract.txt
# Sandbox OpenCode config (source: config/opencode-sandbox.json in repo).
# opencode needs blanket permission from config (unlike claude's CLI flag),
# and /etc is read-only at runtime — so the file must be baked here, never
# uploaded. Auth still comes only from the attached provider (see 04).
COPY config/opencode-sandbox.json /etc/opencode/opencode.json
# Harness command (source: harness/wrapper.py in repo).
# Python-only (no jq in base image — stdlib json suffices).
# Invoked explicitly per attempt via `sandbox exec` (see specs/04-worker-cell.md).
# Entrypoint stays the base default (/bin/bash); cell keepalive is provided
# by the sandbox runtime — `sandbox create` takes no initial command, and
# stays attached while the keepalive runs, so the spawner polls for Ready.
# The wrapper is invoked explicitly per exec — never as PID 1.
COPY harness/wrapper.py /usr/local/bin/cell-harness
RUN chmod +x /usr/local/bin/cell-harness \
  && chmod 644 /etc/prompts/worker_contract.txt /etc/prompts/triage_contract.txt /etc/opencode/opencode.json
USER sandbox

WORKDIR /sandbox
