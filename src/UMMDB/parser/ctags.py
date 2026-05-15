import os
import subprocess
from typing import List, Optional

class CtagsParser:
    def can_parse(self, file_path: str, language: Optional[str]) -> bool:
        # Check if ctags is available
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
                    
            if not chunks:
                # If ctags yielded no symbols, we might just read a bit
                with open(file_path, 'r', encoding='utf-8') as f:
                    chunks.append(ParsedChunk(f.read()[:500], "L-2", {"parser": "ctags-fallback"}))
            return chunks
        except Exception:
            raise
