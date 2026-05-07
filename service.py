"""
TESSR-LOGIC Windows Service Wrapper (pywin32)
Usage:
    python service.py install    - Install as Windows service
    python service.py start      - Start the service
    python service.py stop       - Stop the service
    python service.py remove     - Remove the service
    python service.py debug      - Run in foreground for debugging

Requires: pip install pywin32
"""
import sys
import os
import subprocess
import logging
import time
from pathlib import Path

# --- Service config ---
SERVICE_NAME = "TESSR-LOGIC"
DISPLAY_NAME = "TESSR-LOGIC Multi-Agent Build System"
DESCRIPTION = "Autonomous build pipeline: Architect → Coder → Validator → Builder → SmokeTester"
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Setup logging to file
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "service.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


class UvicornService:
    """Lightweight service runner that can be used with or without pywin32."""

    def __init__(self):
        self._proc = None
        self._running = False
        self._base_dir = Path(__file__).parent

    def _build_cmd(self):
        """Build the uvicorn command."""
        python = sys.executable
        # Ensure PYTHONPATH includes the backend parent
        env = os.environ.copy()
        backend_parent = str(self._base_dir / "backend" / "..")
        env["PYTHONPATH"] = backend_parent + os.pathsep + env.get("PYTHONPATH", "")
        cmd = [python, "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
        return cmd, env

    def run(self):
        """Run in foreground (for debugging)."""
        cmd, env = self._build_cmd()
        logger.info("Starting TESSR-LOGIC in foreground...")
        logger.info("Command: %s", " ".join(cmd))
        logger.info("Open http://localhost:8000")
        subprocess.run(cmd, cwd=self._base_dir, env=env)

    def start(self):
        """Start the uvicorn process."""
        if self._running:
            return
        cmd, env = self._build_cmd()
        logger.info("Starting uvicorn: %s", " ".join(cmd))
        self._proc = subprocess.Popen(cmd, cwd=self._base_dir, env=env,
            stdout=open(LOG_DIR / "service-out.log", "a"),
            stderr=open(LOG_DIR / "service-err.log", "a"),
        )
        self._running = True
        logger.info("Uvicorn started (PID %s)", self._proc.pid)

    def stop(self):
        """Stop the uvicorn process."""
        if not self._running:
            return
        logger.info("Stopping uvicorn...")
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning("Force killing uvicorn")
                self._proc.kill()
        self._running = False
        logger.info("Uvicorn stopped")

    def monitor(self):
        """Monitor and restart if process dies."""
        self.start()
        while self._running:
            if self._proc and self._proc.poll() is not None:
                logger.warning("Uvicorn exited (code %s), restarting...", self._proc.returncode)
                self.start()
            time.sleep(5)


# --- Windows Service integration (pywin32) ---
try:
    import win32serviceutil
    import win32service
    import win32event
    import servicemanager
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False


if HAS_WIN32:
    class TESSRService(win32serviceutil.ServiceFramework):
        _svc_name_ = SERVICE_NAME
        _svc_display_name_ = DISPLAY_NAME
        _svc_description_ = DESCRIPTION

        def __init__(self, args):
            win32serviceutil.ServiceFramework.__init__(self, args)
            self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
            self.runner = UvicornService()

        def SvcStop(self):
            logger.info("Service stop signal received")
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            self.runner.stop()
            win32event.SetEvent(self.hWaitStop)
            self.ReportServiceStatus(win32service.SERVICE_STOPPED)

        def SvcDoRun(self):
            logger.info("Service starting...")
            servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STARTED, (self._svc_name_, ''))
            self.ReportServiceStatus(win32service.SERVICE_RUNNING)
            try:
                self.runner.start()
                # Wait for stop signal
                while self.runner._running:
                    rc = win32event.WaitForSingleObject(self.hWaitStop, 5000)
                    if rc == win32event.WAIT_OBJECT_0:
                        break
                    # Check if uvicorn died
                    if self.runner._proc and self.runner._proc.poll() is not None:
                        logger.warning("Uvicorn died, restarting...")
                        self.runner.start()
            except Exception as e:
                logger.exception("Service error: %s", e)
                servicemanager.LogMsg(servicemanager.EVENTLOG_ERROR_TYPE,
                    servicemanager.PYS_SERVICE_STARTED, (self._svc_name_, str(e)))

            self.runner.stop()
            servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STOPPED, (self._svc_name_, ''))


def main():
    if len(sys.argv) < 2:
        print("Usage: python service.py <install|start|stop|remove|debug>")
        print("  install  - Install as Windows service (requires admin)")
        print("  start    - Start the service")
        print("  stop     - Stop the service")
        print("  remove   - Remove the service")
        print("  debug    - Run in foreground (no service registration)")
        return

    action = sys.argv[1].lower()

    if action == "debug":
        UvicornService().run()
        return

    if not HAS_WIN32:
        print("ERROR: pywin32 not installed.")
        print("Install with: pip install pywin32")
        print("")
        print("Alternative: Use install-service.ps1 (NSSM-based, no pywin32 needed)")
        sys.exit(1)

    if action == "install":
        win32serviceutil.HandleCommandLine(TESSRService, argv=[sys.argv[0], "install", SERVICE_NAME])
        print(f"Service '{SERVICE_NAME}' installed.")
        print(f"Start with: python service.py start")
    elif action == "start":
        win32serviceutil.HandleCommandLine(TESSRService, argv=[sys.argv[0], "start", SERVICE_NAME])
    elif action == "stop":
        win32serviceutil.HandleCommandLine(TESSRService, argv=[sys.argv[0], "stop", SERVICE_NAME])
    elif action == "remove":
        win32serviceutil.HandleCommandLine(TESSRService, argv=[sys.argv[0], "remove", SERVICE_NAME])
        print(f"Service '{SERVICE_NAME}' removed.")
    else:
        print(f"Unknown action: {action}")


if __name__ == "__main__":
    main()
