import os
import subprocess
from pathlib import Path
from typing import List, Optional

SUPPORTED_LANGUAGES = {
    "python",
    "javascript",
    "typescript",
    "go",
    "rust",
    "c",
    "cpp",
    "java",
    "csharp",
}

EXTENSION_LANGUAGES = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".java": "java",
    ".cs": "csharp",
}

class CtagsParser:
    def can_parse(self, file_path: str, language: Optional[str]) -> bool:
        language_name = (language or EXTENSION_LANGUAGES.get(Path(file_path).suffix.lower()) or "").lower()
        if language_name not in SUPPORTED_LANGUAGES:
            return False
        try:
            subprocess.run(['ctags', '--version'], capture_output=True, check=False)
            return True
        except FileNotFoundError:
            return False
            
    def parse(self, file_path: str, language: Optional[str]) -> List[any]:
        from .cascade import ParsedChunk
        
        try:
            # We would typically run `ctags -x file_path` to get cross references
            result = subprocess.run(['ctags', '-x', file_path], capture_output=True, text=True, check=True)
            output = result.stdout
            
            chunks = []
            for line in output.splitlines():
                if line.strip():
                    chunks.append(ParsedChunk(line.strip(), "L-2", {"parser": "ctags"}))
                    
            return chunks
        except Exception:
            raise
