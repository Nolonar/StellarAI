"""
Handle inbound communication from the tinyK22.

This module takes in a binary stream and returns concrete values, as recorded
by the array of sensors connected to the tinyK22.

The tinyK22 sends bundled sensor data over an UART serial interface. These
messages are demodulated here into distinct values. A UART message consists
of a start bit, 8 bits of data and a stop bit. Multiple messages can be send
indipendently until the stop bit is set.

Multiple steps are performed read and parse UART messages:
    1. Read raw binary data from the device
    2. Reassemble original payload from fragmented messages
    3. Reconstruct original payload by parsing the binary blobs.

"""
import io
import queue
import struct
import sys
from os import path
from typing import List

DIRECTORY = path.dirname(path.abspath(__file__))
sys.path.append(path.dirname(DIRECTORY))
# workaround for autopep8 moving imports to the top.
if 'send_message' not in sys.modules:
    from communication.sender import send_message

simulator = None


def decode_blob(blob: bytes, fmt="=ffffii"):
    """Decode sensor data array from tinyK22.

    NOTE: No error is raised if the byte length matches, e.g. "=ffffii"
    matches "=ddd" well, so no error is raised. Perform sanity checks.
    """
    try:
        return struct.unpack(fmt, blob)
    except struct.error:
        import binascii
        error_blob = binascii.hexlify(bytearray(blob))
        raise ValueError(f"Unable to decode data, got: {error_blob}")


def combine_messages(blobs: List[bytes]) -> bytes:
    """Combines multiple UART messages into a single data buffer.

    Assumes structure described in the module docstring. Start- and
    """
    buf = []
    for blob in blobs:
        stop_bit = blob[-1]
        buf.append(blob[1:9])

        if stop_bit == 0x01:
            break

    return b''.join(buf)


def send_data_to_observatory(data: dict):
    """Sends data to observatory"""
    send_message('perception/sensors', data)


class Sensors:
    """Continuously read sensor data from the tinyK22."""

    def __init__(self, device: io.BytesIO, out_queue: queue.Queue, fmt="=xffffiix"):
        self.device = device
        self.out_queue = out_queue
        self.fmt = fmt

    def read(self):
        """Reads and decodes sensor signals."""
        blob = self.device.read()
        if blob:
            values = decode_blob(blob, self.fmt)
            self.out_queue.put(values)

    def get_image_data(self):
        from pylon_detection import PylonDetector
        import json
        import base64

        frame = simulator.current_frame
        pylons_found = PylonDetector.find_pylons(frame)
        image_out = PylonDetector.mark_pylons(frame, pylons_found)

        json_encoded = json.dumps(image_out.tolist())

        return base64.b64encode(json_encoded.encode('utf-8'))

    import datetime
    time_created = datetime.datetime.now()  # temp

    def get_mock_data(self) -> dict:
        """Returns mock data to be sent to observatory."""
        import random
        import datetime

        return {
            'time': {
                'current': (datetime.datetime.now() - self.time_created).seconds * 1000,
                'best': (datetime.datetime.now() - self.time_created).seconds * 1000
            },
            'battery': 99,
            'map': None,
            'cameraFeed': self.get_image_data(),
            'sensorMech': {
                'motor': random.randint(0, 1600),
                'steering': random.randint(-90, 90)
            },
            'sensorElec': {
                'cpu': {
                    'load': [
                        random.randint(0, 100),
                        random.randint(0, 100),
                        random.randint(0, 100),
                        random.randint(0, 100)
                    ],
                    'temp': random.randint(0, 100)
                },
                'ram': random.randint(0, 100)
            }
        }


if __name__ == '__main__':
    from picam_simulator import Simulator
    from threading import Thread
    import time

    sensors = Sensors(None, None)  # temporary
    simulator = Simulator("stellar/perception/cv_video_final.mp4")
    Thread(target=simulator.run).start()

    while True:
        try:
            time.sleep(0.01)
            send_data_to_observatory(sensors.get_mock_data())
        except:
            simulator.stop()
            break
