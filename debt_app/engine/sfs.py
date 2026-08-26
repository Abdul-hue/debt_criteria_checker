def derive_household_key(adults: int, children: int) -> str:
    adults = min(max(int(adults), 1), 2)
    children = min(int(children), 5)
    if children == 0:
        return 'adult_1' if adults == 1 else 'adult_2'
    adult_part = 'adult_1' if adults == 1 else 'adult_2'
    return f"{adult_part}_child_{children}"


def get_guideline_rate(guideline, hh_key: str) -> float:
    return float(getattr(guideline, hh_key, None) or 0.0)


def apply_guideline_constraint(
    rate: float,
    min_flag: bool,
    max_flag: bool,
    declared: float,
) -> dict:
    upper = rate if max_flag else 0.0
    lower = rate if min_flag else 0.0
    if upper > 0 and declared >= upper:
        status = 'Red'
    elif upper > 0 and declared >= upper * 0.85:
        status = 'Amber'
    else:
        status = 'Green'
    return {
        'guideline_rate': rate,
        'upper_bound': upper,
        'lower_bound': lower,
        'status': status,
    }
