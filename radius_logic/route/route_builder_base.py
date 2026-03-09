"""
Base Route Builder - Chứa các helper methods chung cho cả 2 mode (target và duration)

Module này định nghĩa lớp BaseRouteBuilder - một lớp cơ sở chứa tất cả các phương thức helper
được sử dụng chung bởi cả TargetRouteBuilder và DurationRouteBuilder.

Các chức năng chính:
- analyze_meal_requirements: Phân tích yêu cầu chèn Restaurant cho meal time
- select_first_poi: Chọn POI đầu tiên dựa trên combined score
- check_first_poi_meal_status: Kiểm tra POI đầu có phải Restaurant trong meal window không
- select_last_poi: Chọn POI cuối cùng gần user location
- format_route_result: Format kết quả route thành cấu trúc chuẩn

Author: Kyanon Team
Created: 2026-01
"""
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional
from utils.time_utils import TimeUtils
from .route_config import RouteConfig
from .geographic_utils import GeographicUtils
from .poi_validator import POIValidator
from .calculator import Calculator

class BaseRouteBuilder:
    """
    Lớp cơ sở chứa các phương thức helper dùng chung cho route building
    
    Class này cung cấp các tiện ích để:
    1. Phân tích meal requirements (lunch/dinner windows)
    2. Chọn POI đầu tiên với combined score cao nhất
    3. Kiểm tra xem POI đầu có phải Restaurant trong meal window không
    4. Chọn POI cuối cùng gần user để giảm thời gian về
    5. Format kết quả route thành JSON chuẩn
    
    Attributes:
        geo (GeographicUtils): Utility class cho các tính toán địa lý
        validator (POIValidator): Validator cho opening hours và POI constraints
        calculator (Calculator): Calculator cho travel time và combined score
    """
    
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
        Phân tích categories và meal requirements để xác định cần chèn Restaurant hay không
        
        Logic:
        - Nếu có Cafe & Bakery → KHÔNG chèn Restaurant (vì Cafe đã có đồ ăn nhẹ)
        - Nếu KHÔNG có Cafe nhưng có Restaurant → Kiểm tra overlap với meal time
        - Nếu overlap >= 60 phút với lunch/dinner → Cần chèn Restaurant
        
        Args:
            places: Danh sách POI candidates
            current_datetime: Thời điểm bắt đầu route (None = không validate meal time)
            max_time_minutes: Thời gian tối đa của route
            
        Returns:
            Dict chứa:
            - all_categories (List[str]): List các category unique, giữ thứ tự xuất hiện
            - should_insert_restaurant_for_meal (bool): True nếu cần ưu tiên Restaurant cho meal
            - meal_windows (Dict): {"lunch": (start, end), "dinner": (start, end)} nếu có overlap
            - need_lunch_restaurant (bool): True nếu overlap lunch >= 60 phút
            - need_dinner_restaurant (bool): True nếu overlap dinner >= 60 phút
        
        Example:
            >>> meal_info = self.analyze_meal_requirements(places, datetime(2026, 1, 22, 11, 0), 180)
            >>> print(meal_info["should_insert_restaurant_for_meal"])  # True (11:00 là lunch time)
            >>> print(meal_info["need_lunch_restaurant"])  # True
        """
        all_categories = list(dict.fromkeys(
            place.get('category') for place in places if 'category' in place
        ))
        has_cafe = "Cafe & Bakery" in all_categories
        has_restaurant = "Restaurant" in all_categories
        # Kiểm tra có "Cafe" (không phải "Cafe & Bakery") để kích hoạt cafe-sequence
        has_cafe_only = "Cafe" in all_categories
        
        should_insert_restaurant_for_meal = False
        meal_windows = None
        need_lunch_restaurant = False
        need_dinner_restaurant = False
        
        # Cafe-sequence flag: bật KHI CÓ "Cafe" (bất kể có "Cafe & Bakery" hay không)
        # "Cafe" sẽ được loại khỏi alternation và chỉ trigger qua sequence
        # "Cafe & Bakery" vẫn tham gia alternation bình thường
        should_insert_cafe = has_cafe_only
        
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
            "need_dinner_restaurant": need_dinner_restaurant,
            "should_insert_cafe": should_insert_cafe
        }
    
    def select_first_poi(
        self,
        places: List[Dict[str, Any]],
        first_place_idx: Optional[int],
        distance_matrix: List[List[float]],
        max_distance: float,
        transportation_mode: str,
        current_datetime: Optional[datetime],
        should_insert_restaurant_for_meal: bool,
        meal_windows: Optional[Dict] = None,
        should_insert_cafe: bool = False
    ) -> Tuple[Optional[int], bool]:
        """
        Chọn POI đầu tiên cho route dựa trên combined score (score + distance)
        
        Quy tắc chọn:
        1. Nếu first_place_idx được chỉ định → Dùng luôn
        2. Kiểm tra current_datetime có rơi vào meal window không:
           - Nếu ĐÃ TRONG meal time → BẮT BUỘC chọn Restaurant
           - Nếu CHƯA TỚI meal time nhưng có overlap → LOẠI Restaurant ra
           - Nếu không overlap → Bình thường
        3. Chọn POI có combined_score cao nhất trong candidates
        4. Validate opening hours nếu current_datetime được cung cấp
        
        Combined score = 0.7 × normalized_score + 0.3 × (1 - normalized_distance)
        
        Args:
            places: Danh sách POI candidates
            first_place_idx: Index của POI đầu tiên được chỉ định (None = auto select)
            distance_matrix: Ma trận khoảng cách [user_location, poi1, poi2, ...]
            max_distance: Khoảng cách lớn nhất trong matrix (để normalize)
            transportation_mode: "DRIVING", "WALKING", hoặc "BICYCLING"
            current_datetime: Thời điểm bắt đầu (None = không validate opening hours)
            should_insert_restaurant_for_meal: True = có meal requirement
            meal_windows: Dict chứa lunch/dinner windows
            
        Returns:
            Index của POI đầu tiên (0-based trong places list) hoặc None nếu không tìm thấy
            
        Note:
            - Nếu ĐÃ TRONG meal time → BẮT BUỘC chọn Restaurant
            - Nếu CHƯA TỚI meal time → LOẠI Restaurant ra (giữ cho meal time sau)
        """
        if first_place_idx is not None:
            return first_place_idx, should_insert_cafe
        
        # Kiểm tra xem current_datetime có rơi vào meal window không
        is_in_meal_time = False
        if should_insert_restaurant_for_meal and current_datetime and meal_windows:
            # Kiểm tra current_datetime có trong meal window không
            if meal_windows.get('lunch'):
                lunch_start, lunch_end = meal_windows['lunch']
                if lunch_start <= current_datetime <= lunch_end:
                    is_in_meal_time = True
                    print(f"🍽️  Current time {current_datetime.strftime('%H:%M')} ĐÃ TRONG LUNCH TIME → BẮT BUỘC chọn Restaurant đầu")
            
            if not is_in_meal_time and meal_windows.get('dinner'):
                dinner_start, dinner_end = meal_windows['dinner']
                if dinner_start <= current_datetime <= dinner_end:
                    is_in_meal_time = True
                    print(f"🍽️  Current time {current_datetime.strftime('%H:%M')} ĐÃ TRONG DINNER TIME → BẮT BUỘC chọn Restaurant đầu")
        
        best_first = None
        best_first_score = -1
        
        def is_cafe_cat(cat: Optional[str]) -> bool:
            # CHỈ "Cafe" (không bao gồm "Cafe & Bakery") mới trigger cafe-sequence
            # "Cafe & Bakery" thuộc Food & Local Flavours → xen kẽ bình thường
            return cat == "Cafe"
        
        def is_restaurant_cat(cat: Optional[str]) -> bool:
            # Category cố định từ UI: "Restaurant"
            return cat == "Restaurant"
        
        for i, place in enumerate(places):
            if current_datetime:
                travel_time = self.calculator.calculate_travel_time(
                    distance_matrix[0][i + 1],
                    transportation_mode
                )
                # validate for travl_time > 10
                if travel_time > 10 and transportation_mode == "WALKING":  
                    print(f"Travel time {travel_time} phút quá lớn → BỎ QUA {place.get('name')}")
                    continue
                arrival_time = TimeUtils.get_arrival_time(current_datetime, travel_time)
                if not self.validator.is_poi_available_at_time(place, arrival_time):
                    continue
            
            # ĐÓNG poi trong category cafe khi cafe-sequence bật: cafe chỉ chèn sau 2 POI, không được là POI đầu
            if should_insert_cafe and is_cafe_cat(place.get('category')):
                continue
            
            # Logic meal time cho POI đầu
            if should_insert_restaurant_for_meal:
                is_restaurant = is_restaurant_cat(place.get('category'))
                
                if is_in_meal_time:
                    # Đã TRONG meal time → BẮT BUỘC chọn Restaurant
                    if not is_restaurant:
                        continue  # Bỏ qua POI không phải Restaurant
                else:
                    # CHƯA TỚI meal time → LOẠI Restaurant ra
                    if is_restaurant:
                        continue  # Bỏ qua Restaurant (giữ cho meal time sau)
            
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
        
        return best_first, should_insert_cafe
    
    def check_first_poi_meal_status(
        self,
        first_poi_idx: int,
        places: List[Dict[str, Any]],
        should_insert_restaurant_for_meal: bool,
        meal_windows: Optional[Dict],
        distance_matrix: List[List[float]],
        transportation_mode: str,
        current_datetime: Optional[datetime],
        should_insert_cafe: bool = False
    ) -> Tuple[bool, bool, int, bool]:
        """
        Simplified: chỉ kiểm tra POI đầu có phải Restaurant trong meal window hay không,
        và khởi tạo cafe_counter dựa trên POI đầu + should_insert_cafe.

        Trả về: (lunch_inserted, dinner_inserted, cafe_counter, should_insert_cafe)
        """
        lunch_inserted = False
        dinner_inserted = False
        cafe_counter = 0

        if first_poi_idx is None or first_poi_idx < 0 or first_poi_idx >= len(places):
            return lunch_inserted, dinner_inserted, cafe_counter, should_insert_cafe

        first_cat = places[first_poi_idx].get("category")

        # Nếu có meal requirement và POI đầu là Restaurant với time info -> check windows
        if should_insert_restaurant_for_meal and first_cat == "Restaurant" and current_datetime and meal_windows:
            travel_time = self.calculator.calculate_travel_time(
                distance_matrix[0][first_poi_idx + 1],
                transportation_mode
            )
            arrival_first = TimeUtils.get_arrival_time(current_datetime, travel_time)

            if meal_windows.get("lunch"):
                lunch_start, lunch_end = meal_windows["lunch"]
                if lunch_start <= arrival_first <= lunch_end:
                    lunch_inserted = True

            if meal_windows.get("dinner"):
                dinner_start, dinner_end = meal_windows["dinner"]
                if dinner_start <= arrival_first <= dinner_end:
                    dinner_inserted = True

        # Khởi tạo cafe_counter (chỉ khi bật cafe-sequence)
        if should_insert_cafe:
            if first_cat in ("Restaurant", "Cafe"):
                cafe_counter = 0
            else:
                cafe_counter = 1
        else:
            cafe_counter = 0

        # Nếu cả 2 meal đã thỏa từ đầu thì disable cafe-sequence
        if lunch_inserted and dinner_inserted:
            should_insert_cafe = False

        return lunch_inserted, dinner_inserted, cafe_counter, should_insert_cafe
    
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
        Chọn POI cuối cùng gần user location để giảm thời gian về
        
        Strategy:
        1. Thử các radius threshold từ nhỏ đến lớn: [0.5, 0.75, 1.0, 1.5, 2.0] × max_radius
        2. Ở mỗi threshold, chọn POI có combined_score cao nhất
        3. Validate opening hours và time budget
        4. Loại trừ Restaurant nếu đã insert cho meal time rồi
        
        Args:
            places: Danh sách POI
            visited: Set các POI đã dùng
            current_pos: Vị trí hiện tại trong distance_matrix
            distance_matrix: Ma trận khoảng cách
            max_radius: Khoảng cách xa nhất từ user đến POI (để tính threshold)
            transportation_mode: Phương tiện di chuyển
            max_distance: Khoảng cách lớn nhất (để normalize)
            total_travel_time: Tổng travel time hiện tại
            total_stay_time: Tổng stay time hiện tại
            max_time_minutes: Time budget tối đa
            current_datetime: Thời điểm bắt đầu
            should_insert_restaurant_for_meal: True nếu có meal requirement
            meal_windows: Dict meal windows
            lunch_restaurant_inserted: True nếu đã insert lunch restaurant
            dinner_restaurant_inserted: True nếu đã insert dinner restaurant
            
        Returns:
            Index của POI cuối (0-based) hoặc None nếu không tìm thấy
            
        Note:
            - POI cuối ưu tiên gần user để giảm return_time
            - Nếu POI cuối là Restaurant và arrival rơi vào meal window đã insert → Bỏ qua
        """
        best_last = None
        best_last_score = -1
        
        radius_thresholds = RouteConfig.LAST_POI_RADIUS_THRESHOLDS
        
        for threshold_multiplier in radius_thresholds:
            current_threshold = threshold_multiplier * max_radius
            print(f"\n{'='*100}")
            print(f"🔍 LAST POI SEARCH @ Threshold {threshold_multiplier*100:.0f}% = {current_threshold:.3f}km")
            print(f"{'='*100}")
            
            for i, place in enumerate(places):
                reasons = []

                travel_time = self.calculator.calculate_travel_time(
                    distance_matrix[current_pos][i + 1],
                    transportation_mode
                )
                # validate for travl_time > 10 
                if travel_time > 10 and transportation_mode == "WALKING":  
                    print(f"Travel time {travel_time} phút quá lớn → BỎ QUA {place.get('name')}")
                    continue
                
                if i in visited:
                    reasons.append("visited")
                
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
                            reasons.append("lunch_already_inserted")
                        if in_dinner and dinner_restaurant_inserted:
                            reasons.append("dinner_already_inserted")
                        if not in_lunch and not in_dinner:
                            reasons.append("not_meal_time")
                
                # Kiểm tra khoảng cách đến user
                dist_to_user = distance_matrix[i + 1][0]
                if dist_to_user > current_threshold:
                    reasons.append(f"far({dist_to_user:.3f}>{current_threshold:.3f})")
                
                # Kiểm tra availability
                arrival_time = None
                if current_datetime:
                    travel_time_to_poi = self.calculator.calculate_travel_time(
                        distance_matrix[current_pos][i + 1],
                        transportation_mode
                    )
                    arrival_time = current_datetime + timedelta(
                        minutes=total_travel_time + total_stay_time + travel_time_to_poi
                    )
                    if not self.validator.is_poi_available_at_time(place, arrival_time):
                        reasons.append(f"closed@{arrival_time.strftime('%H:%M')}")
                
                # Kiểm tra thời gian khả thi
                temp_travel = total_travel_time + self.calculator.calculate_travel_time(
                    distance_matrix[current_pos][i + 1],
                    transportation_mode
                )
                temp_stay = total_stay_time + self.calculator.get_stay_time(
                    places[i].get("poi_type", ""),
                    places[i].get("stay_time")
                )
                return_time = self.calculator.calculate_travel_time(
                    dist_to_user, transportation_mode
                )
                total_time = temp_travel + temp_stay + return_time
                
                if total_time > max_time_minutes:
                    reasons.append(f"time({total_time:.1f}>{max_time_minutes})")
                
                # Tính combined score nếu valid
                combined = 0.0
                if not reasons:
                    combined = self.calculator.calculate_combined_score(
                        place_idx=i,
                        current_pos=current_pos,
                        places=places,
                        distance_matrix=distance_matrix,
                        max_distance=max_distance,
                        is_last=True
                    )
                
                # In tất cả POI
                status = "❌" if reasons else "✅"
                print(
                    f"{status} [{i:2d}] {place.get('name')[:45]:45s} | "
                    f"dist={dist_to_user:.3f} | rate={place.get('rating',0):.3f} | "
                    f"sim={place.get('score',0):.3f} | comb={combined:.4f} | "
                    f"{','.join(reasons) if reasons else 'OK'}"
                )
                
                if reasons:
                    continue
                
                if combined > best_last_score or (
                    combined == best_last_score and (best_last is None or i < best_last)
                ):
                    best_last_score = combined
                    best_last = i
                    print(f"    ⭐ NEW BEST (combined={combined:.4f})")
            
            if best_last is not None:
                print(f"\n🎯 Chọn POI cuối: [{best_last}] {places[best_last].get('name')} (threshold={threshold_multiplier*100:.0f}%)")
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
        Format route thành cấu trúc JSON chuẩn để trả về cho client
        
        Tính toán và bổ sung thông tin cho mỗi POI:
        - travel_time: Thời gian di chuyển từ POI trước
        - stay_time: Thời gian lưu trú tại POI
        - combined_score: Score kết hợp giữa similarity và distance
        
        Args:
            route: List các index POI trong route (0-based)
            places: Danh sách POI gốc
            distance_matrix: Ma trận khoảng cách
            transportation_mode: Phương tiện di chuyển
            max_distance: Khoảng cách lớn nhất (để normalize score)
            total_travel_time: Tổng thời gian di chuyển
            total_stay_time: Tổng thời gian lưu trú
            
        Returns:
            Dict chứa:
            - route: List index POI
            - total_time_minutes: Tổng thời gian (travel + stay)
            - travel_time_minutes: Tổng travel time
            - stay_time_minutes: Tổng stay time
            - total_score: Tổng similarity score
            - avg_score: Average similarity score
            - efficiency: (total_score / total_time) × 100
            - places: List POI đầy đủ thông tin (place_id, name, category, travel_time, etc.)
        """
        route_places = []
        prev_pos = 0
        
        for i, place_idx in enumerate(route):
            place = places[place_idx]
            travel_time = self.calculator.calculate_travel_time(
                distance_matrix[prev_pos][place_idx + 1],
                transportation_mode
            )
            stay_time = self.calculator.get_stay_time(
                place.get("poi_type", ""),
                place.get("stay_time")
            )
            
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

        # import json
        # with open("result1.json", "w", encoding="utf-8") as f:
        #     json.dump(route_places, f, ensure_ascii=False, indent=4)

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
