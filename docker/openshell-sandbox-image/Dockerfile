# syntax=docker/dockerfile:1

# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# OpenShell Community base sandbox image — CentOS Stream 10 variant
#
# Provides the foundational system tools, users, and developer environment
# that all other community sandbox images build on top of.
# Ported from Ubuntu (nvcr.io/nvidia/base/ubuntu:noble) to CentOS Stream 10.
#
# Build:  podman build -t openshell-base:centos-stream10 -f Dockerfile .
#         podman build -t openshell-base:centos-stream10 .
#         docker build -t openshell-base:centos-stream10 .

# System base
FROM quay.io/centos/centos:stream10 AS system

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /sandbox

# Core system dependencies (EL10/RHEL10 package names)
# bind-utils: dig, nslookup (dnsutils on Debian)
# iproute: network namespace management (ip netns, veth pairs) (iproute2 on Debian)
# iptables-nft: nft-based iptables compat (iptables on Debian)
# nftables: bypass detection — log + reject rules
# iputils: ping (iputils-ping on Debian)
# net-tools: ifconfig, etc.
# nmap-ncat: netcat replacement (netcat-openbsd on Debian)
# openssh-server: provides /usr/libexec/openssh/sftp-server (openssh-sftp-server on Debian)
# procps-ng: ps, etc. (procps on Debian)
# traceroute: traceroute
RUN dnf install -y --setopt=install_weak_deps=False \
        ca-certificates \
        curl \
        bind-utils \
        iproute \
        iptables-nft \
        nftables \
        iputils \
        net-tools \
        nmap-ncat \
        openssh-server \
        procps-ng \
        traceroute \
    && dnf clean all \
    && rm -rf /var/cache/dnf /var/cache/yum

# Compatibility symlinks for scripts expecting Debian binary names and PATH
# EL10 places ip/iptables/nft in /usr/sbin which is not in the default sandbox PATH.
# Provide /usr/bin symlinks so tools work without modifying PATH expectations.
RUN ln -sf /usr/bin/ncat /usr/bin/nc 2>/dev/null || true; \
    ln -sf /usr/sbin/ip /usr/bin/ip 2>/dev/null || true; \
    ln -sf /usr/sbin/iptables /usr/bin/iptables 2>/dev/null || true; \
    ln -sf /usr/sbin/iptables-nft /usr/bin/iptables-nft 2>/dev/null || true; \
    ln -sf /usr/sbin/nft /usr/bin/nft 2>/dev/null || true; \
    ln -sf /usr/sbin/iptables /usr/sbin/iptables-legacy 2>/dev/null || true; \
    ln -sf /usr/sbin/ip6tables /usr/bin/ip6tables 2>/dev/null || true

# Create supervisor and sandbox users/groups
RUN groupadd -r supervisor && useradd -r -g supervisor -s /usr/sbin/nologin supervisor && \
    groupadd -r sandbox && useradd -r -g sandbox -d /sandbox -s /bin/bash sandbox

# Developer tools
FROM system AS devtools

# Node.js 22 + build toolchain (needed by npm packages with native addons).
# CentOS Stream 10 AppStream provides nodejs 22.23.1 (patched).
# CVE-2026-21637, CVE-2025-59466, CVE-2025-59465, CVE-2025-55131 affect
# Node.js <= 22.22.1. Stream's 22.23.1 is patched (>22.23.0). The Ubuntu build
# pins to 22.22.1-1nodesource1 (vulnerable) pending upstream patch; here we
# take the distro's patched 22.x.
#
# nodejs-npm ships npm 10 (tar@6.2.1 vulns). Upgraded to npm 11 in same layer.
# npm 11 ships tar@^7.5.9, fixing GHSA-r6q2-hw4h-h46w, GHSA-8qq5-rm4j-mr97,
# GHSA-83g3-92jg-28cx, GHSA-34x7-hfp2-rc4v, GHSA-qffp-2rhf-9h96.
RUN dnf install -y --setopt=install_weak_deps=False \
        gcc \
        gcc-c++ \
        make \
        git \
        nodejs \
        nodejs-npm \
        vim-minimal \
        nano \
    && dnf clean all \
    && rm -rf /var/cache/dnf /var/cache/yum \
    && npm install -g npm@11.11.0

# Global npm packages — pinned for reproducibility.
# tar + @hono/node-server: transitive vuln fixes
#   (GHSA-qffp-2rhf-9h96, GHSA-9ppj-qmqm-q256, GHSA-8qq5-rm4j-mr97,
#    GHSA-r6q2-hw4h-h46w, GHSA-34x7-hfp2-rc4v, GHSA-83g3-92jg-28cx,
#    GHSA-wc8c-qw6v-h7f6).
# opencode-ai + @openai/codex: agent CLIs.
RUN npm install -g \
        tar@7.5.11 \
        @hono/node-server@1.19.11 \
        opencode-ai@1.18.27 \
        @openai/codex@0.117.0 \
        @github/copilot@1.0.16

# GitHub CLI (RPM repo, RHEL/CentOS method)
RUN curl -fsSL https://cli.github.com/packages/rpm/gh-cli.repo -o /etc/yum.repos.d/gh-cli.repo && \
    dnf install -y gh && \
    dnf clean all && rm -rf /var/cache/dnf /var/cache/yum

# Install Claude CLI via native installer (npm method is deprecated)
RUN curl -fsSL https://claude.ai/install.sh | bash \
    && cp /root/.local/bin/claude /usr/local/bin/claude \
    && chmod 755 /usr/local/bin/claude

# uv (Python package/project manager) — pinned for reproducibility.
# uv manages the Python toolchain; no system Python packages are needed.
COPY --from=ghcr.io/astral-sh/uv:0.10.8 /uv /usr/local/bin/uv
ENV UV_PYTHON_INSTALL_DIR="/sandbox/.uv/python"
RUN uv python install 3.14.3 && \
    ln -s $(uv python find 3.14.3) /usr/local/bin/python3 && \
    ln -s $(uv python find 3.14.3) /usr/local/bin/python && \
    uv cache clean

# Final base image
FROM devtools AS final

# Add venvs to PATH -- /sandbox/.venv (writable, user-installed packages)
# takes priority over system paths.
# VIRTUAL_ENV and UV_PYTHON_INSTALL_DIR are also exported in .bashrc
# so that login shell sessions (interactive and exec) see them.
ENV PATH="/sandbox/.venv/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin" \
    VIRTUAL_ENV="/sandbox/.venv"

# Default sandbox network / filesystem policy
COPY policy.yaml /etc/openshell/policy.yaml

# Copy custom skills into the image.
# To add a skill, create a subdirectory under skills/
# with a SKILL.md file (and any supporting files). It will be installed into
# both ~/.claude/skills/ and ~/.agents/skills/ for agent discovery.
COPY skills/ /sandbox/.agents/skills/

# Set up sandbox user home directory
RUN mkdir -p /sandbox/.claude/skills && \
    # Create a writable venv using uv-managed Python 3.14.3.
    # Sandbox users can `uv pip install` (or `pip install`) into
    # this venv without touching the base image layer.
    uv venv --python 3.14.3 --seed /sandbox/.venv && \
    uv pip install --python /sandbox/.venv/bin/python cloudpickle && \
    uv cache clean && \
    chown -R sandbox:sandbox /sandbox/.venv && \
    # Minimal shell init files so interactive and non-interactive shells
    # get a sane PATH and prompt.  Without these, bash sources nothing
    # under /sandbox and tools like VS Code Remote-SSH may mis-detect
    # the platform.
    printf 'export PATH="/sandbox/.venv/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin"\nexport VIRTUAL_ENV="/sandbox/.venv"\nexport UV_PYTHON_INSTALL_DIR="/sandbox/.uv/python"\nexport PS1="\\u@\\h:\\w\\$ "\n' \
        > /sandbox/.bashrc && \
    printf '[ -f ~/.bashrc ] && . ~/.bashrc\n' > /sandbox/.profile && \
    chown sandbox:sandbox /sandbox/.bashrc /sandbox/.profile && \
    # Symlink skills into agent discovery directories
    for skill in /sandbox/.agents/skills/*/; do \
        [ -d "$skill" ] || continue; \
        ln -sf "$skill" "/sandbox/.claude/skills/$(basename "$skill")"; \
    done && \
    chown -R sandbox:sandbox /sandbox/.claude /sandbox/.agents /sandbox

USER sandbox

ENTRYPOINT ["/bin/bash"]
