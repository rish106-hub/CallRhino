import os
import wave
from pathlib import Path


def wav_duration_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as audio:
        return audio.getnframes() / audio.getframerate()


def ensure_ffmpeg_on_path(cache_dir: Path = Path("evals/cache/bin")) -> None:
    if _has_executable("ffmpeg"):
        return
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError(
            "FFmpeg is missing. Install the evaluation dependency group."
        ) from exc

    source = Path(imageio_ffmpeg.get_ffmpeg_exe())
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / "ffmpeg"
    if not target.exists():
        target.symlink_to(source)
    os.environ["PATH"] = f"{cache_dir.resolve()}:{os.environ.get('PATH', '')}"


def _has_executable(name: str) -> bool:
    return any(
        (Path(directory) / name).is_file()
        for directory in os.environ.get("PATH", "").split(os.pathsep)
        if directory
    )
