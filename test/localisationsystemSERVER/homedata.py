from typing import Tuple
import cv2
import requests
import numpy as np
import time
import json
import socket
from threading import Thread
import zmq

import joblib

PI_IP = "192.168.128.242"
PORT = 8888


def localize(img: np.ndarray) -> Tuple[float, float]:
    AREA_THRES = 100.0
    # AREA_THRES = 50.0
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    frame_HSV = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    # cv2.imshow('frame HSV', frame_HSV)
    # print(frame_HSV[521,493])
    frame_threshold = cv2.inRange(img, (35, 100, 150), (80, 160, 240))
    # frame_threshold = cv2.inRange(img, (99, 125, 187), (115 , 138, 198))
    cnts = cv2.findContours(
        frame_threshold, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    # print(cnts)
    cnts = cnts[0] if len(cnts) == 2 else cnts[1]
    x = None
    y = None
    if len(cnts) > 0:
        blue_box = max(cnts, key=cv2.contourArea)
        if cv2.contourArea(blue_box) > AREA_THRES:
            # return its center point
            x, y, w, h = cv2.boundingRect(blue_box)
            x = x + w / 2
            y = y + h / 2
    x = round(6 * x / 720, 2) if x else x
    y = round(6 * y / 720, 2) if y else y
    return x, y


def annotate_image(x: float, y: float, image: np.ndarray) -> np.ndarray:
    """Given x and y coordinates of data annotate the image."""
    org = [int((x * 720) / 6), int((y * 720) / 6)]
    if x > 500:
        org[0] = 500
    if y > 650:
        org[1] = 650
    font = cv2.FONT_HERSHEY_SIMPLEX
    fontScale = 0.8
    color = (0, 0, 255)
    thickness = 2

    return cv2.putText(
        image,
        f"car({x},{y})",
        org,
        font,
        fontScale,
        color,
        thickness,
        cv2.LINE_AA,
    )


class LocalisationServer:
    """Home Localisation Server"""

    def __init__(self, preview=False) -> None:

        self.preview = preview
        self.port = PORT
        self.serverIp = PI_IP  # pi addr
        self.threads = list()
        self._init_socket()

    def _init_socket(self):
        """Initialize the communication socket client."""
        self.client_socket = socket.socket(
            family=socket.AF_INET, type=socket.SOCK_DGRAM
        )

    def run(self):
        """Obtains image, applies the required image processing and computes the steering angle value.

        Parameters
        ----------
        inP  : Pipe
            Input pipe to read the frames from other process.
        outP : Pipe
            Output pipe to send the steering angle value to other process.
        """

        context_send = zmq.Context()
        pub_hl = context_send.socket(zmq.PUB)
        pub_hl.setsockopt(zmq.CONFLATE, 1)
        pub_hl.bind("ipc:///tmp/vhl")

        print("Started Home Localization System")
        count = 0
        skip_count = 24
        r = requests.get(
            "http://10.20.2.114/asp/video.cgi", auth=("admin", "admin"), stream=True
        )
        rx = []
        ry = []
        bytes1 = bytes()  # buffer
        if r.status_code == 200:
            for idx, chunk in enumerate(r.iter_content(chunk_size=100_000)):
                start_time = time.time()
                count += 1
                bytes1 += chunk
                a = bytes1.find(b"\xff\xd8")  # marks start of the frame
                b = bytes1.find(b"\xff\xd9")  # marks end   of the frame
                # the end of last frame in chunks
                c = bytes1.rfind(b"\xff\xd9")

                if idx < skip_count or a == -1 or b == -1:
                    continue
                jpg = bytes1[a: b + 2]  # get frame based on markers
                bytes1 = bytes1[c + 2:]  # update buffer to store data
                # of last frame present in chunk
                # i = cv2.imdecode(np.fromstring(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                i = cv2.imdecode(np.frombuffer(
                    jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                # specify desired output size
                width = 720
                height = 1280
                # specify conjugate x,y coordinates (not y,x)
                # input = np.float32([[61, 345], [616, 35], [1279, 51], [870, 676]])
                # input = np.float32([[0, 366], [582, 51], [1257, 66], [788, 715]])
                input = np.float32(
                    [[38, 344], [617, 38], [1279, 57], [860, 669]])

                output = np.float32(
                    [[0, 0], [width - 1, 0], [width - 1, width - 1], [0, width - 1]]
                )

                # compute perspective matrixbytes1 = bytes1[b+2:]
                # i = cv2.imdecode(np.fromstring(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                i = cv2.imdecode(np.frombuffer(
                    jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                # specify desired output size
                width = 720
                # height = 1280
                matrix = cv2.getPerspectiveTransform(input, output)

                # do perspective transformation setting area outside input to black
                image = cv2.warpPerspective(
                    i,
                    matrix,
                    (width, width),
                    cv2.INTER_LINEAR,
                    borderMode=cv2.BORDER_CONSTANT,
                    borderValue=(0, 0, 0),
                )
                x, y = localize(image)
                # print(x,y)
                if x and y:
                    # rx.append(x)
                    # ry.append(y)
                    data = {
                        "timestamp": time.time(),
                        "posA": x,
                        "posB": y,
                        "rotA": 0,
                    }
                    data = json.dumps(data).encode()
                    # data = data.decode('utf-8')
                    self.client_socket.sendto(data, (self.serverIp, self.port))
                    # pub_hl.send_json(data, flags=zmq.NOBLOCK)
                    print(data)
                    imgOutput = annotate_image(x, y, image)
                else:
                    imgOutput = image
                if self.preview:
                    cv2.imshow("Track Image", imgOutput)
                    key = cv2.waitKey(1)
                    if key == 27 or key == 113:
                        joblib.dump({"x": rx, "y": ry}, "coordlist.z")
                        cv2.destroyAllWindows()
                        break
                    else:
                        if key != -1:
                            print(key)
                        pass
        else:
            print("Received unexpected status code {}".format(r.status_code))


if __name__ == "__main__":
    loc = LocalisationServer(preview=True)
    loc.run()
