"""Generate a platform-appropriate icon from the phone emoji.

Windows: launcher.ico (Segoe UI Emoji)
macOS:   launcher.icns (Apple Color Emoji via iconutil)
"""

import os
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

EMOJI = "\U0001F4F1"  # 📱
IS_MAC = sys.platform == "darwin"

# .icns requires these specific sizes (with @2x variants)
ICNS_SIZES = [16, 32, 64, 128, 256, 512]
ICO_SIZES = [16, 32, 48, 64, 128, 256]


def _render_emoji_windows(size):
    """Render emoji at the given size using Segoe UI Emoji (vector font)."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font_size = int(size * 0.85)
    try:
        font = ImageFont.truetype("seguiemj.ttf", font_size)
    except OSError:
        font = ImageFont.truetype("C:/Windows/Fonts/seguiemj.ttf", font_size)

    bbox = draw.textbbox((0, 0), EMOJI, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (size - text_w) // 2 - bbox[0]
    y = (size - text_h) // 2 - bbox[1]

    draw.text((x, y), EMOJI, font=font, embedded_color=True)
    return img


def _render_emoji_mac(size):
    """Render emoji by drawing at a supported bitmap size and scaling down.

    Apple Color Emoji is a bitmap font that only supports specific pixel sizes.
    We render at 160px (a supported size) and resize to the target.
    """
    render_size = 160
    img = Image.new("RGBA", (render_size, render_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font = ImageFont.truetype("/System/Library/Fonts/Apple Color Emoji.ttc", render_size)

    bbox = draw.textbbox((0, 0), EMOJI, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (render_size - text_w) // 2 - bbox[0]
    y = (render_size - text_h) // 2 - bbox[1]

    draw.text((x, y), EMOJI, font=font, embedded_color=True)

    if size != render_size:
        img = img.resize((size, size), Image.LANCZOS)
    return img


def render_emoji(size):
    """Render the phone emoji onto a transparent RGBA image."""
    if IS_MAC:
        return _render_emoji_mac(size)
    return _render_emoji_windows(size)


def build_ico():
    """Generate launcher.ico for Windows."""
    images = [render_emoji(s) for s in ICO_SIZES]
    images[0].save(
        "launcher.ico",
        format="ICO",
        sizes=[(s, s) for s in ICO_SIZES],
        append_images=images[1:],
    )
    print(f"Created launcher.ico with sizes: {ICO_SIZES}")


def build_icns():
    """Generate launcher.icns for macOS using iconutil."""
    iconset = "launcher.iconset"
    os.makedirs(iconset, exist_ok=True)

    for size in ICNS_SIZES:
        img = render_emoji(size)
        img.save(os.path.join(iconset, f"icon_{size}x{size}.png"))
        # @2x variant (double resolution for the half-size label)
        if size >= 32:
            half = size // 2
            img.save(os.path.join(iconset, f"icon_{half}x{half}@2x.png"))

    subprocess.run(["iconutil", "-c", "icns", iconset], check=True)
    shutil.rmtree(iconset)
    print(f"Created launcher.icns with sizes: {ICNS_SIZES}")


def main():
    if IS_MAC:
        build_icns()
    else:
        build_ico()


if __name__ == "__main__":
    main()
