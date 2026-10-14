"""SALVA scientific core (pure Python: no web framework, no database, no network)."""

from .risk import RiskAssessment, classify_risk

__version__ = "0.2.0"

__all__ = ["RiskAssessment", "classify_risk"]
