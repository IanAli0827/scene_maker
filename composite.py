import argparse
from pathlib import Path
import cv2
import numpy as np
import yaml
from PIL import Image
from rug_renderer import render_rug_image, rgba_to_numpy, numpy_to_rgba, SIZE_CONFIGS

SCENE_TEMPLATES_DIR = Path(__file__).parent / "templates"

def load_scene_config(scene_name: str) -> dict:
    yaml_path = SCENE_TEMPLATES_DIR / f"{scene_name}.yaml"
    if not yaml_path.exists():
        raise FileNotFoundError(f"场景配置文件不存在: {yaml_path}")
    with open(yaml_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    images = config.get("images", {})

    # 使用 _wf (white floor) 提取阴影
    wf_path = SCENE_TEMPLATES_DIR / f"{scene_name}_wf.png"
    if not wf_path.exists():
        print(f"未找到 _wf 版本，将使用原始图片提取阴影: {wf_path}")
        wf_path = SCENE_TEMPLATES_DIR / images.get("original")
    image_path = SCENE_TEMPLATES_DIR / images.get("original")
    fg_path = SCENE_TEMPLATES_DIR / f"{scene_name}_fg.png" if (SCENE_TEMPLATES_DIR / f"{scene_name}_fg.png").exists() else None

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

def add_thickness_to_visible_edges(rug_rgba: np.ndarray, dst_points: list[tuple[int, int]], thickness: int = 6) -> np.ndarray:
    result = rug_rgba.copy()
    h, w = result.shape[:2]
    alpha = result[:, :, 3]
    visible_edges = get_visible_edges(dst_points)

    if len(visible_edges) == 0:
        print("⚠️  没有检测到可见边，跳过厚度条添加")
        return result

    print(f"开始为 {len(visible_edges)} 条可见边添加厚度条...")

    min_thickness = 4
    max_thickness = thickness
    img_bottom = h

    # 厚度方向：垂直向下（图片坐标系的Y轴正方向）
    thickness_direction = np.array([0, 1], dtype=np.float32)

    # 厚度条颜色：上米白，下黑
    top_color = np.array([255, 250, 230], dtype=np.float32)  # 米黄色
    bottom_color = np.array([20, 20, 20], dtype=np.float32)  # 深灰色（接近黑色）

    for edge in visible_edges:
        start, end = edge["start"], edge["end"]
        edge_len = np.linalg.norm(end - start)
        num_samples = int(edge_len) + 1

        for i in range(num_samples):
            t = i / max(1, num_samples - 1)
            point = start + t * (end - start)
            depth_ratio = point[1] / img_bottom
            local_thickness = min_thickness + (max_thickness - min_thickness) * depth_ratio
            offset = thickness_direction * local_thickness

            if i < num_samples - 1:
                next_t = (i + 1) / max(1, num_samples - 1)
                next_point = start + next_t * (end - start)
                next_depth_ratio = next_point[1] / img_bottom
                next_thickness = min_thickness + (max_thickness - min_thickness) * next_depth_ratio
                next_offset = thickness_direction * next_thickness
                poly = np.array([point, next_point, next_point + next_offset, point + offset], dtype=np.int32)
            else:
                poly = np.array([point, point, point + offset, point + offset], dtype=np.int32)

            x_min, x_max = int(max(0, np.min(poly[:, 0]))), int(min(w - 1, np.max(poly[:, 0])))
            y_min, y_max = int(max(0, np.min(poly[:, 1]))), int(min(h - 1, np.max(poly[:, 1])))
            if x_max < x_min or y_max < y_min: continue

            mask_roi = np.zeros((y_max - y_min + 1, x_max - x_min + 1), dtype=np.uint8)
            cv2.fillConvexPoly(mask_roi, (poly - [x_min, y_min]), 255)
            mask_roi = cv2.GaussianBlur(mask_roi, (1, 1), 0)

            roi_h, roi_w = mask_roi.shape
            soft_mask = mask_roi.astype(np.float32) / 255.0

            # 创建渐变颜色图
            gradient_map = np.zeros((roi_h, roi_w, 3), dtype=np.float32)

            # 对每个像素，根据其在厚度条中的相对位置计算颜色
            for y in range(roi_h):
                global_y = y + y_min
                # 计算该行在厚度条中的相对位置（0=顶边，1=底边）
                # 找到该像素对应的边上的点
                edge_progress = (global_y - point[1]) / max(0.1, offset[1]) if offset[1] > 0 else 0
                edge_progress = np.clip(edge_progress, 0, 1)

                # 根据相对位置插值颜色（0=米白，1=黑色）
                lerp_factor = edge_progress
                pixel_color = top_color * (1 - lerp_factor) + bottom_color * lerp_factor
                gradient_map[y, :] = pixel_color

            alpha_roi = alpha[y_min : y_max + 1, x_min : x_max + 1]
            rug_alpha_f = alpha_roi.astype(np.float32) / 255.0
            thickness_weight = soft_mask * (1.0 - rug_alpha_f)

            for c in range(3):
                roi_c = result[y_min : y_max + 1, x_min : x_max + 1, c].astype(np.float32)
                gradient_c = gradient_map[:, :, c]

                result[y_min : y_max + 1, x_min : x_max + 1, c] = (
                    roi_c * (1.0 - thickness_weight) + gradient_c * thickness_weight
                ).astype(np.uint8)

            alpha[y_min : y_max + 1, x_min : x_max + 1] = (np.maximum(rug_alpha_f, soft_mask) * 255).astype(np.uint8)

    print(f"✓ 厚度条添加完成\n")
    return result

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

def composite_scene(scene_name: str, design_path: str = None, output_path: str = "output.png",
                    shadow_intensity: float = 1.0, rug_thickness: int = 6, debug: bool = False,
                    skip_render: bool = False, texture_strength: float = 0.55):
    """
    Composite a rug into a scene.

    Args:
        scene_name: Scene configuration name
        design_path: Path to rug design image (optional, uses red placeholder if not provided)
        output_path: Output file path
        shadow_intensity: Shadow intensity (0-2)
        rug_thickness: Rug edge thickness in pixels
        debug: Enable debug output
        skip_render: Skip rug rendering (texture and seam effects)
        texture_strength: Texture effect strength (0-1)
    """
    config = load_scene_config(scene_name)
    scene_rgb = np.array(Image.open(config["image_path"]).convert("RGB"))
    shadow_ref_rgb = np.array(Image.open(config["wf_path"]).convert("RGB"))

    h, w = scene_rgb.shape[:2]

    # 检查并调整 wf 图尺寸
    wf_h, wf_w = shadow_ref_rgb.shape[:2]
    wf_ratio = wf_w / wf_h
    scene_ratio = w / h

    if abs(wf_ratio - scene_ratio) > 0.01:
        print(f"警告: wf 图比例 ({wf_w}x{wf_h}, {wf_ratio:.3f}) 与原图比例 ({w}x{h}, {scene_ratio:.3f}) 不一致")

    if wf_h != h or wf_w != w:
        print(f"自动调整 wf 图尺寸: {wf_w}x{wf_h} -> {w}x{h}")
        shadow_ref_rgb = cv2.resize(shadow_ref_rgb, (w, h), interpolation=cv2.INTER_LINEAR)

    # 加载或创建地毯图像
    if design_path:
        rug_pil = Image.open(design_path).convert("RGBA")
        print(f"加载地毯图像: {design_path}")
    else:
        rug_pil = Image.new("RGBA", (1000, 1000), (255, 0, 0, 255))
        print("使用红色占位地毯")

    # 渲染地毯
    if not skip_render:
        print("应用地毯材质渲染...")

        # 计算目标渲染尺寸
        suitable_rug_size = config.get("suitable_rug_size")
        if suitable_rug_size and suitable_rug_size in SIZE_CONFIGS:
            # 使用 SIZE_CONFIGS 中的预定义尺寸
            size_config = SIZE_CONFIGS[suitable_rug_size]
            target_w = size_config["target_width"]
            target_h = size_config["target_height"]
            print(f"使用地毯尺寸: {suitable_rug_size} (渲染为 {target_w}x{target_h})")
        else:
            # 如果没有指定尺寸或尺寸不在配置中，使用地毯当前尺寸
            target_w, target_h = rug_pil.size
            if suitable_rug_size:
                print(f"警告: 尺寸 {suitable_rug_size} 不在 SIZE_CONFIGS 中，使用原始尺寸: {target_w}x{target_h}")
            else:
                print(f"使用地毯原始尺寸: {target_w}x{target_h}")

        rug_pil_rendered = render_rug_image(
            rug_pil,
            target_w=target_w,
            target_h=target_h,
            texture_strength=texture_strength,
        )
        rug_rgba = rgba_to_numpy(rug_pil_rendered)
        print("地毯渲染完成")
    else:
        print("跳过地毯渲染")
        rug_rgba = np.array(rug_pil)
    
    src_pts = np.float32([(0, 0), (rug_rgba.shape[1], 0), (rug_rgba.shape[1], rug_rgba.shape[0]), (0, rug_rgba.shape[0])])
    dst_pts = np.float32(config["corners"])
    M = cv2.getPerspectiveTransform(src_pts, dst_pts)
    
    warped_rgb = cv2.warpPerspective(rug_rgba[:, :, :3], M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    warped_alpha = cv2.warpPerspective(rug_rgba[:, :, 3], M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    warped_rug = np.dstack([warped_rgb, warped_alpha])
    
    top_mask = warped_rug[:, :, 3].copy()
    warped_rug = add_thickness_to_visible_edges(warped_rug, config["corners"], thickness=rug_thickness)
    warped_rug = apply_lighting(warped_rug, shadow_ref_rgb, shadow_intensity)
    
    warped_rug = gaussian_blur_edges(warped_rug, radius=1, erode=True)
    alpha = warped_rug[:, :, 3].astype(np.float32) / 255.0
    result = scene_rgb.astype(np.float32)
    for c in range(3):
        result[:, :, c] = result[:, :, c] * (1.0 - alpha) + warped_rug[:, :, c].astype(np.float32) * alpha
    
    if config["fg_path"]:
        fg = np.array(Image.open(config["fg_path"]).convert("RGBA"))
        fg_h, fg_w = fg.shape[:2]
        fg_ratio = fg_w / fg_h
        
        if abs(fg_ratio - scene_ratio) > 0.01:
            print(f"警告: fg 图比例 ({fg_w}x{fg_h}, {fg_ratio:.3f}) 与原图比例 ({w}x{h}, {scene_ratio:.3f}) 不一致")
        
        if fg_h != h or fg_w != w:
            print(f"自动调整 fg 图尺寸: {fg_w}x{fg_h} -> {w}x{h}")
            fg = cv2.resize(fg, (w, h), interpolation=cv2.INTER_LINEAR)
        
        fg = gaussian_blur_edges(fg, radius=2, erode=False)
        fg_a = fg[:, :, 3].astype(np.float32) / 255.0
        for c in range(3):
            result[:, :, c] = result[:, :, c] * (1.0 - fg_a) + fg[:, :, c].astype(np.float32) * fg_a
            
    Image.fromarray(result.astype(np.uint8)).save(output_path)
    print(f"已保存: {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Composite a rug into a scene with optional texture rendering")
    parser.add_argument("scene", help="Scene configuration name")
    parser.add_argument("--design", required=False, help="Path to rug design image (optional)")
    parser.add_argument("--output", default="output.png", help="Output file path")
    parser.add_argument("--shadow-intensity", type=float, default=1.0, help="Shadow intensity (0-2)")
    parser.add_argument("--thickness", type=int, default=7, help="Rug edge thickness in pixels")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument("--skip-render", action="store_true", help="Skip rug texture/seam rendering")
    parser.add_argument("--texture-strength", type=float, default=0.7, help="Texture effect strength (0-1)")
    args = parser.parse_args()
    composite_scene(args.scene, args.design, args.output, args.shadow_intensity, args.thickness,
                    args.debug, args.skip_render, args.texture_strength)
