"""使用 Replicate API 移除图片背景
模型: 851-labs/background-remover
"""

import os
import time
from pathlib import Path
from typing import Literal

import replicate
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量（从脚本所在目录加载）
_script_dir = Path(__file__).parent
load_dotenv(_script_dir / ".env")

# 模型版本
# MODEL_VERSION = "851-labs/background-remover:a029dff38972b5fda4ec5d75d7d1cd25aeff621d2cf4946a41055d7db66b80bc"
# MODEL_VERSION = "bria/remove-background"
MODEL_VERSION = "recraft-ai/recraft-remove-background"


class BackgroundRemover:
    """背景移除客户端"""

    def __init__(self, model_version: str = MODEL_VERSION, api_token: str | None = None):
        """初始化客户端

        Args:
            model_version: 模型版本
            api_token: Replicate API token，默认从环境变量读取
        """
        if api_token:
            self.client = replicate.Client(api_token=api_token)
        else:
            self.client = replicate
        self.model_version = model_version

    def remove_background(
        self,
        image_path: str | Path,
        output_path: str | Path | None = None,
        format: Literal["png", "jpg"] = "png",
        reverse: bool = False,
        threshold: int = 0,
        background_type: Literal["rgba", "color"] = "rgba",
        print_log: bool = True,
    ) -> bytes:
        """移除图片背景

        Args:
            image_path: 输入图片路径（本地文件或 URL）
            output_path: 输出路径，如不指定则不保存
            format: 输出格式，png 或 jpg
            reverse: 是否反向（保留背景，移除前景）
            threshold: 阈值，0-255
            background_type: 背景类型，rgba（透明）或 color（纯色）
            print_log: 是否打印日志

        Returns:
            处理后的图片 bytes
        """
        image_path = str(image_path)

        # 判断是本地文件还是 URL
        is_url = image_path.startswith(("http://", "https://"))

        if print_log:
            print(f"处理图片: {image_path}")

        # 调用 Replicate API
        if is_url:
            output = self.client.run(
                self.model_version,
                input={
                    "image": image_path,
                    "format": format,
                    "reverse": reverse,
                    "threshold": threshold,
                    "background_type": background_type,
                },
            )
        else:
            # 上传本地文件
            img_path = Path(image_path)
            if not img_path.exists():
                # 尝试解析为绝对路径
                abs_path = img_path.resolve()
                raise FileNotFoundError(f"图片不存在: {image_path}\n解析的绝对路径: {abs_path}\n当前工作目录: {os.getcwd()}")

            with open(image_path, "rb") as image_input:
                output = self.client.run(
                    self.model_version,
                    input={
                        "image": image_input,
                        "format": format,
                        "reverse": reverse,
                        "threshold": threshold,
                        "background_type": background_type,
                    },
                )

        # 读取结果
        image_bytes = output.read()

        # 保存文件
        if not output_path:
            output_path = Path(image_path).with_stem(f"{Path(image_path).stem}_fg")
        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(image_bytes)
            if print_log:
                print(f"已保存: {output_path}")

        if print_log:
            print(f"完成，大小: {len(image_bytes)} bytes")
        return image_bytes

    def process_directory(
        self,
        input_dir: str | Path,
        output_dir: str | Path | None = None,
        **kwargs
    ):
        """串行处理目录中的所有图片

        Args:
            input_dir: 输入目录
            output_dir: 输出目录（未使用，输出在同目录）
            **kwargs: 其他参数传递给 remove_background
        """
        input_path = Path(input_dir)
        if not input_path.is_dir():
            raise NotADirectoryError(f"路径不是目录: {input_dir}")

        # 过滤图片文件，跳过 _fg 和 _wf 后缀的文件
        extensions = (".png", ".jpg", ".jpeg", ".webp")
        image_files = [
            f for f in input_path.iterdir()
            if f.is_file() and f.suffix.lower() in extensions
            and not (f.stem.endswith('_fg') or f.stem.endswith('_wf'))
        ]

        print(f"在目录 {input_path} 中找到 {len(image_files)} 张图片")

        target_format = kwargs.get("format", "png")
        results = []
        skipped = 0

        for i, file_path in enumerate(image_files, 1):
            # 在同目录下输出，文件名加后缀
            out_file = file_path.parent / f"{file_path.stem}_fg.{target_format}"

            # 检查目标文件是否已存在
            if out_file.exists():
                print(f"[{i}/{len(image_files)}] [{file_path.name}] 跳过（已存在）")
                skipped += 1
                results.append({"file": file_path.name, "status": "skipped"})
                continue

            print(f"[{i}/{len(image_files)}] [{file_path.name}] 处理中...")

            try:
                self.remove_background(
                    image_path=file_path,
                    output_path=out_file,
                    print_log=False,
                    **kwargs
                )
                print(f"[{i}/{len(image_files)}] [{file_path.name}] OK")
                results.append({"file": file_path.name, "status": "success", "output": out_file.name})

            except Exception as e:
                error_msg = str(e) or e.__class__.__name__
                print(f"[{i}/{len(image_files)}] [{file_path.name}] ERROR: {error_msg}")
                results.append({"file": file_path.name, "status": "error", "error": error_msg})

        # 统计
        success = sum(1 for r in results if r["status"] == "success")
        errors = sum(1 for r in results if r["status"] == "error")
        print(f"\n处理完成！成功: {success}, 跳过: {skipped}, 错误: {errors}")


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="使用 Replicate API 移除图片背景")
    parser.add_argument("input", help="输入图片路径、URL 或目录")
    parser.add_argument("-o", "--output", help="输出图片路径或目录")
    parser.add_argument("-f", "--format", choices=["png", "jpg"], default="png", help="输出格式")
    parser.add_argument("-r", "--reverse", action="store_true", help="反向（保留背景）")
    parser.add_argument("-t", "--threshold", type=int, default=0, help="阈值 (0-255)")
    parser.add_argument(
        "-b",
        "--background-type",
        choices=["rgba", "color"],
        default="rgba",
        help="背景类型",
    )

    args = parser.parse_args()

    remover = BackgroundRemover()
    input_path = Path(args.input)

    if input_path.is_dir():
        # 处理目录
        remover.process_directory(
            input_dir=args.input,
            output_dir=args.output,
            format=args.format,
            reverse=args.reverse,
            threshold=args.threshold,
            background_type=args.background_type,
        )
    else:
        # 处理单个文件或 URL
        remover.remove_background(
            image_path=args.input,
            output_path=args.output,
            format=args.format,
            reverse=args.reverse,
            threshold=args.threshold,
            background_type=args.background_type,
        )


if __name__ == "__main__":
    main()
