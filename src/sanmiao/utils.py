# Utility functions for sanmiao

# Character variant detection sets
simplified_only = set("宝応暦寿観斉亀")
traditional_only = set("寶應曆壽觀齊龜")


def guess_variant(text):
    """
    Guess whether text uses traditional or simplified Chinese characters.

    :param text: str, text to analyze
    :return: str, '1' for traditional, '3' for simplified, '0' for mixed/unknown
    """
    s_count = sum(ch in simplified_only for ch in text)
    t_count = sum(ch in traditional_only for ch in text)
    if t_count > s_count:
        return "1"
    elif s_count > t_count:
        return "3"
    else:
        return "0"