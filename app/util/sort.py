import re


def natural_sort_key(s: str):
    """
    Returns a key for natural sorting (e.g., '2' comes before '10').
    """
    return [
        int(text) if text.isdigit() else text.lower()
        for text in re.split("([0-9]+)", s)
    ]


def natural_sort(data_list: list[str]):
    """
    Sorts a list in-place using natural sort order.
    """
    data_list.sort(key=natural_sort_key)
    return data_list
