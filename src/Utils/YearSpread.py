def ParseYearSpread(spec: str) -> list[int]:
    """'2023' -> [2023]; '2020-2025' -> [2020, 2021, 2022, 2023, 2024, 2025]."""
    if "-" in spec:
        start_str, end_str = spec.split("-", 1)
        start, end = int(start_str), int(end_str)
        if end < start:
            raise ValueError(f"Year range end {end} is before start {start}.")
        return list(range(start, end + 1))
    return [int(spec)]


if __name__ == "__main__":
    assert ParseYearSpread("2023")      == [2023]
    assert ParseYearSpread("2020-2022") == [2020, 2021, 2022]
    try:
        ParseYearSpread("2025-2020")
        raise AssertionError("expected ValueError for a backwards range")
    except ValueError:
        pass

    print("YearSpread self-checks passed.")
