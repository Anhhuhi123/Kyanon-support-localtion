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
from .route.calculator import Calculator
from .route.route_builder_greedy import GreedyRouteBuilder

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
        self.calculator = Calculator(self.geo)
        self.greedy_builder = GreedyRouteBuilder(
            geo=self.geo,
            validator=self.validator,
            calculator=self.calculator
        )
        
      
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
                travel_time = self.calculator.calculate_travel_time(
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
            
            combined = self.calculator.calculate_combined_score(
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
                    travel_time = self.calculator.calculate_travel_time(
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
                    travel_time = self.calculator.calculate_travel_time(
                        distance_matrix[0][i + 1],
                        transportation_mode
                    )
                    arrival_time = TimeUtils.get_arrival_time(current_datetime, travel_time)
                    
                    if not self.validator.is_poi_available_at_time(place, arrival_time):
                        continue
                
                # Tính combined score
                combined = self.calculator.calculate_combined_score(
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
        route_1 = self.greedy_builder.build_single_route_greedy(
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
                
                route_result = self.greedy_builder.build_single_route_greedy(
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
