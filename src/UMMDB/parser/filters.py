import os

class FileHeuristics:
    def __init__(self, max_line_length=500, max_binary_ratio=0.001, exclude_patterns=None):
        self.max_line_length = max_line_length
        self.max_binary_ratio = max_binary_ratio
        self.exclude_patterns = exclude_patterns or []

    def is_human_readable(self, file_path: str) -> bool:
        if not os.path.exists(file_path):
            return False
        for pattern in self.exclude_patterns:
            if pattern in file_path:
                return False
        if os.path.getsize(file_path) == 0:
            return True

        try:
            with open(file_path, 'rb') as f:
                content = f.read(8192)
                if not content:
                    return True
                
                null_bytes = content.count(b'\x00')
                binary_ratio = null_bytes / len(content)
                if binary_ratio > self.max_binary_ratio:
                    return False
            
            with open(file_path, 'r', encoding='utf-8') as f:
                total_length = 0
                lines = 0
                for line in f:
                    total_length += len(line)
                    lines += 1
                
                if lines > 0:
                    avg_length = total_length / lines
                    if avg_length > self.max_line_length:
                        return False
            
            return True
        except UnicodeDecodeError:
            return False
        except Exception:
            return False
