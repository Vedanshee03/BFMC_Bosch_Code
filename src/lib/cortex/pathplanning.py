import heapq
import math
from operator import index
from pickletools import optimize
from typing import List, Tuple

from scipy.interpolate import interp1d
from scipy.optimize import minimize
from src.lib.cortex import cubic_spline_planner
import networkx as nx
import numpy as np
from copy import deepcopy,copy


def dijkstra(G, start, target):
    d = {start: 0}
    parent = {start: None}
    pq = [(0, start)]
    visited = set()
    while pq:
        du, u = heapq.heappop(pq)
        if u in visited:
            continue
        if u == target:
            break
        visited.add(u)
        for v in G.adj[u]:
            if v not in d or d[v] > du + 1:
                d[v] = du + 1
                parent[v] = u
                heapq.heappush(pq, (d[v], v))

    fp = [target]
    tg = target
    ptype = [("lk" if len([i for i in G.neighbors(tg)]) < 2 else "int")]

    while tg != start:
        fp.insert(0, parent[tg])
        tg = parent[tg]
        ptype.insert(0, ("lk" if len([i for i in G.neighbors(tg)]) < 2 else "int"))
        # print([i for i in G.neighbors(tg)])

    ptyperet = ptype.copy()
    for i in range(len(ptype)):
        if ptype[i] == "int":
            try:
                ptyperet[i - 1] = "int"
            except Exception as e:
                print("pathplanning.py[46]", e)

            try:
                ptyperet[i + 1] = "int"
                i += 1
            except Exception as e:
                print("pathplanning.py[52]", e)

    edgeret = []

    for i in range(len(fp) - 1):
        dt = G.get_edge_data(fp[i], fp[i + 1])
        edgeret.append(dt["dotted"])

    edgeret.append(None)

    return fp, ptyperet, edgeret


def add_yaw(G):
    node_dict = deepcopy(dict(G.nodes(data=True)))
    for current_node in node_dict:
        for v in G.adj[current_node]:
            c_data = node_dict[current_node]
            v_data = node_dict[v]
            dx = v_data["x"] - c_data["x"]
            dy = v_data["y"] - c_data["y"]
            # print(c_data, v_data, "\n", dx, dy)
            yaw = math.atan2(dy, dx)
            if "yaw" in node_dict[current_node]:
                node_dict[current_node]["yaw"] += [yaw]
            else:
                node_dict[current_node].update({"yaw": [yaw]})
    return node_dict


def give_perpendicular_park_pts(x, y, spot=1):
    if spot == 1:
        pt0x, pt0y = x + 0.01, y + 0.01
        pt1x, pt1y = x + 0.5588, pt0y - 0.5334
        pt2x, pt2y = pt1x + 0.508, pt1y + 0.3302
        pt3x, pt3y = pt2x - 0.127, pt2y + 0.66
        pt4x, pt4y = pt3x + 0, pt3y + 0.2032
        pt5x, pt5y = pt4x, pt4y + 0.2032
        park_x_n, park_y_n = [pt0x, pt1x, pt2x, pt3x, pt4x, pt5x], [
            pt0x,
            pt1y,
            pt2y,
            pt3y,
            pt4y,
            pt5y,
        ]
        cx, cy, cyaw, rk, s = cubic_spline_planner.calc_spline_course(
            park_x_n, park_y_n, ds=0.15
        )

        return [i for i in zip(cx, cy)]


class PathPlanning:
    def __init__(self, test: bool = True) -> None:
        if test:
            self.graph = nx.read_graphml(
                "./src/lib/cortex/path_data/test_track.graphml"
            )
        else:
            self.graph = nx.read_graphml(
                "./src/lib/cortex/path_data/comp_track.graphml"
            )

        self.node_dict = add_yaw(self.graph)

    def get_path(self, start_idx: str, end_idx: str) -> Tuple[List[Tuple[int]], str]:

        path_list, _ptype, _edgret = dijkstra(self.graph, start_idx, end_idx)

        return self._smooth_point_list(
            self._convert_nx_path2list(path_list), _ptype, _edgret
        )

    def get_nearest_node(self, x, y, yaw):
        dx = []
        dy = []
        for node in self.node_dict:
            dx.append(self.node_dict[node]["x"] - x)
            dy.append(self.node_dict[node]["y"] - y)

        d = np.hypot(dx, dy)
        idxs = np.argsort(d)
        for idx in idxs:
            try:
                dyaw = np.array(self.node_dict[str(idx)]["yaw"]) - yaw
            except KeyError as e:
                print(e)
                continue
            if (abs(dyaw) < 0.7).any():
                return idx  # , self.node_dict[str(idx)]

    def _convert_nx_path2list(self, path_list) -> List[Tuple[int]]:
        coord_list = []
        for i in path_list:
            data = self.node_dict[i]
            coord_list.append([data["x"], data["y"]])
        return coord_list

    def _smooth_point_list(self, coord_list, ptype, etype) -> List[Tuple[int]]:
        coordlist_new = []
        count = 0
        sizeincrease = 0
        countfinal = len(coord_list)
        print(countfinal)
        ptype_new = ptype.copy()
        etype_new = etype.copy()

        while count < countfinal:
            if ptype[count] == "int":
                # append first point
                coordlist_new.append(coord_list[count])
                # find midpoint of intersection start and end
                xmidint = (coord_list[count][0] + coord_list[count + 2][0]) / 2
                ymidint = (coord_list[count][1] + coord_list[count + 2][1]) / 2

                xfinmid = (xmidint + coord_list[count + 1][0]) / 2
                yfinmid = (ymidint + coord_list[count + 1][1]) / 2

                pts = [coord_list[count], (xfinmid, yfinmid), coord_list[count + 2]]

                x, y = zip(*pts)

                i = np.arange(len(x))

                # 5x the original number of points
                interp_i = np.linspace(0, i.max(), 5 * i.max())

                xi = interp1d(i, x, kind="quadratic")(interp_i)
                yi = interp1d(i, y, kind="quadratic")(interp_i)

                for i in range(len(xi)):
                    coordlist_new.append((xi[i], yi[i]))
                    ptype_new.insert(count + sizeincrease, "int")
                    etype_new.insert(count + sizeincrease, False)
                    sizeincrease += 1

                # coordlist_new.append((xfinmid,yfinmid))
                coordlist_new.append(coord_list[count + 2])
                count += 3

                # coordlist_new.append((xfinmid, yfinmid))
                # coordlist_new.append(coord_list[count + 2])
                # count += 3
            else:
                coordlist_new.append(coord_list[count])
                count += 1

        return coordlist_new, ptype_new, etype_new


class Purest_Pursuit:
    def __init__(self, coord_list):
        self.k = 0.01  # look forward gain
        self.Lfc = 0.125  # [m] look-ahead distance
        self.Kp = 1.0  # speed proportional gain
        self.WB = 0.3  # [m] wheel base of vehicle
        self.cx, self.cy = zip(*coord_list)
        self.old_nearest_point_index = None

    def search_target_index(self, state):

        # To speed up nearest point search, doing it at only first time.
        if self.old_nearest_point_index is None:
            # search nearest point index
            dx = [state.rear_x - icx for icx in self.cx]
            dy = [state.rear_y - icy for icy in self.cy]
            d = np.hypot(dx, dy)
            ind = np.argmin(d)
            self.old_nearest_point_index = ind
        else:
            ind = self.old_nearest_point_index
            distance_this_index = state.calc_distance(self.cx[ind], self.cy[ind])
            while True:
                try:
                    distance_next_index = state.calc_distance(
                        self.cx[ind + 1], self.cy[ind + 1]
                    )
                except IndexError as e:
                    distance_next_index = state.calc_distance(self.cx[-1], self.cy[-1])
                    break

                if distance_this_index < distance_next_index:
                    break
                ind = ind + 1 if (ind + 1) < len(self.cx) else ind
                distance_this_index = distance_next_index
            self.old_nearest_point_index = ind

        Lf = self.k * state.v + self.Lfc  # update look ahead distance

        # search look ahead target point index
        while Lf > state.calc_distance(self.cx[ind], self.cy[ind]):
            if (ind + 1) >= len(self.cx):
                break  # not exceed goal
            ind += 1

        return ind, Lf

    def purest_pursuit_steer_control(self, state, ind, Lf):
        if ind < len(self.cx):
            tx = self.cx[ind]
            ty = self.cy[ind]
        else:  # toward goal
            tx = self.cx[-1]
            ty = self.cy[-1]
            ind = len(self.cx) - 1

        alpha = math.atan2(ty - state.rear_y, tx - state.rear_x) - state.yaw

        delta = math.atan2(2.0 * self.WB * math.sin(alpha) / Lf, 1.0)

        return delta

    def reset_coord_list(self, coord_list, Lfc):
        self.cx, self.cy = zip(*coord_list)
        self.old_nearest_point_index = None
        self.Lfc = Lfc


class MPC_Controller:
    def __init__(self,coords):
        self.horiz = None
        self.R = np.diag([0.01, 0.01])                 # input cost matrix
        self.Rd = np.diag([0.01, 1.0])                 # input difference cost matrix
        self.Q = np.diag([1.0, 1.0])                   # state cost matrix
        self.Qf = self.Q                               # state final matrix
        self.maxvn=-.5
        self.maxvp=.5
        self.coords=coords
        self.MPC_HORIZON=5

    def search_target_index(self, state):

        # To speed up nearest point search, doing it at only first time.
        if self.old_nearest_point_index is None:
            # search nearest point index
            dx = [state.rear_x - icx for icx in self.cx]
            dy = [state.rear_y - icy for icy in self.cy]
            d = np.hypot(dx, dy)
            ind = np.argmin(d)
            self.old_nearest_point_index = ind
        else:
            ind = self.old_nearest_point_index
            distance_this_index = state.calc_distance(self.cx[ind], self.cy[ind])
            while True:
                try:
                    distance_next_index = state.calc_distance(
                        self.cx[ind + 1], self.cy[ind + 1]
                    )
                except IndexError as e:
                    distance_next_index = state.calc_distance(self.cx[-1], self.cy[-1])
                    break

                if distance_this_index < distance_next_index:
                    break
                ind = ind + 1 if (ind + 1) < len(self.cx) else ind
                distance_this_index = distance_next_index
            self.old_nearest_point_index = ind

        Lf = self.k * state.v + self.Lfc  # update look ahead distance

        # search look ahead target point index
        while Lf > state.calc_distance(self.cx[ind], self.cy[ind]):
            if (ind + 1) >= len(self.cx):
                break  # not exceed goal
            ind += 1

        return ind, Lf


    def mpc_cost(self, u_k, my_car, points):
        mpc_car = copy(my_car)
        u_k = u_k.reshape(self.horiz, 2).T
        z_k = np.zeros((2, self.horiz+1))
    
        desired_state = points.T
        cost = 0.0

        for i in range(self.horiz):
            state_dot = mpc_car.move(u_k[0,i], u_k[1,i])
            mpc_car.update_state(state_dot)
        
            z_k[:,i] = [mpc_car.x, mpc_car.y]
            cost += np.sum(self.R@(u_k[:,i]**2))
            cost += np.sum(self.Q@((desired_state[:,i]-z_k[:,i])**2))
            if i < (self.horiz-1):     
                cost += np.sum(self.Rd@((u_k[:,i+1] - u_k[:,i])**2))
        return cost

    def optimize(self, my_car, index):
        # print(self.coords)
        print(index)
        points=self.coords[index:index+self.MPC_HORIZON]
        points=np.array(points)
        print(points)
        self.horiz = points.shape[0]
        bnd = [(-self.maxvn, self.maxvp),(np.deg2rad(-21), np.deg2rad(21))]*self.horiz
        print("in optimise")
        result = minimize(self.mpc_cost, args=(my_car, points), x0 = np.zeros((2*self.horiz)), method='SLSQP', bounds = bnd)
        print("out optimise")
        return result.x[0],  result.x[1]

    
    def purest_pursuit_steer_control(self, state, ind, Lf):
        return optimize(self,state,index)