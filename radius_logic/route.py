"""
Route Builder Service
Xây dựng lộ trình tối ưu từ danh sách địa điểm sử dụng thuật toán Greedy
"""
import asyncio
import functools
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional
from utils.time_utils import TimeUtils
from .route.route_config import RouteConfig
from .route.geographic_utils import GeographicUtils
from .route.poi_validator import POIValidator
from .route.score_calculator import ScoreCalculator

class RouteBuilder:
    """
    Class xây dựng lộ trình tối ưu sử dụng thuật toán Greedy với weighted scoring
    
    Thuật toán:
    1. Chọn điểm xuất phát có combined_score cao nhất từ vị trí user
    2. Chọn các điểm tiếp theo có combined_score cao nhất từ vị trí hiện tại
    3. Điểm cuối phải gần user (< 20% max_distance) và có điểm cao
    
    Combined score = 0.7 × normalized_score + 0.3 × (1 - normalized_distance)
    """
    
    # Thời gian tham quan cố định cho tất cả địa điểm (phút)
    DEFAULT_STAY_TIME = RouteConfig.DEFAULT_STAY_TIME
    
    
    def __init__(self):
        """Khởi tạo RouteBuilder"""
        self.geo = GeographicUtils()
        self.validator = POIValidator()
        self.scorer = ScoreCalculator(self.geo)
        
    
    def calculate_travel_time(self, distance_km: float, transportation_mode: str) -> float:
        """
        Tính thời gian di chuyển (phút)
        
        Args:
            distance_km: Khoảng cách (km)
            transportation_mode: Phương tiện
            
        Returns:
            Thời gian (phút)
        """
        speed = RouteConfig.TRANSPORTATION_SPEEDS.get(transportation_mode.upper(), 30)
        return (distance_km / speed) * 60  # Chuyển giờ sang phút
    
    def get_stay_time(self, poi_type: str) -> int:
        """
        Lấy thời gian tham quan cố định (phút)
        
        Args:
            poi_type: Loại POI (không sử dụng)
            
        Returns:
            Thời gian tham quan cố định 30 phút
        """
        return self.DEFAULT_STAY_TIME
    
    
    def build_single_route_greedy(
        self,
        user_location: Tuple[float, float],
        places: List[Dict[str, Any]],
        transportation_mode: str,
        max_time_minutes: int,
        target_places: int,
        first_place_idx: Optional[int] = None,
        current_datetime: Optional[datetime] = None,
        distance_matrix: Optional[List[List[float]]] = None,
        max_distance: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Xây dựng 1 lộ trình theo thuật toán Greedy
        
        Args:
            user_location: (lat, lon) của user
            places: Danh sách địa điểm (mỗi place có: id, name, score, lat, lon, poi_type)
            transportation_mode: Phương tiện di chuyển
            max_time_minutes: Thời gian tối đa (phút)
            target_places: Số địa điểm muốn đi
            first_place_idx: Index điểm xuất phát (None = tự động chọn)
            current_datetime: Thời điểm hiện tại của user (để kiểm tra opening hours)
            distance_matrix: Ma trận khoảng cách (tính sẵn để tránh tính lại)
            max_distance: Khoảng cách tối đa (tính sẵn để tránh tính lại)
            
        Returns:
            Dict chứa thông tin lộ trình hoặc None nếu không khả thi
        """
        if target_places > len(places):
            return None
        
        # 1. Xây dựng distance matrix (nếu chưa có)
        if distance_matrix is None:
            distance_matrix = self.geo.build_distance_matrix(user_location, places)
        
        # Tìm max distance để normalize (nếu chưa có)
        if max_distance is None:
            max_distance = max(max(row) for row in distance_matrix)
        
        # Tính radius (khoảng cách xa nhất từ user)
        max_radius = max(distance_matrix[0][1:])
        
        # 🔧 TÍNH TRƯỚC: Category analysis và meal logic (để tránh NameError khi dùng sau)
        # Lấy danh sách tất cả category có trong places (GIỮ THỨ TỰ xuất hiện)
        all_categories = list(dict.fromkeys(place.get('category') for place in places if 'category' in place))
        has_cafe = "Cafe & Bakery" in all_categories
        has_restaurant = "Restaurant" in all_categories
        
        # Xác định có cần chèn Restaurant cho meal time không
        should_insert_restaurant_for_meal = False
        meal_windows = None
        
        if not has_cafe and has_restaurant:
            # Không có Cafe nhưng có Restaurant → Chắc chắn do overlap meal time
            if current_datetime and max_time_minutes:
                meal_check = TimeUtils.check_overlap_with_meal_times(current_datetime, max_time_minutes)
                if meal_check["needs_restaurant"]:
                    should_insert_restaurant_for_meal = True
                    meal_windows = {
                        "lunch": meal_check.get("lunch_window"),
                        "dinner": meal_check.get("dinner_window")
                    }
                    print(f"🍽️  Không có Cafe & Bakery nhưng có Restaurant → Chèn ĐÚNG 1 Restaurant vào meal time")
        
        # 2. Chọn điểm đầu tiên
        route = []
        visited = set()
        current_pos = 0  # Bắt đầu từ user
        total_travel_time = 0
        total_stay_time = 0
        
        if first_place_idx is not None:
            best_first = first_place_idx
        else:
            # Tính combined score cho tất cả địa điểm từ user
            best_first = None
            best_first_score = -1
            
            for i, place in enumerate(places):
                # Nếu có current_datetime, kiểm tra opening_hours trước
                if current_datetime:
                    travel_time = self.calculate_travel_time(
                        distance_matrix[0][i + 1],
                        transportation_mode
                    )
                    arrival_time = TimeUtils.get_arrival_time(current_datetime, travel_time)
                    
                    # Bỏ qua POI nếu không đủ thời gian stay
                    if not self.validator.is_poi_available_at_time(place, arrival_time):
                        continue
                
                # Loại bỏ Restaurant khỏi POI đầu nếu đang trong chế độ chèn cho meal
                # (Không có Cafe & Bakery nhưng có Restaurant)
                if should_insert_restaurant_for_meal and place.get('category') == 'Restaurant':
                    continue
                
                combined = self.scorer.calculate_combined_score(
                    place_idx=i,
                    current_pos=0,
                    places=places,
                    distance_matrix=distance_matrix,
                    max_distance=max_distance,
                    is_first=True
                )
                if combined > best_first_score:
                    best_first_score = combined
                    best_first = i
        
        if best_first is None:
            return None
        
        # Thêm điểm đầu tiên
        route.append(best_first)
        visited.add(best_first)
        travel_time = self.calculate_travel_time(
            distance_matrix[0][best_first + 1],
            transportation_mode
        )
        stay_time = self.get_stay_time(places[best_first].get("poi_type", ""))
        total_travel_time += travel_time
        total_stay_time += stay_time
        current_pos = best_first + 1
        
        # Tính bearing từ user đến POI đầu (để dùng cho POI thứ 2)
        prev_bearing = self.geo.calculate_bearing(
            user_location[0], user_location[1],
            places[best_first]["lat"], places[best_first]["lon"]
        )
        
        # 3. Chọn các điểm tiếp theo (trừ điểm cuối) - BẮT BUỘC XEN KẼ CATEGORY
        # Track thứ tự category đã dùng
        category_sequence = []
        if 'category' in places[best_first]:
            category_sequence.append(places[best_first].get('category'))
        
        # ⚠️ KIỂM TRA: Nếu POI đầu tiên là Restaurant và đang trong chế độ meal → Đánh dấu đã chèn
        restaurant_inserted_for_meal = False
        if should_insert_restaurant_for_meal and places[best_first].get('category') == 'Restaurant':
            restaurant_inserted_for_meal = True
            print(f"✅ POI đầu đã là Restaurant → Không chọn Restaurant nữa cho các POI sau")
        
        # target_places là số POI cần đi (không tính user)
        # Đã có 1 POI đầu, cần chọn (target_places - 2) POI giữa, và 1 POI cuối
        for step in range(target_places - 2):
            best_next = None
            best_next_score = -1
            
            # 🍽️ MEAL TIME PRIORITY: Kiểm tra xem có cần ưu tiên Restaurant không
            # CHỈ ưu tiên nếu CHƯA chèn Restaurant cho meal
            arrival_at_next = None
            if current_datetime:
                arrival_at_next = current_datetime + timedelta(minutes=total_travel_time + total_stay_time)
            
            should_prioritize_restaurant = False
            if meal_windows and arrival_at_next and not restaurant_inserted_for_meal:
                # Kiểm tra xem arrival time có nằm trong meal window không
                for meal_type, window in meal_windows.items():
                    if window:
                        meal_start, meal_end = window
                        # Nếu đến trong khoảng meal time, ưu tiên Restaurant
                        if meal_start <= arrival_at_next <= meal_end:
                            should_prioritize_restaurant = True
                            print(f"🍽️  Ưu tiên Restaurant vì đến lúc {arrival_at_next.strftime('%H:%M')} (trong {meal_type} window)")
                            break
            
            # Xác định category BẮT BUỘC cho POI tiếp theo
            required_category = None
            # Mặc định loại Restaurant nếu đang trong chế độ chèn cho meal
            exclude_restaurant = should_insert_restaurant_for_meal
            
            # Nếu cần ưu tiên Restaurant (chưa chèn cho meal), bắt buộc chọn Restaurant
            if should_prioritize_restaurant:
                # Kiểm tra xem có Restaurant trong places không
                has_restaurant_available = any(p.get('category') == 'Restaurant' and i not in visited for i, p in enumerate(places))
                if has_restaurant_available:
                    required_category = 'Restaurant'
                    restaurant_inserted_for_meal = True  # Đánh dấu đã chèn Restaurant
                    exclude_restaurant = False  # Cho phép chọn Restaurant cho bước này
                    print(f"   → BẮT BUỘC chọn Restaurant cho bước này (chỉ 1 lần)")
            # Nếu đã chèn Restaurant cho meal rồi, tiếp tục loại bỏ Restaurant
            elif should_insert_restaurant_for_meal and restaurant_inserted_for_meal:
                exclude_restaurant = True
                print(f"   → Đã chèn Restaurant cho meal, chỉ chọn từ category ban đầu")
            
            # Nếu không ưu tiên Restaurant, áp dụng logic xen kẽ category bình thường
            if required_category is None and category_sequence and all_categories:
                # Lấy category của POI vừa thêm
                last_category = category_sequence[-1]
                # Tìm index của category hiện tại trong danh sách
                try:
                    current_idx = all_categories.index(last_category)
                    # Chọn category tiếp theo (tuần hoàn)
                    next_idx = (current_idx + 1) % len(all_categories)
                    required_category = all_categories[next_idx]
                except ValueError:
                    # Nếu không tìm thấy, lấy category đầu tiên
                    required_category = all_categories[0] if all_categories else None
            
            # Lần 1: Tìm POI với category BẮT BUỘC
            candidates_with_required_category = []
            # Lấy POI vừa thêm để so sánh 3 level
            last_added_place = places[route[-1]] if route else None
            
            for i, place in enumerate(places):
                if i in visited:
                    continue
                
                # Loại bỏ Restaurant nếu đã chèn cho meal
                if exclude_restaurant and place.get('category') == 'Restaurant':
                    continue
                
                # Chỉ xét POI có đúng category yêu cầu
                if required_category and place.get('category') != required_category:
                    continue
                
                # Kiểm tra 3 level nếu cả 2 POI đều là food category
                if last_added_place and self.validator.is_same_food_type(last_added_place, place):
                    continue  # Bỏ qua POI này vì giống hệt 3 level với POI trước
                
                # Nếu có current_datetime, kiểm tra opening_hours
                if current_datetime:
                    travel_time_to_poi = self.calculate_travel_time(
                        distance_matrix[current_pos][i + 1],
                        transportation_mode
                    )
                    arrival_time = current_datetime + timedelta(minutes=total_travel_time + total_stay_time + travel_time_to_poi)
                    
                    # Bỏ qua POI nếu không đủ thời gian stay
                    if not self.validator.is_poi_available_at_time(place, arrival_time):
                        continue
                
                combined = self.scorer.calculate_combined_score(
                    place_idx=i,
                    current_pos=current_pos,
                    places=places,
                    distance_matrix=distance_matrix,
                    max_distance=max_distance,
                    prev_bearing=prev_bearing,
                    user_location=user_location
                )
                
                # Kiểm tra thời gian khả thi
                temp_travel = total_travel_time + self.calculate_travel_time(
                    distance_matrix[current_pos][i + 1],
                    transportation_mode
                )
                temp_stay = total_stay_time + self.get_stay_time(places[i].get("poi_type", ""))
                estimated_return = self.calculate_travel_time(
                    distance_matrix[i + 1][0],
                    transportation_mode
                )
                
                if temp_travel + temp_stay + estimated_return > max_time_minutes:
                    continue
                
                candidates_with_required_category.append((i, combined))
            
            # Chọn POI tốt nhất trong category yêu cầu
            if candidates_with_required_category:
                candidates_with_required_category.sort(key=lambda x: x[1], reverse=True)
                best_next = candidates_with_required_category[0][0]
                best_next_score = candidates_with_required_category[0][1]
            
            # Lần 2: Nếu không tìm thấy POI với category yêu cầu, xét tất cả POI còn lại
            if best_next is None:
                for i, place in enumerate(places):
                    if i in visited:
                        continue
                    
                    # Loại bỏ Restaurant nếu đã chèn cho meal
                    if exclude_restaurant and place.get('category') == 'Restaurant':
                        continue
                    
                    # Kiểm tra 3 level nếu cả 2 POI đều là food category
                    if last_added_place and self.validator.is_same_food_type(last_added_place, place):
                        continue  # Bỏ qua POI này vì giống hệt 3 level với POI trước
                    
                    # Nếu có current_datetime, kiểm tra opening_hours
                    if current_datetime:
                        travel_time_to_poi = self.calculate_travel_time(
                            distance_matrix[current_pos][i + 1],
                            transportation_mode
                        )
                        arrival_time = current_datetime + timedelta(minutes=total_travel_time + total_stay_time + travel_time_to_poi)
                        
                        # Bỏ qua POI nếu không đủ thời gian stay
                        if not self.validator.is_poi_available_at_time(place, arrival_time):
                            continue
                    
                    combined = self.scorer.calculate_combined_score(
                        place_idx=i,
                        current_pos=current_pos,
                        places=places,
                        distance_matrix=distance_matrix,
                        max_distance=max_distance,
                        prev_bearing=prev_bearing,
                        user_location=user_location
                    )
                    
                    # Kiểm tra thời gian khả thi
                    temp_travel = total_travel_time + self.calculate_travel_time(
                        distance_matrix[current_pos][i + 1],
                        transportation_mode
                    )
                    temp_stay = total_stay_time + self.get_stay_time(places[i].get("poi_type", ""))
                    estimated_return = self.calculate_travel_time(
                        distance_matrix[i + 1][0],
                        transportation_mode
                    )
                    
                    if temp_travel + temp_stay + estimated_return > max_time_minutes:
                        continue
                    
                    if combined > best_next_score:
                        best_next_score = combined
                        best_next = i
            
            if best_next is None:
                break
            
            # Thêm điểm tiếp theo
            route.append(best_next)
            visited.add(best_next)
            if 'category' in places[best_next]:
                category_sequence.append(places[best_next].get('category'))
            
            travel_time = self.calculate_travel_time(
                distance_matrix[current_pos][best_next + 1],
                transportation_mode
            )
            stay_time = self.get_stay_time(places[best_next].get("poi_type", ""))
            total_travel_time += travel_time
            total_stay_time += stay_time
            
            # Cập nhật bearing cho bước tiếp theo
            prev_place = places[route[-2]] if len(route) >= 2 else None
            current_place = places[best_next]
            if prev_place:
                prev_bearing = self.geo.calculate_bearing(
                    prev_place["lat"], prev_place["lon"],
                    current_place["lat"], current_place["lon"]
                )
            else:
                # Nếu chỉ có 1 POI trước đó, tính từ user
                prev_bearing = self.geo.calculate_bearing(
                    user_location[0], user_location[1],
                    current_place["lat"], current_place["lon"]
                )
            
            current_pos = best_next + 1
        
        # 4. Chọn điểm cuối (gần user) - với tăng dần bán kính nếu không tìm thấy
        best_last = None
        best_last_score = -1
        
        # Thử các mức bán kính: 30%, 50%, 70%, 90%, 110%, 130%
        radius_thresholds = RouteConfig.LAST_POI_RADIUS_THRESHOLDS
        
        for threshold_multiplier in radius_thresholds:
            current_threshold = threshold_multiplier * max_radius
            
            for i, place in enumerate(places):
                if i in visited:
                    continue
                
                # 🍽️ Logic lọc Restaurant cho POI cuối
                if should_insert_restaurant_for_meal and place.get('category') == 'Restaurant':
                    # Nếu đã chèn Restaurant rồi → Loại bỏ
                    if restaurant_inserted_for_meal:
                        continue
                    
                    # Nếu chưa chèn Restaurant → Chỉ cho phép nếu arrival time nằm trong meal window
                    if current_datetime and meal_windows:
                        travel_time_to_last = self.calculate_travel_time(
                            distance_matrix[current_pos][i + 1],
                            transportation_mode
                        )
                        arrival_at_last = current_datetime + timedelta(minutes=total_travel_time + total_stay_time + travel_time_to_last)
                        
                        # Kiểm tra xem có nằm trong meal window không
                        in_meal_window = False
                        for meal_type, window in meal_windows.items():
                            if window:
                                meal_start, meal_end = window
                                if meal_start <= arrival_at_last <= meal_end:
                                    in_meal_window = True
                                    break
                        
                        # Nếu KHÔNG nằm trong meal window → Loại bỏ Restaurant
                        if not in_meal_window:
                            continue
                
                # Kiểm tra khoảng cách đến user
                dist_to_user = distance_matrix[i + 1][0]
                if dist_to_user > current_threshold:
                    continue
                
                # Nếu có current_datetime, kiểm tra opening_hours
                if current_datetime:
                    travel_time_to_poi = self.calculate_travel_time(
                        distance_matrix[current_pos][i + 1],
                        transportation_mode
                    )
                    arrival_time = current_datetime + timedelta(minutes=total_travel_time + total_stay_time + travel_time_to_poi)
                    
                    # Bỏ qua POI nếu không đủ thời gian stay
                    if not self.validator.is_poi_available_at_time(place, arrival_time):
                        continue
                
                # Kiểm tra thời gian
                temp_travel = total_travel_time + self.calculate_travel_time(
                    distance_matrix[current_pos][i + 1],
                    transportation_mode
                )
                temp_stay = total_stay_time + self.get_stay_time(places[i].get("poi_type", ""))
                return_time = self.calculate_travel_time(dist_to_user, transportation_mode)
                
                if temp_travel + temp_stay + return_time > max_time_minutes:
                    continue
                
                # POI cuối: ưu tiên gần user
                combined = self.scorer.calculate_combined_score(
                    place_idx=i,
                    current_pos=current_pos,
                    places=places,
                    distance_matrix=distance_matrix,
                    max_distance=max_distance,
                    is_last=True
                )
                
                if combined > best_last_score:
                    best_last_score = combined
                    best_last = i
            
            # Nếu tìm được POI cuối, dừng lại
            if best_last is not None:
                print(f"🎯 Tìm được POI cuối ở mức {threshold_multiplier*100:.0f}% bán kính ({current_threshold:.0f}km)")
                break
    
        # Thêm POI cuối
        if best_last is not None:
            route.append(best_last)
            visited.add(best_last)
            travel_time = self.calculate_travel_time(
                distance_matrix[current_pos][best_last + 1],
                transportation_mode
            )
            stay_time = self.get_stay_time(places[best_last].get("poi_type", ""))
            total_travel_time += travel_time
            total_stay_time += stay_time
            current_pos = best_last + 1
        
        # 5. Thêm thời gian quay về user
        return_time = self.calculate_travel_time(
            distance_matrix[current_pos][0],
            transportation_mode
        )
        total_travel_time += return_time
        
        total_time = total_travel_time + total_stay_time
        
        if total_time > max_time_minutes:
            return None
        
        # 6. Format kết quả
        route_places = []
        prev_pos = 0
        
        for i, place_idx in enumerate(route):
            place = places[place_idx]
            travel_time = self.calculate_travel_time(
                distance_matrix[prev_pos][place_idx + 1],
                transportation_mode
            )
            stay_time = self.get_stay_time(place.get("poi_type", ""))
            
            # Tính combined score cho POI này
            is_first_poi = (i == 0)
            is_last_poi = (i == len(route) - 1)
            combined_score = self.scorer.calculate_combined_score(
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
        
        # Tính tổng score
        total_score = sum(places[idx]["score"] for idx in route)
        
        return {
            "route": route,  # Danh sách index (dùng nội bộ)
            "total_time_minutes": round(total_time, 1),
            "travel_time_minutes": round(total_travel_time, 1),
            "stay_time_minutes": round(total_stay_time, 1),
            "total_score": round(total_score, 2),
            "avg_score": round(total_score / len(route), 2),
            "efficiency": round(total_score / total_time * 100, 2),
            "places": route_places
        }
    
    def build_routes(
        self,
        user_location: Tuple[float, float],
        places: List[Dict[str, Any]],
        transportation_mode: str,
        max_time_minutes: int,
        target_places: int = 5,
        max_routes: int = 3,
        current_datetime: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Xây dựng nhiều lộ trình (top 3) bằng cách thử các điểm xuất phát khác nhau
        
        Args:
            user_location: (lat, lon) của user
            places: Danh sách địa điểm từ Qdrant (top 10)
            transportation_mode: Phương tiện
            max_time_minutes: Thời gian tối đa
            target_places: Số địa điểm mỗi lộ trình
            max_routes: Số lộ trình tối đa (mặc định 3)
            current_datetime: Thời điểm bắt đầu route (để validate opening hours)
            
        Returns:
            List các lộ trình tốt nhất (đã loại bỏ trùng lặp và validate thời gian mở cửa)
        """
        if not places:
            return []
        
        if target_places > len(places):
            target_places = len(places)
        
        # Xây dựng distance matrix 1 lần
        distance_matrix = self.geo.build_distance_matrix(user_location, places)
        max_distance = max(max(row) for row in distance_matrix)
        
        # Kiểm tra categories có trong places (GIỮ THỨ TỰ xuất hiện)
        all_categories = list(dict.fromkeys(place.get('category') for place in places if 'category' in place))
        has_cafe = "Cafe & Bakery" in all_categories
        has_restaurant = "Restaurant" in all_categories
        
        # Nếu không có Cafe nhưng có Restaurant → Đang ở chế độ chèn cho meal
        should_insert_restaurant_for_meal = (not has_cafe and has_restaurant)
        
        # Tìm top điểm xuất phát có combined_score cao nhất
        first_candidates = []
        for i, place in enumerate(places):
            # Nếu có current_datetime, kiểm tra opening_hours trước
            if current_datetime:
                travel_time = self.calculate_travel_time(
                    distance_matrix[0][i + 1],
                    transportation_mode
                )
                arrival_time = TimeUtils.get_arrival_time(current_datetime, travel_time)
                
                # Bỏ qua POI nếu không đủ thời gian stay
                if not self.validator.is_poi_available_at_time(place, arrival_time):
                    continue
            
            # Loại bỏ Restaurant nếu đang trong chế độ chèn cho meal (Restaurant sẽ chỉ được chèn vào meal time)
            if should_insert_restaurant_for_meal and place.get('category') == 'Restaurant':
                continue
            
            combined = self.scorer.calculate_combined_score(
                place_idx=i,
                current_pos=0,
                places=places,
                distance_matrix=distance_matrix,
                max_distance=max_distance
            )
            first_candidates.append((i, combined, place.get('category')))
        
        # Nếu không có POI nào mở cửa, return []
        if not first_candidates:
            print("⚠️ Không có POI nào mở cửa tại thời điểm hiện tại")
            return []
        
        first_candidates.sort(key=lambda x: x[1], reverse=True)
        
        # 🍽️ Kiểm tra xem có cần ưu tiên Restaurant cho POI đầu tiên không
        # CHỈ ưu tiên khi: Đang trong chế độ chèn cho meal VÀ có overlap meal time
        should_prioritize_restaurant_first = False
        
        if should_insert_restaurant_for_meal and current_datetime and max_time_minutes:
            meal_check = TimeUtils.check_overlap_with_meal_times(current_datetime, max_time_minutes)
            if meal_check["needs_restaurant"]:
                # Tính thời gian đến POI đầu tiên (candidate có score cao nhất)
                if first_candidates:
                    first_idx = first_candidates[0][0]
                    travel_time = self.calculate_travel_time(
                        distance_matrix[0][first_idx + 1],
                        transportation_mode
                    )
                    arrival_at_first = TimeUtils.get_arrival_time(current_datetime, travel_time)
                    
                    # Kiểm tra xem arrival time có trong meal window không
                    for meal_type, window in [("lunch", meal_check.get("lunch_window")), ("dinner", meal_check.get("dinner_window"))]:
                        if window:
                            meal_start, meal_end = window
                            if meal_start <= arrival_at_first <= meal_end:
                                should_prioritize_restaurant_first = True
                                print(f"🍽️  Đến POI đầu lúc {arrival_at_first.strftime('%H:%M')} (trong {meal_type}) → Ưu tiên Restaurant")
                                break
        
        # Lấy địa điểm có score cao nhất làm điểm đầu tiên BẮT BUỘC
        # NHƯNG: Nếu cần ưu tiên Restaurant, BẮT BUỘC chọn Restaurant đầu tiên
        best_first_place = None
        
        if should_prioritize_restaurant_first:
            # ⚠️ BUG FIX: Tìm Restaurant trực tiếp trong places (không dùng first_candidates đã lọc bỏ Restaurant)
            restaurant_candidates = []
            for i, place in enumerate(places):
                if place.get('category') != 'Restaurant':
                    continue
                
                # Kiểm tra opening hours
                if current_datetime:
                    travel_time = self.calculate_travel_time(
                        distance_matrix[0][i + 1],
                        transportation_mode
                    )
                    arrival_time = TimeUtils.get_arrival_time(current_datetime, travel_time)
                    
                    if not self.validator.is_poi_available_at_time(place, arrival_time):
                        continue
                
                # Tính combined score
                combined = self.scorer.calculate_combined_score(
                    place_idx=i,
                    current_pos=0,
                    places=places,
                    distance_matrix=distance_matrix,
                    max_distance=max_distance,
                    is_first=True
                )
                restaurant_candidates.append((i, combined))
            
            # Sắp xếp theo score và chọn Restaurant cao nhất
            if restaurant_candidates:
                restaurant_candidates.sort(key=lambda x: x[1], reverse=True)
                best_first_place = restaurant_candidates[0][0]
                print(f"🍽️  BẮT BUỘC chọn 'Restaurant' đầu tiên: {places[best_first_place]['name']} (score={places[best_first_place]['score']:.3f})")
            else:
                best_first_place = first_candidates[0][0]
                print(f"⚠️ Không có Restaurant mở cửa, chọn POI cao nhất: {places[best_first_place]['name']}")
        else:
            # Trường hợp bình thường: chọn POI có score cao nhất
            best_first_place = first_candidates[0][0]
            print(f"🎯 Điểm đầu tiên BẮT BUỘC (score cao nhất): {places[best_first_place]['name']} (score={places[best_first_place]['score']:.3f})")
        
        # Xây dựng route đầu tiên từ điểm có score cao nhất
        route_1 = self.build_single_route_greedy(
            user_location=user_location,
            places=places,
            transportation_mode=transportation_mode,
            max_time_minutes=max_time_minutes,
            target_places=target_places,
            first_place_idx=best_first_place,
            current_datetime=current_datetime,
            distance_matrix=distance_matrix,
            max_distance=max_distance
        )
        
        if route_1 is None:
            return []
        
        all_routes = [route_1]
        seen_place_sets = {tuple(sorted(route_1["route"]))}
        
        # Nếu cần nhiều hơn 1 route, thử các điểm xuất phát khác
        if max_routes > 1:
            # Thử các điểm xuất phát khác (vẫn ưu tiên score cao)
            num_candidates_to_try = min(len(places), max(10, max_routes * 3))
            
            for first_idx, _, _ in first_candidates[1:num_candidates_to_try]:
                # Dừng nếu đã đủ số routes
                if len(all_routes) >= max_routes:
                    break
                
                route_result = self.build_single_route_greedy(
                    user_location=user_location,
                    places=places,
                    transportation_mode=transportation_mode,
                    max_time_minutes=max_time_minutes,
                    target_places=target_places,
                    first_place_idx=first_idx,
                    current_datetime=current_datetime,
                    distance_matrix=distance_matrix,
                    max_distance=max_distance
                )
                
                if route_result is None:
                    continue
                
                # Tạo key duy nhất cho tập địa điểm
                place_set_key = tuple(sorted(route_result["route"]))
                
                # Bỏ qua nếu trùng
                if place_set_key in seen_place_sets:
                    continue
                
                seen_place_sets.add(place_set_key)
                all_routes.append(route_result)
        
        # Sắp xếp theo total_score (route 1 luôn ở đầu vì có điểm xuất phát tốt nhất)
        # Nhưng các route còn lại sắp xếp theo score
        if len(all_routes) > 1:
            first_route = all_routes[0]
            other_routes = sorted(all_routes[1:], key=lambda x: x["total_score"], reverse=True)
            all_routes = [first_route] + other_routes
        
        # Format kết quả cuối cùng với route_id và order
        result = []
        for idx, route in enumerate(all_routes, 1):
            # Thêm route_id và order (số thứ tự di chuyển) vào mỗi place
            places_with_metadata = []
            current_time_in_route = current_datetime  # Track thời gian trong route
            
            for order, place in enumerate(route["places"], 1):
                place_data = place.copy()
                # place_data["route_id"] = idx
                
                # Thêm opening hours info nếu có current_datetime
                if current_datetime:
                    # Tính thời gian đến POI này
                    if order == 1:
                        # POI đầu tiên: travel time từ user
                        travel_time = place_data.get("travel_time_minutes", 0)
                        arrival_time = TimeUtils.get_arrival_time(current_datetime, travel_time)
                    else:
                        # POI tiếp theo: cộng dồn travel + stay time
                        prev_place = route["places"][order - 2]
                        travel_time = place_data.get("travel_time_minutes", 0)
                        stay_time = prev_place.get("stay_time_minutes", self.DEFAULT_STAY_TIME)
                        current_time_in_route = TimeUtils.get_arrival_time(
                            current_time_in_route, 
                            stay_time
                        )
                        arrival_time = TimeUtils.get_arrival_time(
                            current_time_in_route, 
                            travel_time
                        )
                    
                    # Lấy opening hours cho ngày đó
                    opening_hours_today = TimeUtils.get_opening_hours_for_day(
                        place_data.get("open_hours", []),
                        arrival_time
                    )
                    
                    # Thêm vào response
                    place_data["arrival_time"] = arrival_time.strftime('%Y-%m-%d %H:%M:%S')
                    place_data["opening_hours_today"] = opening_hours_today
                    place_data["order"] = order  # Số thứ tự di chuyển (1, 2, 3, ...)

                    # Update current time cho POI tiếp theo
                    current_time_in_route = arrival_time
                
                places_with_metadata.append(place_data)
            
            route_data = {
                "route_id": idx,
                "total_time_minutes": route["total_time_minutes"],
                "travel_time_minutes": route["travel_time_minutes"],
                "stay_time_minutes": route["stay_time_minutes"],
                "total_score": route["total_score"],
                "avg_score": route["avg_score"],
                "efficiency": route["efficiency"],
                "places": places_with_metadata
            }
            
            result.append(route_data)
        
        return result
    
    async def build_routes_async(
        self,
        user_location: Tuple[float, float],
        places: List[Dict[str, Any]],
        transportation_mode: str,
        max_time_minutes: int,
        target_places: int = 5,
        max_routes: int = 3,
        current_datetime: Optional[datetime] = None,
        executor: Optional[ProcessPoolExecutor] = None
    ) -> List[Dict[str, Any]]:
        """
        Async wrapper: offload build_routes sang ProcessPoolExecutor để không block event loop
        
        Args:
            user_location: Tọa độ user (lat, lon)
            places: Danh sách địa điểm
            transportation_mode: Phương tiện di chuyển
            max_time_minutes: Thời gian tối đa (phút)
            target_places: Số lượng địa điểm trong mỗi route
            max_routes: Số lượng routes tối đa
            current_datetime: Thời điểm hiện tại của user
            executor: ProcessPoolExecutor (None = dùng default threadpool)
            
        Returns:
            List các routes tối ưu
            
        Note:
            - Dùng ProcessPoolExecutor cho CPU-intensive greedy algorithm
            - Nếu không truyền executor, sẽ dùng default threadpool (tốt cho quick tests)
            - Production nên tạo ProcessPoolExecutor pool và reuse
        """
        loop = asyncio.get_running_loop()
        func = functools.partial(
            self.build_routes,
            user_location,
            places,
            transportation_mode,
            max_time_minutes,
            target_places,
            max_routes,
            current_datetime
        )
        
        # Nếu không truyền executor (process pool), dùng default threadpool
        # ProcessPoolExecutor tốt hơn cho CPU-bound nhưng cần pickle-safe
        return await loop.run_in_executor(executor, func)
