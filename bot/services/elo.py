from __future__ import annotations


def expected_score(player_rating: int, opponent_rating: int) -> float:
    return 1 / (1 + 10 ** ((opponent_rating - player_rating) / 400))


def calculate_elo_delta(player_rating: int, opponent_rating: int, score: float, k_factor: int) -> int:
    expected = expected_score(player_rating, opponent_rating)
    return round(k_factor * (score - expected))
