"""
Agent adapters for asdlc.
Wraps commodity coding agents (opencode, claude, antigravity, and mock) as subprocesses.
"""

from __future__ import annotations

import abc
from pathlib import Path
import subprocess
from typing import Callable, Any


class AgentAdapter(abc.ABC):
    """Abstract interface for external coding agents."""

    def __init__(self, name: str):
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @abc.abstractmethod
    def run_turn(
        self,
        prompt: str,
        workdir: Path,
        trace_logger: Callable[[dict[str, Any]], None],
    ) -> int:
        """Executes one attempt by the agent in workdir. Returns exit code."""
        ...


class MockAgentAdapter(AgentAdapter):
    """Deterministic adapter for fast offline testing and verification."""

    def __init__(self, name: str = "mock", solver_fn: Callable[[Path], None] | None = None):
        super().__init__(name)
        self.solver_fn = solver_fn

    def run_turn(
        self,
        prompt: str,
        workdir: Path,
        trace_logger: Callable[[dict[str, Any]], None],
    ) -> int:
        if self.solver_fn:
            self.solver_fn(workdir)
        trace_logger({"action": "mock_solve", "exit_code": 0})
        return 0


class SubprocessAgentAdapter(AgentAdapter):
    """Base class for CLI-wrapped coding agents."""

    def __init__(self, name: str, cli_command: list[str]):
        super().__init__(name)
        self.cli_command = cli_command

    def run_turn(
        self,
        prompt: str,
        workdir: Path,
        trace_logger: Callable[[dict[str, Any]], None],
    ) -> int:
        cmd = [*self.cli_command, prompt]
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(workdir),
                capture_output=True,
                text=True,
            )
            exit_code = proc.returncode
            trace_logger({
                "action": "execute_agent_subshell",
                "command": " ".join(cmd),
                "exit_code": exit_code,
                "stdout_snippet": proc.stdout[:200] if proc.stdout else "",
                "stderr_snippet": proc.stderr[:200] if proc.stderr else "",
            })
            return exit_code
        except FileNotFoundError as e:
            trace_logger({"action": "error", "error": f"Agent executable not found: {e}"})
            return 127


class OpenCodeAdapter(SubprocessAgentAdapter):
    def __init__(self):
        super().__init__(name="opencode", cli_command=["opencode", "run"])


class ClaudeAdapter(SubprocessAgentAdapter):
    def __init__(self):
        super().__init__(name="claude", cli_command=["claude", "-p"])


class AntigravityAdapter(SubprocessAgentAdapter):
    def __init__(self):
        super().__init__(name="antigravity", cli_command=["agy", "--prompt"])


def get_adapter(name: str) -> AgentAdapter:
    """Factory function returning the adapter by name."""
    adapters: dict[str, type[AgentAdapter]] = {
        "mock": MockAgentAdapter,
        "opencode": OpenCodeAdapter,
        "claude": ClaudeAdapter,
        "antigravity": AntigravityAdapter,
    }
    adapter_cls = adapters.get(name.lower())
    if not adapter_cls:
        raise ValueError(f"Unknown agent adapter: '{name}'. Supported: {list(adapters.keys())}")
    return adapter_cls()
