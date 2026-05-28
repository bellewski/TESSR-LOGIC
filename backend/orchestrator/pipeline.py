import logging
import json
import shutil
import time
from pathlib import Path
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models.build import BuildStatus, BuildPhase
from backend.repositories.build_repo import BuildRepository
from backend.repositories.event_repo import EventRepository
from backend.repositories.file_repo import FileRepository
from backend.repositories.finding_repo import FindingRepository
from backend.repositories.directory_repo import DirectoryConfigRepository
from backend.providers.ollama_provider import OllamaProvider
from backend.agents.architect import ArchitectAgent, ArchitectInput
from backend.agents.coder import CoderAgent, CoderInput
from backend.agents.hardener import HardenerAgent, HardenerInput
from backend.agents.fixer import FixerAgent, FixerInput
from backend.agents.validator import ValidatorAgent, ValidatorInput
from backend.agents.builder import BuilderAgent, BuilderInput, cleanup_build_procs
from backend.agents.smoke_tester import SmokeTesterAgent, SmokeTesterInput
from backend.agents.ui_designer import UIDesignerAgent, UIDesignerInput
from backend.orchestrator.event_bus import event_bus

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


def _cleanup_old_builds(builds_root: Path, max_age_hours: int = 24, keep_max: int = 10):
    """Remove build directories older than max_age_hours, keeping at most keep_max recent ones."""
    if not builds_root.exists():
        return
    dirs = [(d, d.stat().st_mtime) for d in builds_root.iterdir() if d.is_dir()]
    if len(dirs) <= keep_max:
        return
    dirs.sort(key=lambda x: x[1], reverse=True)
    cutoff = time.time() - (max_age_hours * 3600)
    removed = 0
    for d, mtime in dirs[keep_max:]:
        if mtime < cutoff:
            try:
                shutil.rmtree(d)
                removed += 1
            except Exception:
                pass
    if removed:
        logger.info("Cleaned up %d old build directories from %s", removed, builds_root)


class BuildPipeline:
    def __init__(self, db: Session):
        self.db = db
        self.build_repo = BuildRepository(db)
        self.event_repo = EventRepository(db)
        self.file_repo = FileRepository(db)
        self.finding_repo = FindingRepository(db)
        self.dir_repo = DirectoryConfigRepository(db)

    async def _check_cancelled(self, build_id: str) -> bool:
        """Return True if build was cancelled by user."""
        build = self.build_repo.get_by_id(build_id)
        if not build:
            cleanup_build_procs(build_id)
            return True
        if build.status == BuildStatus.failed and build.error_message and "cancelled" in build.error_message.lower():
            logger.info("Build %s was cancelled — aborting pipeline", build_id)
            cleanup_build_procs(build_id)
            return True
        return False

    async def run(self, build_id: str):
        build = self.build_repo.get_by_id(build_id)
        if not build:
            logger.error("Build %s not found", build_id)
            return

        # Load directory config if present
        dir_cfg = self.dir_repo.get_by_build(build_id)
        workspace_base = (
            Path(dir_cfg.workspace_dir) if dir_cfg and dir_cfg.workspace_dir
            else Path(settings.workspace_path)
        )
        build_dir = workspace_base / build_id
        build_dir.mkdir(parents=True, exist_ok=True)

        # Cleanup old build directories to prevent file buildup
        _cleanup_old_builds(workspace_base)

        # Load project context summary if linked
        project_context_summary = ""
        source_dir = dir_cfg.source_dir if dir_cfg else ""
        if dir_cfg and dir_cfg.project_context_id:
            from backend.models.project_context import ProjectContext
            ctx = self.db.query(ProjectContext).filter(
                ProjectContext.id == dir_cfg.project_context_id
            ).first()
            if ctx and ctx.context_summary:
                project_context_summary = ctx.context_summary

        provider = OllamaProvider(mode=build.mode)

        await self._emit(build_id, "pipeline_start", "Pipeline started", status="running")
        self.build_repo.update_status(build_id, BuildStatus.running)

        try:
            # ── Phase 1: Architect (with timeout retry) ────────────────────────
            arch_output = None
            for arch_attempt in range(2):
                if await self._check_cancelled(build_id): return
                if arch_attempt > 0:
                    await self._emit(build_id, "architect_retry", f"Architect timeout — retrying ({arch_attempt}/1)...", phase="architecting")
                arch_output = await self._run_architect(
                    build, build_dir, provider,
                    project_context_summary=project_context_summary,
                    source_dir=source_dir or "",
                )
                if arch_output.success:
                    break
                if "timed out" in (arch_output.error or "").lower() and arch_attempt == 0:
                    continue  # Retry once on timeout
                break
            if not arch_output or not arch_output.success:
                await self._fail(build_id, f"Architect failed: {arch_output.error if arch_output else 'No output'}")
                return

            # ── Project Manager: resolve any architectural conflicts ────────
            if await self._check_cancelled(build_id): return
            pm_output = await self._run_project_manager(build, build_dir, provider, arch_output)
            if pm_output and pm_output.success and pm_output.corrected_file_plan:
                logger.info("Pipeline: Project Manager corrected file plan (%d → %d files)",
                            len(arch_output.file_plan), len(pm_output.corrected_file_plan))
                arch_output.file_plan = pm_output.corrected_file_plan
                await self._emit(build_id, "project_manager_correction",
                    f"Project Manager corrected file plan: {pm_output.resolution[:200]}",
                    phase="architecting")

            # ── Outer loop: keep regenerating until builder can run something ──
            MAX_BUILD_RETRIES = 2
            fix_feedback = ""
            coder_output = None
            smoke_output = None  # type: SmokeTesterOutput | None
            previous_findings = []  # Store Hardener findings for retry cycles

            for build_round in range(MAX_BUILD_RETRIES + 1):
                if await self._check_cancelled(build_id): return
                if build_round > 0:
                    await self._emit(build_id, "build_retry",
                        f"Build round {build_round}: previous output not runnable — regenerating with feedback",
                        phase="coding")
                    # Create isolated round folder and clean previous artifacts
                    round_dir = build_dir / f"round_{build_round}"
                    round_dir.mkdir(exist_ok=True)
                    src_dir = round_dir / "src"
                    if src_dir.exists():
                        import shutil
                        shutil.rmtree(src_dir)
                    # Clear accumulated generated files from database
                    cleared_count = self.file_repo.clear_by_build(build_id)
                    logger.info("Pipeline: Cleared %d accumulated file records for round %d", cleared_count, build_round)
                else:
                    # First round - use standard src directory
                    src_dir = build_dir / "src"
                    if src_dir.exists():
                        import shutil
                        shutil.rmtree(src_dir)
                    round_dir = build_dir

                # Inner retry loop (validator feedback)
                for attempt in range(MAX_RETRIES + 1):
                    if attempt > 0:
                        self.build_repo.increment_retry(build_id)
                        await self._emit(build_id, "retry", f"Retry attempt {attempt}", phase="coding")
                        # Wipe src/ before retry so stale files don't accumulate
                        src_dir = round_dir / "src"
                        if src_dir.exists():
                            import shutil as _shutil
                            _shutil.rmtree(src_dir)
                            logger.info("Pipeline: Wiped src/ before inner retry attempt %d", attempt)
                        # Clear DB file records so UI doesn't show duplicates
                        self.file_repo.clear_by_build(build_id)
                        logger.info("Pipeline: Cleared file records before inner retry attempt %d", attempt)

                    if await self._check_cancelled(build_id): return
                    # Pass previous Hardener findings to Coder on retry cycles
                    coder_output = await self._run_coder(build, round_dir, provider, arch_output, fix_feedback, previous_findings)
                    if not coder_output.success:
                        # ALL coder validation failures are retryable — pass error back as feedback
                        fix_feedback = (
                            f"CRITICAL: Coder failed self-validation. Error: {coder_output.error}\n"
                            f"You MUST fix ALL issues listed above. "
                            f"Every file must have real, working code with no stubs or placeholders."
                        )
                        await self._emit(build_id, "coder_retry",
                            f"Validation failed — retrying: {coder_output.error[:200]}", phase="coding")
                        continue  # retry in next inner loop attempt

                    # Pre-flight: verify coder actually produced runnable files
                    src_dir = round_dir / "src"
                    found_files = list(src_dir.rglob("*")) if src_dir.exists() else []
                    found_exts = sorted(set(p.suffix.lower() for p in found_files if p.is_file()))
                    has_pkg = (src_dir / "package.json").exists() if src_dir.exists() else False
                    has_req = any(src_dir.glob("requirements*.txt")) if src_dir.exists() else False
                    has_html = any(src_dir.rglob("*.html")) if src_dir.exists() else False
                    has_py = any(src_dir.rglob("*.py")) if src_dir.exists() else False
                    has_js = any(src_dir.rglob("*.js")) if src_dir.exists() else False
                    file_list = [str(p.relative_to(src_dir)) for p in found_files if p.is_file()][:20]
                    runnable = has_pkg or has_req or has_html or has_py or has_js
                    await self._emit(build_id, "coder_files",
                        f"Coder wrote {len([p for p in found_files if p.is_file()])} files. Extensions: {found_exts or 'none'}. Runnable={runnable}",
                        phase="coding",
                        payload=json.dumps({
                            "file_count": len([p for p in found_files if p.is_file()]),
                            "extensions": found_exts,
                            "has_package_json": has_pkg,
                            "has_requirements": has_req,
                            "has_html": has_html,
                            "has_python": has_py,
                            "has_javascript": has_js,
                            "files_preview": file_list,
                        }))

                    if not runnable:
                        fix_feedback = (
                            f"CRITICAL: No runnable project files were generated. "
                            f"Files found: {found_exts}. "
                            f"You MUST generate a complete runnable project with actual code files. "
                            f"For web apps: src/index.html + src/style.css + src/app.js. "
                            f"For Node.js: src/package.json with dependencies and scripts + JS files. "
                            f"For Python: src/requirements.txt + src/app.py. "
                            f"DO NOT generate documentation, README, or planning files. ONLY code."
                        )
                        await self._emit(build_id, "coder_missing_runnable",
                            f"No runnable files detected — skipping to next round", phase="coding")
                        continue  # Skip to next build round

                    if await self._check_cancelled(build_id): return
                    # ── Phase 2.5: File Consolidator ───────────────────────────
                    logger.info("Pipeline: Starting FileConsolidator phase for build %s", build_id)
                    await self._emit(build_id, "phase_start", "Consolidating files...", phase="coding")
                    from backend.agents.file_consolidator import FileConsolidatorAgent, FileConsolidatorInput
                    consolidator = FileConsolidatorAgent(round_dir)
                    consolidate_input = FileConsolidatorInput(build_id=build.id, build_dir=str(round_dir))
                    consolidate_output = await consolidator.run(consolidate_input)
                    logger.info("Pipeline: FileConsolidator completed with success=%s", consolidate_output.success)
                    if not consolidate_output.success:
                        await self._emit(build_id, "consolidator_error", f"FileConsolidator failed: {consolidate_output.error}", phase="coding")
                        # Don't fail the build, just log the error
                        logger.warning("FileConsolidator failed but continuing: %s", consolidate_output.error)
                    else:
                        await self._emit(build_id, "files_consolidated", 
                            f"Consolidated files: removed {len(consolidate_output.removed_files)} extra files", 
                            phase="coding")
                        logger.info("Pipeline: FileConsolidator removed %d files", len(consolidate_output.removed_files))

                    if await self._check_cancelled(build_id): return
                    # ── Phase 3: UI Designer ─────────────────────────────────
                    ui_fix_feedback = ""
                    for ui_attempt in range(MAX_RETRIES + 1):
                        ui_output = await self._run_ui_designer(build, round_dir, provider, arch_output, coder_output, ui_fix_feedback)
                        if ui_output and ui_output.success and ui_output.generated_files:
                            coder_output.generated_files.extend(ui_output.generated_files)
                            break
                        if ui_attempt >= MAX_RETRIES:
                            await self._emit(build_id, "phase_error", f"UI Designer exhausted {MAX_RETRIES} retries: {ui_output.error if ui_output else 'No output'}", phase="designing")
                            break
                        ui_fix_feedback = (
                            f"UI Designer failed: {ui_output.error if ui_output else 'No parseable CSS output'}\n"
                            f"You MUST output CSS files inside ```css blocks with /* FILE: filename.css */ header. "
                            f"Generate complete CSS with real rules."
                        )
                        await self._emit(build_id, "retry", f"UI Designer retry {ui_attempt + 1}", phase="designing")

                    if await self._check_cancelled(build_id): return
                    # ── Phase 3.5: File Consolidator (after UI Designer) ─────────────
                    logger.info("Pipeline: Running FileConsolidator after UI Designer")
                    from backend.agents.file_consolidator import FileConsolidatorAgent, FileConsolidatorInput
                    consolidator = FileConsolidatorAgent(round_dir)
                    consolidate_input = FileConsolidatorInput(build_id=build.id, build_dir=str(round_dir))
                    consolidate_output = await consolidator.run(consolidate_input)
                    if consolidate_output.success and consolidate_output.removed_files:
                        await self._emit(build_id, "files_consolidated", 
                            f"Removed {len(consolidate_output.removed_files)} duplicate CSS/JS files", 
                            phase="designing")
                        logger.info("Pipeline: FileConsolidator removed %d files", len(consolidate_output.removed_files))

                    if await self._check_cancelled(build_id): return
                    # ── Phase 4: Hardener ──────────────────────────────────
                    hard_output = await self._run_hardener(build, round_dir, provider, coder_output)
                    if not hard_output.success:
                        await self._fail(build_id, f"Hardener failed: {hard_output.error}")
                        return
                    
                    # Store findings for next retry cycle
                    previous_findings = hard_output.findings

                    if await self._check_cancelled(build_id): return
                    # ── Phase 4: Security Check (HIGH severity → retry with feedback) ───
                    high_severity_findings = [
                        f for f in hard_output.findings
                        if f.get("severity") == "high"
                    ]

                    if high_severity_findings:
                        if attempt >= MAX_RETRIES:
                            # Exhausted all retries — hard fail
                            await self._fail(build_id,
                                f"Build blocked by {len(high_severity_findings)} HIGH severity security findings after {MAX_RETRIES} retries:\n" +
                                "\n".join(f"- {f.get('description', 'Unknown')}" for f in high_severity_findings[:5])
                            )
                            return
                        # Still have retries — feed security issues back to Coder
                        security_details = "\n".join(
                            f"- {f.get('severity','?').upper()} [{f.get('category','?')}] {f.get('description','')} "
                            f"(file: {f.get('file_path','?')}, line: {f.get('line_number','?')}) — fix: {f.get('remediation','')}"
                            for f in high_severity_findings[:10]
                        )
                        fix_feedback = (
                            f"SECURITY FAILURE — {len(high_severity_findings)} HIGH severity issue(s) must be fixed before this build can pass:\n"
                            f"{security_details}\n\n"
                            f"You MUST rewrite all affected files to eliminate these vulnerabilities. "
                            f"Do NOT reproduce the same patterns. Apply the remediation steps exactly."
                        )
                        await self._emit(build_id, "security_retry",
                            f"{len(high_severity_findings)} HIGH severity findings — retrying with security feedback (attempt {attempt + 1}/{MAX_RETRIES})",
                            phase="hardening")
                        self.build_repo.increment_retry(build_id)
                        continue  # retry inner loop with security fix_feedback

                    if await self._check_cancelled(build_id): return
                    # ── Phase 5: Fixer ───────────────────────────────────
                    fix_output = await self._run_fixer(build, round_dir, provider, coder_output, hard_output)
                    # Fixer failures are not fatal - continue with validator

                    if await self._check_cancelled(build_id): return
                    # ── Phase 5: Validator ─────────────────────────────────
                    val_output = await self._run_validator(build, round_dir, provider, coder_output, hard_output, fix_output, arch_output)
                    if not val_output.success:
                        await self._fail(build_id, f"Validator error: {val_output.error}")
                        return

                    if val_output.passed or attempt >= MAX_RETRIES:
                        break

                    fix_feedback = val_output.fix_feedback
                    await self._emit(build_id, "validation_failed", f"Validation failed — queuing retry: {val_output.fix_feedback[:200]}", phase="validating")

                if await self._check_cancelled(build_id): return
                # ── Phase 5: Builder (run & test) ───────────────────────────
                build_output = await self._run_builder(build, round_dir)
                if not build_output.success or build_output.project_type == "unknown":
                    await self._emit(build_id, "build_feedback",
                        f"Builder error: {build_output.error}", phase="building")
                    fix_feedback = (
                        f"BUILD FAILED — the project could not be built or run.\n"
                        f"Builder detected type: {build_output.project_type}\n"
                        f"Error: {build_output.error}\n"
                        f"Log:\n{build_output.build_log[:1000]}\n\n"
                        f"INSTRUCTIONS: You MUST produce a complete, runnable project. "
                        f"Include ALL necessary files (e.g. package.json + src/ for Node, "
                        f"requirements.txt + app.py for Python, or index.html + css + js for static). "
                        f"Do NOT use placeholders. Generate working code for every file."
                    )
                    continue  # Go to next build round

                if await self._check_cancelled(build_id): return
                # ── Phase 6: Smoke Tester (deep inspection) ────────────────
                smoke_output = await self._run_smoke_tester(build, round_dir, build_output, arch_output)
                if smoke_output.success:
                    # Final consolidation to ensure clean state before completion
                    logger.info("Pipeline: Running final FileConsolidation")
                    from backend.agents.file_consolidator import FileConsolidatorAgent, FileConsolidatorInput
                    final_consolidator = FileConsolidatorAgent(round_dir)
                    final_consolidate_input = FileConsolidatorInput(build_id=build.id, build_dir=str(round_dir))
                    final_consolidate_output = await final_consolidator.run(final_consolidate_input)
                    if final_consolidate_output.success and final_consolidate_output.removed_files:
                        await self._emit(build_id, "files_consolidated", 
                            f"Final cleanup: removed {len(final_consolidate_output.removed_files)} files", 
                            phase="testing")
                        logger.info("Pipeline: Final FileConsolidator removed %d files", len(final_consolidate_output.removed_files))
                    break  # All tests passed — we have a real, runnable project

                # Smoke tests failed — feed detailed QA feedback back to coder
                await self._emit(build_id, "smoke_feedback",
                    f"QA found {smoke_output.tests_failed} issues", phase="testing")
                # Build a detailed file list for the coder
                src_dir = build_dir / "src"
                found_files = [str(p.relative_to(src_dir)) for p in src_dir.rglob("*") if p.is_file()] if src_dir.exists() else []
                file_list = "\n".join(f"  - {f}" for f in found_files[:30]) if found_files else "  (no files found)"
                fix_feedback = (
                    f"QA/SMOKE TEST FAILED — the project built but does not meet quality standards.\n"
                    f"Builder type: {build_output.project_type}\n"
                    f"Commands run: {', '.join(build_output.commands_run) or 'none'}\n"
                    f"Build log:\n{build_output.build_log[:500]}\n\n"
                    f"Test results: {smoke_output.tests_passed} passed, {smoke_output.tests_failed} failed\n"
                    f"Files generated:\n{file_list}\n\n"
                    f"Issues found (FIX THESE EXACT ISSUES):\n{smoke_output.fix_feedback}\n\n"
                    f"INSTRUCTIONS: Rewrite EVERY failing file completely with real code. "
                    f"Do NOT preserve broken files as-is. Every JS file MUST contain at least one function, "
                    f"arrow function, class, or DOM event. Every HTML file MUST have <!DOCTYPE html> + <html> + <body>. "
                    f"Every CSS file MUST have {{...}} rules. package.json MUST have dependencies AND scripts. "
                    f"Do NOT write empty files, TODOs, or placeholder comments. ONLY working code."
                )

            # If we exhausted all rounds without passing smoke tests, fail
            if smoke_output is None or not smoke_output.success:
                reason = "Build could not produce a runnable project after all rounds"
                if smoke_output:
                    reason = f"Build produced output but failed QA: {smoke_output.fix_feedback[:300]}"
                await self._fail(build_id, reason)
                return

            # ── Copy outputs to final output_dir if configured ─────────────
            final_output_path = str(build_dir)
            files_written = len(coder_output.generated_files) if coder_output else 0
            if dir_cfg and dir_cfg.output_dir:
                import shutil
                out_dest = Path(dir_cfg.output_dir) / build_id
                try:
                    if out_dest.exists():
                        shutil.rmtree(out_dest)
                    shutil.copytree(build_dir, out_dest)
                    final_output_path = str(out_dest)
                    await self._emit(build_id, "output_written",
                                     f"Files written to output directory: {final_output_path}")
                except Exception as copy_err:
                    logger.error("Failed to copy to output_dir: %s", copy_err)
            self.dir_repo.update_output(build_id, final_output_path, files_written)

            # ── Auto-deploy: DISABLED to prevent OneDrive file creation ───────────
            # Agents were auto-deploying to OneDrive folder, causing unwanted files
            # To enable manual deployment, uncomment the code below
            # deploy_dir = Path(r"C:\Users\gaylo\OneDrive\Desktop\TESSR-LOGIC-Deploy")
            # src_dir = build_dir / "src"
            # if src_dir.exists():
            #     try:
            #         import shutil
            #         # Clean old files in deploy (keep folder)
            #         for old in deploy_dir.glob("*"):
            #             if old.is_file():
            #                 old.unlink()
            #             elif old.is_dir():
            #                 shutil.rmtree(old)
            #         # Copy new src contents flat into deploy
            #         for item in src_dir.iterdir():
            #             dest = deploy_dir / item.name
            #             if item.is_dir():
            #                 shutil.copytree(item, dest)
            #             else:
            #                 shutil.copy2(item, dest)
            #         await self._emit(build_id, "deployed",
            #                          f"Auto-deployed {len(list(src_dir.iterdir()))} items to {deploy_dir}")
            #     except Exception as deploy_err:
            #         logger.error("Auto-deploy failed: %s", deploy_err)

            # Publish final artifacts from winning round to canonical output directory
            await self._emit(build_id, "publishing_artifacts", "Publishing final artifacts...", phase="testing")
            final_src_dir = build_dir / "src"
            winning_src_dir = round_dir / "src"
            
            # If this was the first round (round_dir == build_dir), files are already in final location
            if round_dir == build_dir:
                if winning_src_dir.exists():
                    file_count = len(list(winning_src_dir.rglob("*")))
                    logger.info("Pipeline: First round completed - %d files already in final location", file_count)
                    await self._emit(build_id, "artifacts_published", f"First round: {file_count} files ready", phase="testing")
            else:
                # Clean final output directory first
                if final_src_dir.exists():
                    import shutil
                    shutil.rmtree(final_src_dir)
                
                # Copy only winning round files to final output
                if winning_src_dir.exists():
                    import shutil
                    shutil.copytree(winning_src_dir, final_src_dir)
                    file_count = len(list(winning_src_dir.rglob("*")))
                    logger.info("Pipeline: Published %d files from round %d to final output", file_count, build_round)
                    await self._emit(build_id, "artifacts_published", f"Published {file_count} final files", phase="testing")

            # Pipeline complete — all phases passed including smoke tests
            await self._emit(build_id, "pipeline_complete",
                f"Build pipeline completed successfully — smoke tests: {smoke_output.tests_passed}/{smoke_output.tests_passed + smoke_output.tests_failed} passed",
                status="completed")
            self.build_repo.update_status(build_id, BuildStatus.completed)

        except Exception as e:
            logger.exception("Pipeline error for build %s", build_id)
            await self._fail(build_id, f"Unexpected pipeline error: {str(e)}")

    async def _run_architect(self, build, build_dir: Path, provider,
                              project_context_summary: str = "", source_dir: str = ""):
        await self._emit(build.id, "phase_start", "Architecting...", phase="architecting")
        self.build_repo.update_status(build.id, BuildStatus.running, BuildPhase.architecting)

        agent = ArchitectAgent(provider, build_dir)
        output = await agent.run(ArchitectInput(
            build_id=build.id,
            mode=build.mode,
            project_name=build.project_name,
            requirement=build.requirement,
            stack_target=build.stack_target,
            project_context_summary=project_context_summary,
            source_dir=source_dir,
        ))

        if output.success:
            self._record_file(build.id, output.structured_spec_path, "structured_spec.md", "architecting")
            self._record_file(build.id, output.file_plan_path, "file_plan.json", "architecting")
            await self._emit(build.id, "phase_complete", f"Architect complete: {len(output.file_plan)} files planned", phase="architecting")
        else:
            await self._emit(build.id, "phase_error", f"Architect error: {output.error}", phase="architecting")

        return output

    async def _run_coder(self, build, build_dir: Path, provider, arch_output, fix_feedback: str, findings: list[dict] = None):
        await self._emit(build.id, "phase_start", "Coding...", phase="coding")
        self.build_repo.update_status(build.id, BuildStatus.running, BuildPhase.coding)

        agent = CoderAgent(provider, build_dir)
        output = await agent.run(CoderInput(
            build_id=build.id,
            mode=build.mode,
            project_name=build.project_name,
            requirement=build.requirement,
            stack_target=build.stack_target,
            spec_summary=arch_output.spec_summary,
            file_plan=arch_output.file_plan,
            archetype=arch_output.archetype.value if arch_output.archetype else "single_page_app",
            fix_feedback=fix_feedback,
            findings=findings or [],
        ))

        if output.success:
            for f in output.generated_files:
                self._record_file(build.id, f["path"], f.get("relative_path", ""), "coding",
                                  size_bytes=f.get("size", 0), content_preview=f.get("content_preview", ""))
            await self._emit(build.id, "phase_complete", f"Coder complete: {len(output.generated_files)} files generated", phase="coding")
        else:
            await self._emit(build.id, "phase_error", f"Coder error: {output.error}", phase="coding")

        return output

    async def _run_ui_designer(self, build, build_dir: Path, provider, arch_output, coder_output, fix_feedback=""):
        """Run UI Designer after Coder to generate proper CSS files."""
        await self._emit(build.id, "phase_start", "Designing UI...", phase="designing")
        self.build_repo.update_status(build.id, BuildStatus.running, BuildPhase.designing)

        # Extract CSS files from file plan and HTML files from coder output
        css_files = [f for f in (arch_output.file_plan or []) if f.get("path", "").endswith(".css")]
        html_files = [f for f in (coder_output.generated_files or []) if f.get("relative_path", "").endswith(".html")]
        css_plan_paths = [f.get("path", "") for f in css_files]
        
        # Ensure html_files has proper structure for UI Designer
        if not html_files:
            # Fallback: check if there are any HTML files in the build directory
            src_dir = build_dir / "src"
            if src_dir.exists():
                html_files = []
                for html_file in src_dir.rglob("*.html"):
                    html_files.append({
                        "path": str(html_file.relative_to(build_dir)),
                        "relative_path": str(html_file.relative_to(src_dir))
                    })

        if not css_plan_paths:
            await self._emit(build.id, "phase_complete", "No CSS files planned — skipping UI Designer", phase="designing")
            return None

        agent = UIDesignerAgent(provider, build_dir)
        output = await agent.run(UIDesignerInput(
            build_id=build.id,
            project_name=build.project_name,
            requirement=build.requirement,
            spec_summary=arch_output.spec_summary,
            html_files=html_files,
            css_plan_files=css_plan_paths,
            fix_feedback=fix_feedback,
        ))

        if output.success:
            for f in output.generated_files:
                self._record_file(build.id, f["path"], f.get("relative_path", ""), "designing",
                                  size_bytes=f.get("size", 0), content_preview=f.get("content_preview", ""))
            await self._emit(build.id, "phase_complete", f"UI Designer complete: {len(output.generated_files)} CSS files", phase="designing")
        else:
            await self._emit(build.id, "phase_error", f"UI Designer error: {output.error}", phase="designing")

        return output

    async def _run_hardener(self, build, build_dir: Path, provider, coder_output):
        await self._emit(build.id, "phase_start", "Hardening...", phase="hardening")
        self.build_repo.update_status(build.id, BuildStatus.running, BuildPhase.hardening)

        agent = HardenerAgent(provider, build_dir)
        output = await agent.run(HardenerInput(
            build_id=build.id,
            mode=build.mode,
            generated_files=coder_output.generated_files,
            build_dir=str(build_dir),
        ))

        if output.success:
            for f in output.findings:
                self.finding_repo.create(
                    build_id=build.id,
                    severity=f.get("severity", "medium"),
                    category=f.get("category", "unknown"),
                    description=f.get("description", ""),
                    file_path=f.get("file_path"),
                    line_number=f.get("line_number"),
                    remediation=f.get("remediation"),
                )
            self._record_file(build.id, output.findings_path, "findings.json", "hardening")
            self._record_file(build.id, output.remediation_path, "remediation_notes.md", "hardening")
            await self._emit(build.id, "phase_complete", f"Hardener complete: {len(output.findings)} findings", phase="hardening")
        else:
            await self._emit(build.id, "phase_error", f"Hardener error: {output.error}", phase="hardening")

        return output

    async def _run_fixer(self, build, build_dir: Path, provider, coder_output, hard_output):
        """Run Fixer agent to apply security and quality fixes."""
        await self._emit(build.id, "phase_start", "Applying fixes...", phase="fixing")
        self.build_repo.update_status(build.id, BuildStatus.running, BuildPhase.fixing)

        agent = FixerAgent(provider, build_dir)
        output = await agent.run(FixerInput(
            build_id=build.id,
            mode=build.mode,
            project_name=build.project_name,
            generated_files=coder_output.generated_files,
            findings=hard_output.findings,
            build_dir=str(build_dir),
        ))

        if output.success:
            for f in output.fixed_files:
                self._record_file(build.id, f["path"], f.get("relative_path", ""), "fixing",
                                  size_bytes=f.get("size", 0), content_preview=f.get("content_preview", ""))
            await self._emit(build.id, "phase_complete", f"Fixer complete: {len(output.applied_fixes)} fixes applied", phase="fixing")
        else:
            await self._emit(build.id, "phase_error", f"Fixer error: {output.error}", phase="fixing")

        return output

    async def _run_validator(self, build, build_dir: Path, provider, coder_output, hard_output, fix_output=None, arch_output=None):
        await self._emit(build.id, "phase_start", "Validating...", phase="validating")
        self.build_repo.update_status(build.id, BuildStatus.running, BuildPhase.validating)

        # Merge: start with all coder files, overlay any fixed files by path
        if fix_output and fix_output.success and fix_output.fixed_files:
            fixed_by_path = {
                Path(f.get("path", "")).name: f
                for f in fix_output.fixed_files
            }
            merged_files = []
            for f in coder_output.generated_files:
                name = Path(f.get("path", "")).name
                merged_files.append(fixed_by_path.pop(name, f))
            merged_files.extend(fixed_by_path.values())
            generated_files = merged_files
        else:
            generated_files = coder_output.generated_files

        agent = ValidatorAgent(provider, build_dir)
        output = await agent.run(ValidatorInput(
            build_id=build.id,
            mode=build.mode,
            project_name=build.project_name,
            requirement=build.requirement,
            generated_files=generated_files,
            findings=hard_output.findings,
            build_dir=str(build_dir),
            file_plan=arch_output.file_plan if arch_output else [],
        ))

        status_msg = "PASSED" if output.passed else "FAILED"
        await self._emit(build.id, "phase_complete", f"Validator: {status_msg} (confidence {output.confidence}%)", phase="validating",
                         payload=json.dumps({"passed": output.passed, "issues": output.issues}))
        return output

    async def _run_builder(self, build, build_dir: Path):
        await self._emit(build.id, "phase_start", "Building & running...", phase="building")
        self.build_repo.update_status(build.id, BuildStatus.running, BuildPhase.building)

        agent = BuilderAgent(build_dir)
        output = await agent.run(BuilderInput(
            build_id=build.id,
            build_dir=str(build_dir),
            project_name=build.project_name,
            stack_target=build.stack_target,
        ))

        if output.success:
            cmds = ", ".join(output.commands_run) if output.commands_run else "static check"
            await self._emit(build.id, "phase_complete",
                f"Build phase: {output.project_type} — {cmds} — artifacts: {len(output.artifacts)}",
                phase="building",
                payload=json.dumps({
                    "project_type": output.project_type,
                    "commands_run": output.commands_run,
                    "artifacts": output.artifacts,
                    "log_preview": output.build_log[:300],
                }))
        else:
            await self._emit(build.id, "phase_error",
                f"Build phase failed: {output.error}",
                phase="building",
                payload=json.dumps({"log": output.build_log[:500]}))

        return output

    async def _run_project_manager(self, build, build_dir: Path, provider, arch_output):
        """Run Project Manager to resolve architectural conflicts."""
        from backend.agents.project_manager import ProjectManagerAgent, ProjectManagerInput
        from backend.core.archetype import ArchetypeClassifier

        # Use Architect's classification directly — never re-classify
        archetype_classifier = ArchetypeClassifier()
        archetype = arch_output.archetype
        contract = archetype_classifier.get_contract(archetype)

        # Check for potential conflicts
        conflicts = []

        # Check file count conflicts
        html_files = [f for f in arch_output.file_plan if f.get('path', '').endswith('.html')]
        if contract.max_html_files and len(html_files) > contract.max_html_files:
            conflicts.append(f"file_count: {len(html_files)} HTML files > max {contract.max_html_files} for {archetype.value}")

        # Check stack conflicts
        if build.stack_target.lower() in ['html5', 'vanilla'] and arch_output.spec_summary:
            if any(framework in arch_output.spec_summary.lower() for framework in ['react', 'jsx', 'vue', 'angular']):
                conflicts.append(f"stack_violation: {build.stack_target} specified but frameworks detected")
        
        if not conflicts:
            # No conflicts detected
            from backend.agents.project_manager import ProjectManagerOutput
            return ProjectManagerOutput(success=True, corrected_file_plan=[])
        
        # Run Project Manager to resolve conflicts
        agent = ProjectManagerAgent(provider, build_dir)
        input_data = ProjectManagerInput(
            build_id=build.id,
            project_name=build.project_name,
            requirement=build.requirement,
            stack_target=build.stack_target,
            archetype=archetype,
            file_plan=arch_output.file_plan,
            conflict_type=conflicts[0].split(':')[0],
            conflict_details=conflicts[0]
        )
        
        output = await agent.run(input_data)
        return output

    async def _run_smoke_tester(self, build, build_dir: Path, builder_output, arch_output):
        await self._emit(build.id, "phase_start", "Smoke testing...", phase="testing")
        self.build_repo.update_status(build.id, BuildStatus.running, BuildPhase.testing)

        agent = SmokeTesterAgent(build_dir)
        output = await agent.run(SmokeTesterInput(
            build_id=build.id,
            build_dir=str(build_dir),
            project_name=build.project_name,
            stack_target=build.stack_target,
            project_type=builder_output.project_type,
            requirement=build.requirement,
            archetype=arch_output.archetype,  # Pass archetype from Architect, not re-classified
        ))

        status = f"passed {output.tests_passed}/{output.tests_passed + output.tests_failed}"
        await self._emit(build.id, "phase_complete" if output.success else "phase_error",
            f"Smoke test {status}: {output.fix_feedback[:200]}",
            phase="testing",
            payload=json.dumps({
                "passed": output.tests_passed,
                "failed": output.tests_failed,
                "results": output.results,
                "fix_feedback": output.fix_feedback,
            }))
        return output

    def _record_file(self, build_id: str, path: str, name: str, phase: str,
                     size_bytes: int = 0, content_preview: str = ""):
        if not path:
            return
        p = Path(path)
        if p.exists() and size_bytes == 0:
            size_bytes = p.stat().st_size
        self.file_repo.create(
            build_id=build_id,
            file_path=path,
            file_name=name or p.name,
            phase=phase,
            size_bytes=size_bytes,
            content_preview=content_preview,
        )

    async def _emit(self, build_id: str, event_type: str, message: str,
                    phase: str | None = None, status: str | None = None, payload: str | None = None):
        self.event_repo.create(build_id=build_id, event_type=event_type, message=message, phase=phase, payload=payload)
        evt = {
            "build_id": build_id,
            "event_type": event_type,
            "message": message,
            "phase": phase,
            "status": status,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await event_bus.publish(build_id, evt)

    async def _fail(self, build_id: str, reason: str):
        logger.error("Build %s failed: %s", build_id, reason)
        cleanup_build_procs(build_id)
        await self._emit(build_id, "pipeline_error", reason, status="failed")
        self.build_repo.update_status(build_id, BuildStatus.failed, error=reason)
