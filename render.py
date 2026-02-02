"""
Rug Renderer - Apply texture and seam effects to carpet designs
Ported from rug_texturing/render.py
"""
import random
from pathlib import Path
from typing import Tuple, Optional
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageEnhance, ImageOps
import numpy as np


# Texture configuration
TEXTURE_BASE_PATH = Path(__file__).parent / "texture"

# Configuration for each carpet size
SIZE_CONFIGS = {
    "2x3": {
        "texture_path": TEXTURE_BASE_PATH / "2x3.jpg",
        "target_width": 640,
        "target_height": 960,
        "seam_inset": 9,
    },
    "3x5": {
        "texture_path": TEXTURE_BASE_PATH / "3x5.jpg",
        "target_width": 600,
        "target_height": 1000,
        "seam_inset": 7,
    },
    "4x6": {
        "texture_path": TEXTURE_BASE_PATH / "4x6.jpg",
        "target_width": 640,
        "target_height": 960,
        "seam_inset": 5,
    },
    "5x7": {
        "texture_path": TEXTURE_BASE_PATH / "5x7.jpg",
        "target_width": 714,
        "target_height": 1000,
        "seam_inset": 4,
    },
    "6x9": {
        "texture_path": TEXTURE_BASE_PATH / "6x9.jpg",
        "target_width": 640,
        "target_height": 960,
        "seam_inset": 3,
    },
    "8x10": {
        "texture_path": TEXTURE_BASE_PATH / "8x10.jpg",
        "target_width": 800,
        "target_height": 1000,
        "seam_inset": 2,
    },
}

# Default texture path - try to find any available texture
TEXTURE_DIR = Path(__file__).parent / "texture"

DEFAULT_TEXTURE: Optional[Image.Image] = None
# Try to load a default texture (prefer 8x10 as it's most common)
for size in ["8x10", "6x9", "5x7", "4x6", "3x5", "2x3"]:
    texture_path = TEXTURE_DIR / f"{size}.jpg"
    if texture_path.exists():
        try:
            with Image.open(texture_path) as img:
                DEFAULT_TEXTURE = img.copy()
                break
        except Exception as e:
            pass

if DEFAULT_TEXTURE is None:
    print(f"Warning: No texture found in {TEXTURE_DIR}")


def create_edge_mask(
    size: Tuple[int, int],
    radius: int,
    jitter: int = 3,
    jitter_density: float = 0.4,
) -> Image.Image:
    """Create an L-mode mask with rounded corners and optional rough edges."""
    width, height = size
    radius = max(0, min(radius, min(width, height) // 2))
    if radius == 0:
        return Image.new("L", size, 255)

    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill=255)

    jitter = max(0, jitter)
    if jitter == 0:
        return mask

    jitter_density = max(0.0, min(1.0, jitter_density))
    if jitter_density == 0.0:
        return mask

    max_jitter = min(jitter, min(width, height) // 2)
    if max_jitter <= 0:
        return mask

    noise = Image.effect_noise(size, 255)
    mask_px = mask.load()
    noise_px = noise.load()

    corner_radius = max(0, min(radius, min(width, height) // 2))
    half_w = width / 2.0
    half_h = height / 2.0

    for y in range(height):
        for x in range(width):
            if mask_px[x, y] == 0:
                continue

            dist_x = min(x, width - 1 - x)
            dist_y = min(y, height - 1 - y)
            dist = float(min(dist_x, dist_y))

            if corner_radius > 0:
                px = x + 0.5
                py = y + 0.5
                px_sym = px if px <= half_w else width - px
                py_sym = py if py <= half_h else height - py
                if px_sym <= corner_radius and py_sym <= corner_radius:
                    dx = corner_radius - px_sym
                    dy = corner_radius - py_sym
                    radial = corner_radius - (dx * dx + dy * dy) ** 0.5
                    if radial < dist:
                        dist = max(radial, 0.0)

            if dist >= max_jitter or dist < 0:
                continue

            rnd = noise_px[x, y] / 255.0
            if rnd >= jitter_density:
                continue

            depth = max(1, int(round(max_jitter * (1.0 - rnd))))
            if dist < depth:
                mask_px[x, y] = 0

    return mask


def create_rectangular_seam_mask(
    size: Tuple[int, int], inset: int, thickness: int
) -> Image.Image:
    """Create an L-mode mask representing straight-edge seam lines."""
    width, height = size
    inset = max(0, inset)
    thickness = max(1, thickness)

    if inset >= width or inset >= height:
        return Image.new("L", size, 0)

    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)

    # Horizontal stripes
    top_y0 = inset
    top_y1 = min(height - 1, inset + thickness - 1)
    if top_y0 <= top_y1:
        draw.rectangle((inset, top_y0, width - inset - 1, top_y1), fill=255)

    bottom_y1 = height - inset - 1
    bottom_y0 = max(0, bottom_y1 - thickness + 1)
    if bottom_y0 <= bottom_y1:
        draw.rectangle((inset, bottom_y0, width - inset - 1, bottom_y1), fill=255)

    # Vertical stripes
    left_x0 = inset
    left_x1 = min(width - 1, inset + thickness - 1)
    vertical_top = top_y1 + 1
    vertical_bottom = bottom_y0 - 1
    if left_x0 <= left_x1 and vertical_top <= vertical_bottom:
        draw.rectangle((left_x0, vertical_top, left_x1, vertical_bottom), fill=255)

    right_x1 = width - inset - 1
    right_x0 = max(0, right_x1 - thickness + 1)
    if right_x0 <= right_x1 and vertical_top <= vertical_bottom:
        draw.rectangle((right_x0, vertical_top, right_x1, vertical_bottom), fill=255)

    return mask


def distort_seam_mask(
    mask: Image.Image, amount: int, frequency: float
) -> Image.Image:
    """Distort a seam mask by applying random pixel shifts."""
    if amount <= 0 or frequency <= 0:
        return mask

    width, height = mask.size
    distorted_mask = Image.new("L", (width, height), 0)

    mask_px = mask.load()
    distorted_px = distorted_mask.load()

    for y in range(height):
        for x in range(width):
            if mask_px[x, y] > 0:
                if random.random() < frequency:
                    pass
                else:
                    distorted_px[x, y] = mask_px[x, y]

    return distorted_mask


def make_texture_map(
    color_texture: Image.Image,
    size: Tuple[int, int],
    blur_radius: float = 0.0,
    contrast: float = 2.0,
) -> Image.Image:
    """Build a single-channel luminance texture map from a color texture photo."""
    tex = color_texture.convert("L")

    orig_w, orig_h = tex.size
    target_w, target_h = size
    scale_factor = max(2.0, min(orig_w / target_w, orig_h / target_h))

    if scale_factor > 2:
        intermediate_w = int(target_w * scale_factor)
        intermediate_h = int(target_h * scale_factor)
        if orig_w < intermediate_w or orig_h < intermediate_h:
            intermediate_w = min(intermediate_w, orig_w)
            intermediate_h = min(intermediate_h, orig_h)
        tex_high = tex.resize((intermediate_w, intermediate_h), Image.LANCZOS)
    else:
        tex_high = tex

    effective_blur = blur_radius if blur_radius > 0 else max(min(size) * 0.005, 3)
    low = tex_high.filter(ImageFilter.GaussianBlur(effective_blur))
    tex_high = ImageChops.subtract(tex_high, low, scale=1.0, offset=128)

    tex = tex_high.resize(size, Image.LANCZOS)

    if contrast != 1.0:
        tex = ImageEnhance.Contrast(tex).enhance(contrast)

    tex = ImageOps.autocontrast(tex, cutoff=0.1)

    return tex


def apply_texture(
    design_rgba: Image.Image,
    color_texture: Image.Image,
    strength: float,
) -> Image.Image:
    """Modulate the design image brightness using texture luminance variation."""
    strength = max(0.0, min(strength, 1.0))

    alpha = design_rgba.getchannel("A") if "A" in design_rgba.getbands() else None
    base = design_rgba.convert("RGB")
    w, h = base.size

    tex = make_texture_map(color_texture, (w, h))
    midpoint = 128

    amplification = 2.8

    shadow_mask = tex.point(
        lambda p, m=midpoint, s=strength, amp=amplification:
            int(max(0, min(255, (m - p) * amp * s)))
    )

    highlight_mask = tex.point(
        lambda p, m=midpoint, s=strength, amp=amplification:
            int(max(0, min(255, (p - m) * amp * s)))
    )

    black = Image.new("RGB", base.size, (0, 0, 0))
    white = Image.new("RGB", base.size, (255, 255, 255))

    dark_amount = 0.6 * strength
    light_amount = 0.6 * strength

    darker = Image.blend(base, black, dark_amount)
    lighter = Image.blend(base, white, light_amount)

    result = base.copy()
    result.paste(darker, mask=shadow_mask)
    result.paste(lighter, mask=highlight_mask)

    result = result.convert("RGBA")
    if alpha is not None:
        result.putalpha(alpha)

    return result


def prepare_design_layers(
    img: Image.Image,
    target_w: int,
    target_h: int,
    corner_radius: int = 1,
    edge_jitter: int = 0,
    edge_jitter_density: float = 0,
    seam_inset: int = 5,
    seam_thickness: int = 1,
    seam_strength: int = 110,
    seam_blur: int = 0,
    seam_noise_amount: int = 2,
    seam_noise_frequency: float = 0.5,
    texture_img: Optional[Image.Image] = None,
    texture_strength: float = 0.55,
) -> Tuple[Image.Image, Image.Image]:
    """Process the base design and return the image and seam layer."""
    img = img.convert("RGBA").resize((target_w, target_h), Image.LANCZOS)

    edge_mask = create_edge_mask(
        (target_w, target_h),
        corner_radius,
        jitter=edge_jitter,
        jitter_density=edge_jitter_density,
    )
    base_alpha = img.getchannel("A") if "A" in img.getbands() else Image.new(
        "L", (target_w, target_h), 255
    )
    combined_alpha = ImageChops.multiply(base_alpha, edge_mask)
    img.putalpha(combined_alpha)

    seam_inset = max(0, seam_inset)
    seam_thickness = max(1, seam_thickness)
    max_inset = max(0, min(target_w, target_h) // 2)
    seam_inset = min(seam_inset, max_inset)
    available = min(target_w, target_h) - seam_inset * 2
    if available <= 0:
        seam_thickness = 0
    else:
        seam_thickness = min(seam_thickness, available)
    seam_strength = max(0, min(seam_strength, 255))
    seam_blur = max(0, seam_blur)
    seam_layer = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))

    if seam_thickness > 0 and seam_strength > 0:
        seam_mask = create_rectangular_seam_mask(
            (target_w, target_h), seam_inset, seam_thickness
        )
        seam_mask = ImageChops.multiply(seam_mask, edge_mask)

        seam_mask = distort_seam_mask(
            seam_mask, seam_noise_amount, seam_noise_frequency
        )

        if seam_blur > 0:
            seam_mask = seam_mask.filter(ImageFilter.GaussianBlur(seam_blur))

        if seam_mask.getextrema()[1] > 0:
            gray = img.convert("L")
            midpoint = 128
            highlight_map = gray.point(
                lambda px, m=midpoint: (255 * max(0, m - px)) // m if px < m else 0
            )
            shadow_map = gray.point(
                lambda px, m=midpoint: (255 * max(0, px - m)) // (255 - m) if px > m else 0
            )

            highlight_alpha = ImageChops.multiply(seam_mask, highlight_map)
            shadow_alpha = ImageChops.multiply(seam_mask, shadow_map)

            strength_factor = 1
            effective_strength = max(0, min(255, seam_strength * strength_factor))

            highlight_alpha = highlight_alpha.point(
                lambda px: px * effective_strength // 255
            )
            shadow_alpha = shadow_alpha.point(lambda px: px * effective_strength // 255)

            if highlight_alpha.getextrema()[1] > 0:
                highlight_layer = Image.new(
                    "RGBA", (target_w, target_h), (255, 255, 255, 0)
                )
                highlight_layer.putalpha(highlight_alpha)
                seam_layer = Image.alpha_composite(seam_layer, highlight_layer)
            if shadow_alpha.getextrema()[1] > 0:
                shadow_layer = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
                shadow_layer.putalpha(shadow_alpha)
                seam_layer = Image.alpha_composite(seam_layer, shadow_layer)

    texture_to_use = texture_img if texture_img is not None else DEFAULT_TEXTURE
    if texture_to_use is not None:
        img = apply_texture(img, texture_to_use, strength=texture_strength)
    else:
        print("Warning: No texture specified.")

    return img, seam_layer


def render_rug_image(
    img: Image.Image,
    target_w: int = 800,
    target_h: int = 1000,
    corner_radius: int = 1,
    edge_jitter: int = 0,
    edge_jitter_density: float = 0,
    seam_inset: int = 5,
    seam_thickness: int = 1,
    seam_strength: int = 110,
    seam_blur: int = 0,
    seam_noise_amount: int = 2,
    seam_noise_frequency: float = 0.5,
    texture_img: Optional[Image.Image] = None,
    texture_strength: float = 0.55,
) -> Image.Image:
    """Render a rug image with texture and seam effects."""
    img, seam_layer = prepare_design_layers(
        img=img,
        target_w=target_w,
        target_h=target_h,
        corner_radius=corner_radius,
        edge_jitter=edge_jitter,
        edge_jitter_density=edge_jitter_density,
        seam_inset=seam_inset,
        seam_thickness=seam_thickness,
        seam_strength=seam_strength,
        seam_blur=seam_blur,
        seam_noise_amount=seam_noise_amount,
        seam_noise_frequency=seam_noise_frequency,
        texture_img=texture_img,
        texture_strength=texture_strength,
    )

    canvas = Image.new("RGBA", (target_w, target_h), (255, 255, 255, 255))
    canvas.alpha_composite(img)
    seam_alpha_extrema = seam_layer.getchannel("A").getextrema()
    if seam_alpha_extrema[1] > 0:
        canvas.alpha_composite(seam_layer)

    return canvas.convert("RGBA")


def rgba_to_numpy(img: Image.Image) -> np.ndarray:
    """Convert PIL RGBA image to numpy array."""
    return np.array(img)


def numpy_to_rgba(arr: np.ndarray) -> Image.Image:
    """Convert numpy array to PIL RGBA image."""
    return Image.fromarray(arr.astype(np.uint8), mode="RGBA")

