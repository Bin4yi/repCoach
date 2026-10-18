from .base import AnalysisContext, ExerciseAnalyzer, ExerciseResult
from .bicep_curl import BicepCurlAnalyzer
from .pushup import PushupAnalyzer
from .squat import SquatAnalyzer

ANALYZERS: dict[str, type[ExerciseAnalyzer]] = {
    "squat": SquatAnalyzer,
    "pushup": PushupAnalyzer,
    "bicep_curl": BicepCurlAnalyzer,
}


def get_analyzer(exercise: str) -> ExerciseAnalyzer:
    try:
        return ANALYZERS[exercise]()
    except KeyError:
        raise ValueError(f"Unsupported exercise: {exercise}") from None


__all__ = ["ANALYZERS", "AnalysisContext", "ExerciseAnalyzer", "ExerciseResult", "get_analyzer",
           "SquatAnalyzer", "PushupAnalyzer", "BicepCurlAnalyzer"]
