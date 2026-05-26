"""Parser tests for the BanlanX FT001 client."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "client.py"
SPEC = importlib.util.spec_from_file_location("banlanx_ft001_client", MODULE_PATH)
assert SPEC is not None
client = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = client
assert SPEC.loader is not None
SPEC.loader.exec_module(client)


def _chunk(chunk_type: int, payload: bytes) -> bytes:
    return bytes([chunk_type]) + len(payload).to_bytes(2, "big") + payload


class ClientParserTest(unittest.TestCase):
    """Parser tests for pure client helpers."""

    def test_parse_status_payload_channel_state(self) -> None:
        """Parse a verified two-channel RGB status payload."""
        channel_payloads = []
        for channel, brightness, rgb in (
            (1, 128, (10, 20, 30)),
            (2, 255, (40, 50, 60)),
        ):
            data = bytearray(24)
            data[1] = 1
            data[4] = 0
            data[5] = 0
            data[7] = brightness
            data[9:12] = bytes(rgb)
            data[14] = 5
            data[15] = 60
            channel_payloads.append(bytes([channel, 5]) + bytes(data))

        payload = bytes([1]) + b"".join(
            _chunk(3, chunk) for chunk in channel_payloads
        )

        status = client._parse_status_payload(payload)

        self.assertEqual(set(status.channels), {1, 2})
        self.assertTrue(status.channels[1].power)
        self.assertEqual(status.channels[1].brightness, 128)
        self.assertEqual(status.channels[1].rgb, (10, 20, 30))
        self.assertEqual(status.channels[2].brightness, 255)
        self.assertEqual(status.channels[2].rgb, (40, 50, 60))

    def test_parse_network_chunk_rejects_truncated_string(self) -> None:
        """Reject a network chunk whose string length runs past the payload."""
        payload = bytes([1]) + _chunk(6, b"\x00\x01\x05ab")

        with self.assertRaises(client.BanlanxFT001ProtocolError):
            client._parse_status_payload(payload)


if __name__ == "__main__":
    unittest.main()
