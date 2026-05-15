import math

class FileHeuristics:
    MAX_AVG_LINE_LENGTH = 150
    MAX_ENTROPY = 5.0 # Typical text is lower, random binary is higher

    @classmethod
    def calculate_entropy(cls, text: str) -> float:
        if not text:
            return 0.0
        probabilities = [text.count(c) / len(text) for c in set(text)]
        return -sum(p * math.log2(p) for p in probabilities)

    @classmethod
    def is_human_readable(cls, content: str) -> bool:
        if not content:
            return True
            
        lines = content.splitlines()
            
        avg_line_length = sum(len(line) for line in lines) / len(lines)
        if avg_line_length > cls.MAX_AVG_LINE_LENGTH:
            return False
            
        entropy = cls.calculate_entropy(content)
        if entropy > cls.MAX_ENTROPY:
            return False
            
        return True
