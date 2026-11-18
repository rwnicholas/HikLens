import unittest

from capture_backends import create_capture_backend, supports_selectable_fps


class FakeBackend:
    def __init__(self, channel, config, parent):
        self.args = (channel, config, parent)


class FakeHTTPBackend(FakeBackend):
    pass


class FakeRTSPBackend(FakeBackend):
    pass


class FakeHikvisionBackend(FakeBackend):
    pass


class CaptureBackendTests(unittest.TestCase):
    def setUp(self):
        self.config = object()
        self.parent = object()

    def create(self, mode):
        return create_capture_backend(
            mode,
            3,
            self.config,
            self.parent,
            http_backend=FakeHTTPBackend,
            rtsp_backend=FakeRTSPBackend,
            hikvision_backend=FakeHikvisionBackend,
        )

    def test_selects_all_supported_backends_with_shared_arguments(self):
        expected_types = {
            "HTTP": FakeHTTPBackend,
            "RTSP": FakeRTSPBackend,
            "HIKVISION": FakeHikvisionBackend,
        }
        for mode, expected_type in expected_types.items():
            with self.subTest(mode=mode):
                backend = self.create(mode)
                self.assertIsInstance(backend, expected_type)
                self.assertEqual(backend.args, (3, self.config, self.parent))

    def test_rejects_unknown_backend_instead_of_falling_back(self):
        with self.assertRaisesRegex(ValueError, "Unknown capture backend: UNKNOWN"):
            self.create("UNKNOWN")

    def test_selectable_fps_is_available_for_rtsp_and_hikvision_only(self):
        self.assertTrue(supports_selectable_fps("RTSP"))
        self.assertTrue(supports_selectable_fps("HIKVISION"))
        self.assertFalse(supports_selectable_fps("HTTP"))


if __name__ == "__main__":
    unittest.main()
