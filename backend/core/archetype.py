"""
Product archetype detection and contract system.
Determines the type of application being built and applies appropriate validation rules.
Stack-agnostic: supports web, Python, Node, CLI, API, fullstack, and more.
"""

from enum import Enum
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import re


class ProductArchetype(Enum):
    """Core product archetypes — web and non-web."""
    # Web archetypes
    LANDING_PAGE = "landing_page"
    SINGLE_PAGE_APP = "single_page_app"
    MULTI_PAGE_SITE = "multi_page_site"
    DASHBOARD = "dashboard"
    GAME = "game"
    DOCS_SITE = "docs_site"
    ADMIN_PANEL = "admin_panel"
    TOOL = "tool"
    TOY_APP = "toy_app"
    # Non-web archetypes
    API_SERVER = "api_server"
    CLI_TOOL = "cli_tool"
    PYTHON_PACKAGE = "python_package"
    NODE_SERVICE = "node_service"
    FULLSTACK_APP = "fullstack_app"
    AUTOMATION_SCRIPT = "automation_script"
    DATABASE_SCHEMA = "database_schema"


class DeliveryArchitecture(Enum):
    """How the product is delivered to users."""
    SINGLE_FILE = "single_file"
    STATIC_MULTI_PAGE = "static_multi_page"
    SPA = "spa"
    MICROSITE = "microsite"
    CANVAS_APP = "canvas_app"
    # Non-web delivery modes
    HTTP_SERVICE = "http_service"
    CLI_BINARY = "cli_binary"
    PYTHON_MODULE = "python_module"
    NODE_MODULE = "node_module"
    SHELL_SCRIPT = "shell_script"
    FULLSTACK_SERVER = "fullstack_server"


@dataclass
class ArchetypeContract:
    """
    Defines structural requirements for an archetype.
    stack_family drives which validation checks SmokeTester applies:
      "web"       → HTML/CSS/JS checks
      "python"    → .py entry point + optional requirements.txt
      "node"      → package.json + .js/.ts files
      "fullstack" → both web UI and server backend checks
      "any"       → only universal required_file_patterns check
    """
    archetype: ProductArchetype
    delivery_architectures: List[DeliveryArchitecture]
    stack_family: str = "web"          # "web" | "python" | "node" | "fullstack" | "any"
    description: str = ""

    # Web-specific counts (only used when stack_family == "web")
    min_html_files: int = 0
    max_html_files: Optional[int] = None
    min_css_files: int = 0
    max_css_files: int = 1
    min_js_files: int = 0
    max_js_files: Optional[int] = None

    # Web feature flags
    requires_navigation: bool = False
    requires_canvas: bool = False
    requires_forms: bool = False
    requires_interactivity: bool = False

    # Universal: file patterns that MUST be present (glob-style, checked relative to src/)
    # e.g. ["*.py", "requirements.txt"] or ["*.js", "package.json"]
    required_file_patterns: List[str] = field(default_factory=list)

    # Minimum total source files for non-web builds
    min_source_files: int = 1


class ArchetypeClassifier:
    """Determines product archetype from requirements and constraints."""

    def __init__(self):
        self.contracts = self._build_contracts()

    def _build_contracts(self) -> Dict[ProductArchetype, ArchetypeContract]:
        return {
            # ── Web archetypes ─────────────────────────────────────────────
            ProductArchetype.LANDING_PAGE: ArchetypeContract(
                archetype=ProductArchetype.LANDING_PAGE,
                delivery_architectures=[DeliveryArchitecture.SINGLE_FILE, DeliveryArchitecture.STATIC_MULTI_PAGE],
                stack_family="web",
                min_html_files=1, max_html_files=1,
                min_css_files=1, max_css_files=1,
                min_js_files=0, max_js_files=1,
                requires_navigation=False, requires_canvas=False,
                requires_forms=True, requires_interactivity=True,
                description="Marketing landing page with single focus",
            ),
            ProductArchetype.SINGLE_PAGE_APP: ArchetypeContract(
                archetype=ProductArchetype.SINGLE_PAGE_APP,
                delivery_architectures=[DeliveryArchitecture.SPA, DeliveryArchitecture.SINGLE_FILE],
                stack_family="web",
                min_html_files=1, max_html_files=1,
                min_css_files=1, max_css_files=1,
                min_js_files=1, max_js_files=2,
                requires_navigation=False, requires_canvas=False,
                requires_forms=False, requires_interactivity=True,
                description="Single-page application with dynamic content",
            ),
            ProductArchetype.MULTI_PAGE_SITE: ArchetypeContract(
                archetype=ProductArchetype.MULTI_PAGE_SITE,
                delivery_architectures=[DeliveryArchitecture.STATIC_MULTI_PAGE],
                stack_family="web",
                min_html_files=2,
                min_css_files=1, max_css_files=1,
                min_js_files=1, max_js_files=2,
                requires_navigation=True, requires_canvas=False,
                requires_forms=False, requires_interactivity=True,
                description="Multi-page website with navigation",
            ),
            ProductArchetype.DASHBOARD: ArchetypeContract(
                archetype=ProductArchetype.DASHBOARD,
                delivery_architectures=[DeliveryArchitecture.SPA, DeliveryArchitecture.SINGLE_FILE],
                stack_family="web",
                min_html_files=1, max_html_files=1,
                min_css_files=1, max_css_files=1,
                min_js_files=1, max_js_files=3,
                requires_navigation=False, requires_canvas=False,
                requires_forms=False, requires_interactivity=True,
                description="Data dashboard with charts and controls",
            ),
            ProductArchetype.GAME: ArchetypeContract(
                archetype=ProductArchetype.GAME,
                delivery_architectures=[DeliveryArchitecture.CANVAS_APP, DeliveryArchitecture.SINGLE_FILE],
                stack_family="web",
                min_html_files=1, max_html_files=1,
                min_css_files=1, max_css_files=1,
                min_js_files=1, max_js_files=3,
                requires_navigation=False, requires_canvas=True,
                requires_forms=False, requires_interactivity=True,
                description="Interactive game with canvas",
            ),
            ProductArchetype.DOCS_SITE: ArchetypeContract(
                archetype=ProductArchetype.DOCS_SITE,
                delivery_architectures=[DeliveryArchitecture.STATIC_MULTI_PAGE],
                stack_family="web",
                min_html_files=3,
                min_css_files=1, max_css_files=1,
                min_js_files=1, max_js_files=2,
                requires_navigation=True, requires_canvas=False,
                requires_forms=False, requires_interactivity=False,
                description="Documentation site with multiple pages",
            ),
            ProductArchetype.ADMIN_PANEL: ArchetypeContract(
                archetype=ProductArchetype.ADMIN_PANEL,
                delivery_architectures=[DeliveryArchitecture.SPA, DeliveryArchitecture.STATIC_MULTI_PAGE],
                stack_family="web",
                min_html_files=1, max_html_files=5,
                min_css_files=1, max_css_files=1,
                min_js_files=1, max_js_files=3,
                requires_navigation=True, requires_canvas=False,
                requires_forms=True, requires_interactivity=True,
                description="Admin panel with forms and data management",
            ),
            ProductArchetype.TOOL: ArchetypeContract(
                archetype=ProductArchetype.TOOL,
                delivery_architectures=[DeliveryArchitecture.SINGLE_FILE, DeliveryArchitecture.SPA],
                stack_family="web",
                min_html_files=1, max_html_files=1,
                min_css_files=1, max_css_files=1,
                min_js_files=1, max_js_files=2,
                requires_navigation=False, requires_canvas=False,
                requires_forms=True, requires_interactivity=True,
                description="Utility tool with specific functionality",
            ),
            ProductArchetype.TOY_APP: ArchetypeContract(
                archetype=ProductArchetype.TOY_APP,
                delivery_architectures=[DeliveryArchitecture.SINGLE_FILE, DeliveryArchitecture.STATIC_MULTI_PAGE],
                stack_family="web",
                min_html_files=1, max_html_files=3,
                min_css_files=1, max_css_files=1,
                # Catch-all default: a vague request (e.g. "basic website") may be a plain
                # static page. Do NOT force JS/interactivity here — that caused valid static
                # sites to fail QA and trigger pointless escalation. Interactivity stays
                # required only for archetypes that genuinely need it (game, dashboard, etc.).
                min_js_files=0, max_js_files=2,
                requires_navigation=False, requires_canvas=False,
                requires_forms=False, requires_interactivity=False,
                description="Simple site or demo (default for unspecified requests)",
            ),

            # ── Non-web archetypes ─────────────────────────────────────────
            ProductArchetype.API_SERVER: ArchetypeContract(
                archetype=ProductArchetype.API_SERVER,
                delivery_architectures=[DeliveryArchitecture.HTTP_SERVICE],
                stack_family="python",
                description="HTTP API server (FastAPI, Flask, Express, etc.)",
                required_file_patterns=["*.py", "requirements*.txt"],
                min_source_files=2,
            ),
            ProductArchetype.CLI_TOOL: ArchetypeContract(
                archetype=ProductArchetype.CLI_TOOL,
                delivery_architectures=[DeliveryArchitecture.CLI_BINARY],
                stack_family="any",
                description="Command-line tool with argument parsing",
                required_file_patterns=["main.*"],
                min_source_files=1,
            ),
            ProductArchetype.PYTHON_PACKAGE: ArchetypeContract(
                archetype=ProductArchetype.PYTHON_PACKAGE,
                delivery_architectures=[DeliveryArchitecture.PYTHON_MODULE],
                stack_family="python",
                description="Reusable Python package or library",
                required_file_patterns=["*.py", "setup.py|pyproject.toml|setup.cfg"],
                min_source_files=2,
            ),
            ProductArchetype.NODE_SERVICE: ArchetypeContract(
                archetype=ProductArchetype.NODE_SERVICE,
                delivery_architectures=[DeliveryArchitecture.HTTP_SERVICE, DeliveryArchitecture.NODE_MODULE],
                stack_family="node",
                description="Node.js service or Express/Fastify API",
                required_file_patterns=["package.json", "*.js|*.ts"],
                min_source_files=2,
            ),
            ProductArchetype.FULLSTACK_APP: ArchetypeContract(
                archetype=ProductArchetype.FULLSTACK_APP,
                delivery_architectures=[DeliveryArchitecture.FULLSTACK_SERVER],
                stack_family="fullstack",
                description="Full-stack app with frontend UI and backend server",
                required_file_patterns=["*.html|*.tsx|*.jsx", "*.py|*.js|*.ts"],
                min_source_files=3,
                # Web side (if React/HTML frontend present)
                min_html_files=0,
                min_css_files=0,
                min_js_files=0,
                requires_interactivity=True,
            ),
            ProductArchetype.AUTOMATION_SCRIPT: ArchetypeContract(
                archetype=ProductArchetype.AUTOMATION_SCRIPT,
                delivery_architectures=[DeliveryArchitecture.SHELL_SCRIPT, DeliveryArchitecture.PYTHON_MODULE],
                stack_family="any",
                description="Automation or batch-processing script",
                required_file_patterns=["*.py|*.sh|*.js"],
                min_source_files=1,
            ),
            ProductArchetype.DATABASE_SCHEMA: ArchetypeContract(
                archetype=ProductArchetype.DATABASE_SCHEMA,
                delivery_architectures=[DeliveryArchitecture.PYTHON_MODULE],
                stack_family="any",
                description="Database schema, migrations, and seed data",
                required_file_patterns=["*.sql|*.py|*.json"],
                min_source_files=1,
            ),
        }

    def classify_requirement(self, requirement: str, explicit_constraints: Optional[Dict] = None) -> Tuple[ProductArchetype, DeliveryArchitecture]:
        requirement_lower = requirement.lower()

        if explicit_constraints:
            archetype = self._apply_explicit_constraints(requirement_lower, explicit_constraints)
            if archetype:
                delivery = self._choose_delivery_architecture(archetype, explicit_constraints)
                return archetype, delivery

        archetype = self._detect_archetype_from_patterns(requirement_lower)
        delivery = self._choose_delivery_architecture(archetype, explicit_constraints)
        return archetype, delivery

    def _looks_multi_page(self, requirement: str) -> bool:
        """Detect a multi-page web site from the requirement text. Returns False if the
        request is explicitly single-page. General signal — covers 'multi-page', a list
        of named pages (Home/About/Services/Contact/Blog/...), or navigation between pages."""
        req = (requirement or "").lower()
        if re.search(r"single[\s-]?page|one[\s-]?page|\bspa\b", req):
            return False
        if re.search(
            r"multi[\s-]?page|multiple\s+pages?|separate\s+pages?|different\s+pages?|"
            r"navigation\s+between|several\s+pages?|multiple\s+tabs?|website\s+with\s+multiple",
            req,
        ):
            return True
        # Count distinct common page names — 3+ implies a multi-page site.
        page_words = [
            "home", "homepage", "about", "services", "contact", "blog", "features",
            "pricing", "portfolio", "faq", "gallery", "team", "how it works", "use cases",
        ]
        distinct = sum(1 for w in page_words if re.search(r"\b" + re.escape(w) + r"\b", req))
        return distinct >= 3

    def _apply_explicit_constraints(self, requirement: str, constraints: Dict) -> Optional[ProductArchetype]:
        stack_constraint = constraints.get("stack", "").lower()

        # FULLSTACK FIRST: if the stack names BOTH a frontend framework AND a backend,
        # it's a full-stack app — build both halves. (This must come before the
        # single-stack checks below, or "Python, FastAPI, React" wrongly routes to
        # api_server and the frontend never gets built.)
        _frontend_kw = any(s in stack_constraint for s in ["react", "vue", "angular", "next", "nuxt", "svelte"])
        _backend_kw = any(s in stack_constraint for s in ["fastapi", "flask", "django", "express", "fastify", "node", "nodejs", "rails", "spring", ".net", "python"])
        if _frontend_kw and _backend_kw:
            return ProductArchetype.FULLSTACK_APP

        # Explicit Python/backend stacks → non-web archetypes
        if any(s in stack_constraint for s in ["fastapi", "flask", "django", "python"]):
            if any(w in requirement for w in ["api", "endpoint", "route", "rest", "graphql"]):
                return ProductArchetype.API_SERVER
            if any(w in requirement for w in ["cli", "command", "script", "automat"]):
                return ProductArchetype.CLI_TOOL
            return ProductArchetype.PYTHON_PACKAGE

        if any(s in stack_constraint for s in ["express", "fastify", "node", "nodejs"]):
            return ProductArchetype.NODE_SERVICE

        if any(s in stack_constraint for s in ["react", "vue", "angular", "next", "nuxt"]):
            if any(w in requirement for w in ["api", "backend", "server", "database"]):
                return ProductArchetype.FULLSTACK_APP
            return ProductArchetype.SINGLE_PAGE_APP

        # HTML5/vanilla constraints
        if any(s in stack_constraint for s in ["html5", "vanilla", "plain", "static"]):
            if "game" not in requirement:
                # Multi-page intent wins over the toy/single defaults (don't trim pages).
                if self._looks_multi_page(requirement):
                    return ProductArchetype.MULTI_PAGE_SITE
                if any(w in requirement for w in ["tool", "utility", "converter"]):
                    return ProductArchetype.TOOL
                if any(w in requirement for w in ["click", "counter", "simple", "basic"]):
                    return ProductArchetype.TOY_APP
                return ProductArchetype.SINGLE_PAGE_APP

        file_constraints = constraints.get("files", {})
        if file_constraints.get("html", 0) == 1:
            if any(w in requirement for w in ["landing", "marketing"]):
                return ProductArchetype.LANDING_PAGE
            if any(w in requirement for w in ["dashboard", "analytics"]):
                return ProductArchetype.DASHBOARD
            if any(w in requirement for w in ["game", "play"]):
                return ProductArchetype.GAME
            if any(w in requirement for w in ["tool", "utility", "converter"]):
                return ProductArchetype.TOOL
            return ProductArchetype.SINGLE_PAGE_APP

        if file_constraints.get("html", 0) > 1:
            if any(w in requirement for w in ["docs", "documentation"]):
                return ProductArchetype.DOCS_SITE
            if any(w in requirement for w in ["admin", "manage", "crud"]):
                return ProductArchetype.ADMIN_PANEL
            return ProductArchetype.MULTI_PAGE_SITE

        return None

    def _detect_archetype_from_patterns(self, requirement: str) -> ProductArchetype:
        # ── Non-web archetypes first (explicit technology keywords) ──────
        # Fullstack first — before individual stack checks to avoid misclassification
        fullstack_patterns = [
            r"\bfullstack\b", r"\bfull.stack\b", r"\bfull\s+stack\b",
            r"\bfrontend.*backend\b", r"\bbackend.*frontend\b",
            r"\b(react|vue|angular|next|nuxt).*\b(api|server|backend|fastapi|flask|express)\b",
            r"\b(api|server|backend|fastapi|flask|express).*\b(react|vue|angular|next|nuxt)\b",
        ]
        if any(re.search(p, requirement) for p in fullstack_patterns):
            return ProductArchetype.FULLSTACK_APP

        node_service_patterns = [
            r"\bnode\.?js\b", r"\bnodejs\b",
            r"\bexpress\.?js\b", r"\bfastify\b",
            r"\bnpm\s+(package|module|service)\b", r"\bnode\s+service\b",
        ]
        if any(re.search(p, requirement) for p in node_service_patterns):
            if any(w in requirement for w in ["api", "server", "service", "endpoint", "route"]):
                return ProductArchetype.NODE_SERVICE

        api_patterns = [
            r"\bfastapi\b", r"\bflask\b", r"\bdjango\b",
            r"\brest\s+api\b", r"\bgraphql\b",
            r"\bapi\s+server\b", r"\bhttp\s+server\b", r"\bweb\s+server\b",
            r"\bendpoints?\b.*\b(get|post|put|delete|patch)\b",
            r"\b(get|post|put|delete)\s+(endpoint|route)\b",
        ]
        if any(re.search(p, requirement) for p in api_patterns):
            return ProductArchetype.API_SERVER

        cli_patterns = [
            r"\bcli\b", r"\bcommand.line\b", r"\bcommand\s+line\s+tool\b",
            r"\bargparse\b", r"\bclick\s+(library|framework|package)\b",
            r"\bterminal\s+(tool|app|script)\b", r"\bshell\s+(script|tool)\b",
            r"\btyper\b",
        ]
        if any(re.search(p, requirement) for p in cli_patterns):
            return ProductArchetype.CLI_TOOL

        node_service_patterns = [
            r"\bnode\.?js\b", r"\bnodejs\b", r"\bexpress\b", r"\bfastify\b",
            r"\bnpm\s+(package|module|service)\b", r"\bnode\s+service\b",
        ]
        if any(re.search(p, requirement) for p in node_service_patterns):
            if any(w in requirement for w in ["api", "server", "service", "endpoint"]):
                return ProductArchetype.NODE_SERVICE

        python_package_patterns = [
            r"\bpython\s+package\b", r"\bpython\s+library\b",
            r"\bpypi\b", r"\bsetup\.py\b", r"\bpyproject\b",
        ]
        if any(re.search(p, requirement) for p in python_package_patterns):
            return ProductArchetype.PYTHON_PACKAGE

        automation_patterns = [
            r"\bautomat(e|ion|ed)\b", r"\bscraper?\b", r"\bweb\s+scrap\b",
            r"\bcrawler?\b", r"\bbatch\s+(process|job|script)\b",
            r"\bscheduled?\s+(task|job|script)\b",
        ]
        if any(re.search(p, requirement) for p in automation_patterns):
            return ProductArchetype.AUTOMATION_SCRIPT

        db_patterns = [
            r"\bsql\s+schema\b", r"\bdatabase\s+schema\b", r"\bmigration\b",
            r"\bsqlalchemy\b", r"\balembic\b", r"\bprisma\b",
        ]
        if any(re.search(p, requirement) for p in db_patterns):
            return ProductArchetype.DATABASE_SCHEMA

        # ── Web archetypes ────────────────────────────────────────────────
        landing_patterns = [
            r"landing\s+page", r"marketing\s+page", r"promo\s+page",
            r"product\s+launch", r"sales\s+page",
        ]
        if any(re.search(p, requirement) for p in landing_patterns):
            return ProductArchetype.LANDING_PAGE

        if self._looks_multi_page(requirement):
            return ProductArchetype.MULTI_PAGE_SITE

        game_patterns = [
            r"\bgame\b", r"play\s+game", r"game\s+play", r"video\s+game",
            r"game\s+mechanics", r"gameplay", r"gaming", r"board\s+game",
            r"card\s+game", r"puzzle\s+game", r"arcade\s+game",
        ]
        if any(re.search(p, requirement) for p in game_patterns):
            return ProductArchetype.GAME

        dashboard_patterns = [
            r"dashboard", r"analytics", r"metrics", r"charts?", r"data\s+viz",
            r"admin\s+panel", r"control\s+panel", r"monitor",
        ]
        if any(re.search(p, requirement) for p in dashboard_patterns):
            return ProductArchetype.DASHBOARD

        blockchain_patterns = [
            r"blockchain", r"identity\s+system", r"digital\s+identity",
            r"mfa", r"two-factor", r"authentication", r"kyc", r"aml",
        ]
        if any(re.search(p, requirement) for p in blockchain_patterns):
            return ProductArchetype.DASHBOARD

        docs_patterns = [
            r"docs?", r"documentation", r"guide", r"manual", r"wiki",
            r"knowledge\s+base", r"help\s+docs", r"api\s+docs",
        ]
        if any(re.search(p, requirement) for p in docs_patterns):
            return ProductArchetype.DOCS_SITE

        admin_patterns = [
            r"admin\s+panel", r"admin\s+dashboard", r"crud", r"manage\s+",
            r"user\s+management", r"content\s+management",
        ]
        if any(re.search(p, requirement) for p in admin_patterns):
            return ProductArchetype.ADMIN_PANEL

        tool_patterns = [
            r"tool", r"utility", r"converter", r"calculator", r"generator",
            r"parser", r"validator", r"formatter", r"analyzer",
        ]
        if any(re.search(p, requirement) for p in tool_patterns):
            return ProductArchetype.TOOL

        single_page_patterns = [
            r"single\s+page", r"one\s+page", r"\bspa\b", r"simple\s+page",
        ]
        if any(re.search(p, requirement) for p in single_page_patterns):
            return ProductArchetype.SINGLE_PAGE_APP

        return ProductArchetype.TOY_APP

    def _choose_delivery_architecture(self, archetype: ProductArchetype, constraints: Optional[Dict] = None) -> DeliveryArchitecture:
        contract = self.contracts[archetype]
        if constraints:
            arch_constraint = constraints.get("architecture")
            if arch_constraint:
                try:
                    return DeliveryArchitecture(arch_constraint)
                except ValueError:
                    pass
        return contract.delivery_architectures[0]

    def get_contract(self, archetype: ProductArchetype) -> ArchetypeContract:
        return self.contracts[archetype]

    def is_web_archetype(self, archetype: ProductArchetype) -> bool:
        return self.contracts[archetype].stack_family == "web"
