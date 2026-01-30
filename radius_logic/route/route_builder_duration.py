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
        # ============================================================
        # BƯỚC 0: Kiểm tra đầu vào (Input Validation)
        # ============================================================
        if not places:
            return None
        
        # Kiểm tra số lượng POI theo category - đảm bảo đủ POI để xen kẽ
        # Nếu mỗi category chỉ có <= 1 POI → không đủ để build route (cần ít nhất 2 POI/category)
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
        
        # ============================================================
        # BƯỚC 1: Xây dựng distance matrix (Ma trận khoảng cách)
        # ============================================================
        # Distance matrix: [user_location, poi1, poi2, ...]
        # distance_matrix[i][j] = khoảng cách từ vị trí i đến vị trí j
        # i=0: user location, i=1,2,3...: các POI
        if distance_matrix is None:
            distance_matrix = self.geo.build_distance_matrix(user_location, places)
        
        if max_distance is None:
            max_distance = max(max(row) for row in distance_matrix)
        
        max_radius = max(distance_matrix[0][1:])
        
        # ============================================================
        # BƯỚC 2: Phân tích meal requirements (Yêu cầu bữa ăn)
        # ============================================================
        # Kiểm tra:
        # - Có "Cafe & Bakery" → KHÔNG cần chèn Restaurant (có đồ ăn nhẹ)
        # - Không có "Cafe & Bakery" nhưng có "Restaurant" → Kiểm tra overlap với meal time
        # - Overlap >= 60 phút với lunch (11:00-14:00) hoặc dinner (17:00-20:00) → Cần chèn Restaurant
        # - Có "Cafe" (không phải "Cafe & Bakery") → Bật cafe-sequence
        meal_info = self.analyze_meal_requirements(places, current_datetime, max_time_minutes)
        all_categories = meal_info["all_categories"]
        should_insert_restaurant_for_meal = meal_info["should_insert_restaurant_for_meal"]
        meal_windows = meal_info["meal_windows"]
        need_lunch_restaurant = meal_info["need_lunch_restaurant"]
        need_dinner_restaurant = meal_info["need_dinner_restaurant"]
        should_insert_cafe = meal_info.get("should_insert_cafe", False)
        
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
        
        # ============================================================
        # BƯỚC 3: Chọn POI đầu tiên
        # ============================================================
        # Logic:
        # - Nếu first_place_idx được chỉ định → Dùng luôn
        # - Nếu ĐÃ TRONG meal time (current_datetime trong window) → BẮT BUỘC chọn Restaurant
        # - Nếu CHƯA TỚI meal time → LOẠI Restaurant ra (giữ cho sau)
        # - Loại "Cafe" nếu bật cafe-sequence (cafe chỉ chèn sau 2 POI)
        # - Chọn POI có combined_score cao nhất (70% similarity + 30% distance)
        best_first, should_insert_cafe = self.select_first_poi(
            places, first_place_idx, distance_matrix, max_distance,
            transportation_mode, current_datetime, should_insert_restaurant_for_meal,
            meal_windows, should_insert_cafe
        )
        
        if best_first is None:
            return None
        
        # ============================================================
        # BƯỚC 4: Khởi tạo route state (Trạng thái ban đầu)
        # ============================================================
        route = [best_first]  # Danh sách index POI trong route  # Danh sách index POI trong route
        visited = {best_first}  # Set các POI đã dùng (tránh trùng lặp)
        current_pos = best_first + 1  # Vị trí hiện tại trong distance_matrix (0=user, 1+=POI)
        
        # Tính travel time từ user → POI đầu và stay time tại POI đầu
        travel_time = self.calculator.calculate_travel_time(
            distance_matrix[0][best_first + 1],
            transportation_mode
        )
        stay_time = self.calculator.get_stay_time(
            places[best_first].get("poi_type", ""),
            places[best_first].get("stay_time")
        )
        total_travel_time = travel_time  # Tổng travel time tích lũy
        total_stay_time = stay_time  # Tổng stay time tích lũy
        
        # Tính bearing (hướng di chuyển) từ user → POI đầu (dùng để tránh quay đầu nhiều)
        prev_bearing = self.geo.calculate_bearing(
            user_location[0], user_location[1],
            places[best_first]["lat"], places[best_first]["lon"]
        )
        
        category_sequence = []
        if 'category' in places[best_first]:
            category_sequence.append(places[best_first].get('category'))
        
        # ============================================================
        # BƯỚC 5: Kiểm tra POI đầu và khởi tạo flags
        # ============================================================
        # check_first_poi_meal_status trả về:
        # - lunch_restaurant_inserted: True nếu POI đầu là Restaurant trong lunch window
        # - dinner_restaurant_inserted: True nếu POI đầu là Restaurant trong dinner window
        # - cafe_counter: Số POI kể từ lần dừng chân gần nhất (0 nếu Restaurant/Cafe, 1 nếu khác)
        # - should_insert_cafe: có thể bị disable nếu cả 2 meal đã thỏa từ đầu
        lunch_restaurant_inserted, dinner_restaurant_inserted, cafe_counter, should_insert_cafe = self.check_first_poi_meal_status(
            best_first, places, should_insert_restaurant_for_meal, meal_windows,
            distance_matrix, transportation_mode, current_datetime, should_insert_cafe
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
        
        # ============================================================
        # BƯỚC 6: WHILE LOOP - Chọn POI giữa cho đến khi còn < 30% thời gian
        # ============================================================
        # Khác với TargetRouteBuilder (FOR LOOP cố định), DurationRouteBuilder dùng WHILE LOOP
        # → Số POI linh hoạt tùy thuộc vào time budget
        # Stop condition: remaining_time < 30% max_time → Chuyển sang chọn POI cuối
        max_iterations = len(places)  # Safety limit tránh infinite loop  # Safety limit tránh infinite loop
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            
            # --- Check 1: Tính thời gian còn lại ---
            remaining_time = max_time_minutes - (total_travel_time + total_stay_time)
            
            # Nếu thời gian còn lại < 30%, chuyển sang chọn điểm cuối
            # --- Check 2: Stop condition (còn < 30% thời gian) ---
            if remaining_time < max_time_minutes * self.TIME_THRESHOLD_FOR_LAST_POI:
                print(f"⏰ Thời gian còn lại ({remaining_time:.1f}m) < 30% → Chọn POI cuối")
                break
            
            # --- Chọn POI tiếp theo với meal-priority và cafe-sequence ---
            # _select_middle_poi trả về:
            # - index: POI index
            # - target_meal_type: 'lunch'/'dinner'/None (nếu chèn cho meal)
            # - reset_cafe_counter: True nếu POI là Restaurant/Cafe
            best_next = self._select_middle_poi(
                places, route, visited, current_pos, distance_matrix, max_distance,
                transportation_mode, max_time_minutes, total_travel_time, total_stay_time,
                current_datetime, prev_bearing, user_location,
                all_categories, category_sequence, should_insert_restaurant_for_meal,
                meal_windows, need_lunch_restaurant, need_dinner_restaurant,
                lunch_restaurant_inserted, dinner_restaurant_inserted,
                should_insert_cafe, cafe_counter
            )
            
            if best_next is None:
                print(f"⚠️ Không tìm được POI phù hợp → Chọn POI cuối")
                break
            
            # --- Lấy kết quả từ _select_middle_poi ---
            poi_idx = best_next['index']
            
            # --- Update meal flags (nếu vừa chèn Restaurant cho meal) ---
            if best_next['target_meal_type']:
                if best_next['target_meal_type'] == 'lunch':
                    lunch_restaurant_inserted = True
                    print(f"🍽️  ✅ Đã chèn RESTAURANT cho LUNCH (POI #{len(route)+1}: {places[poi_idx].get('name', 'N/A')})")
                elif best_next['target_meal_type'] == 'dinner':
                    dinner_restaurant_inserted = True
                    print(f"🍽️  ✅ Đã chèn RESTAURANT cho DINNER (POI #{len(route)+1}: {places[poi_idx].get('name', 'N/A')})")
            
            # --- Thêm POI vào route ---
            route.append(poi_idx)
            visited.add(poi_idx)
            
            # --- Cập nhật category_sequence và cafe_counter ---
            # category_sequence: lịch sử category để xen kẽ
            # cafe_counter: số POI kể từ lần dừng chân gần nhất (Restaurant/Cafe)
            selected_cat = places[poi_idx].get('category')
            if selected_cat:
                category_sequence.append(selected_cat)
                
                # Cập nhật cafe_counter:
                # - Nếu reset_cafe_counter=True (Restaurant/Cafe) → reset về 0
                # - Ngược lại (category khác) → +1
                # Khi cafe_counter >= 2 → trigger cafe-sequence (chèn Cafe)
                if should_insert_cafe:
                    if best_next.get("reset_cafe_counter", False):
                        # Restaurant hoặc Cafe → reset counter (cả 2 đều là nơi dừng chân)
                        cafe_counter = 0
                        print(f"   🍽️/☕ Chọn {selected_cat} (dừng chân) → Reset cafe_counter = 0")
                    else:
                        # POI khác → +1
                        cafe_counter += 1
                        print(f"   📍 Chọn {selected_cat} → cafe_counter = {cafe_counter}")
            
            # --- Cập nhật total travel/stay time ---
            travel_time = self.calculator.calculate_travel_time(
                distance_matrix[current_pos][poi_idx + 1],
                transportation_mode
            )
            stay_time = self.calculator.get_stay_time(
                places[poi_idx].get("poi_type", ""),
                places[poi_idx].get("stay_time")
            )
            total_travel_time += travel_time
            total_stay_time += stay_time
            
            # --- Cập nhật bearing (hướng di chuyển) để tính angle penalty ---
            # Angle penalty: tránh quay đầu nhiều lần (di chuyển zigzag)
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
        
        # ============================================================
        # BƯỚC 7: Chọn POI cuối gần user (giảm return time)
        # ============================================================
        # Strategy: Thử các radius threshold từ nhỏ → lớn (50%, 75%, 100%, 150%, 200%)
        # Ở mỗi threshold, chọn POI có combined_score cao nhất
        # Validate: opening hours, time budget, meal constraints
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
            stay_time = self.calculator.get_stay_time(
                places[best_last].get("poi_type", ""),
                places[best_last].get("stay_time")
            )
            total_travel_time += travel_time
            total_stay_time += stay_time
            current_pos = best_last + 1
        
        # ============================================================
        # BƯỚC 8: Tính return time và validate time budget
        # ============================================================
        return_time = self.calculator.calculate_travel_time(
            distance_matrix[current_pos][0],
            transportation_mode
        )
        total_travel_time += return_time
        
        total_time = total_travel_time + total_stay_time
        if total_time > max_time_minutes:
            return None  # Vượt time budget → không feasible
        
        # ============================================================
        # BƯỚC 9: Format kết quả trả về client
        # ============================================================
        # Bổ sung thông tin: travel_time, stay_time, combined_score cho mỗi POI
        return self.format_route_result(
            route, places, distance_matrix, transportation_mode,
            max_distance, total_travel_time, total_stay_time
        )
    
    def _select_middle_poi(
        self, places, route, visited, current_pos, distance_matrix, max_distance,
        transportation_mode, max_time_minutes, total_travel_time, total_stay_time,
        current_datetime, prev_bearing, user_location, all_categories, category_sequence,
        should_insert_restaurant_for_meal, meal_windows, need_lunch_restaurant,
        need_dinner_restaurant, lunch_restaurant_inserted, dinner_restaurant_inserted,
        should_insert_cafe: bool = False, cafe_counter: int = 0
    ) -> Optional[Dict[str, Any]]:
        """Chọn POI giữa - hỗ trợ meal-priority và cafe-sequence insertion."""
        
        def is_cafe_cat(cat: Optional[str]) -> bool:
            # Category cố định từ UI: "Cafe" hoặc "Cafe & Bakery"
            return cat == "Cafe"
        
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
        
        # ============================================================
        # BƯỚC 1: Xác định category bắt buộc cho POI tiếp theo
        # ============================================================
        # required_category: ép chọn loại POI cụ thể ('Restaurant'/'Cafe'/alternation)
        # exclude_restaurant: True = loại TẤT CẢ restaurant khỏi candidates (giữ cho meal time)
        #                     False = cho phép restaurant được xét bình thường
        
        required_category = None  # Chưa ép category nào
        
        # Khởi tạo exclude_restaurant:
        # - Nếu should_insert_restaurant_for_meal = True → ban đầu exclude_restaurant = True
        #   (loại restaurant để "giữ" cho meal time, tránh chọn quá sớm)
        # - Nếu should_insert_restaurant_for_meal = False → exclude_restaurant = False
        #   (không loại restaurant, chạy bình thường)
        exclude_restaurant = should_insert_restaurant_for_meal
        
        if should_prioritize_restaurant:
            has_restaurant_available = any(
                p.get('category') == 'Restaurant' and i not in visited
                for i, p in enumerate(places)
            )
            if has_restaurant_available:
                required_category = 'Restaurant'
                exclude_restaurant = False
        # Nếu đã chèn đủ 2 bữa thì xét thành True luôn  để ko chèn nữa
        elif should_insert_restaurant_for_meal and lunch_restaurant_inserted and dinner_restaurant_inserted:
            exclude_restaurant = True
        
        # ============================================================
        # BƯỚC 3: CAFE-SEQUENCE - Chèn Cafe sau mỗi 2 POI
        # ============================================================
        # Logic: Nếu cafe_counter >= 2 → chèn POI loại "Cafe" (không phải "Cafe & Bakery")
        # NHƯNG: Meal time có priority cao hơn → block cafe-sequence khi trong meal window
        if should_insert_cafe and required_category is None:
            # Check xem có đang trong meal window không
            in_meal_window = False
            if meal_windows and arrival_at_next:
                if meal_windows.get('lunch') and need_lunch_restaurant and not lunch_restaurant_inserted:
                    lunch_start, lunch_end = meal_windows['lunch']
                    if lunch_start <= arrival_at_next <= lunch_end:
                        in_meal_window = True
                        print(f"🍽️  Block cafe-sequence: Đang trong LUNCH window ({arrival_at_next.strftime('%H:%M')})")
                
                if meal_windows.get('dinner') and need_dinner_restaurant and not dinner_restaurant_inserted:
                    dinner_start, dinner_end = meal_windows['dinner']
                    if dinner_start <= arrival_at_next <= dinner_end:
                        in_meal_window = True
                        print(f"🍽️  Block cafe-sequence: Đang trong DINNER window ({arrival_at_next.strftime('%H:%M')})")
            
            # Chỉ chèn cafe khi KHÔNG trong meal window
            if not in_meal_window and cafe_counter >= 2:
                # Trigger cafe-insert using sentinel 'CAFE' (so sánh bằng is_cafe_cat sau)
                required_category = 'Cafe'
                # exclude_restaurant  là ưu tiên lv1 nên cần false lại thì mới chèn được cafe
                exclude_restaurant = False
                print(f"☕ Cafe-sequence triggered: cafe_counter={cafe_counter} >= 2 → Chèn Cafe")
        
        # ============================================================
        # BƯỚC 4: Xây dựng alternation_categories (xen kẽ category)
        # ============================================================
        # Loại "Cafe" khỏi alternation khi cafe-sequence bật
        # Lý do: Cafe chỉ được chèn theo sequence (sau 2 POI), không xen kẽ bình thường
        # Ví dụ: all_categories = ["Culture", "Nature", "Cafe", "Restaurant"]
        #        → alternation_categories = ["Culture", "Nature", "Restaurant"] (bỏ "Cafe")
        alternation_categories = [
            c for c in all_categories
            if not (should_insert_cafe and is_cafe_cat(c))  # Bỏ "Cafe" nếu bật sequence
        ] if all_categories else []
        
        # Debug: in ra để kiểm tra
        print(f"🔍 DEBUG: all_categories={all_categories}")
        print(f"🔍 DEBUG: should_insert_cafe={should_insert_cafe}")
        print(f"🔍 DEBUG: alternation_categories={alternation_categories}")
        print(f"🔍 DEBUG: cafe_counter={cafe_counter}")

        # Cách 2 cho dê hiểu
        # alternation_categories = []

        # if all_categories:
        #     for c in all_categories:
        #         if should_insert_cafe and is_cafe_cat(c):
        #             continue
        #         alternation_categories.append(c)

        
        # ============================================================
        # BƯỚC 5: ALTERNATION - Xen kẽ category khi không có yêu cầu đặc biệt
        # ============================================================
        # Nếu không có required_category (không ép Restaurant/Cafe) → dùng alternation
        # Logic: Chọn category tiếp theo trong vòng luân phiên dựa trên category vừa chọn
        # Ví dụ: alternation_categories = ["Culture", "Nature", "Restaurant"]
        #        category_sequence[-1] = "Nature" → chọn "Restaurant" (phần tử kế tiếp)
        if required_category is None and category_sequence and alternation_categories:
            last_category = category_sequence[-1]  # Category POI vừa thêm
            try:
                # Tìm vị trí của last_category trong list alternation
                current_idx = alternation_categories.index(last_category)
                # Chọn phần tử kế tiếp (vòng quanh nếu hết list)
                next_idx = (current_idx + 1) % len(alternation_categories)
                required_category = alternation_categories[next_idx]
            except ValueError:
                # Nếu last_category không có trong alternation → chọn phần tử đầu
                required_category = alternation_categories[0] if alternation_categories else None
        
        # ============================================================
        # BƯỚC 6: Tính target_bearing và lọc candidates với bearing filter
        # ============================================================
        # Tính target_bearing (hướng từ vị trí hiện tại về user - để tạo vòng cung)
        target_bearing = None
        current_lat, current_lon = None, None
        if user_location:
            if current_pos == 0:  # Từ user
                current_lat, current_lon = user_location
            else:
                current_place = places[current_pos - 1]
                current_lat, current_lon = current_place["lat"], current_place["lon"]
            
            # Hướng về user (để POI tiếp theo tiến dần về phía user)
            target_bearing = self.geo.calculate_bearing(
                current_lat, current_lon, user_location[0], user_location[1]
            )
        
        candidates = []
        last_added_place = places[route[-1]] if route else None
        bearing_range = RouteConfig.INITIAL_BEARING_RANGE  # Bắt đầu với ±90°
        
        while not candidates and bearing_range <= RouteConfig.MAX_BEARING_RANGE:
            # Debug: In thông tin bearing range hiện tại
            if target_bearing is not None:
                print(f"🧭 Bearing filter: target={target_bearing:.1f}°, range=±{bearing_range:.1f}°")
            
            for i, place in enumerate(places):
                # --- Filter 1: Bỏ POI đã dùng ---
                if i in visited:
                    continue
                
                # --- Filter 2: Loại Restaurant nếu exclude_restaurant = True ---
                # (Đang giữ restaurant cho meal time)
                if exclude_restaurant and place.get('category') == 'Restaurant':
                    continue
                
                # --- Filter 3: Kiểm tra required_category (ép chọn loại POI) ---
                # Nếu required_category == 'CAFE' thì match bằng substring (is_cafe_cat),
                # ngược lại match bằng equality như trước
                if required_category:
                    # Kiểm tra trường hợp đặc biệt khi yêu cầu là "Cafe" (xử lý khác với các category khác).
                    if required_category == 'Cafe':
                        # Kiểm tra xem place có phải là cafe không bằng hàm is_cafe_cat  nếu ko thì bỏ qua nhảy qua POI tiếp thep
                        if not is_cafe_cat(place.get('category')):
                            continue
                    else:
                        if place.get('category') != required_category:
                            continue
                
                # --- Filter 4: Tránh chọn 2 POI cùng loại đồ ăn liên tiếp ---
                # Ví dụ: Phở → Bún chả (cùng Vietnamese food) → bỏ
                if last_added_place and self.validator.is_same_food_type(last_added_place, place):
                    continue
                
                # ⭐ BEARING FILTER: Chỉ POI trong phạm vi góc cho phép
                if target_bearing is not None and current_lat is not None:
                    poi_in_range = self.geo.is_poi_in_bearing_range(
                        current_lat, current_lon,
                        place["lat"], place["lon"],
                        target_bearing, bearing_range
                    )
                    if not poi_in_range:
                        continue  # Loại bỏ POI ngoài phạm vi
                
                # --- Filter 5: Kiểm tra opening hours (giờ mở cửa) ---
                if current_datetime:
                    travel_time_to_poi = self.calculator.calculate_travel_time(
                        distance_matrix[current_pos][i + 1],
                        transportation_mode
                    )
                    arrival_time = current_datetime + timedelta(
                        minutes=total_travel_time + total_stay_time + travel_time_to_poi
                    )
                    # Bỏ nếu POI đóng cửa vào thời điểm arrival
                    if not self.validator.is_poi_available_at_time(place, arrival_time):
                        continue
                
                # --- Tính combined score (70% similarity + 30% distance + angle penalty) ---
                combined = self.calculator.calculate_combined_score(
                    place_idx=i,
                    current_pos=current_pos,
                    places=places,
                    distance_matrix=distance_matrix,
                    max_distance=max_distance,
                    prev_bearing=prev_bearing,
                    user_location=user_location
                )
                
                # --- Filter 6: Kiểm tra TIME BUDGET ---
                # Phải đủ thời gian: (travel đến POI) + (stay tại POI) + (quay về user) <= max_time
                temp_travel = total_travel_time + self.calculator.calculate_travel_time(
                    distance_matrix[current_pos][i + 1],
                    transportation_mode
                )
                temp_stay = total_stay_time + self.calculator.get_stay_time(
                    places[i].get("poi_type", ""),
                    places[i].get("stay_time")
                )
                estimated_return = self.calculator.calculate_travel_time(
                    distance_matrix[i + 1][0],  # Từ POI này về user
                    transportation_mode
                )
                
                # Bỏ nếu vượt quá time budget
                if temp_travel + temp_stay + estimated_return > max_time_minutes:
                    continue
                
                # ✅ POI này pass tất cả filters → thêm vào candidates
                candidates.append((i, combined))
            
            # Nếu không tìm được candidates và chưa đến max range, mở rộng thêm
            if not candidates and bearing_range < RouteConfig.MAX_BEARING_RANGE:
                bearing_range += RouteConfig.BEARING_EXPANSION_STEP
                print(f"   ⚠️  Không tìm được POI, mở rộng sang ±{bearing_range:.1f}°")
            else:
                break  # Tìm được hoặc đã max range
        
        # ============================================================
        # BƯỚC 7: Chọn POI tốt nhất từ candidates
        # ============================================================
        if candidates:
            # Sort: combined score cao → thấp; nếu bằng nhau thì index nhỏ hơn (deterministic)
            candidates.sort(key=lambda x: (-x[1], x[0]))
            best_idx = candidates[0][0]
            
            # ============================================================
            # BƯỚC 8: Xác định có reset cafe_counter hay không
            # ============================================================
            # Logic reset cafe_counter:
            # - "Restaurant" hoặc "Cafe" → reset về 0 (cả 2 đều là nơi dừng chân nghỉ ngơi)
            # - "Cafe & Bakery" → KHÔNG reset (thuộc Food & Local Flavours, xen kẽ bình thường)
            # - Category khác → caller sẽ tăng cafe_counter += 1
            selected_cat = places[best_idx].get('category')
            if selected_cat in ("Restaurant", "Cafe"):
                # Trả về flag reset_cafe_counter=True → caller sẽ set cafe_counter = 0
                return {
                    'index': best_idx,
                    'target_meal_type': target_meal_type,
                    'reset_cafe_counter': True
                }
            
            # Category khác → caller sẽ tăng cafe_counter += 1
            return {
                'index': best_idx,
                'target_meal_type': target_meal_type
            }
        
        # ============================================================
        # BƯỚC 9: FALLBACK - Nếu không tìm được candidate với required_category
        # ============================================================
        # Bỏ constraint category và tìm lại (vẫn tôn trọng exclude_restaurant và các filter khác)
        if not candidates and required_category:
            print(f"   ⚠️  Không tìm được POI với category '{required_category}', bỏ qua category constraint")
            bearing_range = RouteConfig.INITIAL_BEARING_RANGE  # Reset về ±90°
            
            while not candidates and bearing_range <= RouteConfig.MAX_BEARING_RANGE:
                if target_bearing is not None:
                    print(f"🧭 Bearing filter (fallback): target={target_bearing:.1f}°, range=±{bearing_range:.1f}°")
                
                for i, place in enumerate(places):
                    if i in visited:
                        continue
                    
                    if exclude_restaurant and place.get('category') == 'Restaurant':
                        continue
                    
                    # QUAN TRỌNG: Fallback vẫn phải tôn trọng cafe-sequence
                    # KHÔNG được chọn "Cafe" nếu should_insert_cafe=True và cafe_counter < 2
                    if should_insert_cafe and is_cafe_cat(place.get('category')) and cafe_counter < 2:
                        continue
                    
                    if last_added_place and self.validator.is_same_food_type(last_added_place, place):
                        continue
                    
                    # ⭐ BEARING FILTER: Áp dụng lại cho fallback
                    if target_bearing is not None and current_lat is not None:
                        poi_in_range = self.geo.is_poi_in_bearing_range(
                            current_lat, current_lon,
                            place["lat"], place["lon"],
                            target_bearing, bearing_range
                        )
                        if not poi_in_range:
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
                        places[i].get("poi_type", ""),
                        places[i].get("stay_time")
                    )
                    estimated_return = self.calculator.calculate_travel_time(
                        distance_matrix[i + 1][0],
                        transportation_mode
                    )
                    
                    if temp_travel + temp_stay + estimated_return > max_time_minutes:
                        continue
                    
                    candidates.append((i, combined))
                
                # Mở rộng nếu cần
                if not candidates and bearing_range < RouteConfig.MAX_BEARING_RANGE:
                    bearing_range += RouteConfig.BEARING_EXPANSION_STEP
                    print(f"   ⚠️  Không tìm được POI (fallback), mở rộng sang ±{bearing_range:.1f}°")
                else:
                    break
            
            if candidates:
                candidates.sort(key=lambda x: (-x[1], x[0]))
                best_idx = candidates[0][0]
                
                # Check category để xác định reset_cafe_counter (giống logic chính)
                selected_cat = places[best_idx].get('category')
                if selected_cat in ("Restaurant", "Cafe"):
                    return {
                        'index': best_idx,
                        'target_meal_type': None,
                        'reset_cafe_counter': True
                    }
                
                return {
                    'index': best_idx,
                    'target_meal_type': None
                }
        
        return None
