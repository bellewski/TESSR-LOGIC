"""Folder scanner service — recursively analyses a source directory and
infers stack, project type, and produces a context summary."""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy.orm import Session

from backend.models.project_context import ProjectContext, FileManifestEntry
from backend.repositories.settings_repo import SettingsRepository

logger = logging.getLogger(__name__)

IGNORE_DIRS = {
    "node_modules", ".git", "venv", ".venv", "env", "dist", "build",
    "__pycache__", "coverage", ".next", ".nuxt", ".svelte-kit",
    ".pytest_cache", ".mypy_cache", "htmlcov", "eggs", ".eggs",
    "target", "out", ".gradle", ".idea", ".vscode",
}

KEY_FILES = {
    "package.json", "pyproject.toml", "requirements.txt", "requirements-dev.txt",
    "docker-compose.yml", "docker-compose.yaml", "Dockerfile",
    "README.md", "README.rst", "tsconfig.json", "vite.config.ts", "vite.config.js",
    ".env.example", ".env.sample", "setup.py", "setup.cfg", "Makefile",
    "cargo.toml", "go.mod", "pom.xml", "build.gradle", "composer.json",
    "gemfile", "gemfile.lock", ".eslintrc.json", ".eslintrc.js",
    "tailwind.config.js", "tailwind.config.ts", "next.config.js", "next.config.ts",
    "nuxt.config.ts", "svelte.config.js", "astro.config.mjs",
    "angular.json", "webpack.config.js",
}

EXTENSION_LANGUAGE_MAP = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript/React", ".jsx": "JavaScript/React",
    ".go": "Go", ".rs": "Rust", ".java": "Java", ".kt": "Kotlin",
    ".rb": "Ruby", ".php": "PHP", ".cs": "C#", ".cpp": "C++",
    ".c": "C", ".html": "HTML", ".css": "CSS", ".scss": "SCSS",
    ".vue": "Vue", ".svelte": "Svelte", ".sh": "Shell",
    ".sql": "SQL", ".yaml": "YAML", ".yml": "YAML", ".json": "JSON",
    ".md": "Markdown", ".toml": "TOML",
}

STACK_INDICATORS = {
    "package.json":       ["Node.js"],
    "requirements.txt":   ["Python"],
    "pyproject.toml":     ["Python"],
    "setup.py":           ["Python"],
    "docker-compose.yml": ["Docker"],
    "docker-compose.yaml":["Docker"],
    "Dockerfile":         ["Docker"],
    "tsconfig.json":      ["TypeScript"],
    "vite.config.ts":     ["Vite", "TypeScript"],
    "vite.config.js":     ["Vite"],
    "tailwind.config.js": ["TailwindCSS"],
    "tailwind.config.ts": ["TailwindCSS"],
    "next.config.js":     ["Next.js"],
    "next.config.ts":     ["Next.js"],
    "nuxt.config.ts":     ["Nuxt.js"],
    "svelte.config.js":   ["SvelteKit"],
    "angular.json":       ["Angular"],
    "go.mod":             ["Go"],
    "cargo.toml":         ["Rust"],
    "pom.xml":            ["Java/Maven"],
    "build.gradle":       ["Java/Gradle"],
    "composer.json":      ["PHP"],
    "gemfile":            ["Ruby"],
}

PROJECT_TYPE_RULES = [
    ({"next.config.js", "next.config.ts"}, "Next.js Web App"),
    ({"nuxt.config.ts"}, "Nuxt.js Web App"),
    ({"svelte.config.js"}, "SvelteKit App"),
    ({"angular.json"}, "Angular App"),
    ({"vite.config.ts", "vite.config.js"}, "Vite Frontend App"),
    ({"package.json"}, "Node.js Project"),
    ({"pyproject.toml", "setup.py", "requirements.txt"}, "Python Project"),
    ({"go.mod"}, "Go Project"),
    ({"cargo.toml"}, "Rust Project"),
    ({"pom.xml", "build.gradle"}, "JVM Project"),
    ({"docker-compose.yml", "docker-compose.yaml"}, "Containerised App"),
]


def scan_folder(source_dir: str) -> dict:
    """Walk the source directory and produce a structured scan result."""
    root = Path(source_dir).resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Source directory does not exist or is not a directory: {source_dir}")

    found_key_files: list[str] = []
    ignored_folders: list[str] = []
    all_files: list[dict] = []
    stack_set: set[str] = set()
    ext_counts: dict[str, int] = {}

    for item in root.rglob("*"):
        # Check if any parent part is in ignore list
        parts = item.relative_to(root).parts
        if any(p in IGNORE_DIRS for p in parts[:-1]):
            if item.is_dir() and item.name in IGNORE_DIRS and str(item.parent.relative_to(root)) not in ignored_folders:
                ignored_folders.append(str(item.relative_to(root)))
            continue
        if item.is_dir():
            if item.name in IGNORE_DIRS:
                ignored_folders.append(str(item.relative_to(root)))
            continue
        if not item.is_file():
            continue

        rel = item.relative_to(root)
        fname = item.name.lower()
        ext = item.suffix.lower()
        size = item.stat().st_size

        ext_counts[ext] = ext_counts.get(ext, 0) + 1

        # Stack indicators (check lowercase filename)
        for key_indicator, stacks in STACK_INDICATORS.items():
            if fname == key_indicator.lower():
                stack_set.update(stacks)

        is_key = fname in {k.lower() for k in KEY_FILES}
        if is_key:
            found_key_files.append(str(rel))

        lang = EXTENSION_LANGUAGE_MAP.get(ext)
        all_files.append({
            "relative_path": str(rel),
            "file_name": item.name,
            "extension": ext,
            "size_bytes": size,
            "is_key_file": is_key,
            "detected_language": lang,
        })

    # Infer project type
    found_lower = {f.lower() for f in found_key_files}
    inferred_type = "Unknown Project"
    for indicators, ptype in PROJECT_TYPE_RULES:
        if any(ind.lower() in found_lower for ind in indicators):
            inferred_type = ptype
            break

    # Build summary
    top_langs = sorted(ext_counts.items(), key=lambda x: -x[1])[:5]
    lang_summary = ", ".join(
        f"{EXTENSION_LANGUAGE_MAP.get(e, e)} ({c})" for e, c in top_langs if e
    )

    context_summary = (
        f"Project type: {inferred_type}. "
        f"Stack: {', '.join(sorted(stack_set)) or 'Unknown'}. "
        f"Key files: {', '.join(found_key_files[:10]) or 'none'}. "
        f"Total files: {len(all_files)}. "
        f"Top languages: {lang_summary or 'unknown'}."
    )

    context_summary_json = {
        "project_type": inferred_type,
        "stack": sorted(stack_set),
        "key_files": found_key_files,
        "total_files": len(all_files),
        "extension_counts": ext_counts,
        "ignored_folders": ignored_folders[:20],
    }

    return {
        "detected_stack": sorted(stack_set),
        "inferred_project_type": inferred_type,
        "total_files": len(all_files),
        "key_files": found_key_files,
        "ignored_folders": ignored_folders[:20],
        "context_summary": context_summary,
        "context_summary_json": context_summary_json,
        "all_files": all_files,
    }


class ProjectContextService:
    def __init__(self, db: Session):
        self.db = db

    def create(self, name: str, source_dir: str | None = None,
               workspace_dir: str | None = None, output_dir: str | None = None) -> ProjectContext:
        ctx = ProjectContext(name=name, source_dir=source_dir,
                             workspace_dir=workspace_dir, output_dir=output_dir)
        self.db.add(ctx)
        self.db.commit()
        self.db.refresh(ctx)
        return ctx

    def get(self, context_id: str) -> ProjectContext | None:
        return self.db.query(ProjectContext).filter(ProjectContext.id == context_id).first()

    def list_all(self) -> list[ProjectContext]:
        return self.db.query(ProjectContext).order_by(ProjectContext.updated_at.desc()).all()

    def update(self, context_id: str, **kwargs) -> ProjectContext | None:
        ctx = self.get(context_id)
        if not ctx:
            return None
        for k, v in kwargs.items():
            if hasattr(ctx, k):
                setattr(ctx, k, v)
        ctx.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(ctx)
        return ctx

    def scan(self, context_id: str, source_dir: str) -> dict:
        """Scan a directory and store results against a ProjectContext."""
        result = scan_folder(source_dir)

        # Delete old manifest entries
        self.db.query(FileManifestEntry).filter(FileManifestEntry.context_id == context_id).delete()

        # Insert new manifest entries (batch, skip overly large sets)
        entries = result["all_files"][:5000]
        for f in entries:
            entry = FileManifestEntry(
                context_id=context_id,
                relative_path=f["relative_path"],
                file_name=f["file_name"],
                extension=f["extension"],
                size_bytes=f["size_bytes"],
                is_key_file=f["is_key_file"],
                detected_language=f["detected_language"],
            )
            self.db.add(entry)

        ctx = self.get(context_id)
        if ctx:
            ctx.source_dir = source_dir
            ctx.detected_stack = json.dumps(result["detected_stack"])
            ctx.detected_files = json.dumps(result["key_files"])
            ctx.inferred_project_type = result["inferred_project_type"]
            ctx.context_summary = result["context_summary"]
            ctx.context_summary_json = json.dumps(result["context_summary_json"])
            ctx.total_files_scanned = result["total_files"]
            ctx.last_scanned_at = datetime.now(timezone.utc)
            ctx.updated_at = datetime.now(timezone.utc)

        self.db.commit()
        if ctx:
            self.db.refresh(ctx)

        return {
            "context_id": context_id,
            "detected_stack": result["detected_stack"],
            "inferred_project_type": result["inferred_project_type"],
            "total_files": result["total_files"],
            "key_files": result["key_files"],
            "ignored_folders": result["ignored_folders"],
            "context_summary": result["context_summary"],
            "context_summary_json": result["context_summary_json"],
        }

    def get_manifest(self, context_id: str) -> list[FileManifestEntry]:
        return (
            self.db.query(FileManifestEntry)
            .filter(FileManifestEntry.context_id == context_id)
            .order_by(FileManifestEntry.is_key_file.desc(), FileManifestEntry.relative_path)
            .all()
        )
