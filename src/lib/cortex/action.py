import time

from src.lib.cortex.control_sys import Pure_Pursuit
import math
import joblib

from src.lib.cortex.carstate import CarState
import pathlib
from src.lib.cortex.PID import PID
from loguru import logger
from src.lib.cortex.cubic_spline_planner import calc_spline_course

# Extra because no path planning at start
####################################################################################
# data_path = pathlib.Path(                                                        #
#     pathlib.Path(__file__).parent.parent.parent.resolve(), "data", "mid_course.z"#
# )                                                                                #
# data = joblib.load(data_path)                                                    #
# ptype = data["ptype"]                                                            #
# etype = data["etype"]                                                            #
# ptype = data[1]                                                                  #
# etype = data[2]                                                                  #
####################################################################################


def isLeft(A, B, isleftpoint):
    yd = math.atan2(B[1] - A[1], B[0] - A[0])
    yd2 = math.atan2(isleftpoint[1] - A[1], isleftpoint[0] - A[0])
    compute = yd - yd2
    # print(compute)
    if abs(compute) > math.pi:
        if compute > 0:
            compute = abs(compute) - 2 * math.pi
        else:
            compute = 2 * math.pi - abs(compute)
    if compute >= 0:
        return True
    else:
        return False


class BehaviourCallback:
    def __init__(self, **kwargs):
        pass

    def out_condition(self, **kwargs) -> bool:
        return False

    def toggle_condition(self, **kwargs) -> bool:
        return False

    def __call__(self, car_state):
        raise NotImplementedError

    def reset(self, **kwargs):
        pass

    def set(self, **kwargs):
        raise NotImplementedError


class TLBehaviour(BehaviourCallback):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.loc = {
            "s0": (1.1, 14),
            "s1": (2, 11),
            "s2": (3, 11),
            "s3": (4, 10),
        }
        self.current_tl = None
        self.over = False

    def __call__(self, car_state: CarState):
        if self.current_tl is None:
            min_d = float("inf")
            min_d_sem = None
            for sem in self.loc.keys():
                d = math.sqrt(
                    (car_state.x - self.loc[sem][0]) ** 2
                    + (car_state.y - self.loc[sem][1]) ** 2
                )
                if d < min_d:
                    min_d = d
                    min_d_sem = sem
            self.current_tl = min_d_sem
        print("Current TL", self.current_tl)
        print(car_state.tl)
        print("TL state", car_state.tl[self.current_tl])
        if car_state.tl[self.current_tl] != 2:
            return {"speed": 0.0}
        else:
            self.over = True

    def out_condition(self, **kwargs) -> bool:
        return self.over

    def set(self, **kwargs):
        pass


class RampBehaviour(BehaviourCallback):
    pass


class StopBehvaiour(BehaviourCallback):
    def __call__(self, car_state):
        # return 0 speed and 0 steering
        return {"speed": 0.0, "steer": 0.0}

    def set(self, **kwargs):
        pass


class PriorityBehaviour(BehaviourCallback):
    def __call__(self, car_state):
        # return pririty speed
        return {"speed": car_state.priority_speed}

    def set(self, **kwargs):
        pass


class HighwayBehaviour(BehaviourCallback):
    def __init__(self, **kwargs):
        self.exit_highway = False

    def __call__(self, car_state: CarState):
        if car_state.detected["highway_exit"][0] or car_state.activity_type!="highway":
            self.exit_highway = True

        return {"speed": car_state.highway_speed}

    def out_condition(self, **kwargs) -> bool:
        return self.exit_highway

    def set(self, **kwargs):
        self.exit_highway = False

    def reset(self, **kwargs):

        self.exit_highway = False
        return True


class OvertakeBehaviour(BehaviourCallback):
    def __init__(self, **kwargs):
        super().__init__()
        self.target_speed = None
        self.values = []
        self.target_deteremined = False
        self.speed = 0.0

        self.parallel_reach = False
        self.parallel_out = False
        self.prev_sensor_val = 0.0
        self.current_sensor_val = 0.0
        self.last_update_time = None
        self.target_speed_array = []
        self.WB = 0.3
        self.set_side = None

        # print("behaviour init")

    def reset(self, **kwargs):
        # set path here for changing lanes
        pass

    def __call__(self, car_state: CarState):
        # get target speed
        self.current_sensor_val = car_state.front_distance

        # print("Called overtake")

        if not self.target_deteremined:
            print("inside overtake speed calc")
            dt = time.time() - self.last_update_time
            self.last_update_time = time.time()
            tspeed = (
                (self.prev_sensor_val - self.current_sensor_val) / dt
            ) - car_state.v
            print("Target Speed: ", tspeed)
            self.target_speed_array.append(tspeed)
            if len(self.target_speed_array) > 3:
                self.target_speed = sum(self.target_speed_array[1:]) / len(
                    self.target_speed_array[1:]
                )
                print("Target Speed determined: ", self.target_speed)
                self.target_deteremined = True
                self.speed = car_state.v
            return {"None": None}
        # once target is determined
        # make new target points on the left lane
        # cx = car_state.rear_x
        # cy = car_state.rear_y
        cx, cy = car_state.navigator.coords[car_state.target_ind - 1]

        # Use Of Inverted Yaw

        # print("cx,cy should be: ",car_state.navigator.get_nearest_node(cx,cy,car_state.yaw))
        # nn = car_state.navigator.get_nearest_node(cx, cy, -car_state.yaw)

        # have to uncomment this no idea why this doesnt work uncommented
        # cx,cy=nn["x"],nn["y"]

        tx = car_state.target_x
        ty = car_state.target_y

        try:
            # find m
            m = -(tx - cx) / (ty - cy)
        except:
            m = -(tx - cx) / 0.0001

        # print("m: ",m)
        # find c
        c = ty - m * tx
        # print("C: ",c)

        x3 = tx + ((0.345 ** 2) / (m ** 2 + 1)) ** 0.5
        x4 = tx - ((0.345 ** 2) / (m ** 2 + 1)) ** 0.5
        y3 = m * x3 + c
        y4 = m * x4 + c

        if isLeft((cx, cy), (tx, ty), (x3, y3)):
            self.set_side = 3
        else:
            self.set_side = 4

        if self.set_side == 4:
            alpha = math.atan2(y4 - car_state.rear_y, x4 - car_state.rear_x) - (
                -car_state.yaw
            )
            delta = math.atan2(
                2.0
                * self.WB
                * math.sin(alpha)
                / math.sqrt(
                    (y4 - car_state.rear_y) ** 2 + (x4 - car_state.rear_x) ** 2
                ),
                1.0,
            )
            print("In Overtake x4 y4 delta:", x4, y4, delta)
        else:
            alpha = math.atan2(y3 - car_state.rear_y, x3 - car_state.rear_x) - (
                -car_state.yaw
            )
            delta = math.atan2(
                2.0
                * self.WB
                * math.sin(alpha)
                / math.sqrt(
                    (y3 - car_state.rear_y) ** 2 + (x3 - car_state.rear_x) ** 2
                ),
                1.0,
            )
            print("In Overtake x3 y3 delta:", x3, y3, delta)

        # print("rear pts: ",state.x,state.y)
        # print("target and yaw :", tx,ty,state.yaw)
        # print("alpha and pts angle", alpha,alpha+state.yaw)

        di = delta * 180 / math.pi
        if di > 23:
            di = 23
        elif di < -23:
            di = -23
        car_state.cs_angle = di

        if car_state.side_distance < 0.5:
            self.parallel_reach = True

        if car_state.side_distance > 0.7 and self.parallel_reach:
            self.parallel_out = True

        print("In Overtake ", self.set_side)

        return {"steer": di, "speed": car_state.v}

    def out_condition(self, **kwargs) -> bool:
        if self.parallel_out:
            return True
        # return super().out_condition(**kwargs)

    def set(self, **kwargs):
        # print("Setting up overtake")
        state: CarState
        state = kwargs["car_state"]
        self.prev_sensor_val = state.front_distance
        self.current_sensor_val = state.front_distance
        self.last_update_time = time.time()
        self.speed = state.v


class LaneKeepBehaviour(BehaviourCallback):
    def __init__(self, **kwargs):
        self.pid_con = PID(P=1.4, I=0.35, D=0.7)
        self.last_angle = 0

    def __call__(self, car_state):
        angle = self.pid_con.update(car_state.lanekeeping_angle)
        # angle = car_state.lanekeeping_angle
        angle = (angle + self.last_angle) / 2
        if angle > 23:
            angle = 23
        elif angle < -23:
            angle = -23
        # print("Lanekeeping angle: ", car_state.lanekeeping_angle)
        # print("Lanekeeping angle: ", angle)
        # return  {"steer":angle}
        #if abs(car_state.cs_angle - angle) > 20 and car_state.current_ptype == "lk":
            # return {"steer": (angle+car_state.cs_angle*2)/3}
        #    return None
#         if car_state.current_ptype == "lk":
#            if abs(car_state.cs_angle - angle)>10:
#                return {"steer":(angle+car_state.cs_angle*5)/6}

        if car_state.current_ptype == "lk":
           if abs(car_state.cs_angle - angle)>7:
               return {"steer":(angle+car_state.cs_angle*5)/6}
           return {"steer":angle}
        #    return None

    def set(self, **kwargs):
        pass


class ControlSystemBehaviour(BehaviourCallback):
    def __init__(self, coord_list):
        super().__init__()
        self.cs = Pure_Pursuit(coord_list,Lfc=0.36)

    def __call__(self, car_state: CarState):
        ind, lf = self.cs.search_target_index(car_state)
        logger.info(
            f"({car_state.x}, {car_state.y}) Target: {ind} ({self.cs.cx[ind]:.2f}, {self.cs.cy[ind]:.2f})"
        )

        car_state.target_x = self.cs.cx[ind]
        car_state.target_y = self.cs.cy[ind]
        car_state.current_target = (car_state.target_x, car_state.target_y)
        car_state.target_ind = ind

        car_state.current_ptype = car_state.navigator.ptype[ind]
        car_state.can_overtake = car_state.navigator.etype[ind]
        car_state.activity_type = car_state.navigator.activity[ind]

        # car_state.current_ptype = car_state.navigator.ptype[ind]
        # car_state.can_overtake = car_state.navigator.etype[ind]

        # car_state.current_ptype = "int"
        # car_state.can_overtake = True

        di = self.cs.purest_pursuit_steer_control(car_state, ind, lf)
        di = di * 180 / math.pi
        if di > 23:
            di = 23
        elif di < -23:
            di = -23
        car_state.cs_angle = di
        return {"steer": di, "speed": car_state.max_v}

    def set(self, **kwargs):
        pass

    def reset(self, **kwargs):
        self.cs.reset(kwargs["coord_list"])
        return True


class ObjectStopBehaviour(BehaviourCallback):
    def __call__(self, car_state:CarState):
        thxl=320
        thxh=370
        thyl=190
        thyh=240

        if car_state.front_distance < 0.27 and car_state.detected["car"][0]:
                return {"speed": 0.0}
        
        if car_state.detected["pedestrian"][0]:
            x,y=car_state.detected["pedestrian"][1][1]
            # print("Pedestrain", car_state.detected["pedestrian"])
            print(f"{x}, {y}")
            #x,y=0,0
            
            if x>thxl and x<thxh and y>thyl and y<thyh:
                return {"speed": 0.0}
            else:
                return None
        else:
            return None

    def set(self, **kwargs):
        pass


class CrosswalkBehavior(BehaviourCallback):
    def __init__(self, **kwargs):
        self.active = None
        self.initx = None
        self.inity = None

    def __call__(self, car_state: CarState):
        if self.active == None:
            self.active = True

        if self.initx is None and self.inity is None:
            self.initx = car_state.rear_x
            self.inity = car_state.rear_y

        d = math.sqrt(
            (self.initx - car_state.rear_x) ** 2 + (self.inity - car_state.rear_y) ** 2
        )

        if d > 1.1:
            self.active = False
        
        if car_state.front_distance < 0.3:
            return {"speed": 0.0}

        if self.active:
            return {"speed": car_state.priority_speed}
        else:
            return {"speed": car_state.max_v}

    def out_condition(self, **kwargs) -> bool:
        if self.active == False:
            return True

    def set(self, **kwargs):
        pass


class ParkingBehaviour(BehaviourCallback):
    def __init__(self, **kwargs):
        if "parkingtype" in kwargs.keys():
            self.type = kwargs["parkingtype"]
        else:
            self.type = "perpendicular"
        self.initx = None
        self.inity = None
        self.phase = 0
        self.over = False
        # self.WB = 0.3
        self.WB = 0.265
        self.slot = 1
        self.offsetx = 0
        # 0 init 1 reach empty 2 check empty 3 reach comfortable park spot 4 park 5 out of park

    def out_condition(self, **kwargs) -> bool:
        return self.over

    def chase(self, car_state: CarState, tx, ty):

        alpha = math.atan2(ty - car_state.rear_y, tx - car_state.rear_x) - (
            -car_state.yaw
        )
        delta = math.atan2(
            2.0
            * self.WB
            * math.sin(alpha)
            / math.sqrt((ty - car_state.rear_y) ** 2 + (tx - car_state.rear_x) ** 2),
            1.0,
        )
        di = delta * 180 / math.pi
        if di > 23:
            di = 23
        elif di < -23:
            di = -23
        car_state.cs_angle = di
        return di

    def reverse_chase(self, car_state: CarState, tx, ty):
        car_state.f_x = car_state.x - (
            (car_state.car_len / 2) * math.cos(car_state.yaw)
        )
        car_state.f_y = car_state.y - (
            (car_state.car_len / 2) * math.sin(car_state.yaw)
        )

        # alpha = math.atan2(ty - car_state.rear_y, tx - car_state.rear_x) - (
        #     car_state.yaw
        # )
        # delta = math.atan2(
        #     2.0
        #     * self.WB
        #     * math.sin(alpha)
        #     / math.sqrt((ty - car_state.rear_y) ** 2 + (tx - car_state.rear_x) ** 2),
        #     1.0,
        # )
        alpha = math.atan2(ty - car_state.f_y, tx - car_state.f_x) - (car_state.yaw)
        delta = math.atan2(
            2.0
            * self.WB
            * math.sin(alpha)
            / math.sqrt((ty - car_state.f_y) ** 2 + (tx - car_state.f_x) ** 2),
            1.0,
        )
        di = delta * 180 / math.pi
        if di > 23:
            di = 23
        elif di < -23:
            di = -23
        car_state.cs_angle = di
        return di

    def __call__(self, car_state: CarState):

        if self.type == "perpendicular":
            if self.initx is None and self.inity is None:
                self.initx = car_state.rear_x
                self.inity = car_state.rear_y
                self.phase = 1

            if self.phase == 1:

                # tx = self.initx + 0.5 + offsetx_1
                # ty = self.inity
                tx = 3.4 + self.offsetx
                ty = 2.0

                print("In Phase 1", tx, ty)
                # go to check spot
                d = math.sqrt(
                    (tx - car_state.rear_x) ** 2 + (ty - car_state.rear_y) ** 2
                )
                if d < 0.2:
                    self.phase = 2

                di = self.chase(car_state, tx, ty)
                return {"steer": di, "speed": car_state.priority_speed}
            elif self.phase == 2:
                print("In Phase 2")
                # check if empty
                if car_state.side_distance < 0.5:
                    if self.slot == 1:
                        print("Parking Spot full")
                        self.offsetx += 0.55
                        self.slot = 2
                        self.phase = 1
                    else:
                        self.over = True
                else:
                    print("Parking Empty, Trying to Park!!")
                    self.phase = 3
            elif self.phase == 3:
                print("In Phase 3")

                # go to safe spot for reverse
                # tx = self.initx + 0.5 +  offsetx_1
                # ty = self.inity - 0.35
                tx = 3.6 + self.offsetx
                ty = 1.6
                print("In Phase 3", tx, ty)
                d = math.sqrt(
                    (tx - car_state.rear_x) ** 2 + (ty - car_state.rear_y) ** 2
                )
                if d < 0.1:
                    self.phase = 4
                di = self.chase(car_state, tx, ty)
                return {"steer": di, "speed": car_state.priority_speed}

            elif self.phase == 4:
                # tx = self.initx + 0.75 + offsetx_1
                # ty = self.inity + 0.35
                tx = 3.3 + self.offsetx
                ty = 2.6
                print("In Phase 4", tx, ty)
                d = math.sqrt(
                    (tx - car_state.rear_x) ** 2 + ((ty - car_state.rear_y) ** 2)
                )
                if d>1.00:
                    self.over=True
                if d < 0.2:
                    #d<0.2 originally
                    self.phase = 5
                di = self.reverse_chase(car_state, tx, ty)
                return {"steer": di, "speed": -car_state.priority_speed}

            elif self.phase == 5:
                print("In Phase 5")
                # reverse into parking
                tx = 3.3 + self.offsetx
                ty = 3.1
                # tx = self.initx + 0.75 +  offsetx_1
                # ty = self.inity + 1
                print("In Phase 5", tx, ty)
                d = math.sqrt(
                    (tx - car_state.rear_x) ** 2 + (ty - car_state.rear_y) ** 2
                )
                print("curx,cury", car_state.rear_x, car_state.rear_y)
                if d>1:
                    self.over=True
                if d < 0.225 or car_state.rear_y > 2.9:
                    self.phase = 6
                    self.over = True
                di = self.reverse_chase(car_state, tx, ty)
                return {"steer": di, "speed": -car_state.priority_speed}

#            elif self.phase == 6:
 #               print("In Phase 6")
  #              tx = 3.4 + self.offsetx
   #             ty = 2.2
    #            d = math.sqrt(
     #               (tx - car_state.rear_x) ** 2 + (ty - car_state.rear_y) ** 2
      #          )
       #         if d < 0.25 or car_state.rear_y > 2.6:
        #            self.over = True
         #       di = self.chase(car_state, tx, ty)
          #      return {"steer": di, "speed": +car_state.priority_speed}

            else:
                print("Parking phase out of sync ")
                self.over = True
                return {"speed": car_state.max_v}

        if self.type == "parallel":
            raise NotImplementedError

    def set(self, **kwargs):
        pass


class RoundAboutBehaviour(BehaviourCallback):
    def __init__(self, **kwargs):
        car_state: CarState = kwargs["car_state"]
        indexes, indexesmax = car_state.target_ind, car_state.target_ind + 10
        self.coords = []
        for i in range(indexes, indexesmax):
            if car_state.navigator.ptype[i] == "roundabout":
                self.coords.append(car_state.navigator.coords[i])
            else:
                break
        if len(self.coords) == 0:
            self.over = True
            return
        x, y = zip(*self.coords)
        cx, cy, _, _, _ = calc_spline_course(x, y, 0.1)
        self.coords = [i for i in zip(cx, cy)]
        self.cs = Pure_Pursuit(self.coords, 0.175)
        self.over = False

    def __call__(self, car_state: CarState):
        try:
            if car_state.current_ptype != "roundabout":
                self.over = True

            ind, lf = self.cs.search_target_index(car_state, flag="roundabout")

            logger.info(
                f"({car_state.x}, {car_state.y}) Target: {ind} ({self.cs.cx[ind]:.2f}, {self.cs.cy[ind]:.2f})"
            )

            di = self.cs.purest_pursuit_steer_control(car_state, ind, lf)
            di = di * 180 / math.pi
            if di > 23:
                di = 23
            elif di < -23:
                di = -23
            car_state.cs_angle = di
            return {"steer": di, "speed": car_state.max_v}
        except:
            return {"steer": car_state.cs_angle, "speed": car_state.max_v}

    def out_condition(self, **kwargs) -> bool:
        return self.over

    def set(self, **kwargs):
        pass


class RoadBlocked(BehaviourCallback):
    def __init__(self, **kwargs):
        self.initx = None
        self.inity = None
        self.over = False
        self.WB = 0.3
        self.set_side = None

    def out_condition(self, **kwargs) -> bool:
        return self.over

    def chase(self, car_state: CarState, tx, ty):

        alpha = math.atan2(ty - car_state.rear_y, tx - car_state.rear_x) - (
            -car_state.yaw
        )
        delta = math.atan2(
            2.0
            * self.WB
            * math.sin(alpha)
            / math.sqrt((ty - car_state.rear_y) ** 2 + (tx - car_state.rear_x) ** 2),
            1.0,
        )
        di = delta * 180 / math.pi
        if di > 23:
            di = 23
        elif di < -23:
            di = -23
        car_state.cs_angle = di
        return di

    def __call__(self, car_state: CarState):

        if self.initx is None and self.inity is None:
            self.initx = car_state.rear_x
            self.inity = car_state.rear_y
            self.phase = 1

        if car_state.current_ptype == "int":
            self.over = True

        cx, cy = car_state.navigator.coords[car_state.target_ind - 1]
        tx = car_state.target_x
        ty = car_state.target_y

        try:
            # find m
            m = -(tx - cx) / (ty - cy)
        except:
            m = -(tx - cx) / 0.0001

        # print("m: ",m)
        # find c
        c = ty - m * tx
        # print("C: ",c)

        x3 = tx + ((0.335 ** 2) / (m ** 2 + 1)) ** 0.5
        x4 = tx - ((0.335 ** 2) / (m ** 2 + 1)) ** 0.5
        y3 = m * x3 + c
        y4 = m * x4 + c

        if not isLeft((cx, cy), (tx, ty), (x3, y3)):
            self.set_side = 3
        else:
            self.set_side = 4

        if self.set_side == 4:
            di = self.chase(car_state, x4, y4)
            return {"steer": di, "speed": +car_state.priority_speed}
        elif self.set_side == 3:
            di = self.chase(car_state, x3, y3)
            return {"steer": di, "speed": +car_state.priority_speed}
        else:
            return None
    
    def set(self, **kwargs):
        pass


# offsetx_1 = 0
class ActionBehaviour:
    def __init__(self, name, release_time=0.0, callback=None):
        self.state = False
        self.state_start = None
        self.action_time = None
        self.release_time = release_time
        self.name = name
        self.callback = callback

    def reset(self, **kwargs):
        self.state = False
        self.state_start = None
        self.action_time = None
        self.callback.reset(**kwargs)
        # self.release_time = release_time
        # self.name = name

    def __call__(self, car_state=None):
        state, toggle = self.state_check()
        if state:
            if self.callback.out_condition():
                self.state = False
                return {"toggle": True}
            return self.callback(car_state)
        elif toggle:
            self.callback.toggle_condition()
            return {"toggle": True}
        else:
            return {}

    def state_check(self, **kwargs):
        if self.state == True:
            if self.action_time is not None:
                if (time.time() - self.state_start) > self.action_time:
                    print("in false state toggle")
                    self.state = False
                    return self.state, True
            return self.state, False
        else:
            return self.state, False

    def set(self, action_time=None, **kwargs):
        if not self.state_start or (
            self.state_start + self.action_time + self.release_time < time.time()
        ):
            self.action_time = action_time
            self.state_start = time.time()
            self.state = True
            self.callback.set(**kwargs)
            print("State set")
            return self.state
        else:
            return self.state

    def check_cooldown(self, **kwargs):

        if self.action_time is None:
            return False

        if not self.state_start or (
            self.state_start + self.action_time + self.release_time < time.time()
        ):
            print("Check Cooldown Called: ", True)
            return True
        else:
            return False


class ActionManager:
    def __init__(self, **kwargs):
        self.lk = None
        self.cs = None
        self.objstop = None
        self.tflight = None
        self.l1_ab = None
        self.l2_ab = None
        self.l3_ab = None
        self.l4_ab = None

    def __call__(self, carstate: CarState):

        obj = [
            self.cs,
            self.lk,
            self.l1_ab,
            self.l2_ab,
            self.l3_ab,
            self.l4_ab,
            self.tflight,
            self.objstop,
        ]
        speed = 0
        steer = 0
        count = 0

        # reset cs after interrupt using either self
        carstate.active_behaviours = []

        for i in obj:
            if i:
                logger.opt(colors=True).info(
                    f"Currently Active Behaviour <light-blue>{i.name}</light-blue>"
                )
                carstate.active_behaviours.append(i.name)
                outputs = i(carstate)
                if outputs and "speed" in outputs.keys():
                    speed = outputs["speed"]
                if outputs and "steer" in outputs.keys():
                    steer = outputs["steer"]
                if outputs and "interrupt" in outputs.keys():
                    self.cs.reset(coord_list=outputs["interrupt"])
                if outputs and "toggle" in outputs.keys():
                    if count == 2:
                        self.l1_ab = None
                    elif count == 3:
                        print("killed l2")
                        self.l2_ab = None
                    elif count == 5:
                        self.l4_ab = None
            count += 1
        # print("Output of system (Speed, Steer): ", speed, steer)
        return speed, steer

    def set_action(self, action, action_time=None, **kwargs):
        if action.name == "cs":
            self.cs = action
            self.cs.set(action_time=action_time, **kwargs)
            return True
        elif action.name == "lk":
            self.lk = action
            self.lk.set(action_time=action_time, **kwargs)
            return True
        elif action.name == "hw" or action.name == "roundabout":
            self.l1_ab = action
            self.l1_ab.set(action_time=action_time, **kwargs)
            return True
        elif (
            action.name == "parking"
            or action.name == "overtaking"
            or action.name == "tailing"
            or action.name == "crosswalk"
        ) and self.l2_ab is None:
            self.l2_ab = action
            self.l2_ab.set(action_time=action_time, **kwargs)
            return True
        elif (action.name == "stop" or action.name == "priority") and (
            self.l3_ab is None
            or self.l3_ab.check_cooldown()
            or action.name != self.l3_ab.name
        ):  # ):
            self.l3_ab = action
            self.l3_ab.set(action_time=action_time, **kwargs)
            return True
        elif action.name == "ramp" or action.name == "roadblocked":
            self.l4_ab = action
            self.l4_ab.set(action_time=action_time, **kwargs)
            return True
        elif action.name == "trafficlight" and self.tflight is None:
            print("TL state set")
            self.tflight = action
            self.tflight.set(action_time=action_time, **kwargs)
            return True
        elif action.name == "objstop":
            self.objstop = action
            self.objstop.set(action_time=action_time, **kwargs)
            return True
        else:
            return False
