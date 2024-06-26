# from multiprocessing import shared_memory
from multiprocessing.connection import Connection
from threading import Thread
import time
from typing import List
import numpy as np
import cv2

# import SharedArray as sa
from loguru import logger
import zmq
import numpy as np

# from simple_pid import PID
from src.lib.perception.lanekeepfunctions import LaneKeep as LaneKeepMethod
from src.templates.workerprocess import WorkerProcess

MAX_STEER = 23

def get_last(inP: Connection):
    timestamp, data = inP.recv()
    while inP.poll():
        timestamp, data = inP.recv()
    return timestamp, data


class LaneKeepingProcess(WorkerProcess):
    # ===================================== Worker process =========================================
    def __init__(
        self, inPs: List[Connection], outPs: List[Connection], enable_stream: bool
    ):
        """Process used for the image processing needed for lane keeping and for computing the steering value.

        Parameters
        ----------
        inPs : list(Pipe)
            List of input pipes (0 - receive image feed from the camera)
        outPs : list(Pipe)
            List of output pipes (0 - send steering data to the movvement control process)
        """
        super(LaneKeepingProcess, self).__init__(inPs, outPs)
        self.lk = LaneKeepMethod(use_perspective=True, computation_method="hough")
        self.enable_stream = enable_stream

    def run(self):
        """Apply the initializing methods and start the threads."""
        super(LaneKeepingProcess, self).run()

    def _init_threads(self):
        """Initialize the thread."""
        if self._blocker.is_set():
            return

        thr = Thread(
            name="StreamSending",
            target=self._the_thread,
            args=(
                self.inPs,
                self.outPs,
            ),
        )
        thr.daemon = True
        self.threads.append(thr)

    # ===================================== Custom methods =========================================
    def computeSteeringAnglePID(self, val):
        # keep the angle between max steer angle
        val = max(-MAX_STEER, min(val - 90, MAX_STEER))
        return val

    def _the_thread(self, inP: Connection, outPs: List[Connection]):
        """Obtains image, applies the required image processing and computes the steering angle value.

        Parameters
        ----------
        inP  : Pipe
            Input pipe to read the frames from other process.
        outP : Pipe
            Output pipe to send the steering angle value to other process.
        """
        count = 0
        t = 0.0
        t_r = 0.1
        context_recv = zmq.Context()
        sub_cam = context_recv.socket(zmq.SUB)
        sub_cam.setsockopt(zmq.CONFLATE, 1)
        sub_cam.connect("ipc:///tmp/v4l")
        sub_cam.setsockopt_string(zmq.SUBSCRIBE, "")

        context_send = zmq.Context()
        pub_lk = context_send.socket(zmq.PUB)
        pub_lk.bind("ipc:///tmp/v51")

        if self.enable_stream:
            context_send_img = zmq.Context()
            pub_lk_img = context_send_img.socket(zmq.PUB)
            pub_lk_img.setsockopt(zmq.CONFLATE, 1)
            pub_lk_img.bind("ipc:///tmp/v52")
        try:
            while True:
                # Obtain image
                image_recv_start = time.time()
                # stamps, img = inP.recv()
                data = sub_cam.recv()
                data = np.frombuffer(data, dtype=np.uint8)
                img = np.reshape(data, (480, 640, 3))
                
                # cv2.imshow('Image', img)
                # cv2.imwrite(time.time(), img)
                # print("lk img recv")
                t_r += time.time() - image_recv_start
                count += 1

                #logger.log(
                 #   "TIME",
                  #  f"Time taken to rec image {(t_r/count):.4f}s",
                #)
                compute_time = time.time()
                # Apply image processing
                # if self.enable_stream and False:
                #     val, intersection_detected, outimage = self.lk(img, True)
                #     angle = self.computeSteeringAnglePID(val)
                #     pub_lk.send_json((angle, intersection_detected), flags=zmq.NOBLOCK)
                #     pub_lk_img.send(outimage.tobytes(), flags=zmq.NOBLOCK)
                # else:
                val, intersection_detected = self.lk(img)
                # print("intersection bool : ")
                # print(intersection_detected)
                angle = self.computeSteeringAnglePID(val)
                # print(angle)
                pub_lk.send_json((angle, intersection_detected), flags=zmq.NOBLOCK)

                if self.enable_stream:
                    pub_lk_img.send(img.tobytes(), flags=zmq.NOBLOCK)

                # print("Timetaken by LK: ", time() - a)
        except Exception as e:
            # print(e)
            raise e
