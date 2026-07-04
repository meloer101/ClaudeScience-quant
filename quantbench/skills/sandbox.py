from __future__ import annotations

import multiprocessing as mp
import os
import queue as queue_mod
import signal
import tempfile
import time
from dataclasses import dataclass
from typing import Any, Callable

from quantbench.config import (
    SANDBOX_CPU_SECONDS,
    SANDBOX_MAX_WRITE_MB,
    SANDBOX_MEM_MB,
    SANDBOX_WALL_TIMEOUT_S,
)

# 'spawn' (not 'fork'): the child gets a fresh interpreter with no inherited
# threads, locks, or open file descriptors from the parent (notably the LLM
# client's connection pool) - fork-safety issues in a long-lived coordinator
# process are a much worse bug than the extra ~100ms interpreter startup cost.
_CONTEXT = mp.get_context("spawn")


class SandboxError(RuntimeError):
    """Raised when the sandboxed call hits a resource limit or otherwise
    fails to produce a result. A plain RuntimeError subclass so existing
    `except Exception` handlers around tool execution (e.g. the coordinator's
    agent loop) already turn this into a structured {"error": ...} result
    without any changes on their end."""


@dataclass(frozen=True)
class SandboxConfig:
    cpu_seconds: int = SANDBOX_CPU_SECONDS
    mem_mb: int = SANDBOX_MEM_MB
    wall_timeout_s: float = SANDBOX_WALL_TIMEOUT_S
    max_write_mb: int = SANDBOX_MAX_WRITE_MB


@dataclass(frozen=True)
class SandboxUsage:
    wall_seconds: float
    exitcode: int | None
    max_rss_bytes: int
    limits: dict[str, int | float]
    unsupported_limits: list[str]
    cpu_limit_hit: bool = False
    wall_timeout_hit: bool = False


_DEFAULT_CONFIG = SandboxConfig()


def run_in_sandbox(
    func: Callable[..., Any],
    *args: Any,
    config: SandboxConfig | None = None,
    usage_sink: list[SandboxUsage] | None = None,
) -> Any:
    """Runs func(*args) in a child process with CPU/address-space/file-size
    rlimits and a wall-clock backstop, and returns its result. `func` must be
    a module-level function (picklable by reference) and its return value
    must be picklable (a pandas Series/DataFrame qualifies).

    Raises SandboxError if the child is killed by a resource limit, times
    out, or otherwise exits without reporting a result. Raises whatever
    exception `func` itself raised (e.g. ValueError from bad signal code)
    unchanged, so callers see the same exception types as the unsandboxed
    path."""
    config = config or _DEFAULT_CONFIG
    result_queue: mp.Queue = _CONTEXT.Queue()
    process = _CONTEXT.Process(target=_run_in_child, args=(func, args, config, result_queue))

    started = time.perf_counter()
    process.start()

    # Drain the queue *while* the child runs, rather than join()-then-get().
    # A child that puts a result larger than the OS pipe buffer (~64KB) cannot
    # terminate until the parent reads it - so joining first would deadlock the
    # parent (blocked in join) against the child (blocked flushing its result).
    # This bit a real cross-sectional backtest: small test panels fit under the
    # buffer, but a full multi-symbol / multi-year factor panel does not, and
    # every such run hung until the wall-clock backstop fired. get() with a
    # timeout reads the result the moment it lands, so the child can exit.
    result_payload = None
    got_result = False
    deadline = started + config.wall_timeout_s
    while True:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            break
        try:
            result_payload = result_queue.get(timeout=min(0.2, remaining))
            got_result = True
            break
        except queue_mod.Empty:
            if not process.is_alive():
                # Child exited without a result on the queue yet; one last
                # non-blocking drain in case it landed as the child exited.
                try:
                    result_payload = result_queue.get_nowait()
                    got_result = True
                except queue_mod.Empty:
                    pass
                break

    if not got_result and process.is_alive():
        # True wall-clock timeout: still running, still no result.
        process.terminate()
        process.join(2.0)
        if process.is_alive():
            process.kill()
            process.join()
        wall_seconds = time.perf_counter() - started
        _append_usage(
            usage_sink,
            SandboxUsage(
                wall_seconds=round(wall_seconds, 6),
                exitcode=process.exitcode,
                max_rss_bytes=0,
                limits=_limits_dict(config),
                unsupported_limits=[],
                wall_timeout_hit=True,
                cpu_limit_hit=_cpu_limit_hit(process.exitcode),
            ),
        )
        raise SandboxError(f"sandbox: wall-clock timeout exceeded ({config.wall_timeout_s}s)")

    process.join(2.0)
    if process.is_alive():
        process.kill()
        process.join()
    wall_seconds = time.perf_counter() - started

    if not got_result:
        _append_usage(
            usage_sink,
            SandboxUsage(
                wall_seconds=round(wall_seconds, 6),
                exitcode=process.exitcode,
                max_rss_bytes=0,
                limits=_limits_dict(config),
                unsupported_limits=[],
                cpu_limit_hit=_cpu_limit_hit(process.exitcode),
            ),
        )
        raise SandboxError(
            f"sandbox: child process terminated abnormally (exit code {process.exitcode}) without "
            "reporting a result - likely killed by the OS for exceeding a resource limit "
            f"(CPU {config.cpu_seconds}s / memory {config.mem_mb}MB)"
        )

    status, payload, child_usage = result_payload
    _append_usage(
        usage_sink,
        SandboxUsage(
            wall_seconds=round(wall_seconds, 6),
            exitcode=process.exitcode,
            max_rss_bytes=child_usage.get("max_rss_bytes", 0),
            limits=_limits_dict(config),
            unsupported_limits=child_usage.get("unsupported_limits", []),
            cpu_limit_hit=_cpu_limit_hit(process.exitcode),
        ),
    )
    if status == "error":
        raise SandboxError(payload)
    if status == "exception":
        exc_type, message = payload
        raise exc_type(message)
    return payload


def _apply_rlimits(config: SandboxConfig) -> list[str]:
    """Applies each POSIX rlimit independently and returns the names of any
    that this platform refused to set, instead of treating one unsupported
    limit as fatal. Notably RLIMIT_AS is unenforceable on macOS/Darwin -
    `setrlimit` fails with EINVAL even though `getrlimit` reports it as
    unlimited - while RLIMIT_CPU and RLIMIT_FSIZE work on both Darwin and
    Linux. CPU time plus the parent's wall-clock join() backstop still bound
    a runaway process even where the memory cap can't be enforced."""
    import resource

    unsupported = []
    for name, limit_id, value in (
        ("RLIMIT_CPU", resource.RLIMIT_CPU, config.cpu_seconds),
        ("RLIMIT_AS", resource.RLIMIT_AS, config.mem_mb * 1024 * 1024),
        ("RLIMIT_FSIZE", resource.RLIMIT_FSIZE, config.max_write_mb * 1024 * 1024),
    ):
        try:
            resource.setrlimit(limit_id, (value, value))
        except (ValueError, OSError):
            unsupported.append(name)
    return unsupported


def _run_in_child(func: Callable[..., Any], args: tuple, config: SandboxConfig, result_queue: mp.Queue) -> None:
    """Runs entirely inside the spawned child process. Never raises back into
    multiprocessing's process bootstrap - every failure mode is caught and
    reported through result_queue instead, since an uncaught exception here
    would just look like an unexplained nonzero exit code to the parent."""
    unsupported_limits = _apply_rlimits(config)

    try:
        # Without Docker/chroot there is no real mount namespace to enforce.
        # Generated code already lacks open()/__import__ at the language layer;
        # running from an empty temp cwd is a small defense-in-depth guard for
        # accidental relative-path writes if that layer is ever loosened.
        with tempfile.TemporaryDirectory(prefix="quantbench-sandbox-") as tmpdir:
            os.chdir(tmpdir)
            result = func(*args)
    except MemoryError:
        result_queue.put(("error", "sandbox: memory limit exceeded", _child_usage(unsupported_limits)))
        return
    except Exception as exc:  # noqa: BLE001 - forward the original exception type/message, not a crash
        result_queue.put(("exception", (type(exc), str(exc)), _child_usage(unsupported_limits)))
        return

    try:
        result_queue.put(("ok", result, _child_usage(unsupported_limits)))
    except Exception as exc:  # noqa: BLE001 - e.g. an unpicklable result; report it rather than hang the parent
        result_queue.put(("error", f"sandbox: failed to serialize result: {exc}", _child_usage(unsupported_limits)))


def _limits_dict(config: SandboxConfig) -> dict[str, int | float]:
    return {
        "cpu_seconds": config.cpu_seconds,
        "mem_mb": config.mem_mb,
        "wall_timeout_s": config.wall_timeout_s,
        "max_write_mb": config.max_write_mb,
    }


def _append_usage(usage_sink: list[SandboxUsage] | None, usage: SandboxUsage) -> None:
    if usage_sink is not None:
        usage_sink.append(usage)


def _cpu_limit_hit(exitcode: int | None) -> bool:
    return exitcode in {-signal.SIGXCPU, -signal.SIGKILL}


def _child_usage(unsupported_limits: list[str]) -> dict[str, Any]:
    import resource
    import sys

    max_rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if sys.platform != "darwin":
        max_rss *= 1024
    return {"max_rss_bytes": max_rss, "unsupported_limits": unsupported_limits}
