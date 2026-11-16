import functools
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from .engine import get_partial_hash, get_full_hash

PolicyResult = Optional[Dict[str, Any]]

def text_file_policy(func: Callable) -> Callable[[Path], PolicyResult]:
    TEXT_EXTENSIONS = {'.txt', '.md', '.log', '.json', '.csv', '.xml', '.yaml', '.yml', '.py'}

    @functools.wraps(func)
    def wrapper(filepath: Path) -> PolicyResult:
        if filepath.suffix.lower() not in TEXT_EXTENSIONS:
            return None

        return func(
            filepath,
            strategy_name="lightweight_text",
            hash_fn=get_full_hash,
            verify_bytes=False,
            max_size=1 * 1024 * 1024,  # 1 MB ceiling
            fallback_hash_fn=get_partial_hash
        )
    return wrapper


def image_file_policy(func: Callable) -> Callable[[Path], PolicyResult]:
    IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.raw', '.svg'}

    @functools.wraps(func)
    def wrapper(filepath: Path) -> PolicyResult:
        if filepath.suffix.lower() not in IMAGE_EXTENSIONS:
            return None

        # Explicitly inject partial hashing for image headers
        return func(filepath, strategy_name="image_partial_first", hash_fn=get_partial_hash)

    return wrapper


def video_file_policy(func: Callable) -> Callable[[Path], PolicyResult]:
    VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v'}

    @functools.wraps(func)
    def wrapper(filepath: Path) -> PolicyResult:
        if filepath.suffix.lower() not in VIDEO_EXTENSIONS:
            return None

        # Explicitly inject partial hashing for large video streams
        return func(filepath, strategy_name="video_stream_partial", hash_fn=get_partial_hash)

    return wrapper


def targeted_file_policy(target_path: Path) -> Callable:
    try:
        target_size = target_path.stat().st_size
        target_partial_hash = get_partial_hash(target_path)
    except (PermissionError, OSError):
        target_size = -1
        target_partial_hash = ""

    def decorator(func: Callable) -> Callable[[Path], PolicyResult]:
        @functools.wraps(func)
        def wrapper(filepath: Path) -> PolicyResult:
            if target_size <= 0 or not target_partial_hash:
                return None

            try:
                if filepath.stat().st_size != target_size:
                    return None
            except (PermissionError, OSError):
                return None

            # Delegate the hashing execution to the wrapped core function
            result = func(filepath, strategy_name="targeted_lookup", hash_fn=get_partial_hash)
            
            if result and result["hash"] == target_partial_hash:
                return result
            return None

        return wrapper
    return decorator