"""BMW repair-group numbering used by the workshop manuals and the ETK parts catalogue.

Repair instructions in BMW/Bentley E30 manuals are numbered "GG SS NNN" (e.g. "11 31 005
Removing and installing camshaft"); the first two digits are the main group below.
"""

MAIN_GROUPS = {
    "00": "Maintenance and general data",
    "11": "Engine",
    "12": "Engine electrical system",
    "13": "Fuel preparation system",
    "16": "Fuel supply",
    "17": "Radiator / cooling",
    "18": "Exhaust system",
    "21": "Clutch",
    "22": "Engine and transmission suspension",
    "23": "Manual transmission",
    "24": "Automatic transmission",
    "25": "Gearshift",
    "26": "Drive shaft",
    "27": "Transfer box",
    "31": "Front axle",
    "32": "Steering",
    "33": "Rear axle",
    "34": "Brakes",
    "35": "Pedals",
    "36": "Wheels and tyres",
    "37": "Integrated suspension systems",
    "41": "Body shell",
    "51": "Body equipment",
    "52": "Seats",
    "54": "Sliding roof / folding top",
    "61": "General electrical system",
    "62": "Instruments",
    "63": "Lights",
    "64": "Heater and air conditioning",
    "65": "Radio, navigation, telephone",
    "66": "Comfort electronics",
    "71": "Equipment parts",
    "72": "Safety and seat belts",
    "81": "Retrofit",
    "82": "Accessories",
    "83": "Body workshop",
    "84": "Communication systems",
    "90": "Equipment",
    "91": "Engine (variants)",
    "99": "Miscellaneous",
}


def group_name(code: str) -> str:
    return MAIN_GROUPS.get(code, f"Group {code}")
