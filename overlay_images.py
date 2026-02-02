"""叠加两个 PNG 图片
检查比例一致性，自动调整尺寸，然后叠加图片
"""

import argparse
from pathlib import Path
from PIL import Image


def check_aspect_ratio(img1: Image.Image, img2: Image.Image, tolerance: float = 0.01) -> bool:
    """检查两个图片的宽高比是否一致

    Args:
        img1: 第一张图片
        img2: 第二张图片
        tolerance: 容差范围（默认 1%）

    Returns:
        True 如果宽高比一致
    """
    ratio1 = img1.width / img1.height
    ratio2 = img2.width / img2.height

    # 计算比例差异
    diff = abs(ratio1 - ratio2) / ratio1

    return diff <= tolerance


def resize_to_match(img1: Image.Image, img2: Image.Image) -> tuple[Image.Image, Image.Image]:
    """将较大的图片缩小到与较小图片相同的尺寸

    Args:
        img1: 第一张图片
        img2: 第二张图片

    Returns:
        调整后的两张图片 (img1, img2)
    """
    size1 = img1.width * img1.height
    size2 = img2.width * img2.height

    if size1 == size2:
        # 尺寸已经相同
        return img1, img2
    elif size1 > size2:
        # img1 更大，缩小到 img2 的尺寸
        print(f"缩小图片1: {img1.size} -> {img2.size}")
        img1 = img1.resize(img2.size, Image.Resampling.LANCZOS)
        return img1, img2
    else:
        # img2 更大，缩小到 img1 的尺寸
        print(f"缩小图片2: {img2.size} -> {img1.size}")
        img2 = img2.resize(img1.size, Image.Resampling.LANCZOS)
        return img1, img2


def overlay_images(
    image1_path: str | Path,
    image2_path: str | Path,
    output_path: str | Path | None = None,
    tolerance: float = 0.01
) -> Image.Image:
    """叠加两个 PNG 图片

    Args:
        image1_path: 第一张图片路径（底层）
        image2_path: 第二张图片路径（顶层）
        output_path: 输出路径，如不指定则自动生成
        tolerance: 宽高比容差（默认 1%）

    Returns:
        叠加后的图片

    Raises:
        ValueError: 如果宽高比不一致
        FileNotFoundError: 如果图片文件不存在
    """
    # 加载图片
    image1_path = Path(image1_path)
    image2_path = Path(image2_path)

    if not image1_path.exists():
        raise FileNotFoundError(f"图片不存在: {image1_path}")
    if not image2_path.exists():
        raise FileNotFoundError(f"图片不存在: {image2_path}")

    print(f"加载图片1: {image1_path}")
    img1 = Image.open(image1_path).convert("RGBA")

    print(f"加载图片2: {image2_path}")
    img2 = Image.open(image2_path).convert("RGBA")

    print(f"图片1尺寸: {img1.size}, 宽高比: {img1.width / img1.height:.4f}")
    print(f"图片2尺寸: {img2.size}, 宽高比: {img2.width / img2.height:.4f}")

    # 检查宽高比
    if not check_aspect_ratio(img1, img2, tolerance):
        ratio1 = img1.width / img1.height
        ratio2 = img2.width / img2.height
        raise ValueError(
            f"图片宽高比不一致！\n"
            f"图片1: {ratio1:.4f} ({img1.size})\n"
            f"图片2: {ratio2:.4f} ({img2.size})\n"
            f"差异: {abs(ratio1 - ratio2) / ratio1 * 100:.2f}%"
        )

    # 调整尺寸
    img1, img2 = resize_to_match(img1, img2)

    # 叠加图片（img2 叠加在 img1 上）
    print(f"叠加图片...")
    result = Image.alpha_composite(img1, img2)

    # 保存结果
    if not output_path:
        # 自动生成输出文件名
        output_path = image1_path.parent / f"{image1_path.stem}_overlay.png"

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.save(output_path, "PNG")
    print(f"已保存: {output_path}")

    return result


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(description="叠加两个 PNG 图片")
    parser.add_argument("image1", help="第一张图片路径（底层）")
    parser.add_argument("image2", help="第二张图片路径（顶层）")
    parser.add_argument("-o", "--output", help="输出图片路径")
    parser.add_argument(
        "-t", "--tolerance",
        type=float,
        default=0.01,
        help="宽高比容差（默认 0.01 即 1%%）"
    )

    args = parser.parse_args()

    try:
        overlay_images(
            image1_path=args.image1,
            image2_path=args.image2,
            output_path=args.output,
            tolerance=args.tolerance
        )
    except Exception as e:
        print(f"错误: {e}")
        exit(1)


if __name__ == "__main__":
    main()
