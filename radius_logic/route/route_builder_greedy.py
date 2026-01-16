from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional
from utils.time_utils import TimeUtils
from .route_config import RouteConfig
from .geographic_utils import GeographicUtils
from .poi_validator import POIValidator
from .calculator import Calculator


class GreedyRouteBuilder:

    def __init__(
        self,
        geo: GeographicUtils,
        validator: POIValidator,
        calculator: Calculator
    ):
        """
        Khởi tạo GreedyRouteBuilder
        
        Args:
            geo: GeographicUtils instance
            validator: POIValidator instance
            calculator: Calculator instance
        """
        self.geo = geo
        self.validator = validator
        self.calculator = calculator

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
                        travel_time = self.calculator.calculate_travel_time(
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
                    
                    combined = self.calculator.calculate_combined_score(
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
            travel_time = self.calculator.calculate_travel_time(
                distance_matrix[0][best_first + 1],
                transportation_mode
            )
            stay_time = self.calculator.get_stay_time(places[best_first].get("poi_type", ""))
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
                        travel_time_to_poi = self.calculator.calculate_travel_time(
                            distance_matrix[current_pos][i + 1],
                            transportation_mode
                        )
                        arrival_time = current_datetime + timedelta(minutes=total_travel_time + total_stay_time + travel_time_to_poi)
                        
                        # Bỏ qua POI nếu không đủ thời gian stay
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
                    
                    # Kiểm tra thời gian khả thi
                    temp_travel = total_travel_time + self.calculator.calculate_travel_time(
                        distance_matrix[current_pos][i + 1],
                        transportation_mode
                    )
                    temp_stay = total_stay_time + self.calculator.get_stay_time(places[i].get("poi_type", ""))
                    estimated_return = self.calculator.calculate_travel_time(
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
                            travel_time_to_poi = self.calculator.calculate_travel_time(
                                distance_matrix[current_pos][i + 1],
                                transportation_mode
                            )
                            arrival_time = current_datetime + timedelta(minutes=total_travel_time + total_stay_time + travel_time_to_poi)
                            
                            # Bỏ qua POI nếu không đủ thời gian stay
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
                        
                        # Kiểm tra thời gian khả thi
                        temp_travel = total_travel_time + self.calculator.calculate_travel_time(
                            distance_matrix[current_pos][i + 1],
                            transportation_mode
                        )
                        temp_stay = total_stay_time + self.calculator.get_stay_time(places[i].get("poi_type", ""))
                        estimated_return = self.calculator.calculate_travel_time(
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
                
                travel_time = self.calculator.calculate_travel_time(
                    distance_matrix[current_pos][best_next + 1],
                    transportation_mode
                )
                stay_time = self.calculator.get_stay_time(places[best_next].get("poi_type", ""))
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
                            travel_time_to_last = self.calculator.calculate_travel_time(
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
                        travel_time_to_poi = self.calculator.calculate_travel_time(
                            distance_matrix[current_pos][i + 1],
                            transportation_mode
                        )
                        arrival_time = current_datetime + timedelta(minutes=total_travel_time + total_stay_time + travel_time_to_poi)
                        
                        # Bỏ qua POI nếu không đủ thời gian stay
                        if not self.validator.is_poi_available_at_time(place, arrival_time):
                            continue
                    
                    # Kiểm tra thời gian
                    temp_travel = total_travel_time + self.calculator.calculate_travel_time(
                        distance_matrix[current_pos][i + 1],
                        transportation_mode
                    )
                    temp_stay = total_stay_time + self.calculator.get_stay_time(places[i].get("poi_type", ""))
                    return_time = self.calculator.calculate_travel_time(dist_to_user, transportation_mode)
                    
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
                travel_time = self.calculator.calculate_travel_time(
                    distance_matrix[current_pos][best_last + 1],
                    transportation_mode
                )
                stay_time = self.calculator.get_stay_time(places[best_last].get("poi_type", ""))
                total_travel_time += travel_time
                total_stay_time += stay_time
                current_pos = best_last + 1
            
            # 5. Thêm thời gian quay về user
            return_time = self.calculator.calculate_travel_time(
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
                travel_time = self.calculator.calculate_travel_time(
                    distance_matrix[prev_pos][place_idx + 1],
                    transportation_mode
                )
                stay_time = self.calculator.get_stay_time(place.get("poi_type", ""))
                
                # Tính combined score cho POI này
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
                    "category": place.get("category", "Unknown"),  # Include category for update POI
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