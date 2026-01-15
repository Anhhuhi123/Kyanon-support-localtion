"""
Route Builder Module
"""
from .route_config import RouteConfig
from .geographic_utils import GeographicUtils
from .poi_validator import POIValidator
from .calculator import Calculator

# Import RouteBuilder from parent module (route.py)
# Use importlib to avoid circular import issues
import importlib.util
import os

# Get the path to route.py (parent directory)
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
route_py_path = os.path.join(parent_dir, 'route.py')

# Load route.py as a module
spec = importlib.util.spec_from_file_location("radius_logic.route_module", route_py_path)
route_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(route_module)

# Export RouteBuilder
RouteBuilder = route_module.RouteBuilder

__all__ = [
    'RouteConfig',
    'GeographicUtils',
    'POIValidator',
    'Calculator',
    'RouteBuilder'
]