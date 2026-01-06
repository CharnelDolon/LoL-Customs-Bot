def calculate_expected_elo(team_elo_a, team_elo_b):
    """
    Standard chess Elo expected score formula.
    Returns tuple (expected_a, expected_b)
    """
    expected_a = 1 / (1 + 10 ** ((team_elo_b - team_elo_a) / 400))
    expected_b = 1 / (1 + 10 ** ((team_elo_a - team_elo_b) / 400))
    return expected_a, expected_b


def update_elo_weighted(team_elo, expected_score, actual_score, team_weight, opponent_weight, base=30):
    """
    Weighted Elo update prioritizing team weights heavily.

    - Heavy teams beating light teams → smaller gain, huge loss if they lose.
    - Light teams beating heavy teams → huge gain, small loss if they lose.
    """
    diff = team_weight - opponent_weight  # positive = heavier

    # Determine modifier based on result
    if actual_score == 1:  # win
        if diff > 0:
            modifier = 0.5 ** diff      # heavy win → smaller gain
        elif diff < 0:
            modifier = 2 ** abs(diff)   # light win → huge gain
        else:
            modifier = 1
    else:  # loss
        if diff > 0:
            modifier = 2 ** diff         # heavy loss → huge penalty
        elif diff < 0:
            modifier = 0.5 ** abs(diff)  # light loss → small penalty
        else:
            modifier = 1

    delta = round(base * modifier)
    if actual_score == 0:
        delta *= -1

    # Ensure minimum movement
    if delta == 0:
        delta = 1 if actual_score == 1 else -1

    new_elo = team_elo + delta
    return new_elo, delta