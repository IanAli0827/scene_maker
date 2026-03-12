"""Rug texture rendering module for design images."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps

TEXTURE_BASE_PATH = Path(__file__).parent / "texture"

D_SEAM_THICKNESS = 1
D_SEAM_STRENGTH = 110
D_SEAM_BLUR = 0
D_SEAM_NOISE_AMT = 2
D_SEAM_NOISE_FREQ = 0.5
D_TEXTURE_STRENGTH = 0.55

SIZE_CONFIGS = {
    "2x3": {"target_width": 640, "target_height": 960, "seam_inset": 9},
    "3x5": {"target_width": 600, "target_height": 1000, "seam_inset": 7},
    "4x6": {"target_width": 640, "target_height": 960, "seam_inset": 5},
    "5x7": {"target_width": 714, "target_height": 1000, "seam_inset": 4},
    "6x9": {"target_width": 640, "target_height": 960, "seam_inset": 3},
    "8x10": {"target_width": 800, "target_height": 1000, "seam_inset": 2},
}
DEFAULT_SIZE = "8x10"


def create_rectangular_seam_mask(size: Tuple[int, int], inset: int, thickness: int) -> Image.Image:
    """Return an L-mode mask representing straight-edge seam lines."""
    width, height = size
    inset, thickness = max(0, inset), max(1, thickness)
    if inset >= width or inset >= height:
        return Image.new("L", size, 0)

    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    t_y1 = min(height - 1, inset + thickness - 1)
    if inset <= t_y1:
        draw.rectangle((inset, inset, width - inset - 1, t_y1), fill=255)
    b_y1 = height - inset - 1
    b_y0 = max(0, b_y1 - thickness + 1)
    if b_y0 <= b_y1:
        draw.rectangle((inset, b_y0, width - inset - 1, b_y1), fill=255)
    l_x1 = min(width - 1, inset + thickness - 1)
    v_top, v_bottom = t_y1 + 1, b_y0 - 1
    if inset <= l_x1 and v_top <= v_bottom:
        draw.rectangle((inset, v_top, l_x1, v_bottom), fill=255)
    r_x1 = width - inset - 1
    r_x0 = max(0, r_x1 - thickness + 1)
    if r_x0 <= r_x1 and v_top <= v_bottom:
        draw.rectangle((r_x0, v_top, r_x1, v_bottom), fill=255)
    return mask


def distort_seam_mask(mask: Image.Image, amount: int, frequency: float) -> Image.Image:
    """Distort a seam mask by applying random pixel shifts."""
    if amount <= 0 or frequency <= 0:
        return mask

    width, height = mask.size
    distorted = Image.new("L", (width, height), 0)
    m_px, d_px = mask.load(), distorted.load()
    for y in range(height):
        for x in range(width):
            if m_px[x, y] > 0 and random.random() >= frequency:
                d_px[x, y] = m_px[x, y]
    return distorted


def make_texture_map(color_texture: Image.Image, size: Tuple[int, int], contrast: float = 2.0) -> Image.Image:
    """Build a single-channel luminance texture map."""
    tex = color_texture
    w, h = size
    scale = max(2.0, min(tex.size[0] / w, tex.size[1] / h))
    if scale > 2:
        iw = min(int(w * scale), tex.size[0])
        ih = min(int(h * scale), tex.size[1])
        tex = tex.resize((iw, ih), Image.LANCZOS)
    blur = max(min(size) * 0.005, 3)
    low = tex.filter(ImageFilter.GaussianBlur(blur))
    tex = ImageChops.subtract(tex, low, scale=1.0, offset=128)
    tex = tex.resize(size, Image.LANCZOS)
    if contrast != 1.0:
        tex = ImageEnhance.Contrast(tex).enhance(contrast)
    return ImageOps.autocontrast(tex, cutoff=0.1)


def apply_texture(design_rgba: Image.Image, color_texture: Image.Image, strength: float) -> Image.Image:
    """Modulate brightness using texture luminance."""
    strength = max(0.0, min(strength, 1.0))
    alpha = design_rgba.getchannel("A") if "A" in design_rgba.getbands() else None
    base = design_rgba.convert("RGB")
    tex = make_texture_map(color_texture, base.size)
    shadow_mask = tex.point(lambda p: int(max(0, min(255, (128 - p) * 2.8 * strength))))
    highlight_mask = tex.point(lambda p: int(max(0, min(255, (p - 128) * 2.8 * strength))))
    darker = Image.blend(base, Image.new("RGB", base.size, (0, 0, 0)), 0.6 * strength)
    lighter = Image.blend(base, Image.new("RGB", base.size, (255, 255, 255)), 0.6 * strength)
    base.paste(darker, mask=shadow_mask)
    base.paste(lighter, mask=highlight_mask)
    if alpha:
        base.putalpha(alpha)
    return base.convert("RGBA")


def load_size_texture(size: str) -> Optional[Image.Image]:
    """Load the texture image for a specific rug size (as L-mode)."""
    path = TEXTURE_BASE_PATH / f"{size}.jpg"
    if not path.exists():
        return None
    try:
        with Image.open(path) as img:
            return img.convert("L")
    except Exception:
        return None


def get_supported_sizes() -> list[str]:
    return list(SIZE_CONFIGS.keys())


def render_design(
    img: Image.Image,
    size: str = DEFAULT_SIZE,
    seam_thickness: int = D_SEAM_THICKNESS,
    seam_strength: int = D_SEAM_STRENGTH,
    seam_blur: int = D_SEAM_BLUR,
    seam_noise_amount: int = D_SEAM_NOISE_AMT,
    seam_noise_frequency: float = D_SEAM_NOISE_FREQ,
    texture_strength: float = D_TEXTURE_STRENGTH,
) -> Image.Image:
    """Render a rug design."""
    if size not in SIZE_CONFIGS:
        raise ValueError(f"Unknown size '{size}'")

    conf = SIZE_CONFIGS[size]
    target_w, target_h = conf["target_width"], conf["target_height"]

    if img.mode != "RGBA":
        img = img.convert("RGBA")
    img = img.resize((target_w, target_h), Image.LANCZOS)

    seam_layer = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    s_thickness = seam_thickness
    if s_thickness > 0 and seam_strength > 0:
        s_mask = create_rectangular_seam_mask((target_w, target_h), int(conf["seam_inset"]), s_thickness)
        s_mask = distort_seam_mask(s_mask, seam_noise_amount, seam_noise_frequency)
        if seam_blur > 0:
            s_mask = s_mask.filter(ImageFilter.GaussianBlur(seam_blur))
        gray = img.convert("L")
        h_alpha = ImageChops.multiply(
            s_mask,
            gray.point(lambda p: (255 * max(0, 128 - p)) // 128 if p < 128 else 0),
        ).point(lambda p: p * seam_strength // 255)
        s_alpha = ImageChops.multiply(
            s_mask,
            gray.point(lambda p: (255 * max(0, p - 128)) // 127 if p > 128 else 0),
        ).point(lambda p: p * seam_strength // 255)
        if h_alpha.getextrema()[1] > 0:
            highlight_layer = Image.new("RGBA", (target_w, target_h), (255, 255, 255, 0))
            highlight_layer.putalpha(h_alpha)
            seam_layer = Image.alpha_composite(seam_layer, highlight_layer)
        if s_alpha.getextrema()[1] > 0:
            shadow_layer = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
            shadow_layer.putalpha(s_alpha)
            seam_layer = Image.alpha_composite(seam_layer, shadow_layer)

    tex_img = load_size_texture(size)
    if tex_img:
        img = apply_texture(img, tex_img, texture_strength)
    img.alpha_composite(seam_layer)
    return img


def render_rug_image(
    img: Image.Image,
    target_w: int = 800,
    target_h: int = 1000,
    corner_radius: int = 1,
    edge_jitter: int = 0,
    edge_jitter_density: float = 0,
    seam_inset: int = 5,
    seam_thickness: int = D_SEAM_THICKNESS,
    seam_strength: int = D_SEAM_STRENGTH,
    seam_blur: int = D_SEAM_BLUR,
    seam_noise_amount: int = D_SEAM_NOISE_AMT,
    seam_noise_frequency: float = D_SEAM_NOISE_FREQ,
    texture_img: Optional[Image.Image] = None,
    texture_strength: float = D_TEXTURE_STRENGTH,
) -> Image.Image:
    """Backward-compatible wrapper for local scene maker scripts."""
    del corner_radius, edge_jitter, edge_jitter_density, seam_inset, texture_img

    size_key = None
    for candidate_size, conf in SIZE_CONFIGS.items():
        if conf["target_width"] == target_w and conf["target_height"] == target_h:
            size_key = candidate_size
            break

    if size_key is not None:
        return render_design(
            img,
            size=size_key,
            seam_thickness=seam_thickness,
            seam_strength=seam_strength,
            seam_blur=seam_blur,
            seam_noise_amount=seam_noise_amount,
            seam_noise_frequency=seam_noise_frequency,
            texture_strength=texture_strength,
        )

    if img.mode != "RGBA":
        img = img.convert("RGBA")
    img = img.resize((target_w, target_h), Image.LANCZOS)
    if texture_strength > 0:
        tex_img = load_size_texture(DEFAULT_SIZE)
        if tex_img:
            img = apply_texture(img, tex_img, texture_strength)
    return img


def render_on_fixed_canvas(
    img: Image.Image,
    size: str = DEFAULT_SIZE,
    canvas_w: int = 1100,
    canvas_h: int = 1100,
    shadow_offset: Tuple[int, int] = (10, 10),
    shadow_blur: int = 8,
    shadow_opacity: int = 140,
    seam_thickness: int = D_SEAM_THICKNESS,
    seam_strength: int = D_SEAM_STRENGTH,
    seam_blur: int = D_SEAM_BLUR,
    seam_noise_amount: int = D_SEAM_NOISE_AMT,
    seam_noise_frequency: float = D_SEAM_NOISE_FREQ,
    bg: Tuple[int, int, int] = (255, 255, 255),
    texture_strength: float = D_TEXTURE_STRENGTH,
) -> Image.Image:
    """Render design on fixed canvas with shadow."""
    rug = render_design(
        img,
        size=size,
        seam_thickness=seam_thickness,
        seam_strength=seam_strength,
        seam_blur=seam_blur,
        seam_noise_amount=seam_noise_amount,
        seam_noise_frequency=seam_noise_frequency,
        texture_strength=texture_strength,
    )
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (*bg, 255))
    pos = ((canvas_w - rug.size[0]) // 2, (canvas_h - rug.size[1]) // 2)

    if shadow_opacity > 0:
        shadow = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        bbox = (
            pos[0] + shadow_offset[0],
            pos[1] + shadow_offset[1],
            pos[0] + shadow_offset[0] + rug.size[0],
            pos[1] + shadow_offset[1] + rug.size[1],
        )
        ImageDraw.Draw(shadow).rectangle(bbox, fill=(0, 0, 0, shadow_opacity))
        if shadow_blur > 0:
            shadow = shadow.filter(ImageFilter.GaussianBlur(shadow_blur))

        mask = rug.getchannel("A")
        filter_size = max(3, 5 * 2 + 1)
        filter_size = filter_size + 1 if filter_size % 2 == 0 else filter_size
        cutout = Image.new("L", (canvas_w, canvas_h), 255)
        cutout.paste(mask.filter(ImageFilter.MinFilter(filter_size)).point(lambda p: 255 - p), pos)
        shadow.putalpha(ImageChops.multiply(shadow.split()[3], cutout))
        canvas.alpha_composite(shadow)

    canvas.alpha_composite(rug, pos)
    return canvas.convert("RGB")


def rgba_to_numpy(img: Image.Image) -> np.ndarray:
    return np.array(img)


def numpy_to_rgba(arr: np.ndarray) -> Image.Image:
    return Image.fromarray(arr.astype(np.uint8), mode="RGBA")
