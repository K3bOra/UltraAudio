"""Exercise image branding and real crest decoding with/without receiver PIL."""
import io
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

ROOT = Path(os.environ['UA_PLUGIN_ROOT']).resolve()
sys.path.insert(0, str(ROOT.parent))
sys.dont_write_bytecode = True
from UltraAudio import livefootball as football, receiverimage


class ImageAndCrests(unittest.TestCase):
    def tearDown(self):
        receiverimage.receiver_image_label.cache_clear()

    def test_branding_and_metadata_fallback(self):
        info = types.ModuleType('Components.SystemInfo')
        info.BoxInfo = types.SimpleNamespace(getItem=lambda key: {
            'displaydistro': 'OpenATV', 'imageversion': '8.0.1'}.get(key))
        with patch.dict(sys.modules, {'Components.SystemInfo': info}):
            self.assertEqual(receiverimage.receiver_image_label(), 'OpenATV 8.0.1')
        receiverimage.receiver_image_label.cache_clear()
        with patch.dict(sys.modules, {'Components.SystemInfo': None, 'boxbranding': None}), \
             patch.object(receiverimage, '_read_fields', side_effect=lambda path: {
                 'imagename': 'DreamOS', 'imageversion': '2.6'} if path.endswith('image-version') else {}):
            self.assertEqual(receiverimage.receiver_image_label(), 'DreamOS 2.6')

    def test_all_png_modes_without_pil(self):
        image = Image.new('RGBA', (64, 64))
        draw = ImageDraw.Draw(image)
        draw.rectangle((12, 4, 51, 59), fill=(210, 30, 50, 255))
        draw.rectangle((24, 16, 39, 42), fill=(255, 255, 255, 255))
        for mode in ('RGBA', 'RGB', 'P', '1', 'L', 'LA'):
            encoded = io.BytesIO()
            image.convert(mode).save(encoded, format='PNG')
            data = encoded.getvalue()
            expected = football._decode_png_rgba(data)
            with patch.dict(sys.modules, {'PIL': None}):
                decoded = football._decode_png_rgba(data)
            with self.subTest(mode=mode, size=len(data)):
                self.assertIsNotNone(decoded)
                self.assertEqual(decoded, expected)

    def test_transparent_crest_resizes_at_each_resolution(self):
        image = Image.new('RGBA', (120, 160))
        draw = ImageDraw.Draw(image)
        draw.polygon([(20, 10), (100, 10), (90, 130), (60, 150), (30, 130)], fill=(190, 30, 30, 255))
        draw.rectangle((50, 30, 70, 100), fill=(255, 255, 255, 255))
        encoded = io.BytesIO()
        image.save(encoded, format='PNG')
        with patch.dict(sys.modules, {'PIL': None}):
            for target in (52, 78, 104, 156):
                result = football._optimize_logo_png(encoded.getvalue(), target)
                self.assertIsNotNone(result)
                decoded = football._decode_png_rgba(result)
                self.assertEqual(decoded[1:], (target, target))
                self.assertEqual(decoded[0][3], 0)
                center = ((target // 2) * target + target // 2) * 4
                self.assertGreater(decoded[0][center + 3], 200)


if __name__ == '__main__':
    unittest.main()
