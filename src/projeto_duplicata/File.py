from pathlib import Path
from dataclasses import dataclass

@dataclass
class File:
    file_path: Path
    file_size: int
    hash_value: str = None

    @property
    def name(self) -> str:
        return self.file_path.name