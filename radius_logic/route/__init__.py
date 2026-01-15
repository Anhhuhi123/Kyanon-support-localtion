"""
Route Builder Module
"""
from .route_config import RouteConfig
from .geographic_utils import GeographicUtils
from .poi_validator import POIValidator
from .score_calculator import ScoreCalculator

# Import RouteBuilder from parent module (route.py)
# We need to import from the parent package's route.py file
import importlib.util
import os

# Get path to route.py (sibling file in parent directory)
_current_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_current_dir)
_route_py_path = os.path.join(_parent_dir, 'route.py')

# Load route.py as a module
_spec = importlib.util.spec_from_file_location("radius_logic_route_builder", _route_py_path)
_route_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_route_module)

# Export RouteBuilder
RouteBuilder = _route_module.RouteBuilder

__all__ = [
    'RouteConfig',
    'GeographicUtils',
    'POIValidator',
    'ScoreCalculator',
    'RouteBuilder'
]