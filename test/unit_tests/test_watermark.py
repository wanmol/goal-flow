import importlib.util
import io
import os
import unittest
from PIL import Image

# 直接从文件加载 watermark 模块，避免触发 utils/__init__.py 的 Redis 依赖链
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_spec = importlib.util.spec_from_file_location(
    "watermark", os.path.join(_project_root, "src", "goalflow", "utils", "watermark.py")
)
_watermark_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_watermark_mod)

add_watermark = _watermark_mod.add_watermark
WATERMARK_OFFSET_X = _watermark_mod.WATERMARK_OFFSET_X
WATERMARK_OFFSET_Y = _watermark_mod.WATERMARK_OFFSET_Y


def _create_test_image(width: int = 200, height: int = 200, color: str = "white") -> bytes:
    """创建测试用纯色图片"""
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestAddWatermark(unittest.TestCase):

    def test_returns_valid_png(self):
        """添加水印后应返回有效的 PNG 二进制数据"""
        original = _create_test_image()
        result = add_watermark(original)
        self.assertIsInstance(result, bytes)
        self.assertGreater(len(result), 0)

        img = Image.open(io.BytesIO(result))
        self.assertEqual(img.format, "PNG")

    def test_output_dimensions_unchanged(self):
        """添加水印后图片尺寸应保持不变"""
        original = _create_test_image(300, 400)
        result = add_watermark(original)

        original_img = Image.open(io.BytesIO(original))
        result_img = Image.open(io.BytesIO(result))
        self.assertEqual(original_img.size, result_img.size)

    def test_watermark_position(self):
        """水印应出现在右下角偏移 (WATERMARK_OFFSET_X, WATERMARK_OFFSET_Y) 处"""
        # 创建纯白背景，水印叠加后水印区域像素应与纯白不同
        bg_size = (300, 300)
        original = _create_test_image(*bg_size, color="white")

        result = add_watermark(original)
        result_img = Image.open(io.BytesIO(result)).convert("RGBA")

        # 右下角水印区域内应有非纯白像素（水印内容）
        wm_region_x = bg_size[0] - 80  # 水印区域大致范围
        wm_region_y = bg_size[1] - 40
        found_watermark_pixel = False
        for x in range(wm_region_x, bg_size[0] - WATERMARK_OFFSET_X + 1):
            for y in range(wm_region_y, bg_size[1] - WATERMARK_OFFSET_Y + 1):
                r, g, b, _ = result_img.getpixel((x, y))
                if (r, g, b) != (255, 255, 255):
                    found_watermark_pixel = True
                    break
            if found_watermark_pixel:
                break
        self.assertTrue(found_watermark_pixel, "应在右下角偏移位置找到水印像素")

    def test_handles_rgba_input(self):
        """应正确处理带透明通道的 RGBA 输入图片"""
        img = Image.new("RGBA", (200, 200), (255, 0, 0, 128))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        original = buf.getvalue()

        result = add_watermark(original)
        result_img = Image.open(io.BytesIO(result))
        self.assertEqual(result_img.mode, "RGBA")
        self.assertEqual(result_img.size, (200, 200))

    def test_handles_different_sizes(self):
        """应正确处理不同尺寸的图片"""
        for size in [(100, 100), (512, 512), (1024, 1024)]:
            original = _create_test_image(*size)
            result = add_watermark(original)
            result_img = Image.open(io.BytesIO(result))
            self.assertEqual(result_img.size, size)


if __name__ == "__main__":
    unittest.main()
