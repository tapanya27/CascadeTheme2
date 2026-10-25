"""Transparent, configurable vulnerability scoring."""

from app.scoring.config import (
    SCORING_VERSION,
    ScoringConfig,
    default_scoring_config,
    load_scoring_config,
)
from app.scoring.engine import (
    ScoreResult,
    categorize,
    combine_components,
    normalize_linear,
    score_zone_features,
)

__all__ = [
    "SCORING_VERSION",
    "ScoringConfig",
    "ScoreResult",
    "categorize",
    "combine_components",
    "default_scoring_config",
    "load_scoring_config",
    "normalize_linear",
    "score_zone_features",
]
