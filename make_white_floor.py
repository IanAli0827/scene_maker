#!/usr/bin/env python3
"""
Make White Floor - Replace floor with pure white while keeping everything else
Uses Google's Gemini 3 Pro Image model to edit reference images.
"""
import os
import argparse
import time
from pathlib import Path
from google import genai
from google.genai import types
from dotenv import load_dotenv


def get_client():
    """Initialize and return Google GenAI client."""
    # Load .env from parent directory
    env_path = Path(__file__).parent.parent / '.env'
    load_dotenv(dotenv_path=env_path)
    api_key = os.getenv("GOOGLE_API_KEY")

    if not api_key:
        raise ValueError("GOOGLE_API_KEY not found in .env file")

    return genai.Client(api_key=api_key)


def make_white_floor(ref_image_bytes, model_id="gemini-3-pro-image-preview",
                     aspect_ratio="1:1", image_size="1K", max_retries=3):
    """
    Replace floor with pure white while keeping everything else unchanged.

    Args:
        ref_image_bytes: Reference image bytes
        model_id: Model identifier (default: gemini-3-pro-image-preview)
        aspect_ratio: Image aspect ratio (default: 1:1)
        image_size: Image size (default: 1K)
        max_retries: Maximum number of retry attempts (default: 3)

    Returns:
        dict with 'success', 'image_bytes', and 'error' keys
    """
    client = get_client()

    prompt = (
        "Replace the floor with a matte pure white color (no texture, no pattern, no reflections). "
        "Keep everything else exactly the same, especially preserve all shadows."
    )

    contents = [
        types.Part.from_bytes(data=ref_image_bytes, mime_type="image/png"),
        prompt
    ]

    # Retry logic with exponential backoff
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model_id,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                    image_config=types.ImageConfig(
                        aspect_ratio=aspect_ratio,
                        image_size=image_size
                    ),
                    safety_settings=[
                        types.SafetySetting(
                            category="HARM_CATEGORY_DANGEROUS_CONTENT",
                            threshold="BLOCK_ONLY_HIGH"
                        ),
                    ],
                )
            )

            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if part.inline_data and part.inline_data.data:
                        return {
                            "success": True,
                            "image_bytes": part.inline_data.data,
                        }

            return {"success": False, "error": "No image data in response"}

        except Exception as e:
            error_msg = str(e)
            is_timeout = "timed out" in error_msg.lower() or "timeout" in error_msg.lower()

            if is_timeout and attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                print(f"  → Timeout, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
                continue
            else:
                return {"success": False, "error": error_msg}

    return {"success": False, "error": "Max retries exceeded"}


def process_directory(input_dir, aspect_ratio='1:1', image_size='1K'):
    """
    Process all images in a directory.

    Args:
        input_dir: Directory containing images to process
        aspect_ratio: Image aspect ratio
        image_size: Image size

    Returns:
        Number of errors encountered
    """
    input_path = Path(input_dir)
    if not input_path.is_dir():
        print(f"Error: {input_dir} is not a directory")
        return 1

    # Find all image files, skip files with _fg or _wf suffix
    image_extensions = {'.png', '.jpg', '.jpeg'}
    image_files = [
        f for f in input_path.iterdir()
        if f.is_file() and f.suffix.lower() in image_extensions
        and not (f.stem.endswith('_fg') or f.stem.endswith('_wf'))
    ]

    if not image_files:
        print(f"No image files found in {input_dir}")
        return 0

    print(f"Found {len(image_files)} image(s) to process")

    errors = 0
    processed = 0
    skipped = 0

    for i, image_file in enumerate(image_files, 1):
        # Generate output path
        output_path = image_file.parent / f"{image_file.stem}_wf{image_file.suffix}"

        # Skip if output already exists
        if output_path.exists():
            print(f"[{i}/{len(image_files)}] Skipping {image_file.name} (output already exists)")
            skipped += 1
            continue

        print(f"[{i}/{len(image_files)}] Processing {image_file.name}...")

        try:
            # Load and process image
            ref_image_bytes = image_file.read_bytes()
            result = make_white_floor(
                ref_image_bytes=ref_image_bytes,
                aspect_ratio=aspect_ratio,
                image_size=image_size
            )

            if result["success"]:
                output_path.write_bytes(result["image_bytes"])
                print(f"  → Saved to: {output_path.name}")
                processed += 1
            else:
                print(f"  → Error: {result['error']}")
                errors += 1

        except Exception as e:
            print(f"  → Error: {str(e)}")
            errors += 1

    print(f"\nSummary: {processed} processed, {skipped} skipped, {errors} errors")
    return errors


def main():
    parser = argparse.ArgumentParser(
        description="Replace floor with pure white while keeping everything else"
    )
    parser.add_argument('input', help='Input reference image path or directory')
    parser.add_argument('--output', help='Output file path (default: input_wf.png, ignored for directories)')
    parser.add_argument('--aspect-ratio', default='1:1',
                       choices=['1:1', '3:4', '4:3', '9:16', '16:9', '4:5', '5:4'],
                       help='Image aspect ratio (default: 1:1)')
    parser.add_argument('--size', default='1K', choices=['1K', '2K', '4K'],
                       help='Image size (default: 1K)')

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input not found: {args.input}")
        return 1

    # Handle directory input
    if input_path.is_dir():
        return process_directory(
            input_dir=input_path,
            aspect_ratio=args.aspect_ratio,
            image_size=args.size
        )

    # Handle single file input
    ref_image_bytes = input_path.read_bytes()

    # Generate output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.parent / f"{input_path.stem}_wf{input_path.suffix}"

    # Skip if output already exists
    if output_path.exists():
        print(f"Output already exists: {output_path}")
        print("Skipping processing")
        return 0

    # Process image
    result = make_white_floor(
        ref_image_bytes=ref_image_bytes,
        aspect_ratio=args.aspect_ratio,
        image_size=args.size
    )

    # Save result
    if result["success"]:
        output_path.write_bytes(result["image_bytes"])
        print(f"Saved to: {output_path}")
        return 0
    else:
        print(f"Error: {result['error']}")
        return 1


if __name__ == "__main__":
    exit(main())
