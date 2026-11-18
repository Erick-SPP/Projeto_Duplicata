import time
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from collections import defaultdict
import hashlib


CHUNK_SIZE = 64 * 1024
# --- CORE UTILITIES (Mechanics only) ---

def get_partial_hash(filepath: Path, bytes_to_read: int = 64 * 1024) -> str:
    hasher = hashlib.sha256()
    try:
        with open(filepath, 'rb') as f:
            hasher.update(f.read(bytes_to_read))
        return hasher.hexdigest()
    except (PermissionError, OSError):
        return ""

def get_full_hash(filepath: Path) -> str:
    hasher = hashlib.sha256()
    try:
        with open(filepath, 'rb') as f:
            while chunk := f.read(CHUNK_SIZE):
                hasher.update(chunk)
            return hasher.hexdigest()
    except (PermissionError, OSError):
        return ""

def are_files_identical(file1: Path, file2: Path) -> bool:
    try:
        with open(file1, 'rb') as f1, open(file2, 'rb') as f2:
            while True:
                b1 = f1.read(CHUNK_SIZE)
                b2 = f2.read(CHUNK_SIZE)
                if b1 != b2:
                    return False
                if not b1:
                    return True
    except (PermissionError, OSError):
        return False


def base_processor(
    filepath: Path, 
    strategy_name: str = "global_standard", 
    hash_fn: Callable[[Path], str] = get_partial_hash,
    verify_bytes: bool = True,
    max_size: Optional[int] = None,
    fallback_hash_fn: Optional[Callable[[Path], str]] = None
) -> Optional[Dict[str, Any]]:
    """
    Core execution unit with centralized I/O exception handling.
    Decorators stay completely free of try/except boilerplate.
    """
    try:
        file_size = filepath.stat().st_size
        
        # Handle size-based fallback if the decorator specified a ceiling
        if max_size is not None and file_size > max_size:
            active_hash_fn = fallback_hash_fn or get_partial_hash
            verify_bytes = True
            strategy_name = f"{strategy_name}_fallback"
        else:
            active_hash_fn = hash_fn

        file_hash = active_hash_fn(filepath)
        if not file_hash:
            return None

        return {
            "strategy": strategy_name,
            "hash": file_hash,
            "path": filepath,
            "verify_bytes": verify_bytes
        }
    except (PermissionError, OSError):
        return None
    
def find_duplicates(
    root_directory: str | Path,
    processor: Callable[[Path], Optional[Dict[str, Any]]] = base_processor,
    target_file: Optional[Path] = None,
    is_cancelled: Optional[Callable[[], bool]] = None
) -> dict[str, Any]:
    """
    3-pass scanner that delegates hashing and verification policies
    to the active decorated processor chosen in the UI.
    """
    t_start = time.perf_counter()
    root = Path(root_directory)
    

    # PASS 1: Lightweight collection & size grouping
    size_map = defaultdict(list)
    file_count = 0
    
    for path in root.rglob('*'):
        if is_cancelled and is_cancelled():
            break
        if path.is_file() and not path.is_symlink():
            file_count += 1
            try:
                size_map[path.stat().st_size].append(path)
            except (PermissionError, OSError):
                continue

    # If searching for duplicates of a specific file outside root_directory, seed it
    if target_file and target_file.is_file():
        try:
            resolved_target = target_file.resolve()
            target_size = resolved_target.stat().st_size
            if all(p.resolve() != resolved_target for p in size_map[target_size]):
                size_map[target_size].append(target_file)
        except (PermissionError, OSError):
            pass

    size_candidates = [files for size, files in size_map.items() if len(files) > 1 and size > 0]
    t_pass1 = time.perf_counter()

    # PASS 2: Dynamic Decorated Dispatching Loop
    processed_candidates = defaultdict(list)
    verify_lookup: Dict[tuple[str, str], bool] = {}

    for file_list in size_candidates:
        if is_cancelled and is_cancelled():
            break
        for filepath in file_list:
            result = processor(filepath)
            if result and result.get("hash"):
                key = (result["strategy"], result["hash"])
                processed_candidates[key].append(result["path"])
                verify_lookup[key] = result.get("verify_bytes", True)
    
    t_pass2 = time.perf_counter()

    # PASS 3: Conditional Verification & Grouping
    verified_duplicates: list[list[Path]] = []

    for key, file_list in processed_candidates.items():
        if is_cancelled and is_cancelled():
            break
        if len(file_list) <= 1:
            continue

        # Fast path: Full hash already proved equality (e.g., text files < 1 MB)
        if not verify_lookup[key]:
            verified_duplicates.append(file_list)
            continue

        # Safe path: Partial hash matched; confirm with byte-by-byte comparison
        confirmed_groups = []
        for filepath in file_list:
            matched = False
            for group in confirmed_groups:
                if are_files_identical(filepath, group[0]):
                    group.append(filepath)
                    matched = True
                    break
            if not matched:
                confirmed_groups.append([filepath])

        for group in confirmed_groups:
            if len(group) > 1:
                verified_duplicates.append(group)
        
    t_pass3 = time.perf_counter()
    
    return {"duplicates": verified_duplicates,
            "timings": {
            "pass1_ms": (t_pass1 - t_start) * 1000,
            "pass2_ms": (t_pass2 - t_pass1) * 1000,
            "pass3_ms": (t_pass3 - t_pass2) * 1000,
            "total_s": t_pass3 - t_start,
            "files_scanned": file_count,
            }
           }
