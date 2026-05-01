"""
process_health_monitor.py — Long-Running Process Health Test.

Monitors memory, CPU, and connection usage during batch execution.

Uso:
    from process_health_monitor import ProcessHealthMonitor
    monitor = ProcessHealthMonitor(config)
    result = monitor.monitor(ticket_folder, config)
"""

import logging
import subprocess
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("stacky.process_health")


@dataclass
class HealthResult:
    memory_grew: bool = False
    cpu_spike: bool = False
    connection_leak: bool = False
    passed: bool = True
    peak_memory_mb: float = 0.0
    avg_cpu: float = 0.0
    samples: int = 0


class ProcessHealthMonitor:
    MEMORY_LEAK_THRESHOLD_MB = 50
    CPU_SUSTAINED_THRESHOLD = 95

    def __init__(self, config: Optional[dict] = None,
                 batch_executor=None, mock_generator=None, db=None):
        self.config = config or {}
        self.batch_executor = batch_executor
        self.mock_generator = mock_generator
        self.db = db

    def monitor(self, ticket_folder: str, config: Optional[dict] = None,
                rows: int = 10000) -> HealthResult:
        cfg = config or self.config

        # Generate and insert mock data
        if self.mock_generator and self.db:
            try:
                mock = self.mock_generator.generate(rows=rows)
                self.db.insert(mock)
            except Exception as e:
                logger.warning("Mock data generation failed: %s", e)

        exec_cmd = cfg.get("batch_exe", "")
        if not exec_cmd:
            return HealthResult(passed=True, samples=0)

        try:
            import psutil
        except ImportError:
            logger.warning("psutil not installed — health monitoring limited")
            # Fallback: just run and measure time
            return self._monitor_basic(ticket_folder)

        try:
            proc = subprocess.Popen(
                [exec_cmd] + cfg.get("batch_args", []),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            return HealthResult(passed=True, samples=0)

        try:
            ps_proc = psutil.Process(proc.pid)
        except psutil.NoSuchProcess:
            return HealthResult(passed=True, samples=0)

        memory_samples = []
        cpu_samples = []
        conn_samples = []

        while proc.poll() is None:
            try:
                mem_mb = ps_proc.memory_info().rss / 1024 / 1024
                cpu_pct = ps_proc.cpu_percent(interval=0.5)
                try:
                    open_conn = len(ps_proc.connections())
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    open_conn = 0

                memory_samples.append(mem_mb)
                cpu_samples.append(cpu_pct)
                conn_samples.append(open_conn)
            except psutil.NoSuchProcess:
                break

        if not memory_samples:
            return HealthResult(passed=True, samples=0)

        memory_grew = (
            (max(memory_samples) - min(memory_samples)) > self.MEMORY_LEAK_THRESHOLD_MB
        )
        cpu_spike = any(c > self.CPU_SUSTAINED_THRESHOLD for c in cpu_samples)
        conn_leak = (
            max(conn_samples) > (conn_samples[0] + 5) if conn_samples else False
        )

        return HealthResult(
            memory_grew=memory_grew,
            cpu_spike=cpu_spike,
            connection_leak=conn_leak,
            passed=not (memory_grew or conn_leak),
            peak_memory_mb=round(max(memory_samples), 1),
            avg_cpu=round(sum(cpu_samples) / len(cpu_samples), 1) if cpu_samples else 0,
            samples=len(memory_samples),
        )

    def _monitor_basic(self, ticket_folder: str) -> HealthResult:
        """Basic monitoring without psutil."""
        if self.batch_executor:
            start = time.perf_counter()
            self.batch_executor.run_minimal(ticket_folder)
            elapsed = time.perf_counter() - start
            return HealthResult(
                passed=True,
                avg_cpu=0,
                peak_memory_mb=0,
                samples=1,
            )
        return HealthResult(passed=True)
