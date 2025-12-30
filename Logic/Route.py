"""
Route Builder Service
Xây dựng lộ trình tối ưu từ danh sách địa điểm sử dụng thuật toán Greedy
"""

import math
from typing import List, Dict, Any, Tuple, Optional
from config.config import Config


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
    DEFAULT_STAY_TIME = 30
    
    # Tốc độ di chuyển theo phương tiện (km/h)
    TRANSPORTATION_SPEEDS = {
        "WALKING": 5,
        "BICYCLING": 15,
        "TRANSIT": 25,
        "FLEXIBLE": 30,
        "DRIVING": 40
    }
    
    def __init__(self):
        """Khởi tạo RouteBuilder"""
        pass
    
    def calculate_distance_haversine(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Tính khoảng cách Haversine giữa 2 điểm (km)
        NHANH HƠN PostGIS rất nhiều (không cần connect DB)
        Đủ chính xác cho khoảng cách ngắn (< 100km)
        
        Args:
            lat1, lon1: Tọa độ điểm 1
            lat2, lon2: Tọa độ điểm 2
            
        Returns:
            Khoảng cách (km)
        """
        R = 6371  # Bán kính trái đất (km)
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c
    
    def calculate_travel_time(self, distance_km: float, transportation_mode: str) -> float:
        """
        Tính thời gian di chuyển (phút)
        
        Args:
            distance_km: Khoảng cách (km)
            transportation_mode: Phương tiện
            
        Returns:
            Thời gian (phút)
        """
        speed = self.TRANSPORTATION_SPEEDS.get(transportation_mode.upper(), 30)
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
    
    def build_distance_matrix(
        self,
        user_location: Tuple[float, float],
        places: List[Dict[str, Any]]
    ) -> List[List[float]]:
        """
        Xây dựng ma trận khoảng cách sử dụng Haversine (NHANH)
        
        Args:
            user_location: (lat, lon) của user
            places: Danh sách địa điểm
            
        Returns:
            Ma trận khoảng cách [n+1][n+1] (index 0 là user)
        """
        n = len(places)
        matrix = [[0.0] * (n + 1) for _ in range(n + 1)]
        
        # Tọa độ tất cả điểm (0 = user, 1-n = places)
        coords = [user_location] + [(p["lat"], p["lon"]) for p in places]
        
        # Tính khoảng cách giữa mọi cặp điểm bằng Haversine (NHANH)
        for i in range(n + 1):
            for j in range(i + 1, n + 1):  # Chỉ tính nửa trên, copy sang nửa dưới
                dist = self.calculate_distance_haversine(
                    coords[i][0], coords[i][1],
                    coords[j][0], coords[j][1]
                )
                matrix[i][j] = dist
                matrix[j][i] = dist  # Ma trận đối xứng
        
        return matrix
    
    def calculate_combined_score(
        self,
        place_idx: int,
        current_pos: int,
        places: List[Dict[str, Any]],
        distance_matrix: List[List[float]],
        max_distance: float,
        score_weight: float = 0.7,
        distance_weight: float = 0.3
    ) -> float:
        """
        Tính điểm kết hợp: score + khoảng cách
        
        Args:
            place_idx: Index địa điểm cần tính (0-based trong places list)
            current_pos: Vị trí hiện tại (0 = user, 1-n = places)
            places: Danh sách địa điểm
            distance_matrix: Ma trận khoảng cách
            max_distance: Khoảng cách tối đa để normalize
            score_weight: Trọng số cho score (mặc định 0.7)
            distance_weight: Trọng số cho khoảng cách (mặc định 0.3)
            
        Returns:
            Combined score (cao hơn = tốt hơn)
        """
        # Normalize score (0-1)
        normalized_score = places[place_idx]["score"]
        
        # Khoảng cách từ current_pos đến place (index trong matrix = place_idx + 1)
        distance = distance_matrix[current_pos][place_idx + 1]
        
        # Normalize distance
        normalized_distance = distance / max_distance if max_distance > 0 else 0
        
        # Distance score: gần = điểm cao (đảo ngược)
        distance_score = 1 - normalized_distance
        
        # Kết hợp
        combined = score_weight * normalized_score + distance_weight * distance_score
        
        return combined
    
    def build_single_route_greedy(
        self,
        user_location: Tuple[float, float],
        places: List[Dict[str, Any]],
        transportation_mode: str,
        max_time_minutes: int,
        target_places: int,
        first_place_idx: Optional[int] = None
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
            
        Returns:
            Dict chứa thông tin lộ trình hoặc None nếu không khả thi
        """
        if target_places > len(places):
            return None
        
        # 1. Xây dựng distance matrix
        distance_matrix = self.build_distance_matrix(user_location, places)
        
        # Tìm max distance để normalize
        max_distance = max(max(row) for row in distance_matrix)
        
        # Tính radius (khoảng cách xa nhất từ user)
        max_radius = max(distance_matrix[0][1:])
        return_threshold = 0.2 * max_radius
        
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
                combined = self.calculate_combined_score(
                    place_idx=i,
                    current_pos=0,
                    places=places,
                    distance_matrix=distance_matrix,
                    max_distance=max_distance
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
        
        # 3. Chọn các điểm tiếp theo (trừ điểm cuối)
        for step in range(target_places - 2):
            best_next = None
            best_next_score = -1
            
            for i, place in enumerate(places):
                if i in visited:
                    continue
                
                combined = self.calculate_combined_score(
                    place_idx=i,
                    current_pos=current_pos,
                    places=places,
                    distance_matrix=distance_matrix,
                    max_distance=max_distance
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
            travel_time = self.calculate_travel_time(
                distance_matrix[current_pos][best_next + 1],
                transportation_mode
            )
            stay_time = self.get_stay_time(places[best_next].get("poi_type", ""))
            total_travel_time += travel_time
            total_stay_time += stay_time
            current_pos = best_next + 1
        
        # 4. Chọn điểm cuối (gần user)
        best_last = None
        best_last_score = -1
        
        for i, place in enumerate(places):
            if i in visited:
                continue
            
            # Kiểm tra khoảng cách đến user
            dist_to_user = distance_matrix[i + 1][0]
            if dist_to_user > return_threshold:
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
            
            # Ưu tiên score hơn vì đã gần user
            combined = self.calculate_combined_score(
                place_idx=i,
                current_pos=current_pos,
                places=places,
                distance_matrix=distance_matrix,
                max_distance=max_distance,
                score_weight=0.8,
                distance_weight=0.2
            )
            
            if combined > best_last_score:
                best_last_score = combined
                best_last = i
        
        # Nếu không tìm được điểm cuối gần user, thử tìm bất kỳ điểm nào
        if best_last is None:
            for i, place in enumerate(places):
                if i in visited:
                    continue
                
                temp_travel = total_travel_time + self.calculate_travel_time(
                    distance_matrix[current_pos][i + 1],
                    transportation_mode
                )
                temp_stay = total_stay_time + self.get_stay_time(places[i].get("poi_type", ""))
                return_time = self.calculate_travel_time(
                    distance_matrix[i + 1][0],
                    transportation_mode
                )
                
                if temp_travel + temp_stay + return_time > max_time_minutes:
                    continue
                
                combined = places[i]["score"]
                if combined > best_last_score:
                    best_last_score = combined
                    best_last = i
        
        if best_last is None:
            if len(route) < 3:
                return None
        else:
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
            
            route_places.append({
                "place_id": place["id"],
                "place_name": place["name"],
                "poi_type": place.get("poi_type", ""),
                "address": place.get("address", ""),
                "lat": place["lat"],
                "lon": place["lon"],
                "score": place["score"],
                "travel_time_minutes": round(travel_time, 1),
                "stay_time_minutes": stay_time
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
        max_routes: int = 3
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
            
        Returns:
            List các lộ trình tốt nhất (đã loại bỏ trùng lặp)
        """
        if not places:
            return []
        
        if target_places > len(places):
            target_places = len(places)
        
        # Xây dựng distance matrix 1 lần
        distance_matrix = self.build_distance_matrix(user_location, places)
        max_distance = max(max(row) for row in distance_matrix)
        
        # Tìm địa điểm có SCORE thuần túy cao nhất (không quan tâm khoảng cách)
        best_score_idx = 0
        best_score = places[0]["score"]
        for i, place in enumerate(places):
            if place["score"] > best_score:
                best_score = place["score"]
                best_score_idx = i
        
        print(f"🎯 Điểm đầu tiên BẮT BUỘC (score thuần túy cao nhất): {places[best_score_idx]['name']} (score={places[best_score_idx]['score']})")
        
        # Xây dựng route đầu tiên từ điểm có score cao nhất
        route_1 = self.build_single_route_greedy(
            user_location=user_location,
            places=places,
            transportation_mode=transportation_mode,
            max_time_minutes=max_time_minutes,
            target_places=target_places,
            first_place_idx=best_score_idx
        )
        
        if route_1 is None:
            return []
        
        all_routes = [route_1]
        seen_place_sets = {tuple(sorted(route_1["route"]))}
        
        # Nếu cần nhiều hơn 1 route, tính combined_score cho các điểm xuất phát khác
        if max_routes > 1:
            # Tính combined_score cho tất cả địa điểm (để chọn điểm xuất phát cho routes khác)
            first_candidates = []
            for i, place in enumerate(places):
                combined = self.calculate_combined_score(
                    place_idx=i,
                    current_pos=0,
                    places=places,
                    distance_matrix=distance_matrix,
                    max_distance=max_distance
                )
                first_candidates.append((i, combined))
            
            first_candidates.sort(key=lambda x: x[1], reverse=True)
            # Thử các điểm xuất phát khác (vẫn ưu tiên score cao)
            num_candidates_to_try = min(len(places), max(10, max_routes * 3))
            
            for first_idx, _ in first_candidates[1:num_candidates_to_try]:
                # Dừng nếu đã đủ số routes
                if len(all_routes) >= max_routes:
                    break
                
                route_result = self.build_single_route_greedy(
                    user_location=user_location,
                    places=places,
                    transportation_mode=transportation_mode,
                    max_time_minutes=max_time_minutes,
                    target_places=target_places,
                    first_place_idx=first_idx
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
            for order, place in enumerate(route["places"], 1):
                place_data = place.copy()
                place_data["route_id"] = idx
                place_data["order"] = order  # Số thứ tự di chuyển (1, 2, 3, ...)
                places_with_metadata.append(place_data)
            
            result.append({
                "route_id": idx,
                "total_time_minutes": route["total_time_minutes"],
                "travel_time_minutes": route["travel_time_minutes"],
                "stay_time_minutes": route["stay_time_minutes"],
                "total_score": route["total_score"],
                "avg_score": route["avg_score"],
                "efficiency": route["efficiency"],
                "places": places_with_metadata
            })
        
        return result
