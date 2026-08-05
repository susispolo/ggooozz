"""
Audio feature extraction using librosa.
Downloads 30s preview MP3 from Deezer and extracts audio features.
"""
import asyncio
import io
import logging
import tempfile
import os
from dataclasses import dataclass, field
from typing import Optional

import aiohttp
import numpy as np

log = logging.getLogger(__name__)


@dataclass
class AudioFeatures:
    """Extracted audio features for similarity comparison."""
    # Basic
    bpm: float = 0.0
    duration: float = 0.0

    # Timbre (MFCCs) - most important for similarity
    mfcc_mean: list[float] = field(default_factory=list)  # 13 coefficients
    mfcc_var: list[float] = field(default_factory=list)

    # Harmonic content
    chroma_mean: list[float] = field(default_factory=list)  # 12 pitch classes

    # Spectral
    spectral_centroid: float = 0.0
    spectral_rolloff: float = 0.0
    spectral_bandwidth: float = 0.0
    spectral_contrast: list[float] = field(default_factory=list)  # 7 bands

    # Energy
    rms_energy: float = 0.0
    rms_var: float = 0.0

    # Rhythm
    onset_rate: float = 0.0
    zero_crossing_rate: float = 0.0

    # Musical properties (inferred)
    key: str = ""  # C, C#, D, etc.
    scale: str = ""  # major or minor
    time_signature: str = "4/4"  # estimated
    genre: str = ""  # inferred from features
    mood: str = ""  # inferred from features

    def to_vector(self) -> np.ndarray:
        """Convert features to a flat numpy array for comparison."""
        vector = [
            self.bpm / 200.0,  # Normalize BPM
            self.spectral_centroid / 5000.0,
            self.spectral_rolloff / 10000.0,
            self.spectral_bandwidth / 3000.0,
            self.rms_energy,
            self.onset_rate / 10.0,
            self.zero_crossing_rate,
        ]
        # Add MFCCs (13 values)
        if self.mfcc_mean:
            vector.extend(self.mfcc_mean)
        else:
            vector.extend([0.0] * 13)
        # Add chroma (12 values)
        if self.chroma_mean:
            vector.extend(self.chroma_mean)
        else:
            vector.extend([0.0] * 12)
        return np.array(vector, dtype=np.float32)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "bpm": self.bpm,
            "duration": self.duration,
            "mfcc_mean": self.mfcc_mean,
            "mfcc_var": self.mfcc_var,
            "chroma_mean": self.chroma_mean,
            "spectral_centroid": self.spectral_centroid,
            "spectral_rolloff": self.spectral_rolloff,
            "spectral_bandwidth": self.spectral_bandwidth,
            "spectral_contrast": self.spectral_contrast,
            "rms_energy": self.rms_energy,
            "rms_var": self.rms_var,
            "onset_rate": self.onset_rate,
            "zero_crossing_rate": self.zero_crossing_rate,
            "key": self.key,
            "scale": self.scale,
            "time_signature": self.time_signature,
            "genre": self.genre,
            "mood": self.mood,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AudioFeatures":
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def _extract_features_sync(audio_bytes: bytes) -> AudioFeatures:
    """Extract audio features from MP3 bytes (synchronous, run in thread)."""
    try:
        import librosa
    except ImportError:
        log.error("librosa not installed! Run: pip install librosa")
        raise

    log.info("[LIBROSA] Starting feature extraction...")

    # Write to temp file (librosa can't read MP3 from BytesIO directly)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        log.info("[LIBROSA] Temp file created: %s (%d bytes)", tmp_path, len(audio_bytes))

        # Load audio from temp file
        log.info("[LIBROSA] Loading audio file...")
        y, sr = librosa.load(tmp_path, sr=22050, duration=30)
        log.info("[LIBROSA] Audio loaded: %.1f seconds, %d Hz sample rate", len(y)/sr, sr)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    features = AudioFeatures()

    # BPM
    log.info("[LIBROSA] Extracting BPM...")
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    features.bpm = float(tempo) if np.isscalar(tempo) else float(tempo[0])
    log.info("[LIBROSA] BPM: %.1f", features.bpm)

    # Duration
    features.duration = librosa.get_duration(y=y, sr=sr)

    # MFCCs (timbre DNA) - 13 coefficients
    log.info("[LIBROSA] Extracting MFCCs (timbre)...")
    mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    features.mfcc_mean = mfccs.mean(axis=1).tolist()
    features.mfcc_var = mfccs.var(axis=1).tolist()
    log.info("[LIBROSA] MFCCs extracted: %d coefficients", len(features.mfcc_mean))

    # Chroma (harmonic content) - 12 pitch classes
    log.info("[LIBROSA] Extracting chroma (harmonics)...")
    chroma = librosa.feature.chroma_stft(y=y, sr=sr)
    features.chroma_mean = chroma.mean(axis=1).tolist()
    log.info("[LIBROSA] Chroma extracted: %d pitch classes", len(features.chroma_mean))

    # Spectral features
    log.info("[LIBROSA] Extracting spectral features...")
    spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
    features.spectral_centroid = float(spectral_centroid.mean())

    spectral_rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)
    features.spectral_rolloff = float(spectral_rolloff.mean())

    spectral_bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr)
    features.spectral_bandwidth = float(spectral_bandwidth.mean())

    # Spectral contrast (7 frequency bands)
    spectral_contrast = librosa.feature.spectral_contrast(y=y, sr=sr)
    features.spectral_contrast = spectral_contrast.mean(axis=1).tolist()
    log.info("[LIBROSA] Spectral: centroid=%.1f, rolloff=%.1f, bandwidth=%.1f",
             features.spectral_centroid, features.spectral_rolloff, features.spectral_bandwidth)

    # Energy (RMS)
    log.info("[LIBROSA] Extracting energy (RMS)...")
    rms = librosa.feature.rms(y=y)
    features.rms_energy = float(rms.mean())
    features.rms_var = float(rms.var())
    log.info("[LIBROSA] Energy: mean=%.4f, var=%.4f", features.rms_energy, features.rms_var)

    # Onset rate (rhythm complexity)
    log.info("[LIBROSA] Extracting onset rate...")
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    features.onset_rate = float(librosa.feature.rms(y=onset_env).mean())
    log.info("[LIBROSA] Onset rate: %.4f", features.onset_rate)

    # Zero crossing rate
    zcr = librosa.feature.zero_crossing_rate(y)
    features.zero_crossing_rate = float(zcr.mean())

    # ═══════════════════════════════════════════════════
    # MUSICAL PROPERTY INFERENCE (from librosa)
    # ═══════════════════════════════════════════════════

    # Infer key from chroma
    log.info("[LIBROSA] Inferring musical key...")
    key_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    if features.chroma_mean:
        key_idx = int(np.argmax(features.chroma_mean))
        features.key = key_names[key_idx % 12]
        log.info("[LIBROSA] Key: %s", features.key)

    # Infer scale (major/minor) from chroma pattern
    log.info("[LIBROSA] Inferring scale (major/minor)...")
    if features.chroma_mean and len(features.chroma_mean) >= 12:
        major_profile = [1, 0, 1, 0, 1, 1, 0, 1, 0, 1, 0, 1]
        minor_profile = [1, 0, 1, 1, 0, 1, 0, 1, 1, 0, 1, 0]

        chroma_arr = np.array(features.chroma_mean)
        major_corr = np.corrcoef(chroma_arr, major_profile)[0, 1]
        minor_corr = np.corrcoef(chroma_arr, minor_profile)[0, 1]

        features.scale = "major" if major_corr > minor_corr else "minor"
        log.info("[LIBROSA] Scale: %s (major=%.2f, minor=%.2f)", features.scale, major_corr, minor_corr)

    # Genre and Mood are fetched from APIs (Deezer, Last.fm, MusicBrainz)
    # Not inferred from librosa - see bot.py for API calls

    return features


async def analyze_audio(preview_url: str) -> Optional[AudioFeatures]:
    """
    Download preview MP3 and extract audio features.
    Returns AudioFeatures or None on failure.
    """
    try:
        # Download preview MP3
        log.info("Downloading preview: %s", preview_url)
        async with aiohttp.ClientSession() as session:
            async with session.get(preview_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    log.warning("Failed to download preview: %s", resp.status)
                    return None
                audio_bytes = await resp.read()
                log.info("Downloaded %d bytes", len(audio_bytes))

        # Run librosa in thread pool (non-blocking)
        log.info("Running librosa analysis...")
        loop = asyncio.get_running_loop()
        try:
            features = await asyncio.wait_for(
                loop.run_in_executor(None, _extract_features_sync, audio_bytes),
                timeout=60
            )
        except asyncio.TimeoutError:
            log.error("Librosa analysis timed out after 60 seconds")
            return None

        log.info("Analyzed audio: BPM=%.1f, RMS=%.3f", features.bpm, features.rms_energy)
        return features

    except Exception as e:
        log.error("Audio analysis failed: %s", e, exc_info=True)
        return None


async def analyze_audio_batch(preview_urls: list[str]) -> list[Optional[AudioFeatures]]:
    """Analyze multiple audio files concurrently."""
    tasks = [analyze_audio(url) for url in preview_urls]
    return await asyncio.gather(*tasks)
