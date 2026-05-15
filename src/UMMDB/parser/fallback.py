import re
from typing import List, Optional

class RegexParser:
    def can_parse(self, file_path: str, language: Optional[str]) -> bool:
        return True # Regex can try anything
        
    def parse(self, file_path: str, language: Optional[str]) -> List[any]:
        from .cascade import ParsedChunk
        chunks = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Naive tokenization by words
            tokens = re.findall(r'\b\w+\b', content)
            if tokens:
                # Group tokens into chunks of 50
                for i in range(0, len(tokens), 50):
                    chunk_text = " ".join(tokens[i:i+50])
                    chunks.append(ParsedChunk(chunk_text, "L-3", {"parser": "regex"}))
            return chunks
        except Exception as e:
            raise e

class SlidingWindowParser:
    def __init__(self, window_size: int = 200, overlap: int = 50):
        self.window_size = window_size
        self.overlap = overlap

        #fallback
    def can_parse(self, file_path: str, language: Optional[str]) -> bool:
        return True
        
    def parse(self, file_path: str, language: Optional[str]) -> List[any]:
        from .cascade import ParsedChunk
        chunks = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            if not content:
                return []
                
            i = 0
            while i < len(content):
                chunk_text = content[i:i + self.window_size]
                chunks.append(ParsedChunk(chunk_text, "L-4", {"parser": "sliding-window"}))
                i += (self.window_size - self.overlap)
                #check for infinite loop
                if i >= len(content) and len(chunk_text) < self.window_size:
                    break
            return chunks
        except Exception:
            raise
