"""Demonstrācijas aprēķins, nevis būvkonstrukciju specifikācija."""
from dataclasses import dataclass
from math import ceil


@dataclass(frozen=True)
class Wall:
    length_m: float
    height_m: float
    openings_m2: float = 0.0
    stud_spacing_m: float = 0.5
    insulation_depth_m: float = 0.2


def calculate_wall(wall: Wall) -> dict:
    if wall.length_m <= 0 or wall.height_m <= 0:
        raise ValueError("Sienas izmēriem jābūt pozitīviem.")
    if wall.stud_spacing_m <= 0 or wall.insulation_depth_m <= 0:
        raise ValueError("Solis un izolācijas biezums jābūt pozitīviem.")
    gross = wall.length_m * wall.height_m
    if not 0 <= wall.openings_m2 < gross:
        raise ValueError("Ailu laukums ir nederīgs.")
    net = gross - wall.openings_m2
    return {
        "gross_area_m2": round(gross, 3),
        "net_area_m2": round(net, 3),
        "estimated_studs_pcs": ceil(wall.length_m / wall.stud_spacing_m) + 1,
        "approx_insulation_m3": round(net * wall.insulation_depth_m, 3),
    }
