import logging
from pathlib import Path
from pydantic import BaseModel
from backend.agents.base import BaseAgent
from backend.providers.base import BaseModelProvider, ModelRequest

logger = logging.getLogger(__name__)

class FileConsolidatorInput(BaseModel):
    build_id: str
    build_dir: str

class FileConsolidatorOutput(BaseModel):
    success: bool
    error: str = ""
    consolidated_files: list[dict] = []
    removed_files: list[str] = []

class FileConsolidatorAgent(BaseAgent[FileConsolidatorInput, FileConsolidatorOutput]):
    """
    Enforces single CSS and JS file structure.
    - Merges multiple CSS files into single styles.css
    - Merges multiple JS files into single app.js (except data.json)
    - Adds missing event listeners to data-only JS files
    - Updates HTML files to reference consolidated files
    """
    def __init__(self, build_dir: Path):
        self.build_dir = build_dir

    async def run(self, inp: FileConsolidatorInput) -> FileConsolidatorOutput:
        src = self.build_dir / "src"
        if not src.exists():
            logger.warning("FileConsolidator: No src/ directory found at %s", src)
            return FileConsolidatorOutput(success=True, error="No src/ directory")
        
        logger.info("FileConsolidator: Starting consolidation for build %s", inp.build_id)
        consolidated_files = []
        removed_files = []
        
        try:
            # Consolidate CSS files
            css_result = self._consolidate_css(src)
            consolidated_files.extend(css_result["consolidated"])
            removed_files.extend(css_result["removed"])
            
            # Consolidate JS files
            js_result = self._consolidate_js(src)
            consolidated_files.extend(js_result["consolidated"])
            removed_files.extend(js_result["removed"])
            
            # Update HTML references
            self._update_html_references(src)
            
            logger.info("FileConsolidator: merged %d CSS files, %d JS files, removed %d files", 
                       len(css_result["removed"]), len(js_result["removed"]), len(removed_files))
            
            return FileConsolidatorOutput(
                success=True,
                consolidated_files=consolidated_files,
                removed_files=removed_files
            )
            
        except Exception as e:
            logger.error("FileConsolidator failed: %s", e)
            return FileConsolidatorOutput(success=False, error=str(e))

    def _consolidate_css(self, src: Path) -> dict:
        """Merge all CSS files into single styles.css"""
        css_files = list(src.rglob("*.css"))
        styles_css = src / "styles.css"
        
        # Also find any files with CSS-like names that might be missed
        all_files = list(src.rglob("*"))
        css_like_files = [f for f in all_files if f.is_file() and (
            f.name.lower().endswith('.css') or 
            'css' in f.name.lower() or
            f.suffix == '' and 'css' in f.name.lower()
        )]
        
        logger.info("FileConsolidator: Found CSS files: %s", [f.name for f in css_files])
        logger.info("FileConsolidator: Found CSS-like files: %s", [f.name for f in css_like_files])
        
        # Use the more comprehensive list
        css_files = css_like_files
        
        if len(css_files) <= 1:
            logger.info("FileConsolidator: Only %d CSS file(s), no consolidation needed", len(css_files))
            return {"consolidated": [], "removed": []}
        
        logger.info("FileConsolidator: Found %d CSS files, consolidating to styles.css", len(css_files))
        
        # Collect all CSS content
        merged_content = []
        for css_file in css_files:
            if css_file.name == "styles.css":
                # Main file goes first
                merged_content.insert(0, f"/* ===== {css_file.name} ===== */\n")
                merged_content.append(css_file.read_text(encoding="utf-8"))
            else:
                # Append other CSS files
                merged_content.append(f"\n/* ===== {css_file.name} ===== */\n")
                merged_content.append(css_file.read_text(encoding="utf-8"))
        
        # Write consolidated styles.css
        final_content = "\n".join(merged_content)
        styles_css.write_text(final_content, encoding="utf-8")
        
        # Remove extra CSS files (aggressive removal)
        removed = []
        for css_file in css_files:
            if css_file != styles_css:  # Remove all except the main styles.css
                logger.info("FileConsolidator: Attempting to remove %s", css_file.name)
                try:
                    # Try multiple deletion methods
                    if css_file.exists():
                        css_file.unlink(missing_ok=False)
                        logger.info("FileConsolidator: Unlinked %s", css_file.name)
                    # Double-check it's gone
                    if css_file.exists():
                        import os
                        os.remove(css_file)
                        logger.info("FileConsolidator: os.remove() %s", css_file.name)
                    # Final check
                    if not css_file.exists():
                        removed.append(css_file.name)
                        logger.info("FileConsolidator: Successfully removed duplicate CSS: %s", css_file.name)
                    else:
                        logger.error("FileConsolidator: Failed to remove %s - file still exists", css_file.name)
                except Exception as e:
                    logger.error("FileConsolidator: Failed to remove %s: %s", css_file.name, e)
        
        logger.info("FileConsolidator: CSS consolidation complete, removed %d files", len(removed))
        return {
            "consolidated": [{"path": str(styles_css), "name": "styles.css", "size": len(final_content)}],
            "removed": removed
        }

    def _consolidate_js(self, src: Path) -> dict:
        """Merge JS files, keeping data.json separate"""
        js_files = list(src.rglob("*.js"))
        app_js = src / "app.js"
        data_files = []
        logic_files = []
        
        if len(js_files) <= 1:
            logger.info("FileConsolidator: Only %d JS file(s), no consolidation needed", len(js_files))
            return {"consolidated": [], "removed": []}
        
        logger.info("FileConsolidator: Found %d JS files, consolidating to app.js", len(js_files))
        
        # Separate data files from logic files
        for js_file in js_files:
            name_lower = js_file.name.lower()
            if ("data" in name_lower or "model" in name_lower or "config" in name_lower or 
                "sounds" in name_lower or "audio" in name_lower or "assets" in name_lower):
                data_files.append(js_file)
            elif js_file.name != "app.js":
                logic_files.append(js_file)
        
        # Build consolidated app.js
        merged_content = []
        
        # Start with existing app.js if it exists
        if app_js.exists():
            merged_content.append(f"/* ===== app.js ===== */\n")
            merged_content.append(app_js.read_text(encoding="utf-8"))
        
        # Merge other logic files
        for js_file in logic_files:
            merged_content.append(f"\n/* ===== {js_file.name} ===== */\n")
            content = js_file.read_text(encoding="utf-8")
            
            # Add event listeners if missing
            if not self._has_event_listeners(content):
                content = self._add_event_listeners(content, js_file.name)
            
            merged_content.append(content)
        
        # Write consolidated app.js
        if merged_content:
            final_content = "\n".join(merged_content)
            app_js.write_text(final_content, encoding="utf-8")
        
        # Remove extra JS files (keep data files, aggressive removal)
        removed = []
        for js_file in logic_files:
            try:
                js_file.unlink()
                removed.append(js_file.name)
                logger.info("FileConsolidator: Removed duplicate JS: %s", js_file.name)
            except Exception as e:
                logger.warning("FileConsolidator: Failed to remove %s: %s", js_file.name, e)
        
        logger.info("FileConsolidator: JS consolidation complete, removed %d files", len(removed))
        return {
            "consolidated": [{"path": str(app_js), "name": "app.js", "size": len(final_content) if merged_content else 0}],
            "removed": removed
        }

    def _update_html_references(self, src: Path) -> None:
        """Update all HTML files to reference consolidated files"""
        html_files = list(src.rglob("*.html"))
        
        for html_file in html_files:
            content = html_file.read_text(encoding="utf-8")
            
            # Replace CSS references with single styles.css
            import re
            css_pattern = r'<link[^>]*rel=["\']stylesheet["\'][^>]*href=["\'][^"\']*\.css["\'][^>]*>'
            css_replacement = '<link rel="stylesheet" href="styles.css">'
            content, n_links = re.subn(css_pattern, css_replacement, content)

            # Inject a stylesheet link if the HTML has NONE (small models often omit it)
            if n_links == 0:
                if '</head>' in content:
                    content = content.replace('</head>', '    <link rel="stylesheet" href="styles.css">\n</head>', 1)
                elif '<body' in content:
                    content = re.sub(r'(<body[^>]*>)', r'\1\n    <link rel="stylesheet" href="styles.css">', content, count=1)
                else:
                    content = '<link rel="stylesheet" href="styles.css">\n' + content

            # Wrap bare body content in a layout container if none exists.
            # Small models often emit elements directly in <body>, which the
            # themes cannot center or space without a .container/main wrapper.
            body_m = re.search(r'<body[^>]*>(.*?)</body>', content, re.DOTALL | re.IGNORECASE)
            if body_m:
                inner = body_m.group(1)
                has_wrapper = re.search(
                    r'<(main|div)[^>]*class=["\'][^"\']*(container|wrapper|app|page)[^"\']*["\']',
                    inner, re.IGNORECASE
                ) or re.search(r'<main[\s>]', inner, re.IGNORECASE)
                if not has_wrapper and inner.strip():
                    nav_m = re.match(r'(\s*<nav.*?</nav>)', inner, re.DOTALL | re.IGNORECASE)
                    head_part = nav_m.group(1) if nav_m else ""
                    rest = inner[len(head_part):]
                    scripts = re.findall(r'<script.*?</script>', rest, re.DOTALL | re.IGNORECASE)
                    for sc in scripts:
                        rest = rest.replace(sc, "")
                    wrapped = (head_part + '\n<main class="container">' + rest.rstrip() +
                               '\n</main>\n' + "\n".join(scripts) + "\n")
                    content = content[:body_m.start(1)] + wrapped + content[body_m.end(1):]

            # Neutralize <img> tags pointing at local files that were never generated
            # (LLMs cannot create binary images). Replace with an emoji placeholder.
            def _fix_img(m):
                src_attr = m.group(1)
                if src_attr.startswith(("http://", "https://", "data:")):
                    return m.group(0)
                candidate = html_file.parent / src_attr
                if candidate.exists():
                    return m.group(0)
                alt_m = re.search(r'alt=["\']([^"\']*)["\']', m.group(0))
                label = alt_m.group(1) if alt_m else ""
                return f'<span class="img-placeholder" role="img" aria-label="{label}" style="font-size:4rem;line-height:1">&#128049;</span>'
            content = re.sub(r'<img[^>]*src=["\']([^"\']+)["\'][^>]*/?>', _fix_img, content)
            
            # Replace JS references with single app.js (except data.json)
            js_pattern = r'<script[^>]*src=["\'][^"\']*\.js["\'][^>]*></script>'
            js_matches = re.findall(js_pattern, content)
            
            # Remove all existing JS script tags
            content = re.sub(js_pattern, '', content)
            
            # Add single app.js reference before closing body tag
            if '</body>' in content:
                app_js_tag = '    <script src="app.js"></script>\n'
                content = content.replace('</body>', app_js_tag + '</body>')
            
            html_file.write_text(content, encoding="utf-8")

    def _has_event_listeners(self, content: str) -> bool:
        """Check if JS content has event listeners"""
        return ("addeventlistener" in content.lower() or 
                "onclick" in content.lower() or 
                "onchange" in content.lower() or
                "onload" in content.lower())

    def _add_event_listeners(self, content: str, filename: str) -> str:
        """Add basic event listeners to JS content"""
        if "document.addeventlistener" in content.lower():
            return content
        
        # Wrap content in DOM ready listener
        wrapped = f"""// Auto-generated event listener wrapper for {filename}
document.addEventListener('DOMContentLoaded', function() {{
    {content}
    
    // Add basic interactivity
    const buttons = document.querySelectorAll('button, .btn');
    buttons.forEach(button => {{
        button.addEventListener('click', function(e) {{
            console.log('Button clicked:', this.textContent);
        }});
    }});
}});
"""
        return wrapped
