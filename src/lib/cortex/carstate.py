import datetime
import math

from time import time
from src.lib.cortex.navigation import Navigator
from typing import List, Tuple

from src.config import get_config

config = get_config()


if config["speed"]:
    activity_config = {
        "nodes": [[86, 220], [221, 85]],  # [],[]],
        "activity": ["navigation", "finish"]
    }
else:
    activity_config = {
        "nodes": [[38, 15], [72, 5]],
        "activity": ["navigation", "nav2"]
    }
#     activity_config = {
#     "nodes": [
#         [86, 78],
#         [87, 42],
#         [98, 1],
#         [111, 71],
#         [124, 158],
#         [159, 226],
#         [227, 345],
#     ],
#     "activity": [
#         "navigation",
#         "priority",
#         "stop",
#         "priority2",
#         "navigation2",
#         "parking",
#         "tohighway",
#     ],
# }
#   activity_config = {
#    "nodes":[[86,158],[159,226],[227,345],[346,105],[106,111],[70,85]],
#    "activity":["navigation","parking","tohighway","highway","finish","finish2"]
# }

print(activity_config)
# car length originally 0.365
# vmax=0.20


class CarState:
    def __init__(self, max_v=0.20, dt=0.13, car_len=0.26, **kwargs) -> None:

        self.max_v = max_v
        # position data
        # 0.75, 4.8
        self.x = 0.8
        self.y = 14.8
        self.yaw = 1.57
        self.pitch = 0
        self.roll = 0
        self.car_len = car_len
        self.rear_x = self.x - ((car_len / 2) * math.cos(-self.yaw))
        self.rear_y = self.y - ((car_len / 2) * math.sin(-self.yaw))
        self.f_x = 0
        self.f_y = 0

        self.target_x = None
        self.target_y = None

        self.navigator = Navigator(activity_config)
        # plan path -> self.navigator.plan_path(self.x,self.y,self.yaw)
        # current node -> self.navigator.get_current_node(self.x, self.y, self.yaw)
        self.last_update_time = time()

        # lane keeping and cs
        self.lanekeeping_angle = 0.0
        self.cs_angle = 0.0

        # intersection detected
        self.detected_intersection = False

        self.parkingcoords = (2.94, 2.09)

        # sign detection
        self.detected = {
            "car": (False, 0, (-1, 1)),
            "crosswalk": (False, 0, (-1, 1)),
            "highway_entry": (False, 0, (-1, 1)),
            "highway_exit": (False, 0, (-1, 1)),
            "no_entry": (False, 0, (-1, 1)),
            "onewayroad": (False, 0, (-1, 1)),
            "parking": (False, 0, (-1, 1)),
            "pedestrian": (False, 0, (-1, 1)),
            "priority": (False, 0, (-1, 1)),
            "roadblock": (False, 0, (-1, 1)),
            "roundabout": (False, 0, (-1, 1)),
            "stop": (False, 0, (-1, 1)),
            "trafficlight": (False, 0, (-1, 1)),
            "doll": (False, 0, (-1, 1))
        }

        # distance sensor
        self.front_distance = float("inf")
        self.side_distance = float("inf")

        self.target_ind = None
        # traffic light semaphore
        self.tl = {"s0": 0, "s1": 0, "s2": 0, "s3": 0}

        # active behavious
        self.active_behaviours = []

        # navigation (control sys)
        self.current_target = (0, 0)
        self.can_overtake = False
        self.current_ptype = ""

        # goal
        self.goal = (float("inf"), float("inf"))
        # control parameters
        self.steering_angle = 0.0
        self.v = max_v
        # self.priority_speed = 0.15
        self.priority_speed = 0.15
        self.highway_speed = 0.275

        # activity type

        self.activity_type = None
        self.car_len = car_len

    def calc_distance(self, point_x: float, point_y: float) -> float:
        dx = self.x - point_x
        dy = self.y - point_y
        # print(dx,dy)
        return math.hypot(dx, dy)

    def check_goal_reached(self) -> bool:
        return self.calc_distance(*self.goal) < 0.01

    def calc_distance_target_node(self) -> float:
        return self.calc_distance(*self.current_target)

    def update_pos(
        self, x: float, y: float, yaw: float, pitch: float, roll: float
    ) -> None:
        self.last_update_time = time()
        self.x = x
        self.y = y
        self.yaw = yaw
        self.pitch = pitch
        self.roll = roll
        self.rear_x = self.x - ((self.car_len / 2) * math.cos(-self.yaw))
        self.rear_y = self.y - ((self.car_len / 2) * math.sin(-self.yaw))

    def update_pos_noloc(self):
        # Use Of Inverted Yaw Here
        dt = time() - self.last_update_time
        self.last_update_time = time()
        self.x = self.x + self.v * math.cos(-self.yaw) * dt
        self.y = self.y + self.v * math.sin(-self.yaw) * dt
        self.yaw = (
            self.yaw
            - self.v / self.car_len *
            math.tan(self.steering_angle * math.pi / 180) * dt
        )
        self.rear_x = self.x - ((self.car_len / 2) * math.cos(-self.yaw))
        self.rear_y = self.y - ((self.car_len / 2) * math.sin(-self.yaw))

    def update_intersection(self, detected_intersection: bool) -> None:
        self.detected_intersection = detected_intersection

    def update_lk_angle(self, lk_angle: float) -> None:
        self.lanekeeping_angle = lk_angle

    def update_object_det(self, front_distance: float, side_distance: float) -> None:
        self.front_distance = front_distance
        self.side_distance = side_distance

    def update_detected(self, detections: dict):
        for c in self.detected.keys():
            if c in detections:
                self.detected[c] = (True, detections[c])
            else:
                self.detected[c] = (False, 0, (-1, -1))

    def update_tl(self, tl):
        self.tl = tl

    def asdict(self) -> dict:
        return {
            "x": float(self.x),
            "y": float(self.y),
            "yaw": float(self.yaw),
            "v": float(self.v),
            "pitch": float(self.pitch),
            "roll": float(self.roll),
            "rear_x": float(self.rear_x),
            "rear_y": float(self.rear_y),
            "target_x": 0,  # float(self.target_x),
            "target_y": 0,  # float(self.target_y),
            "target_idx": 0,  # float(self.target_ind),
            "lk_angle": float(self.lanekeeping_angle),
            "cs_angle": float(self.cs_angle),
            "front_distance": 0,  # float(self.front_distance),
            "side_distance": 0,  # float(self.side_distance),
            "current_ptype": self.current_ptype,
            "current_target": self.current_target,
            "detected_intersection": self.detected_intersection,
            "car_detected": self.detected["car"],
            "crosswalk": self.detected["crosswalk"],
            "highway_entry": self.detected["highway_entry"],
            "highway_exit": self.detected["highway_exit"],
            "no_entry": self.detected["no_entry"],
            "onewayroad": self.detected["onewayroad"],
            "parking": self.detected["parking"],
            "pedestrian": self.detected["pedestrian"],
            "priority": self.detected["priority"],
            "roadblock": self.detected["roadblock"],
            "roundabout": self.detected["roundabout"],
            "stop": self.detected["stop"],
            "trafficlight": self.detected["trafficlight"],
            "active_behaviours": self.active_behaviours,
            "steering_angle": float(self.steering_angle),
        }
