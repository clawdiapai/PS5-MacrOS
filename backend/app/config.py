"""Application settings. Canonical analysis frame is 1280×720 unless overridden."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WEB2PS5_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Web2PS5"
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = True

    # Canonical working resolution for vision + authoring coordinate space
    frame_width: int = 1280
    frame_height: int = 720

    # Fake / real bridge feedback cadence
    feedback_hz: float = 60.0
    min_press_ms: float = 80.0

    # Fake video ingest (Phase 1.2)
    fake_fps: float = 30.0

    # MJPEG preview — quality is for fallback encode only; ingest uses side-thread JPEG
    preview_fps: float = 30.0
    preview_jpeg_quality: int = 55

    # Hardware bridge (Phase 2)
    # fake = synthetic frames (default)
    # pyremoteplay = real PS4/PS5 Remote Play
    bridge: str = "fake"
    auto_connect: bool = True
    ps5_host: str = ""
    ps5_user: str = ""  # control / macros account (empty → first profile)
    ps5_spectator_user: str = ""  # optional second PSN account (view-only role)
    ps5_resolution: str = "720p"
    ps5_fps: str = "high"  # low=30, high=60
    ps5_quality: str = "default"
    ps5_codec: str = "h264"
    # First-run wizard: false until save/skip
    setup_skipped: bool = False
    setup_complete: bool = False

    # Video ingest: fake | remoteplay | ustreamer
    # ustreamer = HDMI capture box / Pi (e.g. http://192.168.1.64:8080/stream)
    video_source: str = "fake"
    video_url: str = ""  # required when video_source=ustreamer

    # Paths
    data_dir: Path = DATA_DIR
    graphs_dir: Path = DATA_DIR / "graphs"
    anchors_dir: Path = DATA_DIR / "anchors"
    ocr_dir: Path = DATA_DIR / "ocr"
    screenshots_dir: Path = DATA_DIR / "screenshots"
    logs_dir: Path = DATA_DIR / "logs"

    frontend_dir: Path = ROOT_DIR / "frontend"

    def ensure_dirs(self) -> None:
        for path in (
            self.data_dir,
            self.graphs_dir,
            self.anchors_dir,
            self.ocr_dir,
            self.screenshots_dir,
            self.logs_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


settings = Settings()
