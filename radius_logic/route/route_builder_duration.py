"""
Duration Route Builder - Xây dựng route dựa trên thời gian tối đa (không cố định số POI)

Module này định nghĩa DurationRouteBuilder - builder chuyên dụng cho chế độ xây dựng route
dựa trên TIME BUDGET thay vì số lượng POI cố định.

Đặc điểm:
- Số POI linh hoạt: Không cố định, tùy thuộc vào time budget
- Stop condition: Khi remaining_time < 30% max_time → Chọn POI cuối
- WHILE LOOP: Tiếp tục thêm POI cho đến khi hết thời gian
- Meal logic: Tự động chèn Restaurant vào lunch/dinner window
- Opening hours: Validate mở cửa cho tất cả POI

Constants:
    TIME_THRESHOLD_FOR_LAST_POI = 0.3 (30%)
    Khi remaining_time < 30% max_time → Dừng và chọn POI cuối

Author: Kyanon Team
Created: 2026-01
"""
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional
from utils.time_utils import TimeUtils
from .route_config import RouteConfig
from .route_builder_base import BaseRouteBuilder

class DurationRouteBuilder(BaseRouteBuilder):
    """
    Route Builder cho chế độ duration (TIME BUDGET, không cố định số POI)
    
    Workflow:
    1. select_first_poi() → Chọn POI đầu tiên
    2. WHILE LOOP:
       - Check remaining_time < 30% max_time → Break và chọn POI cuối
       - _select_middle_poi() → Chọn POI giữa (category alternation + meal priority)
       - Validate opening hours
       - Update time counters
    3. select_last_poi() → Chọn POI cuối gần user
    4. format_route_result() → Format JSON response
    
    Đặc điểm:
    - WHILE LOOP: Không cố định số POI, loop cho đến khi còn < 30% thời gian
    - Linh hoạt: Route có thể có 3, 5, 7 POI... tùy thuộc vào time budget
    - Stop early: Nếu remaining_time < 30% → Chọn POI cuối để về
    - Meal logic: Giống target mode, tự động insert Restaurant
    
    Example:
        >>> builder = DurationRouteBuilder(geo, validator, calculator)
        >>> route = builder.build_route(
        ...     user_location=(21.028, 105.852),
        ...     places=semantic_places,
        ...     transportation_mode="DRIVING",
        ...     max_time_minutes=240  # 4 hours
        ...     # Số POI không cố định, tùy vào time budget
        ... )
        >>> print(f"Route có {len(route['places'])} POI")  # Có thể là 5, 6, 7...
    """
    
    TIME_THRESHOLD_FOR_LAST_POI = 0.3  # 30% thời gian còn lại
    
    def build_route(
        self,
        user_location: Tuple[float, float],
        places: List[Dict[str, Any]],
        transportation_mode: str,
        max_time_minutes: int,
        first_place_idx: Optional[int] = None,
        current_datetime: Optional[datetime] = None,
        distance_matrix: Optional[List[List[float]]] = None,
        max_distance: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Xây dựng route DỰA TRÊN TIME BUDGET (số POI linh hoạt)
        
        Flow:
        1. Build distance matrix
        2. Phân tích meal requirements
        3. Chọn POI đầu
        4. WHILE LOOP:
           - Calculate remaining_time = max_time - (travel + stay)
           - IF remaining_time < 30% max_time → BREAK
           - ELSE → _select_middle_poi() và thêm vào route
        5. Chọn POI cuối gần user
        6. Validate time budget
        7. Format result
        
        Args:
            user_location: (lat, lon) của user
            places: Danh sách POI candidates
            transportation_mode: "DRIVING", "WALKING", "BICYCLING"
            max_time_minutes: TIME BUDGET tối đa (phút)
            first_place_idx: Index POI đầu (None = auto)
            current_datetime: Thời điểm bắt đầu
            distance_matrix: Ma trận khoảng cách (optional)
            max_distance: Max distance (optional)
            
        Returns:
            Dict chứa route info hoặc None nếu không feasible
            - Số POI KHÔNG CỐ ĐỊNH (có thể 3, 5, 7... tùy time budget)
            - Loop cho đến khi remaining_time < 30%
            
        Note:
            - Khác với TargetRouteBuilder: WHILE LOOP thay vì FOR LOOP
            - Stop condition: remaining_time < TIME_THRESHOLD_FOR_LAST_POI (30%)
            - Ví dụ: max_time=180 → Dừng khi còn < 54 phút
        """
        if not places:
            return None
        
        # 0. Kiểm tra số lượng POI theo category - nếu mỗi category <= 3 POI thì không build
        category_counts = {}
        for place in places:
            category = place.get('category')
            if category:
                category_counts[category] = category_counts.get(category, 0) + 1
        
        if category_counts:
            max_count_per_category = max(category_counts.values())
            if max_count_per_category <= 1:
                print(f"⚠️ Số lượng POI quá ít (mỗi category <= 3): {category_counts}")
                print("   → Không build route, trả về rỗng\n")
                return None
        
        # 1. Xây dựng distance matrix
        if distance_matrix is None:
            distance_matrix = self.geo.build_distance_matrix(user_location, places)
        
        if max_distance is None:
            max_distance = max(max(row) for row in distance_matrix)
        
        max_radius = max(distance_matrix[0][1:])
        
        # 2. Phân tích meal requirements
        meal_info = self.analyze_meal_requirements(places, current_datetime, max_time_minutes)
        all_categories = meal_info["all_categories"]
        should_insert_restaurant_for_meal = meal_info["should_insert_restaurant_for_meal"]
        meal_windows = meal_info["meal_windows"]
        need_lunch_restaurant = meal_info["need_lunch_restaurant"]
        need_dinner_restaurant = meal_info["need_dinner_restaurant"]
        
        # Print thông báo meal time overlap
        if should_insert_restaurant_for_meal:
            print("\n" + "="*60)
            print("🍽️  MEAL TIME ANALYSIS (Duration Mode)")
            print("="*60)
            if need_lunch_restaurant:
                print("✅ Overlap với LUNCH TIME (11:00-14:00) >= 60 phút")
            if need_dinner_restaurant:
                print("✅ Overlap với DINNER TIME (17:00-20:00) >= 60 phút")
            print("="*60 + "\n")
        
        # 3. Chọn điểm đầu tiên
        best_first = self.select_first_poi(
            places, first_place_idx, distance_matrix, max_distance,
            transportation_mode, current_datetime, should_insert_restaurant_for_meal,
            meal_windows
        )
        
        if best_first is None:
            return None
        
        # Khởi tạo route
        route = [best_first]
        visited = {best_first}
        current_pos = best_first + 1
        
        travel_time = self.calculator.calculate_travel_time(
            distance_matrix[0][best_first + 1],
            transportation_mode
        )
        stay_time = self.calculator.get_stay_time(places[best_first].get("poi_type", ""))
        total_travel_time = travel_time
        total_stay_time = stay_time
        
        prev_bearing = self.geo.calculate_bearing(
            user_location[0], user_location[1],
            places[best_first]["lat"], places[best_first]["lon"]
        )
        
        category_sequence = []
        if 'category' in places[best_first]:
            category_sequence.append(places[best_first].get('category'))
        
        # Kiểm tra POI đầu có phải Restaurant trong meal không
        lunch_restaurant_inserted, dinner_restaurant_inserted = self.check_first_poi_meal_status(
            best_first, places, should_insert_restaurant_for_meal, meal_windows,
            distance_matrix, transportation_mode, current_datetime
        )
        
        # Print thông báo POI đầu
        if should_insert_restaurant_for_meal:
            first_poi = places[best_first]
            is_restaurant = first_poi.get('category') == 'Restaurant'
            print("🔍 Kiểm tra POI đầu tiên:")
            print(f"   - Tên: {first_poi.get('name', 'N/A')}")
            print(f"   - Category: {first_poi.get('category', 'N/A')}")
            if is_restaurant and (lunch_restaurant_inserted or dinner_restaurant_inserted):
                print("   ✅ POI đầu là RESTAURANT trong meal time!")
                if lunch_restaurant_inserted:
                    print("      → Đã tính là Restaurant cho LUNCH")
                if dinner_restaurant_inserted:
                    print("      → Đã tính là Restaurant cho DINNER")
            else:
                print("   ℹ️  POI đầu KHÔNG phải Restaurant trong meal time")
            print()
        
        # 4. Chọn các POI giữa - VÒNG LẶP cho đến khi còn < 30% thời gian
        max_iterations = len(places)
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            
            # Tính thời gian còn lại
            remaining_time = max_time_minutes - (total_travel_time + total_stay_time)
            
            # Nếu thời gian còn lại < 30%, chuyển sang chọn điểm cuối
            if remaining_time < max_time_minutes * self.TIME_THRESHOLD_FOR_LAST_POI:
                print(f"⏰ Thời gian còn lại ({remaining_time:.1f}m) < 30% → Chọn POI cuối")
                break
            
            best_next = self._select_middle_poi(
                places, route, visited, current_pos, distance_matrix, max_distance,
                transportation_mode, max_time_minutes, total_travel_time, total_stay_time,
                current_datetime, prev_bearing, user_location,
                all_categories, category_sequence, should_insert_restaurant_for_meal,
                meal_windows, need_lunch_restaurant, need_dinner_restaurant,
                lunch_restaurant_inserted, dinner_restaurant_inserted
            )
            
            if best_next is None:
                print(f"⚠️ Không tìm được POI phù hợp → Chọn POI cuối")
                break
            
            # Lấy POI index trước
            poi_idx = best_next['index']
            
            # Update restaurant insertion flags
            if best_next['target_meal_type']:
                if best_next['target_meal_type'] == 'lunch':
                    lunch_restaurant_inserted = True
                    print(f"🍽️  ✅ Đã chèn RESTAURANT cho LUNCH (POI #{len(route)+1}: {places[poi_idx].get('name', 'N/A')})")
                elif best_next['target_meal_type'] == 'dinner':
                    dinner_restaurant_inserted = True
                    print(f"🍽️  ✅ Đã chèn RESTAURANT cho DINNER (POI #{len(route)+1}: {places[poi_idx].get('name', 'N/A')})")
            
            # Thêm POI vào route
            route.append(poi_idx)
            visited.add(poi_idx)
            
            if 'category' in places[poi_idx]:
                category_sequence.append(places[poi_idx].get('category'))
            
            travel_time = self.calculator.calculate_travel_time(
                distance_matrix[current_pos][poi_idx + 1],
                transportation_mode
            )
            stay_time = self.calculator.get_stay_time(places[poi_idx].get("poi_type", ""))
            total_travel_time += travel_time
            total_stay_time += stay_time
            
            # Cập nhật bearing
            prev_place = places[route[-2]] if len(route) >= 2 else None
            current_place = places[poi_idx]
            if prev_place:
                prev_bearing = self.geo.calculate_bearing(
                    prev_place["lat"], prev_place["lon"],
                    current_place["lat"], current_place["lon"]
                )
            else:
                prev_bearing = self.geo.calculate_bearing(
                    user_location[0], user_location[1],
                    current_place["lat"], current_place["lon"]
                )
            
            current_pos = poi_idx + 1
        
        # 5. Chọn điểm cuối
        best_last = self.select_last_poi(
            places, visited, current_pos, distance_matrix, max_radius,
            transportation_mode, max_distance, total_travel_time, total_stay_time,
            max_time_minutes, current_datetime, should_insert_restaurant_for_meal,
            meal_windows, lunch_restaurant_inserted, dinner_restaurant_inserted
        )
        
        if best_last is not None:
            route.append(best_last)
            travel_time = self.calculator.calculate_travel_time(
                distance_matrix[current_pos][best_last + 1],
                transportation_mode
            )
            stay_time = self.calculator.get_stay_time(places[best_last].get("poi_type", ""))
            total_travel_time += travel_time
            total_stay_time += stay_time
            current_pos = best_last + 1
        
        # 6. Thêm thời gian quay về user
        return_time = self.calculator.calculate_travel_time(
            distance_matrix[current_pos][0],
            transportation_mode
        )
        total_travel_time += return_time
        
        total_time = total_travel_time + total_stay_time
        if total_time > max_time_minutes:
            return None
        
        # 7. Format kết quả
        return self.format_route_result(
            route, places, distance_matrix, transportation_mode,
            max_distance, total_travel_time, total_stay_time
        )
    
    def _select_middle_poi(
        self, places, route, visited, current_pos, distance_matrix, max_distance,
        transportation_mode, max_time_minutes, total_travel_time, total_stay_time,
        current_datetime, prev_bearing, user_location, all_categories, category_sequence,
        should_insert_restaurant_for_meal, meal_windows, need_lunch_restaurant,
        need_dinner_restaurant, lunch_restaurant_inserted, dinner_restaurant_inserted
    ) -> Optional[Dict[str, Any]]:
        """Chọn POI giữa - tương tự target mode"""
        
        # Kiểm tra meal time priority
        arrival_at_next = None
        if current_datetime:
            arrival_at_next = current_datetime + timedelta(
                minutes=total_travel_time + total_stay_time
            )
        
        should_prioritize_restaurant = False
        target_meal_type = None
        
        if meal_windows and arrival_at_next:
            if meal_windows.get('lunch') and need_lunch_restaurant and not lunch_restaurant_inserted:
                lunch_start, lunch_end = meal_windows['lunch']
                if lunch_start <= arrival_at_next <= lunch_end:
                    should_prioritize_restaurant = True
                    target_meal_type = 'lunch'
            
            if not should_prioritize_restaurant and meal_windows.get('dinner') and need_dinner_restaurant and not dinner_restaurant_inserted:
                dinner_start, dinner_end = meal_windows['dinner']
                if dinner_start <= arrival_at_next <= dinner_end:
                    should_prioritize_restaurant = True
                    target_meal_type = 'dinner'
        
        # Xác định category bắt buộc
        required_category = None
        exclude_restaurant = should_insert_restaurant_for_meal
        
        if should_prioritize_restaurant:
            has_restaurant_available = any(
                p.get('category') == 'Restaurant' and i not in visited
                for i, p in enumerate(places)
            )
            if has_restaurant_available:
                required_category = 'Restaurant'
                exclude_restaurant = False
        elif should_insert_restaurant_for_meal and lunch_restaurant_inserted and dinner_restaurant_inserted:
            exclude_restaurant = True
        
        if required_category is None and category_sequence and all_categories:
            last_category = category_sequence[-1]
            try:
                current_idx = all_categories.index(last_category)
                next_idx = (current_idx + 1) % len(all_categories)
                required_category = all_categories[next_idx]
            except ValueError:
                required_category = all_categories[0] if all_categories else None
        
        # Tìm candidates với category yêu cầu
        candidates = []
        last_added_place = places[route[-1]] if route else None
        
        for i, place in enumerate(places):
            if i in visited:
                continue
            
            if exclude_restaurant and place.get('category') == 'Restaurant':
                continue
            
            if required_category and place.get('category') != required_category:
                continue
            
            if last_added_place and self.validator.is_same_food_type(last_added_place, place):
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
            
            combined = self.calculator.calculate_combined_score(
                place_idx=i,
                current_pos=current_pos,
                places=places,
                distance_matrix=distance_matrix,
                max_distance=max_distance,
                prev_bearing=prev_bearing,
                user_location=user_location
            )
            
            # Kiểm tra thời gian: phải đủ để đi + stay + quay về
            temp_travel = total_travel_time + self.calculator.calculate_travel_time(
                distance_matrix[current_pos][i + 1],
                transportation_mode
            )
            temp_stay = total_stay_time + self.calculator.get_stay_time(
                places[i].get("poi_type", "")
            )
            estimated_return = self.calculator.calculate_travel_time(
                distance_matrix[i + 1][0],
                transportation_mode
            )
            
            if temp_travel + temp_stay + estimated_return > max_time_minutes:
                continue
            
            candidates.append((i, combined))
        
        # Chọn POI tốt nhất
        if candidates:
            candidates.sort(key=lambda x: (-x[1], x[0]))
            return {
                'index': candidates[0][0],
                'target_meal_type': target_meal_type
            }
        
        # Nếu không tìm thấy với category yêu cầu, bỏ qua category constraint
        if not candidates and required_category:
            for i, place in enumerate(places):
                if i in visited:
                    continue
                
                if exclude_restaurant and place.get('category') == 'Restaurant':
                    continue
                
                if last_added_place and self.validator.is_same_food_type(last_added_place, place):
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
                
                combined = self.calculator.calculate_combined_score(
                    place_idx=i,
                    current_pos=current_pos,
                    places=places,
                    distance_matrix=distance_matrix,
                    max_distance=max_distance,
                    prev_bearing=prev_bearing,
                    user_location=user_location
                )
                
                temp_travel = total_travel_time + self.calculator.calculate_travel_time(
                    distance_matrix[current_pos][i + 1],
                    transportation_mode
                )
                temp_stay = total_stay_time + self.calculator.get_stay_time(
                    places[i].get("poi_type", "")
                )
                estimated_return = self.calculator.calculate_travel_time(
                    distance_matrix[i + 1][0],
                    transportation_mode
                )
                
                if temp_travel + temp_stay + estimated_return > max_time_minutes:
                    continue
                
                candidates.append((i, combined))
            
            if candidates:
                candidates.sort(key=lambda x: (-x[1], x[0]))
                return {
                    'index': candidates[0][0],
                    'target_meal_type': None
                }
        
        return None
