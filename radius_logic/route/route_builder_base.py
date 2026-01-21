"""
Base Route Builder - Chứa các helper methods chung cho cả 2 mode
"""
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional
from utils.time_utils import TimeUtils
from .route_config import RouteConfig
from .geographic_utils import GeographicUtils
from .poi_validator import POIValidator
from .calculator import Calculator

class BaseRouteBuilder:
    """Base class chứa các helper methods chung"""
    
    def __init__(
        self,
        geo: GeographicUtils,
        validator: POIValidator,
        calculator: Calculator
    ):
        self.geo = geo
        self.validator = validator
        self.calculator = calculator
    
    def analyze_meal_requirements(
        self,
        places: List[Dict[str, Any]],
        current_datetime: Optional[datetime],
        max_time_minutes: int
    ) -> Dict[str, Any]:
        """
        Phân tích categories và meal requirements
        
        Returns:
            Dict chứa:
            - all_categories: List các category (giữ thứ tự)
            - should_insert_restaurant_for_meal: bool
            - meal_windows: Dict[str, Tuple[datetime, datetime]]
            - need_lunch_restaurant: bool
            - need_dinner_restaurant: bool
        """
        all_categories = list(dict.fromkeys(
            place.get('category') for place in places if 'category' in place
        ))
        has_cafe = "Cafe & Bakery" in all_categories
        has_restaurant = "Restaurant" in all_categories
        
        should_insert_restaurant_for_meal = False
        meal_windows = None
        need_lunch_restaurant = False
        need_dinner_restaurant = False
        
        if not has_cafe and has_restaurant:
            if current_datetime and max_time_minutes:
                meal_check = TimeUtils.check_overlap_with_meal_times(
                    current_datetime, max_time_minutes
                )
                if meal_check["needs_restaurant"]:
                    should_insert_restaurant_for_meal = True
                    lunch_overlap = meal_check['lunch_overlap_minutes'] >= 60
                    dinner_overlap = meal_check['dinner_overlap_minutes'] >= 60
                    
                    need_lunch_restaurant = lunch_overlap
                    need_dinner_restaurant = dinner_overlap
                    
                    meal_windows = {
                        "lunch": meal_check.get("lunch_window"),
                        "dinner": meal_check.get("dinner_window")
                    }
        
        return {
            "all_categories": all_categories,
            "should_insert_restaurant_for_meal": should_insert_restaurant_for_meal,
            "meal_windows": meal_windows,
            "need_lunch_restaurant": need_lunch_restaurant,
            "need_dinner_restaurant": need_dinner_restaurant
        }
    
    def select_first_poi(
        self,
        places: List[Dict[str, Any]],
        first_place_idx: Optional[int],
        distance_matrix: List[List[float]],
        max_distance: float,
        transportation_mode: str,
        current_datetime: Optional[datetime],
        should_insert_restaurant_for_meal: bool
    ) -> Optional[int]:
        """
        Chọn POI đầu tiên
        
        Returns:
            Index của POI đầu tiên hoặc None nếu không tìm thấy
        """
        if first_place_idx is not None:
            return first_place_idx
        
        best_first = None
        best_first_score = -1
        
        for i, place in enumerate(places):
            if current_datetime:
                travel_time = self.calculator.calculate_travel_time(
                    distance_matrix[0][i + 1],
                    transportation_mode
                )
                arrival_time = TimeUtils.get_arrival_time(current_datetime, travel_time)
                if not self.validator.is_poi_available_at_time(place, arrival_time):
                    continue
            
            if should_insert_restaurant_for_meal and place.get('category') == 'Restaurant':
                continue
            
            combined = self.calculator.calculate_combined_score(
                place_idx=i,
                current_pos=0,
                places=places,
                distance_matrix=distance_matrix,
                max_distance=max_distance,
                is_first=True
            )
            
            if combined > best_first_score or (
                combined == best_first_score and (best_first is None or i < best_first)
            ):
                best_first_score = combined
                best_first = i
        
        return best_first
    
    def check_first_poi_meal_status(
        self,
        first_poi_idx: int,
        places: List[Dict[str, Any]],
        should_insert_restaurant_for_meal: bool,
        meal_windows: Optional[Dict],
        distance_matrix: List[List[float]],
        transportation_mode: str,
        current_datetime: Optional[datetime]
    ) -> Tuple[bool, bool]:
        """
        Kiểm tra xem POI đầu có phải Restaurant trong meal window không
        
        Returns:
            (lunch_restaurant_inserted, dinner_restaurant_inserted)
        """
        lunch_inserted = False
        dinner_inserted = False
        
        if not should_insert_restaurant_for_meal:
            return lunch_inserted, dinner_inserted
        
        if places[first_poi_idx].get('category') != 'Restaurant':
            return lunch_inserted, dinner_inserted
        
        if not (current_datetime and meal_windows):
            return lunch_inserted, dinner_inserted
        
        travel_time = self.calculator.calculate_travel_time(
            distance_matrix[0][first_poi_idx + 1],
            transportation_mode
        )
        arrival_first = TimeUtils.get_arrival_time(current_datetime, travel_time)
        
        if meal_windows.get('lunch'):
            lunch_start, lunch_end = meal_windows['lunch']
            if lunch_start <= arrival_first <= lunch_end:
                lunch_inserted = True
        
        if meal_windows.get('dinner'):
            dinner_start, dinner_end = meal_windows['dinner']
            if dinner_start <= arrival_first <= dinner_end:
                dinner_inserted = True
        
        return lunch_inserted, dinner_inserted
    
    def select_last_poi(
        self,
        places: List[Dict[str, Any]],
        visited: set,
        current_pos: int,
        distance_matrix: List[List[float]],
        max_radius: float,
        transportation_mode: str,
        max_distance: float,
        total_travel_time: float,
        total_stay_time: float,
        max_time_minutes: int,
        current_datetime: Optional[datetime],
        should_insert_restaurant_for_meal: bool,
        meal_windows: Optional[Dict],
        lunch_restaurant_inserted: bool,
        dinner_restaurant_inserted: bool
    ) -> Optional[int]:
        """
        Chọn POI cuối cùng gần user
        
        Returns:
            Index của POI cuối hoặc None
        """
        best_last = None
        best_last_score = -1
        
        radius_thresholds = RouteConfig.LAST_POI_RADIUS_THRESHOLDS
        
        for threshold_multiplier in radius_thresholds:
            current_threshold = threshold_multiplier * max_radius
            
            for i, place in enumerate(places):
                if i in visited:
                    continue
                
                # Logic lọc Restaurant cho POI cuối
                if should_insert_restaurant_for_meal and place.get('category') == 'Restaurant':
                    if current_datetime and meal_windows:
                        travel_time_to_last = self.calculator.calculate_travel_time(
                            distance_matrix[current_pos][i + 1],
                            transportation_mode
                        )
                        arrival_at_last = current_datetime + timedelta(
                            minutes=total_travel_time + total_stay_time + travel_time_to_last
                        )
                        
                        in_lunch = False
                        in_dinner = False
                        
                        if meal_windows.get('lunch'):
                            lunch_start, lunch_end = meal_windows['lunch']
                            if lunch_start <= arrival_at_last <= lunch_end:
                                in_lunch = True
                        
                        if meal_windows.get('dinner'):
                            dinner_start, dinner_end = meal_windows['dinner']
                            if dinner_start <= arrival_at_last <= dinner_end:
                                in_dinner = True
                        
                        if in_lunch and lunch_restaurant_inserted:
                            continue
                        if in_dinner and dinner_restaurant_inserted:
                            continue
                        if not in_lunch and not in_dinner:
                            continue
                
                # Kiểm tra khoảng cách đến user
                dist_to_user = distance_matrix[i + 1][0]
                if dist_to_user > current_threshold:
                    continue
                
                if current_datetime:
                    travel_time_to_poi = self.calculator.calculate_travel_time(
                        distance_matrix[current_pos][i + 1],
                        transportation_mode
                    )
                    arrival_time = current_datetime + timedelta(
                        minutes=total_travel_time + total_stay_time + travel_time_to_poi
                    )
                    if not self.validator.is_poi_available_at_time(place, arrival_time):
                        continue
                
                # Kiểm tra thời gian khả thi
                temp_travel = total_travel_time + self.calculator.calculate_travel_time(
                    distance_matrix[current_pos][i + 1],
                    transportation_mode
                )
                temp_stay = total_stay_time + self.calculator.get_stay_time(
                    places[i].get("poi_type", "")
                )
                return_time = self.calculator.calculate_travel_time(
                    dist_to_user, transportation_mode
                )
                
                if temp_travel + temp_stay + return_time > max_time_minutes:
                    continue
                
                # POI cuối: ưu tiên gần user
                combined = self.calculator.calculate_combined_score(
                    place_idx=i,
                    current_pos=current_pos,
                    places=places,
                    distance_matrix=distance_matrix,
                    max_distance=max_distance,
                    is_last=True
                )
                
                if combined > best_last_score or (
                    combined == best_last_score and (best_last is None or i < best_last)
                ):
                    best_last_score = combined
                    best_last = i
            
            if best_last is not None:
                print(f"🎯 Tìm được POI cuối ở mức {threshold_multiplier*100:.0f}% bán kính")
                break
        
        return best_last
    
    def format_route_result(
        self,
        route: List[int],
        places: List[Dict[str, Any]],
        distance_matrix: List[List[float]],
        transportation_mode: str,
        max_distance: float,
        total_travel_time: float,
        total_stay_time: float
    ) -> Dict[str, Any]:
        """
        Format kết quả route thành dict
        
        Returns:
            Dict chứa thông tin route đầy đủ
        """
        route_places = []
        prev_pos = 0
        
        for i, place_idx in enumerate(route):
            place = places[place_idx]
            travel_time = self.calculator.calculate_travel_time(
                distance_matrix[prev_pos][place_idx + 1],
                transportation_mode
            )
            stay_time = self.calculator.get_stay_time(place.get("poi_type", ""))
            
            is_first_poi = (i == 0)
            is_last_poi = (i == len(route) - 1)
            combined_score = self.calculator.calculate_combined_score(
                place_idx=place_idx,
                current_pos=prev_pos,
                places=places,
                distance_matrix=distance_matrix,
                max_distance=max_distance,
                is_first=is_first_poi,
                is_last=is_last_poi
            )
            
            route_places.append({
                "place_id": place["id"],
                "place_name": place["name"],
                "poi_type": place.get("poi_type", ""),
                "poi_type_clean": place.get("poi_type_clean", ""),
                "main_subcategory": place.get("main_subcategory", ""),
                "specialization": place.get("specialization", ""),
                "category": place.get("category", "Unknown"),
                "address": place.get("address", ""),
                "lat": place["lat"],
                "lon": place["lon"],
                "similarity": round(place["score"], 3),
                "rating": round(float(place.get("rating") or 0.5), 3),
                "combined_score": round(combined_score, 3),
                "travel_time_minutes": round(travel_time, 1),
                "stay_time_minutes": stay_time,
                "open_hours": place.get("open_hours", [])
            })
            
            prev_pos = place_idx + 1
        
        total_score = sum(places[idx]["score"] for idx in route)
        total_time = total_travel_time + total_stay_time
        
        return {
            "route": route,
            "total_time_minutes": round(total_time, 1),
            "travel_time_minutes": round(total_travel_time, 1),
            "stay_time_minutes": round(total_stay_time, 1),
            "total_score": round(total_score, 2),
            "avg_score": round(total_score / len(route), 2),
            "efficiency": round(total_score / total_time * 100, 2),
            "places": route_places
        }
