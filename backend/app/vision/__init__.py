"""Frame ingest and OpenCV helpers (thread-offloaded)."""

from backend.app.vision.fake_source import FakeFrameSource
from backend.app.vision.frame_holder import AtomicFrameHolder, FrameSnapshot
from backend.app.vision.template_match import MatchResult, match_template

__all__ = [
    "AtomicFrameHolder",
    "FakeFrameSource",
    "FrameSnapshot",
    "MatchResult",
    "match_template",
]
