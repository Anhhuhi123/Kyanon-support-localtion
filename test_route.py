import json
import math
import matplotlib.pyplot as plt

# ====== NHẬP JSON TỪ CMD ======
print("Paste JSON vào đây, kết thúc bằng dòng trống rồi Enter:")

lines = []
while True:
    line = input()
    if line.strip() == "":
        break
    lines.append(line)

json_text = "\n".join(lines)
data = json.loads(json_text)
# ==============================


def bearing(p1, p2):
    lat1, lon1 = math.radians(p1["lat"]), math.radians(p1["lon"])
    lat2, lon2 = math.radians(p2["lat"]), math.radians(p2["lon"])

    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    brng = math.degrees(math.atan2(x, y))
    return (brng + 360) % 360


def angle_diff(a1, a2):
    diff = abs(a2 - a1)
    return min(diff, 360 - diff)


ORTHO_MIN = 70
ORTHO_MAX = 110


for route in data["routes"]:
    places = route["places"]

    lats = [p["lat"] for p in places]
    lons = [p["lon"] for p in places]

    plt.figure(figsize=(7, 7))
    plt.plot(lons, lats, "-o")

    for i, p in enumerate(places):
        plt.text(p["lon"], p["lat"], f"{i+1}", fontsize=9, ha="right")

    for i in range(1, len(places) - 1):
        b1 = bearing(places[i-1], places[i])
        b2 = bearing(places[i], places[i+1])
        angle = angle_diff(b1, b2)

        color = "red" if ORTHO_MIN <= angle <= ORTHO_MAX else "gray"

        plt.text(
            places[i]["lon"],
            places[i]["lat"],
            f"{int(angle)}°",
            color=color,
            fontsize=9,
            ha="left"
        )

    plt.title(f"Route {route['route_id']} – POI geometry")
    plt.xlabel("Longitude")
    plt.ylabel("Latitude")
    plt.grid(True)
    plt.axis("equal")
    plt.show()
