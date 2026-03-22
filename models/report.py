from enum import Enum
from typing import List

from pydantic import BaseModel


class ExportFormat(str, Enum):
    CSV = "csv"
    JSON = "json"


class PeakHourItem(BaseModel):
    hour: int
    count: int


class ReportSummary(BaseModel):
    total_entries: int
    total_reservations: int
    peak_hours: List[PeakHourItem]


class DailyUsageItem(BaseModel):
    date: str
    total_entries: int
    total_exits: int
    total_reservations: int


class DailyUsageResponse(BaseModel):
    start_date: str
    end_date: str
    items: List[DailyUsageItem]
