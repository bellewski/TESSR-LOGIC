"""
Product archetype detection and contract system.
Determines the type of application being built and applies appropriate validation rules.
"""

from enum import Enum
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import re

class ProductArchetype(Enum):
    """Core product archetypes with distinct structural requirements."""
    LANDING_PAGE = "landing_page"
    SINGLE_PAGE_APP = "single_page_app" 
    MULTI_PAGE_SITE = "multi_page_site"
    DASHBOARD = "dashboard"
    GAME = "game"
    DOCS_SITE = "docs_site"
    ADMIN_PANEL = "admin_panel"
    TOOL = "tool"
    TOY_APP = "toy_app"

class DeliveryArchitecture(Enum):
    """How the product is delivered to users."""
    SINGLE_FILE = "single_file"      # One HTML with embedded CSS/JS
    STATIC_MULTI_PAGE = "static_multi_page"  # Multiple HTML files
    SPA = "spa"                     # Single HTML with JS routing
    MICROSITE = "microsite"         # Small focused site
    CANVAS_APP = "canvas_app"       # Game/canvas-based

@dataclass
class ArchetypeContract:
    """Defines the structural requirements for an archetype."""
    archetype: ProductArchetype
    delivery_architectures: List[DeliveryArchitecture]
    min_html_files: int
    max_html_files: Optional[int] = None
    min_css_files: int = 1
    max_css_files: int = 1
    min_js_files: int = 0
    max_js_files: Optional[int] = None
    requires_navigation: bool = False
    requires_canvas: bool = False
    requires_forms: bool = False
    requires_interactivity: bool = False
    description: str = ""

class ArchetypeClassifier:
    """Determines product archetype from requirements and constraints."""
    
    def __init__(self):
        self.contracts = self._build_contracts()
    
    def _build_contracts(self) -> Dict[ProductArchetype, ArchetypeContract]:
        """Build archetype-specific contracts."""
        return {
            ProductArchetype.LANDING_PAGE: ArchetypeContract(
                archetype=ProductArchetype.LANDING_PAGE,
                delivery_architectures=[DeliveryArchitecture.SINGLE_FILE, DeliveryArchitecture.STATIC_MULTI_PAGE],
                min_html_files=1,
                max_html_files=1,
                min_css_files=1,
                max_css_files=1,
                min_js_files=0,
                max_js_files=1,
                requires_navigation=False,
                requires_canvas=False,
                requires_forms=True,
                requires_interactivity=True,
                description="Marketing landing page with single focus"
            ),
            
            ProductArchetype.SINGLE_PAGE_APP: ArchetypeContract(
                archetype=ProductArchetype.SINGLE_PAGE_APP,
                delivery_architectures=[DeliveryArchitecture.SPA, DeliveryArchitecture.SINGLE_FILE],
                min_html_files=1,
                max_html_files=1,
                min_css_files=1,
                max_css_files=1,
                min_js_files=1,
                max_js_files=2,
                requires_navigation=False,
                requires_canvas=False,
                requires_forms=False,
                requires_interactivity=True,
                description="Single-page application with dynamic content"
            ),
            
            ProductArchetype.MULTI_PAGE_SITE: ArchetypeContract(
                archetype=ProductArchetype.MULTI_PAGE_SITE,
                delivery_architectures=[DeliveryArchitecture.STATIC_MULTI_PAGE],
                min_html_files=2,
                min_css_files=1,
                max_css_files=1,
                min_js_files=1,
                max_js_files=2,
                requires_navigation=True,
                requires_canvas=False,
                requires_forms=False,
                requires_interactivity=True,
                description="Multi-page website with navigation"
            ),
            
            ProductArchetype.DASHBOARD: ArchetypeContract(
                archetype=ProductArchetype.DASHBOARD,
                delivery_architectures=[DeliveryArchitecture.SPA, DeliveryArchitecture.SINGLE_FILE],
                min_html_files=1,
                max_html_files=1,
                min_css_files=1,
                max_css_files=1,
                min_js_files=1,
                max_js_files=3,
                requires_navigation=False,
                requires_canvas=False,
                requires_forms=False,
                requires_interactivity=True,
                description="Data dashboard with charts and controls"
            ),
            
            ProductArchetype.GAME: ArchetypeContract(
                archetype=ProductArchetype.GAME,
                delivery_architectures=[DeliveryArchitecture.CANVAS_APP, DeliveryArchitecture.SINGLE_FILE],
                min_html_files=1,
                max_html_files=1,
                min_css_files=1,
                max_css_files=1,
                min_js_files=1,
                max_js_files=3,
                requires_navigation=False,
                requires_canvas=True,
                requires_forms=False,
                requires_interactivity=True,
                description="Interactive game with canvas"
            ),
            
            ProductArchetype.DOCS_SITE: ArchetypeContract(
                archetype=ProductArchetype.DOCS_SITE,
                delivery_architectures=[DeliveryArchitecture.STATIC_MULTI_PAGE],
                min_html_files=3,
                min_css_files=1,
                max_css_files=1,
                min_js_files=1,
                max_js_files=2,
                requires_navigation=True,
                requires_canvas=False,
                requires_forms=False,
                requires_interactivity=False,
                description="Documentation site with multiple pages"
            ),
            
            ProductArchetype.ADMIN_PANEL: ArchetypeContract(
                archetype=ProductArchetype.ADMIN_PANEL,
                delivery_architectures=[DeliveryArchitecture.SPA, DeliveryArchitecture.STATIC_MULTI_PAGE],
                min_html_files=1,
                max_html_files=5,
                min_css_files=1,
                max_css_files=1,
                min_js_files=1,
                max_js_files=3,
                requires_navigation=True,
                requires_canvas=False,
                requires_forms=True,
                requires_interactivity=True,
                description="Admin panel with forms and data management"
            ),
            
            ProductArchetype.TOOL: ArchetypeContract(
                archetype=ProductArchetype.TOOL,
                delivery_architectures=[DeliveryArchitecture.SINGLE_FILE, DeliveryArchitecture.SPA],
                min_html_files=1,
                max_html_files=1,
                min_css_files=1,
                max_css_files=1,
                min_js_files=1,
                max_js_files=2,
                requires_navigation=False,
                requires_canvas=False,
                requires_forms=True,
                requires_interactivity=True,
                description="Utility tool with specific functionality"
            ),
            
            ProductArchetype.TOY_APP: ArchetypeContract(
                archetype=ProductArchetype.TOY_APP,
                delivery_architectures=[DeliveryArchitecture.SINGLE_FILE, DeliveryArchitecture.STATIC_MULTI_PAGE],
                min_html_files=1,
                max_html_files=3,
                min_css_files=1,
                max_css_files=1,
                min_js_files=1,
                max_js_files=2,
                requires_navigation=False,
                requires_canvas=False,
                requires_forms=False,
                requires_interactivity=True,
                description="Simple toy app or demo"
            )
        }
    
    def classify_requirement(self, requirement: str, explicit_constraints: Optional[Dict] = None) -> Tuple[ProductArchetype, DeliveryArchitecture]:
        """
        Classify the product archetype from requirement text.
        
        Args:
            requirement: User requirement text
            explicit_constraints: Explicit user constraints (e.g., {"files": {"html": 1}})
            
        Returns:
            Tuple of (archetype, delivery_architecture)
        """
        requirement_lower = requirement.lower()
        
        # Step 1: Check for explicit user constraints first
        if explicit_constraints:
            archetype = self._apply_explicit_constraints(requirement_lower, explicit_constraints)
            if archetype:
                delivery = self._choose_delivery_architecture(archetype, explicit_constraints)
                return archetype, delivery
        
        # Step 2: Pattern-based archetype detection
        archetype = self._detect_archetype_from_patterns(requirement_lower)
        
        # Step 3: Choose delivery architecture
        delivery = self._choose_delivery_architecture(archetype, explicit_constraints)
        
        return archetype, delivery
    
    def _apply_explicit_constraints(self, requirement: str, constraints: Dict) -> Optional[ProductArchetype]:
        """Apply explicit user constraints to determine archetype."""
        # Check for explicit file count constraints
        file_constraints = constraints.get("files", {})
        
        # Check for explicit stack constraints (HTML5, vanilla JS, etc.)
        stack_constraint = constraints.get("stack", "")
        if stack_constraint:
            stack_lower = stack_constraint.lower()
            # If user explicitly wants HTML5/vanilla, avoid game archetype unless explicitly requested
            if any(term in stack_lower for term in ["html5", "vanilla", "plain", "static"]):
                if "game" not in requirement.lower():  # Only avoid game if not explicitly requested
                    # Favor toy_app or tool for simple interactive requirements
                    if any(word in requirement for word in ["click", "counter", "simple", "basic"]):
                        return ProductArchetype.TOY_APP
                    elif any(word in requirement for word in ["tool", "utility", "converter"]):
                        return ProductArchetype.TOOL
                    else:
                        return ProductArchetype.SINGLE_PAGE_APP
        
        # If user explicitly wants 1 HTML file, favor single-page archetypes
        if file_constraints.get("html", 0) == 1:
            # Look for other clues to determine which single-page type
            if any(word in requirement for word in ["landing", "marketing", "promo"]):
                return ProductArchetype.LANDING_PAGE
            elif any(word in requirement for word in ["dashboard", "analytics", "metrics"]):
                return ProductArchetype.DASHBOARD
            elif any(word in requirement for word in ["game", "play"]):  # Removed "score" to avoid false positives
                return ProductArchetype.GAME
            elif any(word in requirement for word in ["tool", "utility", "converter"]):
                return ProductArchetype.TOOL
            else:
                return ProductArchetype.SINGLE_PAGE_APP
        
        # If user explicitly wants multiple pages, favor multi-page archetypes
        if file_constraints.get("html", 0) > 1:
            if any(word in requirement for word in ["docs", "documentation", "guide"]):
                return ProductArchetype.DOCS_SITE
            elif any(word in requirement for word in ["admin", "manage", "crud"]):
                return ProductArchetype.ADMIN_PANEL
            else:
                return ProductArchetype.MULTI_PAGE_SITE
        
        return None
    
    def _detect_archetype_from_patterns(self, requirement: str) -> ProductArchetype:
        """Detect archetype from requirement text patterns."""
        
        # Landing page patterns
        landing_patterns = [
            r"landing\s+page", r"marketing\s+page", r"promo\s+page",
            r"product\s+launch", r"sales\s+page", r"squeeze\s+page"
        ]
        if any(re.search(pattern, requirement) for pattern in landing_patterns):
            return ProductArchetype.LANDING_PAGE
        
        # Game patterns (more specific to avoid false positives)
        game_patterns = [
            r"\bgame\b", r"play\s+game", r"game\s+play", r"video\s+game",
            r"game\s+mechanics", r"gameplay", r"gaming", r"board\s+game",
            r"card\s+game", r"puzzle\s+game", r"arcade\s+game"
        ]
        # Only match if explicit game terms are found, not just "score" or "level"
        if any(re.search(pattern, requirement) for pattern in game_patterns):
            return ProductArchetype.GAME
        
        # Dashboard patterns
        dashboard_patterns = [
            r"dashboard", r"analytics", r"metrics", r"charts?", r"data\s+viz",
            r"admin\s+panel", r"control\s+panel", r"monitor"
        ]
        if any(re.search(pattern, requirement) for pattern in dashboard_patterns):
            return ProductArchetype.DASHBOARD
        
        # Blockchain identity patterns - should be dashboard/single-page, not multi-page
        blockchain_patterns = [
            r"blockchain", r"identity\s+system", r"digital\s+identity", r"verification",
            r"mfa", r"two-factor", r"authentication", r"recovery", r"kyc", r"aml"
        ]
        if any(re.search(pattern, requirement) for pattern in blockchain_patterns):
            return ProductArchetype.DASHBOARD
        
        # Documentation patterns
        docs_patterns = [
            r"docs?", r"documentation", r"guide", r"manual", r"wiki",
            r"knowledge\s+base", r"help\s+docs", r"api\s+docs"
        ]
        if any(re.search(pattern, requirement) for pattern in docs_patterns):
            return ProductArchetype.DOCS_SITE
        
        # Admin panel patterns
        admin_patterns = [
            r"admin\s+panel", r"admin\s+dashboard", r"crud", r"manage\s+",
            r"user\s+management", r"content\s+management"
        ]
        if any(re.search(pattern, requirement) for pattern in admin_patterns):
            return ProductArchetype.ADMIN_PANEL
        
        # Tool patterns
        tool_patterns = [
            r"tool", r"utility", r"converter", r"calculator", r"generator",
            r"parser", r"validator", r"formatter", r"analyzer"
        ]
        if any(re.search(pattern, requirement) for pattern in tool_patterns):
            return ProductArchetype.TOOL
        
        # Multi-page patterns
        multi_page_patterns = [
            r"multiple\s+pages?", r"separate\s+pages?", r"different\s+pages?",
            r"navigation\s+between", r"link\s+pages?", r"website\s+with\s+multiple",
            r"multi-page\s+site", r"several\s+pages?"
        ]
        if any(re.search(pattern, requirement) for pattern in multi_page_patterns):
            return ProductArchetype.MULTI_PAGE_SITE
        
        # Single page patterns
        single_page_patterns = [
            r"single\s+page", r"one\s+page", r"spa", r"simple\s+page",
            r"basic\s+page", r"test\s+page"
        ]
        if any(re.search(pattern, requirement) for pattern in single_page_patterns):
            return ProductArchetype.SINGLE_PAGE_APP
        
        # Default to toy app for simple requirements
        return ProductArchetype.TOY_APP
    
    def _choose_delivery_architecture(self, archetype: ProductArchetype, constraints: Optional[Dict] = None) -> DeliveryArchitecture:
        """Choose delivery architecture based on archetype and constraints."""
        contract = self.contracts[archetype]
        
        # Check for explicit architecture constraints
        if constraints:
            arch_constraint = constraints.get("architecture")
            if arch_constraint:
                try:
                    return DeliveryArchitecture(arch_constraint)
                except ValueError:
                    pass  # Fall through to default choice
        
        # Default to first available architecture for the archetype
        return contract.delivery_architectures[0]
    
    def get_contract(self, archetype: ProductArchetype) -> ArchetypeContract:
        """Get the contract for a specific archetype."""
        return self.contracts[archetype]
