import math
import time
from threading import Event
from datetime import datetime, timedelta
import cv2

from ..base import *
import pyrealsense2 as rs


class RSStandard(InputElement):
    name = "RealSense Standard"
    comment = "RealSense Standard Input with Preset Config"
    package = "RealSense"
    device_lock = Lock()
    colorizer = rs.colorizer()

    def __init__(self):
        super(RSStandard, self).__init__()

        # Create a pipeline
        self.pipeline = rs.pipeline()

        # Create a config and configure the pipeline to stream
        #  different resolutions of color and depth streams
        self.config = rs.config()

        # Get device product line for setting a supporting resolution
        pipeline_wrapper = rs.pipeline_wrapper(self.pipeline)
        pipeline_profile = self.config.resolve(pipeline_wrapper)
        device = pipeline_profile.get_device()
        device_product_line = str(device.get_info(rs.camera_info.product_line))

        self.config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
        self.config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)

        if device_product_line == 'L500':
            self.config.enable_stream(rs.stream.color, 960, 540, rs.format.bgr8, 30)
        else:
            self.config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)

        # Start streaming
        profile = self.pipeline.start(self.config)

        # Create an align object
        # rs.align allows us to perform alignment of depth frames to others frames
        # The "align_to" is the stream type to which we plan to align depth frames.
        align_to = rs.stream.color
        self.align = rs.align(align_to)

        self.capture = None
        self.actual_parameters = {"device": None, "width": 0, "height": 0, "fps": 0, "align": 0, "depthColor": 0}
        self.last_frame_time = datetime.now()
        self.play = Event()  # todo: we should load this state from some parameter
        self.play.set()
        self.recalculate(True, True, True)

    def get_attributes(self):
        return [], [
            Output("color"),
            Output("depth")
        ], [
            FloatParameter("fps", value=15, min_=0.1, max_=120),
            ButtonParameter("pause", self.playpause, "Play / Pause"),
            ComboboxParameter('align',name='Align Depth To Color',values=[('False',0),('True',1)],default_value_idx=0),
            ComboboxParameter('depthColor',name='Depth Colorizes',values=[
                ('RAW',0X80),
                ('Colorize(RS)',0x81),
                ('Gray(UINT8)',0x82),
                ('COLORMAP_AUTUMN',cv2.COLORMAP_AUTUMN),
                ('COLORMAP_BONE',cv2.COLORMAP_BONE),
                ('COLORMAP_COOL',cv2.COLORMAP_COOL),
                ('COLORMAP_HOT',cv2.COLORMAP_HOT),
                ('COLORMAP_HSV',cv2.COLORMAP_HSV),
                ('COLORMAP_JET',cv2.COLORMAP_JET),
                ('COLORMAP_OCEAN',cv2.COLORMAP_OCEAN),
                ('COLORMAP_PARULA',cv2.COLORMAP_PARULA),
                ('COLORMAP_PINK',cv2.COLORMAP_PINK),
                ('COLORMAP_RAINBOW',cv2.COLORMAP_RAINBOW),
                ('COLORMAP_SPRING',cv2.COLORMAP_SPRING),
                ('COLORMAP_SUMMER',cv2.COLORMAP_SUMMER),
                ('COLORMAP_WINTER',cv2.COLORMAP_WINTER),
            ],default_value_idx=2),
       ]

    def playpause(self):
        if self.play.is_set():
            self.play.clear()
        else:
            self.play.set()

    # def process_inputs(self, inputs, outputs, parameters):
    def process(self):
        parameters = {}
        for name, parameter in self.parameters.items():
            parameters[name] = parameter.get()

        if self.actual_parameters["fps"] != parameters["fps"]:
            self.actual_parameters["fps"] = parameters["fps"]
            self.may_interrupt()

        if self.actual_parameters["align"] != parameters["align"]:
            self.actual_parameters["align"] = parameters["align"]
            self.may_interrupt()

        if self.actual_parameters["depthColor"] != parameters["depthColor"]:
            self.actual_parameters["depthColor"] = parameters["depthColor"]
            self.may_interrupt()

        if not self.outputs["color"].get():
            color_output = Data()
            self.outputs["color"].put(color_output)
        else:
            color_output = self.outputs["color"].get()

        if not self.outputs["depth"].get():
            depth_output = Data()
            self.outputs["depth"].put(depth_output)
        else:
            depth_output = self.outputs["depth"].get()

        while True:
            self.may_interrupt()
            now = datetime.now()
            if now - self.last_frame_time < timedelta(seconds=1.0 / parameters["fps"]):
                seconds_to_wait = 1.0 / parameters["fps"] - (now - self.last_frame_time).total_seconds()
                breaks = int(round(seconds_to_wait * 10 + 1))
                for _ in range(breaks):
                    time.sleep(seconds_to_wait / breaks)
                    self.may_interrupt()
            self.last_frame_time = datetime.now()
            self.may_interrupt()
            self.set_state(Element.STATE_BUSY)

            # Get frameset of color and depth
            frames = self.pipeline.wait_for_frames()
            self.may_interrupt()

            if self.actual_parameters["align"] == 1:
                # Align the depth frame to color frame
                aligned_frames = self.align.process(frames)

                # Get aligned frames
                depth_frame = aligned_frames.get_depth_frame()  # depth_frame is a 640x480 depth image
                color_frame = aligned_frames.get_color_frame()
            else:
                depth_frame = frames.get_depth_frame()
                color_frame = frames.get_color_frame()
            self.may_interrupt()

            # Validate that both frames are valid
            if not depth_frame or not color_frame:
                return

            color_image = np.asanyarray(color_frame.get_data())
            color_output.value = color_image
            self.may_interrupt()

            if self.actual_parameters["depthColor"] == 0X80:
                depth_image = np.asanyarray(depth_frame.get_data())
                depth_output.value = depth_image
            elif self.actual_parameters["depthColor"] == 0X81:
                depth_color_frame = self.colorizer.colorize(depth_frame)
                depth_output.value = np.asanyarray(depth_color_frame.get_data())
            elif self.actual_parameters["depthColor"] == 0X82:
                depth_image = np.asanyarray(depth_frame.get_data())
                depth_output.value = cv2.convertScaleAbs(depth_image, alpha=0.08)
            else:
                depth_image = np.asanyarray(depth_frame.get_data())
                depth_output.value = cv2.applyColorMap(
                    cv2.convertScaleAbs(depth_image, alpha=0.08),
                    self.actual_parameters["depthColor"]
                )
            self.may_interrupt()

            self.set_state(Element.STATE_READY)
            self.notify_state_changed()

            self.may_interrupt()
            self.play.wait()

    def delete(self):
        self.pipeline.stop()
        ThreadedElement.delete(self)

    def __del__(self):
        self.pipeline.stop()
