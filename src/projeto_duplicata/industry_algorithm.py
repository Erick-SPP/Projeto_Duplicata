import os
import time
import hashlib
from collections import defaultdict
from pathlib import Path

CHUNK_SIZE = 64 * 1024  # define o tamanho do chunk para leitura de arquivos grandes

def get_partial_hash(filepath: Path, bytes_to_read: int = 64 * 1024) -> str:
    """computa o hash SHA-256 parcial de um arquivo, lendo apenas os primeiros bytes especificados. Para fins de desempenho."""
    hasher = hashlib.sha256()
    try:
        with open(filepath, 'rb') as f:
            chunk = f.read(bytes_to_read)
            hasher.update(chunk)
        return hasher.hexdigest()
    except (PermissionError, OSError):
        return ""

def get_full_hash(filepath: Path) -> str:
    """computa o hash SHA-256 completo de um arquivo, lendo-o em chunks para lidar com arquivos de tamanho arbitrário."""
    hasher = hashlib.sha256()
    try:
        with open(filepath, 'rb') as f:
            while chunk := f.read(CHUNK_SIZE):
                hasher.update(chunk)
        return hasher.hexdigest()
    except (PermissionError, OSError):
        return ""

def are_files_identical(file1: Path, file2: Path) -> bool:
    """verificação direta byte a byte para garantir risco zero de colisão de hash."""
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

def find_duplicate_files(root_directory: str) -> dict[str, list[Path]]:
    """
    Scanner de deduplicação de arquivos padrão da indústria.        
    """
    root = Path(root_directory)
    
    # PASS 1: Agrupar arquivos por tamanho exato de bytes para eliminar rapidamente candidatos óbvios
    size_map = defaultdict(list)
    for path in root.rglob('*'):
        if path.is_file() and not path.is_symlink():
            try:
                size_map[path.stat().st_size].append(path)
            except (PermissionError, OSError):
                continue

    # filtrar arquivos que têm mais de um candidato de tamanho e tamanho maior que 0
    size_candidates = [files for size, files in size_map.items() if len(files) > 1 and size > 0]

    # PASS 2: Agrupar por hash parcial (primeiros 64KB)
    partial_hash_map = defaultdict(list)
    for file_list in size_candidates:
        for filepath in file_list:
            p_hash = get_partial_hash(filepath)
            if p_hash:
                partial_hash_map[(filepath.stat().st_size, p_hash)].append(filepath)

    partial_candidates = [files for files in partial_hash_map.values() if len(files) > 1]

    # PASS 3: Agrupar por hash criptográfico completo (SHA-256)
    full_hash_map = defaultdict(list)
    for file_list in partial_candidates:
        for filepath in file_list:
            f_hash = get_full_hash(filepath)
            if f_hash:
                full_hash_map[f_hash].append(filepath)

    # PASS 4: Verificação opcional byte a byte para eliminar falsos positivos de hash (extremamente raro, mas possível)
    verified_duplicates = {}
    for f_hash, file_list in full_hash_map.items():
        if len(file_list) <= 1:
            continue
        
        # Agrupar arquivos idênticos byte a byte para garantir que não haja falsos positivos
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

        for group_idx, group in enumerate(confirmed_groups):
            if len(group) > 1:
                verified_duplicates[f"{f_hash}_{group_idx}"] = group

    return verified_duplicates


if __name__ == "__main__":
    target_dir = "D:\Downloads"
    duplicates = find_duplicate_files(target_dir)

    
    for hash_key, paths in duplicates.items():
        print(f"\n[Duplicate Group {hash_key[:8]}]")
        print(f"Original : {paths[0]}")
        for dup in paths[1:]:
            print(f"Duplicate: {dup}")

    