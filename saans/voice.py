"""Amazon Polly voice notes (Kajal, neural) stored in S3, or on disk for local runs."""

from __future__ import annotations

import os
from pathlib import Path

from .store import DATA_DIR

VOICE_ID = "Kajal"
LANGUAGE_CODES = {"hi": "hi-IN", "en": "en-IN"}


def synthesize(text: str, lang: str) -> bytes:
    import boto3

    polly = boto3.client("polly", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    resp = polly.synthesize_speech(
        Text=text,
        VoiceId=VOICE_ID,
        Engine="neural",
        LanguageCode=LANGUAGE_CODES[lang],
        OutputFormat="mp3",
    )
    return resp["AudioStream"].read()


def save_audio(plan_id: str, lang: str, audio: bytes) -> str:
    """Upload to AUDIO_BUCKET if set, else write under .data/audio. Returns the location."""
    key = f"audio/{plan_id}/{lang}.mp3"
    bucket = os.environ.get("AUDIO_BUCKET")
    if bucket:
        import boto3

        boto3.client("s3").put_object(Bucket=bucket, Key=key, Body=audio, ContentType="audio/mpeg")
        return f"s3://{bucket}/{key}"
    path = DATA_DIR / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(audio)
    return str(path)
