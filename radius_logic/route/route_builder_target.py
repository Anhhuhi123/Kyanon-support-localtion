"""
Target Route Builder - Xây dựng route với số lượng POI cố định (target_places)

Module này định nghĩa TargetRouteBuilder - builder chuyên dụng cho chế độ xây dựng route
với số lượng POI được chỉ định trước (target_places).

Đặc điểm:
- Số POI cố định: target_places (ví dụ: 5 POI)
- Cấu trúc route: POI đầu → (target_places - 2) POI giữa → POI cuối
- Xen kẽ category: Tự động alternate giữa các category (Cafe → Restaurant → Cafe)
- Meal logic: Tự động chèn Restaurant vào lunch/dinner window nếu cần
- Opening hours: Validate mở cửa cho tất cả POI

Author: Kyanon Team
Created: 2026-01
"""
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional
from utils.time_utils import TimeUtils
from .route_builder_base import BaseRouteBuilder

class TargetRouteBuilder(BaseRouteBuilder):
    """
    Route Builder cho chế độ target_places (số POI cố định)
    
    Workflow:
    1. select_first_poi() → Chọn POI đầu tiên (combined_score cao nhất)
    2. Loop (target_places - 2) lần:
       - _select_middle_poi() → Chọn POI giữa với category alternation
       - Ưu tiên Restaurant nếu arrival rơi vào meal window
    3. select_last_poi() → Chọn POI cuối gần user
    4. format_route_result() → Format JSON response
    
    Đặc điểm:
    - FOR LOOP cố định: Chính xác (target_places - 2) POI giữa
    - Category xen kẽ: Cafe → Restaurant → Cafe → ...
    - Meal priority: Nếu arrival trong lunch/dinner window → Ưu tiên Restaurant
    - Fallback: Nếu hết POI category yêu cầu → Bỏ category constraint
    
    Example:
        >>> builder = TargetRouteBuilder(geo, validator, calculator)
        >>> route = builder.build_route(
        ...     user_location=(21.028, 105.852),
        ...     places=semantic_places,
        ...     transportation_mode="DRIVING",
        ...     max_time_minutes=180,
        ...     target_places=5  # Luôn trả về 5 POI nếu feasible
        ... )
    """
    
    def build_route(
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
        Xây dựng route với SỐ LƯỢNG POI CỐ ĐỊNH (target_places)
        
        Flow:
        1. Build distance matrix (nếu chưa có)
        2. Phân tích meal requirements → should_insert_restaurant_for_meal
        3. Chọn POI đầu (score + distance cao nhất, loại Restaurant nếu có meal requirement)
        4. FOR LOOP (target_places - 2) lần → Chọn POI giữa:
           - Xen kẽ category (Cafe → Restaurant → Cafe)
           - Ưu tiên Restaurant khi arrival rơi vào meal window
           - Validate opening hours
        5. Chọn POI cuối gần user
        6. Validate time budget: total_time <= max_time_minutes
        7. Format result
        
        Args:
            user_location: (lat, lon) của user
            places: Danh sách POI candidates từ semantic search
            transportation_mode: "DRIVING", "WALKING", "BICYCLING"
            max_time_minutes: Time budget tối đa (phút)
            target_places: SỐ POI MUỐN ĐI (cố định, ví dụ: 5)
            first_place_idx: Index POI đầu (None = auto select)
            current_datetime: Thời điểm bắt đầu (để validate opening hours)
            distance_matrix: Ma trận khoảng cách (pre-computed, optional)
            max_distance: Max distance trong matrix (pre-computed, optional)
            
        Returns:
            Dict chứa:
            - route: List index POI
            - total_time_minutes: Tổng thời gian
            - places: List POI với đầy đủ thông tin
            Hoặc None nếu không feasible (không đủ POI hoặc quá time budget)
            
        Note:
            - Luôn trả về ĐÚNG target_places POI (nếu feasible)
            - Nếu target_places > len(places) → Return None
            - Nếu total_time > max_time_minutes → Return None
        """
        if target_places > len(places):
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
        
        # 1. Xây dựng distance matrix (nếu chưa có)
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
        should_insert_cafe = meal_info.get("should_insert_cafe", False)
        
        # Print thông báo meal time overlap
        if should_insert_restaurant_for_meal:
            print("\n" + "="*60)
            print("🍽️  MEAL TIME ANALYSIS (Target Mode)")
            print("="*60)
            if need_lunch_restaurant:
                print("✅ Overlap với LUNCH TIME (11:00-14:00) >= 60 phút")
            if need_dinner_restaurant:
                print("✅ Overlap với DINNER TIME (17:00-20:00) >= 60 phút")
            print("="*60 + "\n")
        
        # 3. Chọn điểm đầu tiên
        best_first, should_insert_cafe = self.select_first_poi(
            places, first_place_idx, distance_matrix, max_distance,
            transportation_mode, current_datetime, should_insert_restaurant_for_meal,
            meal_windows, should_insert_cafe
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
        stay_time = self.calculator.get_stay_time(
            places[best_first].get("poi_type", ""),
            places[best_first].get("stay_time")
        )
        total_travel_time = travel_time
        total_stay_time = stay_time
        
        prev_bearing = self.geo.calculate_bearing(
            user_location[0], user_location[1],
            places[best_first]["lat"], places[best_first]["lon"]
        )
        
        category_sequence = []
        if 'category' in places[best_first]:
            category_sequence.append(places[best_first].get('category'))
        
        # Kiểm tra POI đầu có phải Restaurant trong meal không và khởi tạo cafe_counter
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
        
        # 4. Chọn các POI giữa (target_places - 2)
        for step in range(target_places - 2):
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
            stay_time = self.calculator.get_stay_time(
                places[best_last].get("poi_type", ""),
                places[best_last].get("stay_time")
            )
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
        need_dinner_restaurant, lunch_restaurant_inserted, dinner_restaurant_inserted,
        should_insert_cafe: bool = False, cafe_counter: int = 0
    ) -> Optional[Dict[str, Any]]:
        """Chọn POI giữa với logic xen kẽ category, meal priority và cafe-sequence"""
        
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
        # BƯỚC 6: Lọc candidates theo các điều kiện
        # ============================================================
        candidates = []
        last_added_place = places[route[-1]] if route else None
        
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
