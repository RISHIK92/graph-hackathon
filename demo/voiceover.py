#!/usr/bin/env python3
"""Generate and sync Sarvam AI voiceover cues across the 7 Nodus demo beats."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "cursorcam-output"
VO_DIR = OUT_DIR / "voiceover"
CUES_DIR = VO_DIR / "cues"

SARVAM_CONFIG = {
    "target_language_code": "en-IN",
    "speaker": "rahul_hi_conversational",
    "model": "bulbul:v4-flash",
}

BEATS = [
    {
        "beat": "01-hook",
        "run": "01-hook-20261018-185129-8d68",
        "duration": 15.30,
        "cues": [
            (0.25, "Engineering facts are scattered across Slack, wikis, and tickets."),
            (4.70, "When teams reorganize, those sources go stale and contradict each other."),
            (10.10, "Nodus connects every source into a temporal knowledge graph on FalkorDB."),
        ],
    },
    {
        "beat": "02-answer-route",
        "run": "02-answer-route-20261018-190444-38c0",
        "duration": 34.03,
        "cues": [
            (0.35, "Ask who owns Ledger: Nodus returns Payments, led by Priya Raman, in two hops."),
            (6.85, "Every claim cites its exact source span and shows its trust rank."),
            (11.60, "Every lookup runs a verified Cypher template, never raw generated queries."),
            (18.30, "Now let's route ticket RDS-42 to the owner. Writes never execute blindly; they stage a proposal."),
            (26.00, "Only an eligible approver can confirm. Switching to Priya Raman and confirming writes the routed edge."),
        ],
    },
    {
        "beat": "03-dispute-confirm",
        "run": "03-dispute-confirm-20261018-191250-7c1a",
        "duration": 46.73,
        "cues": [
            (0.35, "What if someone says in chat: Infra owns Ledger now? Chat has lower trust than the service catalogue."),
            (7.10, "So Nodus doesn't overwrite the catalogue. Asking who owns Ledger surfaces both sides and flags the dispute."),
            (15.20, "The Cypher trace shows both candidate facts retrieved alongside their trust ranks."),
            (21.80, "If Bob Lindqvist tries to settle it in the Inbox, Nodus blocks him; only Priya Raman can confirm."),
            (30.30, "Switching to Priya and confirming closes the old ownership window and opens the new one."),
            (38.20, "Asking who owns Ledger now returns Infra, led by Bob Lindqvist, backed by the confirmed reorg."),
        ],
    },
    {
        "beat": "04-time-travel",
        "run": "04-time-travel-20261018-192754-0d51",
        "duration": 34.97,
        "cues": [
            (0.35, "Because every edge carries a valid-from and valid-to window, we can set the As-of lens to March thirty-first."),
            (8.50, "Asking who owns Ledger on that date returns Platform, the owner before both reorganizations."),
            (16.70, "We can also ask which systems are most critical, ranking Aurora and Ledger by transitive dependents."),
            (25.00, "Every bitemporal Cypher query filters edges by the chosen timestamp, before we jump back to today."),
        ],
    },
    {
        "beat": "05-then-now",
        "run": "05-then-now-20261018-193908-ae5b",
        "duration": 30.92,
        "cues": [
            (0.35, "Now ask an audit question: why did you route ticket RDS-42 to Priya?"),
            (6.80, "Nodus compares When Routed with Now: Payments owned it then; Infra owns it today."),
            (13.10, "The Cypher trace evaluates the graph at the action's timestamp and at the present side by side."),
            (19.80, "Opening the routed action lets us toggle between the historical path when taken and the live ownership path today."),
        ],
    },
    {
        "beat": "06-impact",
        "run": "06-impact-20261018-194506-364c",
        "duration": 23.32,
        "cues": [
            (0.35, "During an incident, ask: what breaks if Ledger goes down, and who do I tell?"),
            (5.80, "Nodus traces upstream dependents: Billing API, Checkout, and EU VAT launch, plus who to page."),
            (14.50, "Both the variable-length Cypher traversal and the full dependency path are inspectable in one click."),
        ],
    },
    {
        "beat": "07-abstain",
        "run": "07-abstain-20261018-200350-c43c",
        "duration": 16.75,
        "cues": [
            (0.35, "Finally, what if we ask for a fact the graph doesn't have, like Ledger's SLA?"),
            (8.20, "Instead of guessing, Nodus abstains cleanly with zero unverified claims. Grounded, temporal, and auditable."),
        ],
    },
]


def load_sarvam_key() -> str:
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    key = (
        os.environ.get("SARVAM_API_KEY")
        or os.environ.get("SARVAM_KEY")
        or os.environ.get("SARVAM_AI_API_KEY")
        or next((v for k, v in os.environ.items() if "SARVAM" in k.upper()), None)
    )
    if not key:
        raise RuntimeError("Missing SARVAM_API_KEY in .env")
    return key


def probe_duration(path: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    ).decode().strip()
    return float(out)


def synthesize_cue(key: str, text: str, raw_wav: Path, trimmed_wav: Path) -> float:
    if not raw_wav.exists():
        payload = {
            "text": text,
            **SARVAM_CONFIG,
        }
        req = urllib.request.Request(
            "https://api.sarvam.ai/text-to-speech",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "api-subscription-key": key,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        wav_bytes = base64.b64decode(data["audios"][0])
        raw_wav.write_bytes(wav_bytes)

    if not trimmed_wav.exists():
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-i",
                str(raw_wav),
                "-af",
                "silenceremove=start_periods=1:start_silence=0.02:start_threshold=-45dB,"
                "areverse,"
                "silenceremove=start_periods=1:start_silence=0.04:start_threshold=-45dB,"
                "areverse",
                "-ar",
                "24000",
                "-ac",
                "1",
                str(trimmed_wav),
            ],
            check=True,
        )
    return probe_duration(trimmed_wav)


def fit_cue(trimmed_wav: Path, fitted_wav: Path, max_dur: float) -> tuple[float, float, float]:
    raw_dur = probe_duration(trimmed_wav)
    if raw_dur <= max_dur:
        subprocess.run(["cp", str(trimmed_wav), str(fitted_wav)], check=True)
        return raw_dur, raw_dur, 1.0

    tempo = min(max(raw_dur / max_dur, 1.0), 1.35)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(trimmed_wav),
            "-af",
            f"atempo={tempo:.4f}",
            "-ar",
            "24000",
            "-ac",
            "1",
            str(fitted_wav),
        ],
        check=True,
    )
    return raw_dur, probe_duration(fitted_wav), tempo


def main() -> None:
    key = load_sarvam_key()
    CUES_DIR.mkdir(parents=True, exist_ok=True)

    voiced_videos: list[Path] = []
    print(f"{'Cue':<10} {'Start':>6} {'Window':>7} {'RawDur':>7} {'FitDur':>7} {'Tempo':>6}  Text")
    print("-" * 105)

    for b_idx, beat in enumerate(BEATS, start=1):
        run_dir = OUT_DIR / beat["run"]
        video_in = run_dir / "video-youtube.mp4"
        beat_dur = probe_duration(video_in)
        cues = beat["cues"]

        fitted_files: list[tuple[float, Path]] = []
        for c_idx, (start_s, text) in enumerate(cues, start=1):
            next_start = cues[c_idx][0] if c_idx < len(cues) else beat_dur - 0.10
            window_s = max(next_start - start_s - 0.12, 1.0)

            h = hashlib.sha1(f"{json.dumps(SARVAM_CONFIG, sort_keys=True)}|{text}".encode()).hexdigest()[:10]
            stem = f"b{b_idx:02d}_c{c_idx:02d}_{h}"
            raw_wav = CUES_DIR / f"{stem}_raw.wav"
            trim_wav = CUES_DIR / f"{stem}_trim.wav"
            fit_wav = CUES_DIR / f"{stem}_fit.wav"

            synthesize_cue(key, text, raw_wav, trim_wav)
            raw_d, fit_d, tempo = fit_cue(trim_wav, fit_wav, window_s)
            fitted_files.append((start_s, fit_wav))
            print(f"{b_idx:02d}.{c_idx:<7} {start_s:5.2f}s {window_s:6.2f}s {raw_d:6.2f}s {fit_d:6.2f}s {tempo:5.2f}x  {text}")

        # Build single beat audio track of exact length beat_dur
        beat_wav = VO_DIR / f"{beat['beat']}.wav"
        inputs: list[str] = []
        filter_parts: list[str] = []
        mix_labels: list[str] = []
        for i, (start_s, wav_path) in enumerate(fitted_files):
            inputs.extend(["-i", str(wav_path)])
            delay_ms = int(round(start_s * 1000))
            filter_parts.append(f"[{i}:a]adelay={delay_ms}|{delay_ms}[a{i}]")
            mix_labels.append(f"[a{i}]")

        n = len(fitted_files)
        filter_complex = (
            ";".join(filter_parts)
            + f";{''.join(mix_labels)}amix=inputs={n}:normalize=0,"
            f"apad=whole_dur={beat_dur:.4f},atrim=0:{beat_dur:.4f}[aout]"
        )
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                *inputs,
                "-filter_complex",
                filter_complex,
                "-map",
                "[aout]",
                "-ar",
                "48000",
                "-ac",
                "2",
                str(beat_wav),
            ],
            check=True,
        )

        # Mux video + audio for this beat
        voiced_mp4 = run_dir / "video-voiced.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-i",
                str(video_in),
                "-i",
                str(beat_wav),
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                str(voiced_mp4),
            ],
            check=True,
        )
        voiced_videos.append(voiced_mp4)

    # Concatenate all 7 voiced beat videos
    concat_file = VO_DIR / "concat-voiced.txt"
    concat_file.write_text("".join(f"file '{p}'\n" for p in voiced_videos))

    full_voiced = OUT_DIR / "nodus-demo-full-voiced.mp4"
    full_default = OUT_DIR / "nodus-demo-full.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            str(full_voiced),
        ],
        check=True,
    )
    subprocess.run(["cp", str(full_voiced), str(full_default)], check=True)
    total_dur = probe_duration(full_voiced)
    print("-" * 105)
    print(f"DONE: {full_voiced} (duration={total_dur:.2f}s / {int(total_dur//60)}:{total_dur%60:04.1f})")


if __name__ == "__main__":
    main()
