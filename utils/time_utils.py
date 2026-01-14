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
    def has_enough_time_to_stay(
        open_hours: List[Dict[str, Any]],
        arrival_datetime: datetime,
        stay_minutes: int
    ) -> bool:
        """
        Kiểm tra POI có đủ thời gian để tham quan hay không
        (Cả arrival_time VÀ departure_time phải nằm trong opening_hours)
        
        Hỗ trợ trường hợp qua ngày mới:
        - POI mở cửa qua đêm (22h-02h)
        - User bắt đầu route gần nửa đêm (23h40)
        
        Args:
            open_hours: Danh sách giờ mở cửa
            arrival_datetime: Thời điểm đến POI
            stay_minutes: Thời gian tham quan (phút)
            
        Returns:
            True nếu có đủ thời gian (arrival + stay đều trong giờ mở cửa)
            False nếu không đủ thời gian (departure_time > close_time)
        """
        if not open_hours:
            return True  # Không có thông tin → giả sử luôn mở
        
        # Tính thời điểm rời đi
        departure_datetime = arrival_datetime + timedelta(minutes=stay_minutes)
        
        # Kiểm tra xem có chuyển ngày không
        is_cross_midnight = departure_datetime.date() != arrival_datetime.date()
        
        # Lấy tên ngày arrival và departure
        arrival_day_name = arrival_datetime.strftime('%A')
        departure_day_name = departure_datetime.strftime('%A')
        
        arrival_minutes = TimeUtils.time_to_minutes(arrival_datetime.hour, arrival_datetime.minute)
        departure_minutes = TimeUtils.time_to_minutes(departure_datetime.hour, departure_datetime.minute)
        
        # Trường hợp 1: KHÔNG qua ngày mới (cùng ngày)
        if not is_cross_midnight:
            # Tìm thông tin ngày arrival
            for day_info in open_hours:
                if day_info.get('day') == arrival_day_name:
                    hours_list = day_info.get('hours', [])
                    
                    # Kiểm tra từng khoảng thời gian trong ngày
                    for time_range in hours_list:
                        start_str = time_range.get('start', '00:00')
                        end_str = time_range.get('end', '23:59')
                        
                        start_hour, start_minute = TimeUtils.parse_time(start_str)
                        end_hour, end_minute = TimeUtils.parse_time(end_str)
                        
                        start_minutes = TimeUtils.time_to_minutes(start_hour, start_minute)
                        end_minutes = TimeUtils.time_to_minutes(end_hour, end_minute)
                        
                        # Kiểm tra CẢ arrival VÀ departure phải nằm trong [start, end]
                        if start_minutes <= arrival_minutes and departure_minutes <= end_minutes:
                            return True
                    
                    return False  # Có thông tin ngày nhưng không đủ thời gian
            
            return False  # Không tìm thấy thông tin ngày
        
        # Trường hợp 2: QUA ngày mới (arrival và departure khác ngày)
        # Cần kiểm tra:
        # - arrival_time phải nằm trong giờ mở cửa của ngày arrival
        # - departure_time phải nằm trong giờ mở cửa của ngày departure (ngày tiếp theo)
        
        # Check arrival time trong ngày đầu tiên
        arrival_valid = False
        for day_info in open_hours:
            if day_info.get('day') == arrival_day_name:
                hours_list = day_info.get('hours', [])
                
                for time_range in hours_list:
                    start_str = time_range.get('start', '00:00')
                    end_str = time_range.get('end', '23:59')
                    
                    start_hour, start_minute = TimeUtils.parse_time(start_str)
                    end_hour, end_minute = TimeUtils.parse_time(end_str)
                    
                    start_minutes = TimeUtils.time_to_minutes(start_hour, start_minute)
                    end_minutes = TimeUtils.time_to_minutes(end_hour, end_minute)
                    
                    # arrival_time phải >= start_time
                    # Với POI mở qua đêm (22h-02h), arrival lúc 23h50 phải nằm trong [22h00, 23h59]
                    if start_minutes <= arrival_minutes <= 1439:  # 1439 = 23h59
                        arrival_valid = True
                        break
                
                if arrival_valid:
                    break
        
        if not arrival_valid:
            return False  # arrival time không hợp lệ
        
        # Check departure time trong ngày tiếp theo
        departure_valid = False
        for day_info in open_hours:
            if day_info.get('day') == departure_day_name:
                hours_list = day_info.get('hours', [])
                
                for time_range in hours_list:
                    start_str = time_range.get('start', '00:00')
                    end_str = time_range.get('end', '23:59')
                    
                    start_hour, start_minute = TimeUtils.parse_time(start_str)
                    end_hour, end_minute = TimeUtils.parse_time(end_str)
                    
                    start_minutes = TimeUtils.time_to_minutes(start_hour, start_minute)
                    end_minutes = TimeUtils.time_to_minutes(end_hour, end_minute)
                    
                    # departure_time phải <= end_time
                    # Với POI mở qua đêm, departure lúc 00h20 phải nằm trong [00h00, 02h00]
                    if 0 <= departure_minutes <= end_minutes:
                        departure_valid = True
                        break
                
                if departure_valid:
                    break
        
        return departure_valid  # True nếu cả arrival và departure đều hợp lệ
    
    @staticmethod
    def overlaps_with_time_window(
        open_hours: List[Dict[str, Any]],
        start_datetime: datetime,
        end_datetime: datetime
    ) -> bool:
        """
        Kiểm tra POI có overlap với time window [start_datetime, end_datetime] không
        Hỗ trợ khoảng mở qua đêm (ví dụ 22:00-02:00).
        
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
                        
                        start_hour, start_minute = TimeUtils.parse_time(start_str)
                        end_hour, end_minute = TimeUtils.parse_time(end_str)
                        
                        # Tạo datetime cho khoảng mở cửa: xử lý trường hợp overnight (end < start)
                        poi_open_time = datetime.combine(current_date, datetime.min.time()).replace(
                            hour=start_hour, minute=start_minute
                        )
                        if TimeUtils.time_to_minutes(end_hour, end_minute) >= TimeUtils.time_to_minutes(start_hour, start_minute):
                            # cùng ngày
                            poi_close_time = datetime.combine(current_date, datetime.min.time()).replace(
                                hour=end_hour, minute=end_minute
                            )
                        else:
                            # qua đêm: close vào ngày tiếp theo
                            poi_close_time = datetime.combine(current_date + timedelta(days=1), datetime.min.time()).replace(
                                hour=end_hour, minute=end_minute
                            )
                        
                        # Kiểm tra overlap: max(start1, start2) < min(end1, end2)
                        overlap_start = max(start_datetime, poi_open_time)
                        overlap_end = min(end_datetime, poi_close_time)
                        
                        if overlap_start < overlap_end:
                            return True
            
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
    
    # validate_route_timing đã bị loại bỏ vì logic filter POI đã được áp dụng
    # ngay trong quá trình build route (xem route.py build_single_route_greedy)
    
    @staticmethod
    def check_overlap_with_meal_times(
        start_datetime: datetime,
        max_time_minutes: int
    ) -> Dict[str, Any]:
        """
        Kiểm tra xem [start_datetime, start_datetime + max_time_minutes] có overlap 
        ít nhất 1 tiếng với khung giờ ăn (12h-15h hoặc 18h30-22h) không
        
        Args:
            start_datetime: Thời điểm bắt đầu
            max_time_minutes: Tổng thời gian có (phút)
            
        Returns:
            Dict {
                "has_lunch_overlap": bool,
                "lunch_overlap_minutes": int,
                "has_dinner_overlap": bool, 
                "dinner_overlap_minutes": int,
                "needs_restaurant": bool  # True nếu có ít nhất 1 meal overlap >= 60 phút
            }
        """
        end_datetime = start_datetime + timedelta(minutes=max_time_minutes)
        
        # Định nghĩa khung giờ ăn
        lunch_start = start_datetime.replace(hour=12, minute=0, second=0, microsecond=0)
        lunch_end = start_datetime.replace(hour=15, minute=0, second=0, microsecond=0)
        dinner_start = start_datetime.replace(hour=18, minute=30, second=0, microsecond=0)
        dinner_end = start_datetime.replace(hour=22, minute=0, second=0, microsecond=0)
        
        # Kiểm tra overlap với lunch (12h-15h)
        lunch_overlap_start = max(start_datetime, lunch_start)
        lunch_overlap_end = min(end_datetime, lunch_end)
        lunch_overlap_minutes = max(0, int((lunch_overlap_end - lunch_overlap_start).total_seconds() / 60))
        
        # Kiểm tra overlap với dinner (18h30-22h)
        dinner_overlap_start = max(start_datetime, dinner_start)
        dinner_overlap_end = min(end_datetime, dinner_end)
        dinner_overlap_minutes = max(0, int((dinner_overlap_end - dinner_overlap_start).total_seconds() / 60))
        
        # Cần restaurant nếu có ít nhất 1 meal overlap >= 60 phút
        needs_restaurant = (lunch_overlap_minutes >= 60) or (dinner_overlap_minutes >= 60)
        
        return {
            "has_lunch_overlap": lunch_overlap_minutes > 0,
            "lunch_overlap_minutes": lunch_overlap_minutes,
            "has_dinner_overlap": dinner_overlap_minutes > 0,
            "dinner_overlap_minutes": dinner_overlap_minutes,
            "needs_restaurant": needs_restaurant,
            "lunch_window": (lunch_start, lunch_end) if lunch_overlap_minutes >= 60 else None,
            "dinner_window": (dinner_start, dinner_end) if dinner_overlap_minutes >= 60 else None
        }