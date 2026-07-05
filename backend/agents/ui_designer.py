import json
import logging
import re
from pathlib import Path

from backend.agents.base import BaseAgent
from backend.providers.base import BaseModelProvider, ModelRequest
from backend.agents.prompt_loader import load_system_prompt

logger = logging.getLogger(__name__)

# Design library lives at repo root: <repo>/design_library/
DESIGN_LIBRARY = Path(__file__).resolve().parents[2] / "design_library"


_UI_DESIGNER_SYSTEM_DEFAULT = """You are a UI designer. You do NOT write stylesheets from scratch.
You SELECT the best pre-built theme for the project and write a SMALL custom override.

You will be given a theme menu. Respond with ONLY a JSON object:
{
  "theme": "<exact theme name from the menu>",
  "custom_css": "<optional short CSS: :root variable overrides and rules for project-specific class names not covered by the theme>"
}

Rules for custom_css:
- Override :root variables (--bg, --accent, --text, etc.) to match colors the user asked for
- Add rules ONLY for project-specific classes/ids you see in the HTML that a generic theme would not cover
- Keep it under 40 rules. The theme already handles nav, buttons, cards, inputs, tabs, tables, layout
- Empty string is fine if the theme fits as-is
Respond with only the JSON object. No explanations."""


def _load_catalog() -> dict:
    try:
        return json.loads((DESIGN_LIBRARY / "themes.json").read_text(encoding="utf-8"))
    except Exception as e:
        logger.error("UI Designer: cannot load theme catalog: %s", e)
        return {"default": "", "themes": []}


def _load_theme_css(catalog: dict, name: str) -> str:
    for t in catalog.get("themes", []):
        if t["name"] == name:
            try:
                return (DESIGN_LIBRARY / t["file"]).read_text(encoding="utf-8")
            except Exception as e:
                logger.error("UI Designer: cannot read theme %s: %s", name, e)
    return ""


def _keyword_match_theme(catalog: dict, text: str) -> str:
    """Pick the theme whose keywords best match the requirement text."""
    text_l = (text or "").lower()
    best, best_score = catalog.get("default", ""), 0
    for t in catalog.get("themes", []):
        score = sum(1 for kw in t.get("keywords", []) if kw in text_l)
        if score > best_score:
            best, best_score = t["name"], score
    return best


class UIDesignerInput:
    def __init__(self, *, build_id: str, project_name: str, requirement: str,
                 spec_summary: str, html_files: list[dict], css_plan_files: list[str],
                 ui_layer: str = "", product_type: str = "", fix_feedback: str = ""):
        self.build_id = build_id
        self.project_name = project_name
        self.requirement = requirement
        self.spec_summary = spec_summary
        self.html_files = html_files
        self.css_plan_files = css_plan_files
        self.ui_layer = ui_layer
        self.product_type = product_type
        self.fix_feedback = fix_feedback


class UIDesignerOutput:
    def __init__(self, *, success: bool, generated_files: list[dict] = None, error: str = ""):
        self.success = success
        self.generated_files = generated_files or []
        self.error = error


class UIDesignerAgent(BaseAgent[UIDesignerInput, UIDesignerOutput]):
    """Theme-library UI designer.

    Instead of asking the model to invent a full stylesheet (which small local
    models do badly), the model only:
      1. picks the best theme from design_library/themes.json
      2. writes a small custom override (root variables + project-specific classes)
    The final styles.css = theme CSS + custom overrides.
    If the model fails entirely, a theme is chosen by keyword match so no build
    ever ships unstyled.
    """

    def __init__(self, provider: BaseModelProvider, build_dir: Path):
        self.provider = provider
        self.build_dir = build_dir

    async def run(self, input_data: UIDesignerInput) -> UIDesignerOutput:
        # Skip CSS generation for non-web projects
        if input_data.ui_layer not in ("html_css", "react", ""):
            logger.info("UI Designer: skipping — ui_layer is %s", input_data.ui_layer)
            return UIDesignerOutput(success=True, generated_files=[])

        catalog = _load_catalog()
        if not catalog.get("themes"):
            return UIDesignerOutput(success=False, error="Design library missing or empty (design_library/themes.json)")

        src = self.build_dir / "src"
        src.mkdir(parents=True, exist_ok=True)

        # Collect the class/id inventory from generated HTML so the model
        # knows which project-specific selectors need custom rules.
        html_previews = []
        selectors: set[str] = set()
        for hf in input_data.html_files:
            rel = hf.get("path", hf.get("relative_path", "")).replace("src/", "")
            p = src / rel
            text = ""
            if p.exists():
                text = p.read_text(errors="replace")
            else:
                text = hf.get("content_preview", "") or hf.get("preview", "")
            if text:
                html_previews.append({"path": rel, "preview": text[:1200]})
                for m in re.findall(r'class="([^"]+)"', text):
                    selectors.update("." + c for c in m.split())
                for m in re.findall(r'id="([^"]+)"', text):
                    selectors.add("#" + m)

        theme_menu = "\n".join(
            f'- "{t["name"]}": {t["description"]}' for t in catalog["themes"]
        )
        feedback = f"\nFIX FEEDBACK:\n{input_data.fix_feedback}\n" if input_data.fix_feedback else ""

        prompt = (
            f"Project: {input_data.project_name}\n"
            f"Requirement: {input_data.requirement}\n"
            f"Spec Summary: {input_data.spec_summary[:800]}\n\n"
            f"THEME MENU:\n{theme_menu}\n\n"
            f"Selectors used in the HTML:\n{json.dumps(sorted(selectors)[:80])}\n\n"
            f"HTML previews:\n{json.dumps(html_previews, indent=1)[:3000]}\n"
            f"{feedback}\n"
            'Pick the best theme and write custom_css. Respond with only the JSON object: {"theme": "...", "custom_css": "..."}'
        )

        theme_name = ""
        custom_css = ""
        response = await self.provider.complete(
            ModelRequest(
                prompt=prompt,
                system_prompt=load_system_prompt("ui_designer", _UI_DESIGNER_SYSTEM_DEFAULT),
                temperature=0.2,
                max_tokens=2048,
                response_format="json",
            )
        )
        if response.success:
            try:
                content = response.content.strip()
                if content.startswith("```"):
                    lines = content.split("\n")
                    content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
                data = json.loads(content)
                theme_name = str(data.get("theme", "")).strip()
                custom_css = str(data.get("custom_css", "") or "")
            except Exception as e:
                logger.warning("UI Designer: JSON parse failed (%s) — falling back to keyword match", e)
        else:
            logger.warning("UI Designer: model call failed (%s) — falling back to keyword match", response.error)

        # Validate theme choice; fall back to keyword match, then default
        valid_names = {t["name"] for t in catalog["themes"]}
        if theme_name not in valid_names:
            theme_name = _keyword_match_theme(catalog, f"{input_data.requirement} {input_data.spec_summary}")
        if theme_name not in valid_names:
            theme_name = catalog.get("default") or catalog["themes"][0]["name"]

        theme_css = _load_theme_css(catalog, theme_name)
        if not theme_css:
            return UIDesignerOutput(success=False, error=f"Theme file for '{theme_name}' could not be read")

        # Basic sanity on custom css — drop it if it is clearly not CSS
        if custom_css and ("{" not in custom_css or len(custom_css) > 20000):
            logger.warning("UI Designer: discarding malformed custom_css (%d chars)", len(custom_css))
            custom_css = ""

        final_css = theme_css
        if custom_css:
            final_css += "\n\n/* === Project custom overrides === */\n" + custom_css.strip() + "\n"

        logger.info("UI Designer: theme=%s custom_css=%d chars", theme_name, len(custom_css))

        # Decide output location (mirror HTML location if under public/)
        out_name = "styles.css"
        if input_data.css_plan_files:
            candidate = self._sanitize_path(input_data.css_plan_files[0])
            if candidate:
                out_name = Path(candidate).name
        if any("public/" in (f.get("relative_path", "") or "") for f in input_data.html_files):
            target = self.build_dir / "src" / "public" / out_name
            relative_path = f"src/public/{out_name}"
        else:
            target = self.build_dir / "src" / out_name
            relative_path = f"src/{out_name}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(final_css, encoding="utf-8")

        generated = [{
            "path": str(target),
            "relative_path": relative_path,
            "size": len(final_css),
            "content_preview": f"/* theme: {theme_name} */\n" + final_css[:400],
        }]
        return UIDesignerOutput(success=True, generated_files=generated)

    def _sanitize_path(self, raw: str) -> str:
        if len(raw) >= 2 and raw[1] == ":":
            raw = raw[2:]
        raw = raw.lstrip("/\\")
        if raw.lower().startswith("src/") or raw.lower().startswith("src\\"):
            raw = raw[4:]
            raw = raw.lstrip("/\\")
        parts = raw.replace("\\", "/").split("/")
        safe = [p for p in parts if p and p != "." and p != ".."]
        if not safe:
            return ""
        joined = "/".join(safe)
        test = (self.build_dir / "src" / joined).resolve()
        src_root = (self.build_dir / "src").resolve()
        try:
            test.relative_to(src_root)
        except ValueError:
            logger.warning("Rejected path-traversal attempt: %s", raw)
            return ""
        return joined
