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
from .route.route_builder_target import TargetRouteBuilder
from .route.route_builder_duration import DurationRouteBuilder

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
        self.target_builder = TargetRouteBuilder(
            geo=self.geo,
            validator=self.validator,
            calculator=self.calculator
        )
        self.duration_builder = DurationRouteBuilder(
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
        current_datetime: Optional[datetime] = None,
        duration_mode: bool = False
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
        
        # Xây dựng route đầu tiên - KHÔNG chỉ định first_place_idx
        # Để logic trong build_route tự động chọn dựa trên meal time
        if duration_mode:
            route_1 = self.duration_builder.build_route(
                user_location=user_location,
                places=places,
                transportation_mode=transportation_mode,
                max_time_minutes=max_time_minutes,
                first_place_idx=None,  # Để tự động chọn dựa trên meal logic
                current_datetime=current_datetime,
                distance_matrix=distance_matrix,
                max_distance=max_distance
            )
        else:
            route_1 = self.target_builder.build_route(
                user_location=user_location,
                places=places,
                transportation_mode=transportation_mode,
                max_time_minutes=max_time_minutes,
                target_places=target_places,
                first_place_idx=None,  # Để tự động chọn dựa trên meal logic
                current_datetime=current_datetime,
                distance_matrix=distance_matrix,
                max_distance=max_distance
            )
        
        if route_1 is None:
            return []
        
        all_routes = [route_1]
        seen_place_sets = {tuple(sorted(route_1["route"]))}
        
        print(f"🎯 Route 1: {len(route_1['route'])} POI, total_score={route_1['total_score']:.2f}")
        
        # Nếu cần nhiều hơn 1 route, thử các POI xuất phát khác
        # Tìm candidates từ POI chưa dùng trong route 1
        if max_routes > 1:
            used_first_poi = route_1["route"][0]  # POI đầu của route 1
            
            # Tìm các POI khác để làm điểm xuất phát cho route 2, 3
            alternative_starts = []
            for i, place in enumerate(places):
                if i == used_first_poi:
                    continue  # Bỏ qua POI đã dùng làm điểm đầu route 1
                
                # Validate opening hours
                if current_datetime:
                    travel_time = self.calculator.calculate_travel_time(
                        distance_matrix[0][i + 1],
                        transportation_mode
                    )
                    arrival_time = TimeUtils.get_arrival_time(current_datetime, travel_time)
                    if not self.validator.is_poi_available_at_time(place, arrival_time):
                        continue
                
                combined = self.calculator.calculate_combined_score(
                    place_idx=i,
                    current_pos=0,
                    places=places,
                    distance_matrix=distance_matrix,
                    max_distance=max_distance,
                    is_first=True
                )
                alternative_starts.append((i, combined))
            
            # Sort và thử từng điểm xuất phát
            alternative_starts.sort(key=lambda x: (-x[1], x[0]))
            
            for first_idx, _ in alternative_starts:
                if len(all_routes) >= max_routes:
                    break
                
                if duration_mode:
                    route_result = self.duration_builder.build_route(
                        user_location=user_location,
                        places=places,
                        transportation_mode=transportation_mode,
                        max_time_minutes=max_time_minutes,
                        first_place_idx=first_idx,  # Chỉ định POI đầu cho route 2, 3
                        current_datetime=current_datetime,
                        distance_matrix=distance_matrix,
                        max_distance=max_distance
                    )
                else:
                    route_result = self.target_builder.build_route(
                        user_location=user_location,
                        places=places,
                        transportation_mode=transportation_mode,
                        max_time_minutes=max_time_minutes,
                        target_places=target_places,
                        first_place_idx=first_idx,  # Chỉ định POI đầu cho route 2, 3
                        current_datetime=current_datetime,
                        distance_matrix=distance_matrix,
                        max_distance=max_distance
                    )
                
                if route_result is None:
                    continue
                
                place_set_key = tuple(sorted(route_result["route"]))
                if place_set_key in seen_place_sets:
                    continue
                
                # Kiểm tra khác ít nhất 2 POI so với tất cả routes trước
                is_different_enough = all(
                    len(set(route_result["route"]).symmetric_difference(set(r["route"]))) >= 2
                    for r in all_routes
                )
                
                if not is_different_enough:
                    continue
                
                seen_place_sets.add(place_set_key)
                all_routes.append(route_result)
        
        print(f"\n📊 Kết quả: {len(all_routes)} route(s)")
        for idx, route in enumerate(all_routes, 1):
            print(f"   Route {idx}: {len(route['route'])} POI, score={route['total_score']:.2f}")
        
        # Format kết quả cuối cùng với route_id và order
        result = []
        for idx, route in enumerate(all_routes, 1):
            # Thêm route_id và order (số thứ tự di chuyển) vào mỗi place
            places_with_metadata = []
            current_time_in_route = current_datetime  # Track thời gian trong route
            
            for order, place in enumerate(route["places"], 1):
                place_data = place.copy()
                
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
        duration_mode: bool = False,
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
            current_datetime,
            duration_mode 
        )
        
        # Nếu không truyền executor (process pool), dùng default threadpool
        # ProcessPoolExecutor tốt hơn cho CPU-bound nhưng cần pickle-safe
        return await loop.run_in_executor(executor, func)
