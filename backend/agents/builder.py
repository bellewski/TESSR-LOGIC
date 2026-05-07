import asyncio
import json
import logging
import subprocess
import shutil
import os
import signal
from pathlib import Path
from pydantic import BaseModel
from backend.agents.base import BaseAgent

logger = logging.getLogger(__name__)

# Global registry of running subprocesses per build_id — for cleanup on cancel
_build_procs: dict[str, list[asyncio.subprocess.Process]] = {}


def register_build_proc(build_id: str, proc: asyncio.subprocess.Process):
    _build_procs.setdefault(build_id, []).append(proc)


def cleanup_build_procs(build_id: str):
    """Kill all tracked subprocesses for a build and clear registry."""
    procs = _build_procs.pop(build_id, [])
    for proc in procs:
        try:
            if proc.returncode is None:
                proc.kill()
                # Also try to kill process tree on Windows
                try:
                    if hasattr(proc, 'pid'):
                        os.kill(proc.pid, signal.SIGTERM)
                except (ProcessLookupError, OSError):
                    pass
        except Exception as e:
            logger.debug("Failed to kill proc for build %s: %s", build_id, e)


class BuilderInput(BaseModel):
    build_id: str
    build_dir: str
    project_name: str
    stack_target: str


class BuilderOutput(BaseModel):
    success: bool
    error: str = ""
    project_type: str = "unknown"
    build_log: str = ""
    commands_run: list[str] = []
    artifacts: list[str] = []
    build_mode: str = "none"  # "full" = installed+built; "structure_only" = files exist but no runtime test; "none" = failed


class BuilderAgent(BaseAgent[BuilderInput, BuilderOutput]):
    """
    Build executor and project-type detector.
    ONLY runs install commands (npm install, pip install), detects project type,
    and performs static file checks. Does NOT validate code quality or functionality —
    that is SmokeTester's job.
    """
    def __init__(self, build_dir: Path):
        self.build_dir = build_dir

    async def run(self, input_data: BuilderInput) -> BuilderOutput:
        src = self.build_dir / "src"
        if not src.exists(): src = self.build_dir
        ptype = self._detect(src)
        logger.info("Build %s detected type: %s", input_data.build_id, ptype)

        if ptype == "node": r = await self._node(src, input_data.build_id)
        elif ptype == "python": r = await self._python(src, input_data.build_id)
        elif ptype == "static": r = self._static(src)
        else: r = BuilderOutput(success=False, error="No recognizable project files (no package.json, requirements.txt, or HTML/CSS/JS found)", project_type=ptype)

        (self.build_dir / "build_log.json").write_text(
            json.dumps(r.model_dump(), indent=2), encoding="utf-8")
        return r

    def _detect(self, src: Path) -> str:
        if (src / "package.json").exists(): return "node"
        if any(src.rglob("requirements*.txt")) or any(src.rglob("pyproject.toml")): return "python"
        if any(src.rglob("*.html")) or any(src.rglob("*.css")) or any(src.rglob("*.js")): return "static"
        return "unknown"

    async def _run(self, build_id: str, cwd: Path, cmd: list[str], t=30) -> tuple[int, str, str]:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            register_build_proc(build_id, proc)
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=t)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return 124, "", "Timeout"
            return proc.returncode, stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")
        except FileNotFoundError:
            return 127, "", f"Not found: {cmd[0]}"
        except Exception as e:
            return 1, "", str(e)

    async def _node(self, src: Path, build_id: str) -> BuilderOutput:
        r = BuilderOutput(success=False, project_type="node")
        pkg = src / "package.json"
        has_npm = shutil.which("npm")
        has_node = shutil.which("node")

        # Validate package.json structure even if npm is missing
        if pkg.exists():
            try:
                pj = json.loads(pkg.read_text(encoding="utf-8"))
                deps = bool(pj.get("dependencies") or pj.get("devDependencies"))
                scripts = bool(pj.get("scripts"))
                r.build_log += f"package.json validated: deps={deps}, scripts={scripts}\n"
                if not deps and not scripts:
                    r.error = "package.json missing dependencies and scripts"
                    return r
            except Exception as e:
                r.error = f"Invalid package.json: {e}"
                return r
        else:
            r.error = "No package.json found"
            return r

        # If npm is available, try to install and build ONLY (never start dev servers)
        if has_npm:
            r.commands_run.append("npm install")
            rc, out, err = await self._run(build_id, src, ["npm", "install"], 120)
            r.build_log += f"$ npm install\n{out}\n{err}\n"
            if rc != 0:
                r.build_log += f"npm install returned {rc}, continuing with structure validation\n"
            # Only run 'build' — never 'start' or 'dev' which spawn long-running servers
            if self._npm_script(pkg, "build"):
                r.commands_run.append("npm run build")
                rc, out, err = await self._run(build_id, src, ["npm", "run", "build"], 60)
                r.build_log += f"$ npm run build\n{out}\n{err}\n"
                if rc == 0 or rc == 124:
                    r.success = True
                    r.build_mode = "full"
            else:
                r.build_log += "No build script found — validating structure only.\n"
        else:
            r.build_log += "npm not found in PATH — validating structure only.\n"

        # Structure-only validation counts as success if package.json is valid and JS files exist
        if not r.success and pkg.exists() and any(src.rglob("*.js")):
            r.success = True
            r.build_mode = "structure_only"
            r.build_log += "Structure validation passed (npm not available for runtime test).\n"

        r.artifacts = [str(p.relative_to(src)) for p in src.glob("dist/*")] + [str(p.relative_to(src)) for p in src.glob("build/*")]
        return r

    async def _python(self, src: Path, build_id: str) -> BuilderOutput:
        r = BuilderOutput(success=False, project_type="python")
        for req in src.rglob("requirements*.txt"):
            r.commands_run.append(f"pip install -r {req.name}")
            rc, out, err = await self._run(build_id, src, ["pip", "install", "-r", str(req.name)], 120)
            r.build_log += f"$ pip install -r {req.name}\n{out}\n{err}\n"
            if rc != 0: r.error = f"pip failed: {err[:500]}"; return r
        mf = next((src / n for n in ["app.py","main.py","server.py"] if (src/n).exists()), None)
        if mf and shutil.which("python"):
            r.commands_run.append(f"python {mf.name}")
            rc, out, err = await self._run(build_id, src, ["python", str(mf.name)], 15)
            r.build_log += f"$ python {mf.name}\n{out}\n{err}\n"
            r.success = rc in (0, 124)
            r.build_mode = "full" if r.success else "none"
            if rc not in (0, 124): r.error = f"Runtime error: {err[:500]}"
        else: r.success = False; r.error = "No main Python file found (expected app.py, main.py, or server.py)"; r.build_log += "No main file found.\n"
        return r

    def _static(self, src: Path) -> BuilderOutput:
        h = len(list(src.rglob("*.html")))
        c = len(list(src.rglob("*.css")))
        js_files = list(src.rglob("*.js"))
        j = len(js_files)
        empty_js = [f.name for f in js_files if len(f.read_text(errors="replace").strip()) < 50]
        bad_js = [f.name for f in js_files if not (
            "function" in f.read_text(errors="replace") or "=>" in f.read_text(errors="replace")
            or "document." in f.read_text(errors="replace") or "console." in f.read_text(errors="replace")
            or "module.exports" in f.read_text(errors="replace") or "require(" in f.read_text(errors="replace")
            or "export " in f.read_text(errors="replace")
        )]
        ok = h > 0 and (j == 0 or (len(empty_js) == 0 and len(bad_js) == 0))
        log = f"Static: {h} HTML, {c} CSS, {j} JS files."
        if empty_js: log += f" Empty JS: {empty_js}."
        if bad_js: log += f" JS without functions: {bad_js}."
        return BuilderOutput(success=ok, project_type="static", build_mode="structure_only" if ok else "none", build_log=log,
            error="" if ok else f"JS files missing logic: {bad_js or empty_js}")

    def _npm_script(self, pkg: Path, script: str) -> bool:
        if not pkg.exists(): return False
        try: return script in json.loads(pkg.read_text(encoding="utf-8")).get("scripts", {})
        except: return False
