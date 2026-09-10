"""한국어 조사 처리.

'판매가을(를)' 같은 어색한 문구 대신 받침에 맞는 조사를 골라 쓴다.
"""

_HANGUL_START = 0xAC00
_HANGUL_END = 0xD7A3

# 받침이 있는 것으로 취급하는 숫자·영문 끝소리 (1, 7, 8, 0, l, m, n, ng ...)
_DIGIT_HAS_BATCHIM = {"0": True, "1": True, "3": True, "6": True, "7": True, "8": True}


def has_batchim(word: str) -> bool:
    """마지막 글자에 받침이 있는지."""
    word = word.strip()
    if not word:
        return False
    last = word[-1]
    code = ord(last)
    if _HANGUL_START <= code <= _HANGUL_END:
        return (code - _HANGUL_START) % 28 != 0
    if last.isdigit():
        return _DIGIT_HAS_BATCHIM.get(last, False)
    return False


def particle(word: str, with_batchim: str, without_batchim: str) -> str:
    """단어에 맞는 조사를 붙여 돌려준다. 예: particle('판매가', '을', '를') -> '판매가를'"""
    return f"{word}{with_batchim if has_batchim(word) else without_batchim}"


def eul_reul(word: str) -> str:
    """을/를"""
    return particle(word, "을", "를")


def i_ga(word: str) -> str:
    """이/가"""
    return particle(word, "이", "가")


def eun_neun(word: str) -> str:
    """은/는"""
    return particle(word, "은", "는")
