"""Run with: python3 -m unittest discover -s tests   (no hardware needed)"""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np

import analysis
import config as C
import hardware as hw


class Modbus(unittest.TestCase):
    def test_crc_known_vector(self):
        self.assertEqual(hw.build_read(1, 0, 1), bytes([0x01, 0x03, 0x00, 0x00, 0x00, 0x01, 0x84, 0x0A]))

    def test_parse_roundtrip(self):
        import struct
        regs = [250, 265, 480, 68, 40, 22, 110]
        body = bytes([1, 3, 14]) + struct.pack(">7h", *regs)
        frame = body + struct.pack("<H", hw.crc16(body))
        self.assertEqual(hw.parse_read(frame, 1, 7), regs)
        bad = frame[:-1] + bytes([frame[-1] ^ 0xFF])
        with self.assertRaises(ValueError):
            hw.parse_read(bad, 1, 7)


class Nmea(unittest.TestCase):
    GGA = "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47"

    def test_gga(self):
        p = hw.parse_nmea(self.GGA)
        self.assertAlmostEqual(p["lat"], 48.1173, places=4)
        self.assertAlmostEqual(p["lon"], 11.5167, places=4)
        self.assertEqual(p["sats"], 8)

    def test_bad_checksum_and_no_fix(self):
        self.assertIsNone(hw.parse_nmea(self.GGA.replace("*47", "*00")))
        self.assertIsNone(hw.parse_nmea("$GPGGA,,,,,,0,00,,,M,,M,,*66"))


class Analysis(unittest.TestCase):
    def frames(self, amp, noise):
        rng = np.random.default_rng(1)
        off = hw.sim_frame(False, rng)
        h, w = off.shape[:2]
        on = off.astype(np.float32).copy()
        x = np.arange(w)
        y = 300 + amp * np.sin(x / 35.0) + rng.normal(0, noise, w)
        rows = np.arange(h)[:, None]
        prof = np.exp(-((rows - y[None, :]) ** 2) / (2 * 1.6 ** 2))
        on[:, :, 0] += 200 * prof
        on[:, :, 1] -= 40 * prof
        on[:, :, 2] -= 40 * prof
        return np.clip(on, 0, 255).astype(np.uint8), off

    def test_rough_vs_smooth(self):
        smooth = analysis.laser_profile(*self.frames(0.3, 0.2))
        rough = analysis.laser_profile(*self.frames(14, 3))
        self.assertTrue(smooth["ok"] and rough["ok"])
        self.assertLess(smooth["roughness_mm"], C.ROUGH_SMOOTH_MM)
        self.assertGreater(rough["roughness_mm"], C.ROUGH_COARSE_MM)

    def test_no_laser(self):
        off = hw.sim_frame(False, np.random.default_rng(2))
        self.assertFalse(analysis.laser_profile(off, off)["ok"])

    def test_soil_classes(self):
        dark = {"hue": 30, "sat": 0.3, "val": 0.2, "grain": 4}
        red = {"hue": 12, "sat": 0.6, "val": 0.5, "grain": 4}
        sand = {"hue": 40, "sat": 0.25, "val": 0.7, "grain": 9}
        self.assertEqual(analysis.classify_soil(dark, "medium")[0], "black")
        self.assertEqual(analysis.classify_soil(red, "medium")[0], "red")
        self.assertEqual(analysis.classify_soil(sand, "coarse")[0], "sandy")

    def test_crops_respond_to_ph_and_soil(self):
        soil = dict(moisture=45, temp_c=28, ec=300, ph=6.5, n=130, p=40, k=200)
        top = [c["name"] for c in analysis.recommend(soil, "clay", top=5)]
        self.assertTrue({"Rice", "Sugarcane"} & set(top))
        acid = dict(soil, ph=4.2)
        best = analysis.recommend(acid, "loam")[0]
        self.assertLess(best["score"], analysis.recommend(soil, "loam")[0]["score"])
        poor = dict(soil, n=10, p=5, k=30)
        self.assertIn(analysis.recommend(poor, "sandy")[0]["name"], ("Groundnut", "Pearl millet", "Chickpea", "Pigeon pea", "Sorghum"))

    def test_water_rank(self):
        s = [{"id": 1, "soil": {"moisture": 12}, "thermal": {"mean": 31}},
             {"id": 2, "soil": {"moisture": 33}, "thermal": {"mean": 26}},
             {"id": 3, "soil": {"moisture": 20}, "thermal": {"mean": 30}}]
        self.assertEqual(analysis.water_rank(s)[0]["id"], 2)


class SimRover(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server
        from rover import Rover
        cls.tmp = tempfile.mkdtemp()
        server.Handler.rover = Rover(sim=True, data_dir=cls.tmp)
        cls.srv = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.srv.daemon_threads = True
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        cls.rover = server.Handler.rover

    def call(self, path, body=None):
        req = urllib.request.Request(self.base + path, data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=10).read())

    def wait(self, cond, t=30):
        end = time.time() + t
        while time.time() < end:
            if cond():
                return True
            time.sleep(0.1)
        return False

    def test_full_flow(self):
        self.assertTrue(self.wait(lambda: self.call("/api/state")["probe"] == "up"))
        page = urllib.request.urlopen(self.base + "/").read().decode()
        self.assertIn("Soil Rover", page)
        self.assertTrue(self.call("/api/drive", {"l": 0.5, "r": 0.5})["ok"])
        time.sleep(0.2)
        self.assertGreater(self.call("/api/state")["distance_mm"], 0)
        time.sleep(C.WATCHDOG_S + 0.4)
        self.assertEqual(self.rover.motors.cmd, (0.0, 0.0))              # watchdog stopped the motors
        self.assertTrue(self.call("/api/sample", {})["ok"])
        self.assertTrue(self.wait(lambda: self.call("/api/state")["busy"] == "" and self.call("/api/state")["n_samples"] == 1))
        s = self.call("/api/samples")[0]
        self.assertIn("crops", s)
        self.assertEqual(len(s["crops"]), 3)
        self.assertTrue(s["laser"]["ok"])
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "photos", "sample_1.jpg")))
        self.assertFalse(self.call("/api/drive", {"l": 1, "r": 1})["ok"] and self.rover.busy)   # refused while busy only
        self.assertTrue(self.call("/api/survey", {"n": 2, "step_mm": 100, "speed": 1})["ok"])
        self.assertTrue(self.wait(lambda: self.call("/api/state")["busy"] == "" and self.call("/api/state")["n_samples"] == 3, 60))
        csv = urllib.request.urlopen(self.base + "/api/export.csv").read().decode().strip().split("\n")
        self.assertEqual(len(csv), 4)
        self.assertEqual(self.rover.probe.state, "up")
        data = urllib.request.urlopen(self.base + "/stream.mjpg", timeout=5).read(2000)
        self.assertIn(b"--frame", data)


if __name__ == "__main__":
    unittest.main()
