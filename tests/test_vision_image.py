"""Проверки Pillow-нормализации vision_image."""

import base64
import io
import unittest
from unittest import mock

import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402
import vision_image  # noqa: E402


def encoded_image(fmt="PNG", size=(12, 8), mode="RGB", color=None, exif=None):
    image = Image.new(mode, size, color or (255, 0, 0))
    output = io.BytesIO()
    save_kwargs = {"exif": exif} if exif is not None else {}
    image.save(output, format=fmt, **save_kwargs)
    image.close()
    return output.getvalue()


class VisionImageTests(unittest.TestCase):
    def assert_jpeg(self, raw):
        mime, jpeg = vision_image.normalize_image(raw)
        self.assertEqual(mime, "image/jpeg")
        with Image.open(io.BytesIO(jpeg)) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(image.mode, "RGB")
        return jpeg

    def test_jpeg_png_and_webp_become_readable_jpeg(self):
        for fmt in ("JPEG", "PNG", "WEBP"):
            with self.subTest(fmt=fmt):
                self.assert_jpeg(encoded_image(fmt, color=(20, 120, 220)))

    def test_data_url_has_exact_prefix_and_decodes(self):
        data_url = vision_image.to_data_url(encoded_image("PNG"))
        prefix = "data:image/jpeg;base64,"
        self.assertTrue(data_url.startswith(prefix))
        self.assertNotRegex(data_url, r"\s")
        decoded = base64.b64decode(data_url[len(prefix):], validate=True)
        self.assert_jpeg(decoded)

    def test_alpha_is_composited_on_white(self):
        raw = encoded_image("PNG", size=(1, 1), mode="RGBA", color=(255, 0, 0, 0))
        jpeg = self.assert_jpeg(raw)
        with Image.open(io.BytesIO(jpeg)) as image:
            self.assertGreater(min(image.getpixel((0, 0))), 230)

    def test_exif_orientation_is_applied(self):
        exif = Image.Exif()
        exif[274] = 6  # rotate 90 degrees clockwise
        raw = encoded_image("JPEG", size=(10, 4), color=(1, 2, 3), exif=exif)
        jpeg = self.assert_jpeg(raw)
        with Image.open(io.BytesIO(jpeg)) as image:
            self.assertEqual(image.size, (4, 10))

    def test_animated_gif_is_rejected(self):
        first = Image.new("RGB", (4, 4), "red")
        second = Image.new("RGB", (4, 4), "blue")
        output = io.BytesIO()
        first.save(output, format="GIF", save_all=True, append_images=[second], duration=1, loop=0)
        first.close()
        second.close()
        with self.assertRaises(vision_image.VisionImageError):
            vision_image.normalize_image(output.getvalue())

    def test_corrupt_empty_and_non_image_bytes_are_rejected(self):
        for raw in (b"", b"not an image", b"\x00" * 100):
            with self.subTest(raw=raw):
                with self.assertRaises(vision_image.VisionImageError):
                    vision_image.normalize_image(raw)

    def test_input_byte_limit_is_checked_before_decode(self):
        with mock.patch.object(vision_image, "MAX_IMAGE_BYTES", 10):
            with self.assertRaisesRegex(vision_image.VisionImageError, "слишком большое"):
                vision_image.normalize_image(b"x" * 11)

    def test_pixel_and_normalized_output_limits_are_checked(self):
        raw = encoded_image("PNG", size=(4, 3))
        with mock.patch.object(vision_image, "MAX_IMAGE_PIXELS", 10):
            with self.assertRaises(vision_image.VisionImageError):
                vision_image.normalize_image(raw)
        with mock.patch.object(vision_image, "MAX_IMAGE_BYTES", 100):
            with self.assertRaises(vision_image.VisionImageError):
                vision_image.normalize_image(raw)


if __name__ == "__main__":
    unittest.main()
