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
        
        # ================================================================
        # Xây dựng route đầu tiên với fallback logic:
        #   Vòng lặp ngoài: nếu cả 5 lần thử đều cho route < 3 POI
        #                   → giảm stay_time 10 phút (qua stay_time_reduction)
        #                     và thử lại từ đầu (tối đa giảm 60 phút)
        #   Vòng lặp trong: thử tối đa 5 first_place_idx khác nhau
        #                   được chọn bởi select_first_poi (đúng logic meal/cafe/opening)
        #   Route hợp lệ: phải có >= 3 POI
        # ================================================================
        _MIN_POI        = 3
        _MAX_ATTEMPTS   = 5
        _REDUCTION_STEP = 10  # Giảm stay_time mỗi vòng (phút)
        _MAX_REDUCTION  = 60  # Giảm tối đa 60 phút (6 vòng)

        # Xây dựng danh sách 5 POI xuất phát hợp lệ THEO ĐÚNG LOGIC của select_first_poi:
        # (meal-time filter, cafe-sequence exclusion, opening hours validation...)
        # Cách làm: gọi select_first_poi 5 lần, mỗi lần loại trừ các index đã chọn trước
        # → khác với cách cũ [None, 0, 1, 2, 3] chỉ sort theo score thuần túy
        _builder_ref = self.duration_builder if duration_mode else self.target_builder
        _meal_info = _builder_ref.analyze_meal_requirements(
            places, current_datetime, max_time_minutes
        )
        _first_idx_list = []
        _exclude: set = set()
        for _ in range(_MAX_ATTEMPTS):
            _idx, _ = _builder_ref.select_first_poi(
                places=places,
                first_place_idx=None,
                distance_matrix=distance_matrix,
                max_distance=max_distance,
                transportation_mode=transportation_mode,
                current_datetime=current_datetime,
                should_insert_restaurant_for_meal=_meal_info["should_insert_restaurant_for_meal"],
                meal_windows=_meal_info["meal_windows"],
                should_insert_cafe=_meal_info.get("should_insert_cafe", False),
                exclude_indices=_exclude
            )
            if _idx is None:
                break  # Không còn POI hợp lệ nào nữa
            _first_idx_list.append(_idx)
            _exclude.add(_idx)

        if not _first_idx_list:
            return []

        print(f"📋 Danh sách {len(_first_idx_list)} POI xuất phát (theo logic select_first_poi): {_first_idx_list}")

        route_1        = None
        _stay_reduction = 0.0

        while _stay_reduction <= _MAX_REDUCTION:
            # Thông báo khi đang chạy fallback (bỏ qua lần đầu stay_reduction=0)
            self.calculator.stay_time_reduction = _stay_reduction
            if _stay_reduction > 0:
                print(
                    f"\n🔄 FALLBACK: Giảm stay_time {_stay_reduction:.0f} phút, "
                    f"thử lại tối đa {_MAX_ATTEMPTS} route..."
                )

            for _attempt, _first_idx in enumerate(_first_idx_list):
                print(
                    f"  → Lần thử {_attempt + 1}/{_MAX_ATTEMPTS}: "
                    f"first_place_idx={_first_idx}, "
                    f"stay_reduction={_stay_reduction:.0f} phút"
                )
                if duration_mode:
                    _candidate = self.duration_builder.build_route(
                        user_location=user_location,
                        places=places,
                        transportation_mode=transportation_mode,
                        max_time_minutes=max_time_minutes,
                        first_place_idx=_first_idx,
                        current_datetime=current_datetime,
                        distance_matrix=distance_matrix,
                        max_distance=max_distance
                    )
                else:
                    _candidate = self.target_builder.build_route(
                        user_location=user_location,
                        places=places,
                        transportation_mode=transportation_mode,
                        max_time_minutes=max_time_minutes,
                        target_places=target_places,
                        first_place_idx=_first_idx,
                        current_datetime=current_datetime,
                        distance_matrix=distance_matrix,
                        max_distance=max_distance
                    )

                if _candidate is not None and len(_candidate.get("places", [])) >= _MIN_POI:
                    route_1 = _candidate
                    print(
                        f"  ✅ Route hợp lệ ({len(_candidate['places'])} POI) "
                        f"tìm được ở lần thử {_attempt + 1} "
                        f"(stay_reduction={_stay_reduction:.0f} phút)"
                    )
                    break  # Thoát vòng lặp trong, giữ stay_time_reduction hiện tại

            if route_1 is not None:
                break  # Đã có route hợp lệ, thoát vòng lặp ngoài

            _best_count = 0  # chỉ để in log
            print(
                f"  ⚠️  Cả {_MAX_ATTEMPTS} lần thử đều không đủ {_MIN_POI} POI. "
                f"Giảm stay_time thêm {_REDUCTION_STEP} phút và thử lại..."
            )
            _stay_reduction += _REDUCTION_STEP

        if route_1 is None:
            print(
                f"  ❌ Không tìm được route >= {_MIN_POI} POI "
                f"dù đã giảm stay_time tới {_MAX_REDUCTION:.0f} phút."
            )
            self.calculator.stay_time_reduction = 0.0
            return []

        all_routes = [route_1]
        seen_place_sets = {tuple(sorted(route_1["route"]))}
        
        print(f"🎯 Route 1: {len(route_1['route'])} POI, total_score={route_1['total_score']:.2f}")
        
        # ================================================================
        # Xây dựng route 2, 3, ... với cùng logic select_first_poi
        # - Giữ nguyên stay_time_reduction đã xác lập lúc build route_1
        # - Mỗi route mới: gọi select_first_poi với exclude_indices = tất cả
        #   first POI đã dùng ở các route trước → đúng filter meal/cafe/opening
        # - Thử tối đa _MAX_ATTEMPTS candidates cho mỗi route; nếu candidate nào
        #   trả về >= 3 POI và đủ khác biệt (>= 2 POI khác) thì chấp nhận
        # ================================================================
        if max_routes > 1:
            # Tập hợp first POI đã dùng, bắt đầu từ route_1
            _used_first_pois: set = {route_1["route"][0]}

            while len(all_routes) < max_routes:
                # Lấy tối đa _MAX_ATTEMPTS POI xuất phát mới (chưa dùng, đúng logic)
                _candidates_n: list = []
                _exclude_n: set = _used_first_pois.copy()
                for _ in range(_MAX_ATTEMPTS):
                    _idx_n, _ = _builder_ref.select_first_poi(
                        places=places,
                        first_place_idx=None,
                        distance_matrix=distance_matrix,
                        max_distance=max_distance,
                        transportation_mode=transportation_mode,
                        current_datetime=current_datetime,
                        should_insert_restaurant_for_meal=_meal_info["should_insert_restaurant_for_meal"],
                        meal_windows=_meal_info["meal_windows"],
                        should_insert_cafe=_meal_info.get("should_insert_cafe", False),
                        exclude_indices=_exclude_n
                    )
                    if _idx_n is None:
                        break
                    _candidates_n.append(_idx_n)
                    _exclude_n.add(_idx_n)

                if not _candidates_n:
                    break  # Không còn POI xuất phát hợp lệ nào

                _found_next = False
                for _first_idx_n in _candidates_n:
                    if duration_mode:
                        route_result = self.duration_builder.build_route(
                            user_location=user_location,
                            places=places,
                            transportation_mode=transportation_mode,
                            max_time_minutes=max_time_minutes,
                            first_place_idx=_first_idx_n,
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
                            first_place_idx=_first_idx_n,
                            current_datetime=current_datetime,
                            distance_matrix=distance_matrix,
                            max_distance=max_distance
                        )

                    if route_result is None or len(route_result.get("places", [])) < _MIN_POI:
                        _used_first_pois.add(_first_idx_n)  # Đánh dấu đã thử, không dùng lại
                        continue

                    place_set_key = tuple(sorted(route_result["route"]))
                    if place_set_key in seen_place_sets:
                        _used_first_pois.add(_first_idx_n)
                        continue

                    is_different_enough = all(
                        len(set(route_result["route"]).symmetric_difference(set(r["route"]))) >= 2
                        for r in all_routes
                    )
                    if not is_different_enough:
                        _used_first_pois.add(_first_idx_n)
                        continue

                    seen_place_sets.add(place_set_key)
                    all_routes.append(route_result)
                    _used_first_pois.add(_first_idx_n)
                    _found_next = True
                    print(
                        f"🎯 Route {len(all_routes)}: {len(route_result['route'])} POI, "
                        f"total_score={route_result['total_score']:.2f}, "
                        f"first_poi={_first_idx_n}"
                    )
                    break  # Đã có route mới, chuyển vòng ngoài

                if not _found_next:
                    break  # Không tìm được route đủ điều kiện, dừng
        
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
        
        self.calculator.stay_time_reduction = 0.0  # Reset sau khi hoàn thành build_routes
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
