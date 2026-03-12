import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import yaml
from PIL import Image
from render import DEFAULT_SIZE, SIZE_CONFIGS, render_design

SCENE_TEMPLATES_DIR = Path(__file__).parent / "templates"
THICKNESS = 6

def load_scene_config(scene_name: str, scene_dir: Path = None) -> dict:
    templates_dir = scene_dir if scene_dir else SCENE_TEMPLATES_DIR
    yaml_path = templates_dir / f"{scene_name}.yaml"
    if not yaml_path.exists():
        raise FileNotFoundError(f"场景配置文件不存在: {yaml_path}")
    with open(yaml_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    images = config.get("images", {})

    # 使用 _wf (white floor) 提取阴影
    wf_path = templates_dir / f"{scene_name}_wf.png"
    if not wf_path.exists():
        print(f"未找到 _wf 版本，将使用原始图片提取阴影: {wf_path}")
        wf_path = templates_dir / images.get("original")
    image_path = templates_dir / images.get("original")
    fg_path = templates_dir / f"{scene_name}_fg.png" if (templates_dir / f"{scene_name}_fg.png").exists() else None

    corners = [
        tuple(config["top_left"]),
        tuple(config["top_right"]),
        tuple(config["bottom_right"]),
        tuple(config["bottom_left"]),
    ]

    # 读取 suitable_rug_size（如果存在）
    suitable_rug_size = config.get("suitable_rug_size", None)

    return {
        "image_path": image_path,
        "wf_path": wf_path,
        "fg_path": fg_path,
        "corners": corners,
        "suitable_rug_size": suitable_rug_size,
        "config": config,
    }


def load_template_images(template: dict) -> dict[str, Optional[np.ndarray]]:
    with Image.open(template["image_path"]) as img:
        scene_rgb = np.array(img.convert("RGB"))

    wf_path = template.get("wf_path")
    if wf_path:
        with Image.open(wf_path) as img:
            shadow_ref_rgb = np.array(img.convert("RGB"))
    else:
        shadow_ref_rgb = None

    fg = None
    if template.get("fg_path"):
        with Image.open(template["fg_path"]) as img:
            fg = np.array(img.convert("RGBA"))

    return {
        "scene": scene_rgb,
        "shadow": shadow_ref_rgb,
        "fg": fg,
    }


@dataclass
class SceneAssets:
    scene_rgb: np.ndarray
    shadow_ref: Optional[np.ndarray]
    fg_processed: Optional[np.ndarray]


def prepare_scene_assets(template_imgs: dict[str, Optional[np.ndarray]]) -> SceneAssets:
    scene_rgb = template_imgs.get("scene")
    if scene_rgb is None:
        raise ValueError("Invalid template images: missing scene layer")

    orig_h, orig_w = scene_rgb.shape[:2]
    shadow_ref = template_imgs.get("shadow")
    if shadow_ref is not None and shadow_ref.shape[:2] != (orig_h, orig_w):
        shadow_ref = cv2.resize(shadow_ref, (orig_w, orig_h), interpolation=cv2.INTER_LINEAR)

    fg_processed = None
    fg = template_imgs.get("fg")
    if fg is not None:
        fg_work = fg
        if fg_work.shape[:2] != (orig_h, orig_w):
            print(f"自动调整 fg 图尺寸: {fg_work.shape[1]}x{fg_work.shape[0]} -> {orig_w}x{orig_h}")
            fg_work = cv2.resize(fg_work, (orig_w, orig_h), interpolation=cv2.INTER_LINEAR)
        fg_processed = gaussian_blur_edges(fg_work, radius=2, erode=False)

    return SceneAssets(scene_rgb=scene_rgb, shadow_ref=shadow_ref, fg_processed=fg_processed)

def get_visible_edges(points: list[tuple[int, int]]) -> list[dict]:
    pts = np.array(points, dtype=np.float32)
    centroid = np.mean(pts, axis=0)
    edges = [("top", pts[0], pts[1]), ("right", pts[1], pts[2]), ("bottom", pts[2], pts[3]), ("left", pts[3], pts[0])]
    visible_edges = []

    print(f"\n=== 检测可见边 ===")
    print(f"四个角点: {points}")
    print(f"中心点: {centroid}")

    for name, start, end in edges:
        vec = end - start
        length = np.linalg.norm(vec)
        if length <= 0: continue
        n1 = np.array([vec[1], -vec[0]], dtype=np.float32)
        n2 = np.array([-vec[1], vec[0]], dtype=np.float32)
        mid = (start + end) / 2
        # outward Normal points away from centroid
        to_center = centroid - mid
        outward = n1 if np.dot(n1, to_center) < 0 else n2
        outward = outward / np.linalg.norm(outward)
        visibility = max(0.0, float(outward[1])) # points down

        print(f"  边 {name}: 起点{start} -> 终点{end}, 法向量{outward}, 可见度={visibility:.3f}")

        if visibility > 0:
            visible_edges.append({"name": name, "start": start, "end": end, "outward": outward, "visibility": visibility})
            print(f"    ✓ 该边可见，将添加厚度条")

    print(f"共找到 {len(visible_edges)} 条可见边\n")
    return visible_edges

def add_thickness_to_visible_edges(rug_rgba: np.ndarray, dst_points: list[tuple[int, int]], scale_factor: int = 1) -> np.ndarray:
    h, w = rug_rgba.shape[:2]
    alpha = rug_rgba[:, :, 3].copy()
    visible_edges = get_visible_edges(dst_points)

    if len(visible_edges) == 0:
        print("⚠️  没有检测到可见边，跳过厚度条添加")
        return rug_rgba

    print(f"开始为 {len(visible_edges)} 条可见边添加厚度条...")

    thickness = THICKNESS * scale_factor
    thickness_direction = np.array([0, 1], dtype=np.float32)

    top_color = np.array([255, 250, 230], dtype=np.float32)
    bottom_color = np.array([20, 20, 20], dtype=np.float32)

    for edge in visible_edges:
        start, end = edge["start"], edge["end"]
        edge_len = np.linalg.norm(end - start)
        num_samples = int(edge_len) + 1
        offset = thickness_direction * max(1, thickness - 2)
        next_offset = offset

        for i in range(num_samples):
            t = i / max(1, num_samples - 1)
            point = start + t * (end - start)

            if i < num_samples - 1:
                next_t = (i + 1) / max(1, num_samples - 1)
                next_point = start + next_t * (end - start)
                poly = np.array([point, next_point, next_point + next_offset, point + offset], dtype=np.int32)
            else:
                poly = np.array([point, point, point + offset, point + offset], dtype=np.int32)

            x_min, x_max = int(max(0, np.min(poly[:, 0]))), int(min(w - 1, np.max(poly[:, 0])))
            y_min, y_max = int(max(0, np.min(poly[:, 1]))), int(min(h - 1, np.max(poly[:, 1])))
            if x_max < x_min or y_max < y_min: continue

            mask_roi = np.zeros((y_max - y_min + 1, x_max - x_min + 1), dtype=np.uint8)
            cv2.fillConvexPoly(mask_roi, (poly - [x_min, y_min]), 255)

            roi_h, roi_w = mask_roi.shape
            soft_mask = mask_roi.astype(np.float32) / 255.0

            gradient_map = np.zeros((roi_h, roi_w, 3), dtype=np.float32)

            for y in range(roi_h):
                global_y = y + y_min
                edge_progress = (global_y - point[1]) / max(0.1, offset[1]) if offset[1] > 0 else 0
                edge_progress = np.clip(edge_progress, 0, 1)
                pixel_color = top_color * (1 - edge_progress) + bottom_color * edge_progress
                gradient_map[y, :] = pixel_color

            alpha_roi = alpha[y_min : y_max + 1, x_min : x_max + 1]
            rug_alpha_f = alpha_roi.astype(np.float32) / 255.0
            thickness_weight = soft_mask * (1.0 - rug_alpha_f)

            for c in range(3):
                roi_c = rug_rgba[y_min : y_max + 1, x_min : x_max + 1, c].astype(np.float32)
                gradient_c = gradient_map[:, :, c]

                rug_rgba[y_min : y_max + 1, x_min : x_max + 1, c] = (
                    roi_c * (1.0 - thickness_weight) + gradient_c * thickness_weight
                ).astype(np.uint8)

            alpha[y_min : y_max + 1, x_min : x_max + 1] = (np.maximum(rug_alpha_f, soft_mask) * 255).astype(np.uint8)

    rug_rgba[:, :, 3] = alpha
    print(f"✓ 厚度条添加完成\n")
    return rug_rgba

def apply_lighting(rug_rgba: np.ndarray, shadow_ref_rgb: np.ndarray, intensity: float = 1.0) -> np.ndarray:
    gray = cv2.cvtColor(shadow_ref_rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    factor = gray * intensity + (1.0 - intensity)
    
    result = rug_rgba.copy()
    mask = result[:, :, 3] > 0
    for c in range(3):
        result[:, :, c][mask] = np.clip(result[:, :, c][mask].astype(np.float32) * factor[mask], 0, 255).astype(np.uint8)
    return result

def gaussian_blur_edges(rgba: np.ndarray, radius: int = 2, erode: bool = True) -> np.ndarray:
    """边缘高斯模糊

    Args:
        rgba: RGBA图像
        radius: 模糊半径
        erode: 是否先腐蚀（用于消除黑边）
    """
    if radius <= 0: return rgba
    result = rgba.copy()
    alpha = result[:, :, 3]
    
    if erode:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        alpha = cv2.erode(alpha, kernel, iterations=1)
    
    alpha_f = cv2.GaussianBlur(alpha, (radius*2+1, radius*2+1), 0)
    result[:, :, 3] = alpha_f
    return result


def composite_rendered_to_scene(
    rendered_design_image: Image.Image,
    *,
    template: dict,
    assets: SceneAssets,
    shadow_intensity: float = 1.6,
    scale_factor: int = 1,
) -> Image.Image:
    scene_rgb = assets.scene_rgb
    shadow_ref = assets.shadow_ref
    fg_processed = assets.fg_processed
    orig_h, orig_w = scene_rgb.shape[:2]
    h, w = orig_h * scale_factor, orig_w * scale_factor
    scaled_corners = [(int(x * scale_factor), int(y * scale_factor)) for x, y in template["corners"]]

    if rendered_design_image.mode == "RGBA":
        rug_rgba = np.array(rendered_design_image)
    else:
        rug_rgba = np.array(rendered_design_image.convert("RGBA"))

    rug_rgb = rug_rgba[:, :, :3]
    rug_alpha = rug_rgba[:, :, 3]
    src_pts = np.float32([(0, 0), (rug_rgb.shape[1], 0), (rug_rgb.shape[1], rug_rgb.shape[0]), (0, rug_rgb.shape[0])])
    dst_pts = np.float32(scaled_corners)
    matrix = cv2.getPerspectiveTransform(src_pts, dst_pts)

    warped_rgb = cv2.warpPerspective(rug_rgb, matrix, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    warped_alpha = cv2.warpPerspective(rug_alpha, matrix, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    warped_rug = np.dstack([warped_rgb, warped_alpha])

    warped_rug = add_thickness_to_visible_edges(warped_rug, scaled_corners, scale_factor)
    warped_rug_down = cv2.resize(warped_rug, (orig_w, orig_h), interpolation=cv2.INTER_LINEAR)

    if shadow_ref is not None:
        warped_rug_down = apply_lighting(warped_rug_down, shadow_ref, shadow_intensity)

    warped_rug_down = gaussian_blur_edges(warped_rug_down, radius=1, erode=False)
    result = scene_rgb.astype(np.float32)
    alpha = warped_rug_down[:, :, 3].astype(np.float32) / 255.0
    warp_rgb = warped_rug_down[:, :, :3].astype(np.float32)
    for c in range(3):
        result[:, :, c] = result[:, :, c] * (1.0 - alpha) + warp_rgb[:, :, c] * alpha

    if fg_processed is not None:
        fg_a = fg_processed[:, :, 3].astype(np.float32) / 255.0
        fg_rgb = fg_processed[:, :, :3].astype(np.float32)
        for c in range(3):
            result[:, :, c] = result[:, :, c] * (1.0 - fg_a) + fg_rgb[:, :, c] * fg_a

    return Image.fromarray(result.astype(np.uint8))


def composite_scene(scene_name: str, design_path: str = None, output_path: str = None,
                    shadow_intensity: float = 1.6, rug_thickness: int = 6, debug: bool = False,
                    skip_render: bool = False, texture_strength: float = 0.55,
                    scale_factor: int = 2, scene_dir: Path = None, webp_quality: int = 85):
    """
    Composite a rug into a scene with 2x supersampling for better quality.

    Args:
        scene_name: Scene configuration name
        design_path: Path to rug design image (optional, uses red placeholder if not provided)
        output_path: Output file path (default: {scene_name}.webp)
        shadow_intensity: Shadow intensity (0-2)
        rug_thickness: Deprecated, kept for CLI compatibility
        debug: Enable debug output
        skip_render: Skip rug rendering (texture and seam effects)
        texture_strength: Texture effect strength (0-1)
        scale_factor: Supersampling factor (default: 2)
        scene_dir: Scene templates directory (default: SCENE_TEMPLATES_DIR)
        webp_quality: WebP quality (1-100, default: 85)
    """
    if output_path is None:
        output_path = f"{scene_name}.webp"

    config = load_scene_config(scene_name, scene_dir)
    assets = prepare_scene_assets(load_template_images(config))

    if design_path:
        rug_pil = Image.open(design_path).convert("RGBA")
        print(f"加载地毯图像: {design_path}")
    else:
        rug_pil = Image.new("RGBA", (1000, 1000), (255, 0, 0, 255))
        print("使用红色占位地毯")

    if not skip_render:
        print("应用地毯材质渲染...")
        suitable_rug_size = config.get("suitable_rug_size")
        if suitable_rug_size not in SIZE_CONFIGS:
            if suitable_rug_size:
                print(f"警告: 尺寸 {suitable_rug_size} 不在 SIZE_CONFIGS 中，回退到 {DEFAULT_SIZE}")
            suitable_rug_size = DEFAULT_SIZE
        print(f"使用地毯尺寸: {suitable_rug_size}")
        rendered_rug = render_design(rug_pil, size=suitable_rug_size, texture_strength=texture_strength)
        print("地毯渲染完成")
    else:
        print("跳过地毯渲染")
        rendered_rug = rug_pil

    result = composite_rendered_to_scene(
        rendered_rug,
        template=config,
        assets=assets,
        shadow_intensity=shadow_intensity,
        scale_factor=scale_factor,
    )

    if rug_thickness != THICKNESS and debug:
        print(f"提示: 当前算法固定使用厚度 {THICKNESS}px，忽略传入值 {rug_thickness}")

    result.save(output_path, format='WEBP', quality=webp_quality, method=6)
    print(f"已保存: {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Composite a rug into a scene with optional texture rendering")
    parser.add_argument("scene", help="Scene configuration name (use 'all' to process all templates)")
    parser.add_argument("--scene-dir", type=lambda x: Path(x), default=None, help=f"Scene templates directory (default: {SCENE_TEMPLATES_DIR})")
    parser.add_argument("--design", required=False, help="Path to rug design image (optional)")
    parser.add_argument("--output", default=None, help="Output file path (default: {scene_name}.webp)")
    parser.add_argument("--shadow-intensity", type=float, default=1.6, help="Shadow intensity (0-2)")
    parser.add_argument("--thickness", type=int, default=6, help="Rug edge thickness in pixels")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument("--skip-render", action="store_true", help="Skip rug texture/seam rendering")
    parser.add_argument("--texture-strength", type=float, default=0.55, help="Texture effect strength (0-1)")
    parser.add_argument("--scale-factor", type=int, default=2, help="Supersampling factor (default: 2)")
    parser.add_argument("--webp-quality", type=int, default=85, help="WebP quality (1-100, default: 85)")
    args = parser.parse_args()
    
    # 支持批量处理所有模板
    if args.scene.lower() == "all":
        templates_dir = args.scene_dir if args.scene_dir else SCENE_TEMPLATES_DIR
        yaml_files = list(templates_dir.glob("*.yaml"))
        
        if not yaml_files:
            print(f"错误: 未在 {templates_dir} 中找到任何 .yaml 模板文件")
            exit(1)
        
        print(f"找到 {len(yaml_files)} 个场景模板，开始批量处理...\n")
        
        for yaml_file in yaml_files:
            scene_name = yaml_file.stem
            print(f"\n{'='*60}")
            print(f"正在处理场景: {scene_name}")
            print(f"{'='*60}\n")
            
            try:
                composite_scene(
                    scene_name, 
                    args.design, 
                    None,  # 自动生成输出文件名
                    args.shadow_intensity, 
                    args.thickness,
                    args.debug, 
                    args.skip_render, 
                    args.texture_strength, 
                    args.scale_factor, 
                    args.scene_dir,
                    args.webp_quality
                )
            except Exception as e:
                print(f"❌ 处理场景 {scene_name} 时出错: {e}")
                if args.debug:
                    import traceback
                    traceback.print_exc()
                continue
        
        print(f"\n\n{'='*60}")
        print(f"批量处理完成！共处理 {len(yaml_files)} 个场景")
        print(f"{'='*60}")
    else:
        composite_scene(
            args.scene, 
            args.design, 
            args.output, 
            args.shadow_intensity, 
            args.thickness,
            args.debug, 
            args.skip_render, 
            args.texture_strength, 
            args.scale_factor, 
            args.scene_dir,
            args.webp_quality
        )
