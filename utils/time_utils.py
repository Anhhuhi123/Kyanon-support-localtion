"""
Time Utilities
Xử lý logic liên quan đến thời gian mở cửa của POI
"""
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple


class TimeUtils:
    """Utility class xử lý thời gian mở cửa của POI"""
    
    # Mapping từ tên ngày sang số (Monday=0, Sunday=6)
    DAY_MAP = {
        'Monday': 0,
        'Tuesday': 1,
        'Wednesday': 2,
        'Thursday': 3,
        'Friday': 4,
        'Saturday': 5,
        'Sunday': 6
    }
    
    @staticmethod
    def parse_time(time_str: str) -> Tuple[int, int]:
        """
        Parse time string 'HH:MM' thành (hour, minute)
        
        Args:
            time_str: Time string format 'HH:MM'
            
        Returns:
            Tuple (hour, minute)
        """
        try:
            hour, minute = map(int, time_str.split(':'))
            return hour, minute
        except:
            return 0, 0
    
    @staticmethod
    def time_to_minutes(hour: int, minute: int) -> int:
        """
        Chuyển (hour, minute) thành số phút từ 00:00
        
        Args:
            hour: Giờ (0-23)
            minute: Phút (0-59)
            
        Returns:
            Số phút từ 00:00
        """
        return hour * 60 + minute
    
    @staticmethod
    def minutes_to_time(minutes: int) -> str:
        """
        Chuyển số phút từ 00:00 thành string 'HH:MM'
        
        Args:
            minutes: Số phút từ 00:00
            
        Returns:
            Time string 'HH:MM'
        """
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours:02d}:{mins:02d}"
    
    @staticmethod
    def is_open_at_time(
        open_hours: List[Dict[str, Any]],
        check_datetime: datetime
    ) -> bool:
        """
        Kiểm tra POI có mở cửa tại thời điểm cụ thể không
        
        Args:
            open_hours: Danh sách giờ mở cửa theo format:
                [{'day': 'Monday', 'hours': [{'start': '08:00', 'end': '22:00'}]}, ...]
            check_datetime: Thời điểm cần kiểm tra
            
        Returns:
            True nếu POI mở cửa, False nếu đóng cửa
        """
        if not open_hours:
            return True  # Không có thông tin → giả sử luôn mở
        
        # Lấy tên ngày từ datetime
        day_name = check_datetime.strftime('%A')  # Monday, Tuesday, ...
        check_minutes = TimeUtils.time_to_minutes(check_datetime.hour, check_datetime.minute)
        
        # Tìm thông tin ngày tương ứng
        for day_info in open_hours:
            if day_info.get('day') == day_name:
                hours_list = day_info.get('hours', [])
                
                # Kiểm tra từng khoảng thời gian trong ngày
                for time_range in hours_list:
                    start_str = time_range.get('start', '00:00')
                    end_str = time_range.get('end', '23:59')
                    
                    start_hour, start_minute = TimeUtils.parse_time(start_str)
                    end_hour, end_minute = TimeUtils.parse_time(end_str)
                    
                    start_minutes = TimeUtils.time_to_minutes(start_hour, start_minute)
                    end_minutes = TimeUtils.time_to_minutes(end_hour, end_minute)
                    
                    # Kiểm tra nếu check_time nằm trong khoảng [start, end]
                    if start_minutes <= check_minutes <= end_minutes:
                        return True
                
                return False  # Có thông tin ngày nhưng không match → đóng cửa
        
        return False  # Không tìm thấy thông tin ngày → giả sử đóng cửa
    
    @staticmethod
    def overlaps_with_time_window(
        open_hours: List[Dict[str, Any]],
        start_datetime: datetime,
        end_datetime: datetime
    ) -> bool:
        """
        Kiểm tra POI có overlap với time window [start_datetime, end_datetime] không
        
        Args:
            open_hours: Danh sách giờ mở cửa
            start_datetime: Thời điểm bắt đầu window
            end_datetime: Thời điểm kết thúc window
            
        Returns:
            True nếu có overlap (POI mở cửa trong ít nhất 1 phần của window)
        """
        if not open_hours:
            return True  # Không có thông tin → giả sử luôn mở
        
        # Kiểm tra từng ngày trong window
        current_date = start_datetime.date()
        end_date = end_datetime.date()
        
        while current_date <= end_date:
            day_name = current_date.strftime('%A')
            
            # Tìm thông tin ngày tương ứng
            for day_info in open_hours:
                if day_info.get('day') == day_name:
                    hours_list = day_info.get('hours', [])
                    
                    for time_range in hours_list:
                        start_str = time_range.get('start', '00:00')
                        end_str = time_range.get('end', '23:59')
                        
                        # Tạo datetime cho khoảng thời gian mở cửa trong ngày
                        start_hour, start_minute = TimeUtils.parse_time(start_str)
                        end_hour, end_minute = TimeUtils.parse_time(end_str)
                        
                        poi_open_time = datetime.combine(current_date, datetime.min.time()).replace(
                            hour=start_hour, minute=start_minute
                        )
                        poi_close_time = datetime.combine(current_date, datetime.min.time()).replace(
                            hour=end_hour, minute=end_minute
                        )
                        
                        # Kiểm tra overlap: [start_datetime, end_datetime] vs [poi_open_time, poi_close_time]
                        # Có overlap nếu: max(start1, start2) < min(end1, end2)
                        overlap_start = max(start_datetime, poi_open_time)
                        overlap_end = min(end_datetime, poi_close_time)
                        
                        if overlap_start < overlap_end:
                            return True
            
            # Chuyển sang ngày tiếp theo
            current_date += timedelta(days=1)
        
        return False
    
    @staticmethod
    def filter_open_pois(
        pois: List[Dict[str, Any]],
        start_datetime: datetime,
        end_datetime: datetime
    ) -> List[Dict[str, Any]]:
        """
        Lọc danh sách POI chỉ giữ những POI có overlap với time window
        
        Args:
            pois: Danh sách POI (mỗi POI phải có field 'open_hours')
            start_datetime: Thời điểm bắt đầu
            end_datetime: Thời điểm kết thúc
            
        Returns:
            Danh sách POI đã lọc
        """
        filtered_pois = []
        
        for poi in pois:
            open_hours = poi.get('open_hours')
            
            if TimeUtils.overlaps_with_time_window(open_hours, start_datetime, end_datetime):
                filtered_pois.append(poi)
        
        return filtered_pois
    
    @staticmethod
    def get_arrival_time(
        start_datetime: datetime,
        travel_time_minutes: float
    ) -> datetime:
        """
        Tính thời điểm đến tại POI
        
        Args:
            start_datetime: Thời điểm bắt đầu
            travel_time_minutes: Thời gian di chuyển (phút)
            
        Returns:
            Thời điểm đến
        """
        return start_datetime + timedelta(minutes=travel_time_minutes)
    
    @staticmethod
    def get_opening_hours_for_day(
        open_hours: List[Dict[str, Any]],
        target_datetime: datetime
    ) -> Optional[Dict[str, Any]]:
        """
        Lấy thông tin opening hours cho ngày cụ thể
        
        Args:
            open_hours: Danh sách opening hours của POI
            target_datetime: Ngày cần lấy thông tin
            
        Returns:
            Dict chứa thông tin mở cửa cho ngày đó:
            {
                "day": "Monday",
                "date": "2026-01-13",
                "is_open": True,
                "hours": [{"start": "08:00", "end": "22:00"}]
            }
            Hoặc None nếu không có thông tin
        """
        if not open_hours:
            return {
                "day": target_datetime.strftime('%A'),
                "date": target_datetime.strftime('%Y-%m-%d'),
                "is_open": True,
                "hours": [{"start": "00:00", "end": "23:59"}],
                "note": "No opening hours data (assumed always open)"
            }
        
        day_name = target_datetime.strftime('%A')
        
        # Tìm thông tin cho ngày cụ thể
        for day_info in open_hours:
            if day_info.get('day') == day_name:
                hours_list = day_info.get('hours', [])
                
                return {
                    "day": day_name,
                    "date": target_datetime.strftime('%Y-%m-%d'),
                    "is_open": len(hours_list) > 0,
                    "hours": hours_list
                }
        
        # Không tìm thấy thông tin cho ngày này
        return {
            "day": day_name,
            "date": target_datetime.strftime('%Y-%m-%d'),
            "is_open": False,
            "hours": []
        }
    
    @staticmethod
    def validate_route_timing(
        route: List[Dict[str, Any]],
        start_datetime: datetime,
        transportation_mode: str,
        distance_matrix: List[List[float]] = None,
        default_stay_minutes: int = 30
    ) -> Tuple[bool, List[str]]:
        """
        Kiểm tra xem route có hợp lệ về mặt thời gian không
        
        Args:
            route: Danh sách POI trong route (mỗi POI có 'open_hours')
            start_datetime: Thời điểm bắt đầu route
            transportation_mode: Phương tiện di chuyển
            distance_matrix: Ma trận khoảng cách (km) giữa các POI
            default_stay_minutes: Thời gian ở mỗi POI (phút)
            
        Returns:
            (is_valid, error_messages)
        """
        # Import RouteBuilder để lấy travel time calculation
        from radius_logic.route import RouteBuilder
        
        route_builder = RouteBuilder()
        current_time = start_datetime
        errors = []
        
        for idx, poi in enumerate(route):
            # Tính thời gian di chuyển đến POI này
            if idx == 0:
                # POI đầu tiên: tính từ user location
                if distance_matrix and len(distance_matrix) > 0:
                    distance_km = distance_matrix[0][idx + 1]  # distance_matrix[0] là user
                    travel_time = route_builder.calculate_travel_time(distance_km, transportation_mode)
                else:
                    travel_time = 0  # Không có thông tin → skip
            else:
                # POI tiếp theo: tính từ POI trước
                if distance_matrix and len(distance_matrix) > idx:
                    prev_idx = idx  # idx trong distance_matrix (có user ở index 0)
                    curr_idx = idx + 1
                    distance_km = distance_matrix[prev_idx][curr_idx]
                    travel_time = route_builder.calculate_travel_time(distance_km, transportation_mode)
                else:
                    travel_time = 0
            
            # Thời điểm đến POI
            arrival_time = current_time + timedelta(minutes=travel_time)
            
            # Kiểm tra POI có mở cửa không
            open_hours = poi.get('open_hours')
            if not TimeUtils.is_open_at_time(open_hours, arrival_time):
                poi_name = poi.get('name', poi.get('id', f'POI #{idx+1}'))
                errors.append(
                    f"POI '{poi_name}' is closed at {arrival_time.strftime('%A %H:%M')}"
                )
            
            # Cập nhật thời gian hiện tại (sau khi tham quan)
            stay_time = default_stay_minutes
            current_time = arrival_time + timedelta(minutes=stay_time)
        
        return len(errors) == 0, errors
