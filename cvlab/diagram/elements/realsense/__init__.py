# import importlib.util
# rs = importlib.util.find_spec("pyrealsense2")
from threading import Event
from datetime import datetime, timedelta

from ..base import *
import pyrealsense2 as rs

class RSStandard(InputElement):
    name = "RealSense Standard"
    comment = "RealSense Standard Input with Preset Config"
    package = "RealSense"
    device_lock = Lock()

    def __init__(self):
        super(RSStandard,self).__init__()

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
        self.actual_parameters = {"device": None, "width": 0, "height": 0, "fps": 0}
        self.last_frame_time = datetime.now()
        self.play = Event()  # todo: we should load this state from some parameter
        self.play.set()
        self.recalculate(True, True, True)

    def get_attributes(self):
        return [], [
            Output("color"),
            Output("depth")
        ], [
            ButtonParameter("pause", self.playpause, "Play / Pause")
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
            self.last_frame_time = datetime.now()
            self.set_state(Element.STATE_BUSY)

            # Get frameset of color and depth
            frames = self.pipeline.wait_for_frames()
            self.may_interrupt()

            # Align the depth frame to color frame
            aligned_frames = self.align.process(frames)

            # Get aligned frames
            aligned_depth_frame = aligned_frames.get_depth_frame() # aligned_depth_frame is a 640x480 depth image
            color_frame = aligned_frames.get_color_frame()

            # Validate that both frames are valid
            if not aligned_depth_frame or not color_frame:
                return

            color_image = np.asanyarray(color_frame.get_data())
            depth_image = np.asanyarray(aligned_depth_frame.get_data())

            color_output.value = color_image
            depth_output.value = depth_image

            self.set_state(Element.STATE_READY)
            self.notify_state_changed()

            self.may_interrupt()
            self.play.wait()

    def delete(self):
        self.pipeline.stop()
        ThreadedElement.delete(self)

    def __del__(self):
        self.pipeline.stop()

register_elements(__name__, [RSStandard])
