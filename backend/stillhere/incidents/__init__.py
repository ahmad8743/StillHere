"""C03: bounded public incident context, separate from eligibility and planning."""

from .facade import IncidentFacade, build_query, query_identity

__all__ = ["IncidentFacade", "build_query", "query_identity"]
