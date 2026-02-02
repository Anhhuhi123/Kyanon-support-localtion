"""
Route Algorithm Backend - Python Implementation
Tách logic thuật toán route building để dễ maintain và test
"""
import math
import json
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, asdict
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

EARTH_RADIUS_KM = 6371

@dataclass
class POI:
    id: str
    name: str
    category: str
    lat: float
    lon: float
    score: float  # similarity (0-1)
    rating: float  # normalized rating (0-1)
    x: float = 0
    y: float = 0
    distance: float = 0
    bearing: float = 0

class GeographicUtils:
    """Các hàm tính toán địa lý"""
    
    @staticmethod
    def calculate_distance_haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Tính khoảng cách Haversine (meters)
        
        Args:
            lat1, lon1: Tọa độ điểm 1
            lat2, lon2: Tọa độ điểm 2
            
        Returns:
            Khoảng cách (meters)
        """
        R = EARTH_RADIUS_KM
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c * 1000  # Convert to meters
    
    @staticmethod
    def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Tính bearing (góc hướng) từ điểm 1 đến điểm 2
        
        Bearing là góc giữa:
        - Vector hướng Bắc từ điểm 1
        - Vector từ điểm 1 đến điểm 2
        
        Args:
            lat1, lon1: Tọa độ điểm 1 (điểm bắt đầu)
            lat2, lon2: Tọa độ điểm 2 (điểm kết thúc)
            
        Returns:
            Bearing (độ, 0-360): 0° = Bắc, 90° = Đông, 180° = Nam, 270° = Tây
        """
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lon = math.radians(lon2 - lon1)
        
        x = math.sin(delta_lon) * math.cos(lat2_rad)
        y = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(delta_lon)
        
        bearing_rad = math.atan2(x, y)
        bearing_deg = math.degrees(bearing_rad)
        
        return (bearing_deg + 360) % 360
    
    @staticmethod
    def calculate_bearing_difference(bearing1: float, bearing2: float) -> float:
        """
        Tính độ chênh lệch góc giữa 2 bearing
        
        Args:
            bearing1: Bearing của vector trước (độ)
            bearing2: Bearing của vector sau (độ)
            
        Returns:
            Độ chênh lệch (0-180 độ)
        """
        diff = abs(bearing1 - bearing2)
        if diff > 180:
            diff = 360 - diff
        return diff
    
    @staticmethod
    def build_distance_matrix(user_location: Tuple[float, float], pois: List[POI]) -> List[List[float]]:
        """
        Xây dựng ma trận khoảng cách (n+1)x(n+1)
        Index 0 = User location
        Index 1 to n = POIs
        
        Args:
            user_location: (lat, lon) của user
            pois: Danh sách POI
            
        Returns:
            Matrix[i][j] = khoảng cách từ i đến j (meters)
        """
        n = len(pois)
        matrix = [[0.0] * (n + 1) for _ in range(n + 1)]
        
        # All coordinates: [user, poi1, poi2, ..., poin]
        coords = [user_location] + [(poi.lat, poi.lon) for poi in pois]
        
        for i in range(n + 1):
            for j in range(n + 1):
                if i != j:
                    lat1, lon1 = coords[i]
                    lat2, lon2 = coords[j]
                    matrix[i][j] = GeographicUtils.calculate_distance_haversine(lat1, lon1, lat2, lon2)
        
        return matrix

class RouteCalculator:
    """Tính toán combined score và xây dựng route"""
    
    def __init__(self):
        self.geo = GeographicUtils()
    
    def calculate_combined_score(
        self,
        poi: POI,
        current_pos: Tuple[float, float],
        prev_bearing: Optional[float],
        is_first: bool,
        is_last: bool,
        max_distance: float,
        user_location: Tuple[float, float]
    ) -> Dict:
        """
        Tính combined score cho POI
        
        Args:
            poi: POI cần tính
            current_pos: Vị trí hiện tại (lat, lon)
            prev_bearing: Bearing của vector trước đó (None nếu là POI đầu)
            is_first: POI đầu tiên?
            is_last: POI cuối cùng?
            max_distance: Khoảng cách tối đa để normalize
            user_location: Tọa độ user
            
        Returns:
            Dict chứa combined score và các thành phần
        """
        similarity = poi.score
        rating = poi.rating
        
        # Calculate distance
        if is_last:
            # POI cuối: distance về user
            distance = self.geo.calculate_distance_haversine(poi.lat, poi.lon, user_location[0], user_location[1])
        else:
            # Distance từ current position đến POI
            distance = self.geo.calculate_distance_haversine(current_pos[0], current_pos[1], poi.lat, poi.lon)
        
        # Normalize distance (1 = gần, 0 = xa)
        normalized_distance = distance / max_distance if max_distance > 0 else 0
        distance_score = 1 - normalized_distance
        
        # Calculate bearing score
        bearing_score = 0.5  # Default
        bearing_to_poi = self.geo.calculate_bearing(current_pos[0], current_pos[1], poi.lat, poi.lon)
        bearing_diff = 0
        
        if not is_first and not is_last and prev_bearing is not None:
            # Bearing của vector từ current đến POI tiếp theo
            current_bearing = bearing_to_poi
            
            # Tính chênh lệch với bearing trước đó
            bearing_diff = self.geo.calculate_bearing_difference(prev_bearing, current_bearing)
            
            # Bearing score: 0° (cùng hướng) = 1.0, 180° (ngược hướng) = 0.0
            bearing_score = 1.0 - (bearing_diff / 180.0)
        
        # Apply weights
        if is_first:
            weights = {"distance": 0.1, "similarity": 0.45, "rating": 0.45, "bearing": 0.0}
            combined = (
                weights["distance"] * distance_score +
                weights["similarity"] * similarity +
                weights["rating"] * rating
            )
        elif is_last:
            weights = {"distance": 0.4, "similarity": 0.3, "rating": 0.3, "bearing": 0.0}
            combined = (
                weights["distance"] * distance_score +
                weights["similarity"] * similarity +
                weights["rating"] * rating
            )
        else:
            # POI giữa
            if similarity >= 0.8:
                weights = {"distance": 0.15, "similarity": 0.5, "rating": 0.3, "bearing": 0.05}
            else:
                weights = {"distance": 0.25, "similarity": 0.1, "rating": 0.4, "bearing": 0.25}
            
            combined = (
                weights["distance"] * distance_score +
                weights["similarity"] * similarity +
                weights["rating"] * rating +
                weights["bearing"] * bearing_score
            )
        
        return {
            "combined_score": combined,
            "distance_score": distance_score,
            "bearing_score": bearing_score,
            "bearing_to_poi": bearing_to_poi,
            "bearing_diff": bearing_diff,
            "distance": distance,
            "weights": weights
        }
    
    def build_route(
        self,
        pois: List[POI],
        user_location: Tuple[float, float],
        target_count: int,
        max_radius: float
    ) -> List[Dict]:
        """
        Xây dựng route bằng greedy algorithm
        
        Args:
            pois: Danh sách POI candidates
            user_location: Tọa độ user (lat, lon)
            target_count: Số POI mục tiêu
            max_radius: Bán kính tối đa (meters)
            
        Returns:
            List các POI trong route với score breakdown
        """
        route = []
        used_ids = set()
        
        current_pos = user_location
        prev_bearing = None
        
        for step in range(target_count):
            is_first = (step == 0)
            is_last = (step == target_count - 1)
            
            best_poi = None
            best_score_data = None
            best_score = -float('inf')
            
            for poi in pois:
                if poi.id in used_ids:
                    continue
                
                score_data = self.calculate_combined_score(
                    poi, current_pos, prev_bearing, is_first, is_last, max_radius, user_location
                )
                
                if score_data["combined_score"] > best_score:
                    best_score = score_data["combined_score"]
                    best_poi = poi
                    best_score_data = score_data
            
            if best_poi is None:
                break
            
            # Add to route
            poi_dict = asdict(best_poi)
            poi_dict.update(best_score_data)
            route.append(poi_dict)
            
            used_ids.add(best_poi.id)
            
            # Update for next iteration
            if not is_last:
                prev_bearing = best_score_data["bearing_to_poi"]
            current_pos = (best_poi.lat, best_poi.lon)
        
        return route

# Flask API endpoints
@app.route('/api/build_route', methods=['POST'])
def api_build_route():
    """
    API endpoint để build route
    
    Request body:
    {
        "pois": [...],
        "user_location": {"lat": ..., "lon": ...},
        "target_count": 5,
        "max_radius": 2000
    }
    """
    data = request.json
    
    # Parse POIs
    pois = [POI(**poi_data) for poi_data in data['pois']]
    user_location = (data['user_location']['lat'], data['user_location']['lon'])
    target_count = data.get('target_count', 5)
    max_radius = data.get('max_radius', 2000)
    
    # Build route
    calculator = RouteCalculator()
    route = calculator.build_route(pois, user_location, target_count, max_radius)
    
    # Build distance matrix
    geo = GeographicUtils()
    distance_matrix = geo.build_distance_matrix(user_location, pois)
    
    return jsonify({
        "route": route,
        "distance_matrix": distance_matrix
    })

@app.route('/api/calculate_distance_matrix', methods=['POST'])
def api_calculate_distance_matrix():
    """
    API để tính distance matrix
    
    Request body:
    {
        "user_location": {"lat": ..., "lon": ...},
        "pois": [...]
    }
    """
    data = request.json
    
    pois = [POI(**poi_data) for poi_data in data['pois']]
    user_location = (data['user_location']['lat'], data['user_location']['lon'])
    
    geo = GeographicUtils()
    matrix = geo.build_distance_matrix(user_location, pois)
    
    return jsonify({
        "distance_matrix": matrix,
        "labels": ["USER"] + [poi.name for poi in pois]
    })

if __name__ == '__main__':
    print("🚀 Starting Route Algorithm Server...")
    print("📍 Server running at: http://localhost:5000")
    print("\nAvailable endpoints:")
    print("  POST /api/build_route - Build optimal route")
    print("  POST /api/calculate_distance_matrix - Calculate distance matrix")
    app.run(debug=True, port=5000)
