import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

WHISPER_DIR = Path.home() / "whisper.cpp"
WHISPER_BIN = WHISPER_DIR / "build" / "bin" / "whisper-cli"
WHISPER_MODEL = WHISPER_DIR / "models" / "ggml-base.en.bin"
WORK_DIR = Path("workspace")
OUTPUT_DIR = Path("/storage/emulated/0/Download/PocketClipper")

HOOK_WORDS = {
    "secret", "mistake", "never", "always", "truth", "actually", "crazy",
    "insane", "money", "stop", "why", "how", "best", "worst", "first",
    "million", "hack", "trick", "important", "listen", "wait", "problem"
}


def run_cmd(cmd):
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        print(f"[ERROR] Command failed: {' '.join(cmd)}")
        print(result.stderr)
        sys.exit(1)
    return result.stdout


def download_video(url: str) -> Path:
    print("[1/5] Downloading YouTube video...")
    video_path = WORK_DIR / "source.mp4"
    cmd = [
        "yt-dlp",
        "-f", "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", str(video_path),
        url,
    ]
    run_cmd(cmd)
    return video_path


def extract_audio(video_path: Path) -> Path:
    print("[2/5] Extracting 16kHz mono audio for Whisper...")
    audio_path = WORK_DIR / "audio.wav"
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
        str(audio_path)
    ]
    run_cmd(cmd)
    return audio_path


def transcribe_audio(audio_path: Path) -> Path:
    print("[3/5] Transcribing locally with whisper.cpp (this may take a few minutes)...")
    srt_prefix = WORK_DIR / "transcript"
    cmd = [
        str(WHISPER_BIN),
        "-m", str(WHISPER_MODEL),
        "-f", str(audio_path),
        "-osrt",
        "-of", str(srt_prefix),
        "-t", "4"
    ]
    run_cmd(cmd)
    return Path(f"{srt_prefix}.srt")


def parse_timestamp(ts: str) -> float:
    h, m, s_ms = ts.split(":")
    s, ms = s_ms.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def format_timestamp(seconds: float) -> str:
    ms = int((seconds - int(seconds)) * 1000)
    s = int(seconds) % 60
    m = (int(seconds) // 60) % 60
    h = int(seconds) // 3600
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def parse_srt(srt_path: Path):
    content = srt_path.read_text(encoding="utf-8", errors="ignore")
    blocks = re.split(r"\n\s*\n", content.strip())
    segments = []
    for block in blocks:
        lines = block.splitlines()
        if len(lines) >= 3 and "-->" in lines[1]:
            start_str, end_str = lines[1].split(" --> ")
            text = " ".join(lines[2:]).strip()
            segments.append({
                "start": parse_timestamp(start_str.strip()),
                "end": parse_timestamp(end_str.strip()),
                "text": text
            })
    return segments


def find_viral_clips(segments, num_clips: int, target_duration: int):
    print("[4/5] Scoring transcript for high-engagement moments...")
    candidates = []

    for i in range(len(segments)):
        start_time = segments[i]["start"]
        window_text = []
        end_time = start_time

        for j in range(i, len(segments)):
            end_time = segments[j]["end"]
            window_text.append(segments[j]["text"])
            if end_time - start_time >= target_duration:
                break

        duration = end_time - start_time
        if duration < target_duration * 0.6:
            continue

        full_text = " ".join(window_text)
        words = re.findall(r"\b\w+\b", full_text.lower())
        if not words:
            continue

        # Score based on speaking pace, hook words, and questions/exclamations
        pace_score = len(words) / max(duration, 1)
        hook_score = sum(2.5 for w in words if w in HOOK_WORDS)
        punct_score = full_text.count("?") * 3.0 + full_text.count("!") * 2.0
        total_score = pace_score + hook_score + punct_score

        candidates.append({
            "start": start_time,
            "end": end_time,
            "score": total_score,
            "segments": segments[i:j + 1]
        })

    candidates.sort(key=lambda x: x["score"], reverse=True)

    # Pick non-overlapping top clips
    selected = []
    for cand in candidates:
        if len(selected) >= num_clips:
            break
        overlaps = any(
            not (cand["end"] <= s["start"] or cand["start"] >= s["end"])
            for s in selected
        )
        if not overlaps:
            selected.append(cand)

    return selected


def write_clip_srt(clip_segments, clip_start: float, out_srt: Path):
    lines = []
    for idx, seg in enumerate(clip_segments, start=1):
        rel_start = max(0.0, seg["start"] - clip_start)
        rel_end = max(rel_start + 0.2, seg["end"] - clip_start)
        lines.append(f"{idx}")
        lines.append(f"{format_timestamp(rel_start)} --> {format_timestamp(rel_end)}")
        lines.append(seg["text"])
        lines.append("")
    out_srt.write_text("\n".join(lines), encoding="utf-8")


def render_clips(video_path: Path, clips):
    print(f"[5/5] Rendering {len(clips)} vertical 9:16 clips with captions...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for idx, clip in enumerate(clips, start=1):
        clip_srt = WORK_DIR / f"clip_{idx}.srt"
        write_clip_srt(clip["segments"], clip["start"], clip_srt)

        out_file = OUTPUT_DIR / f"viral_clip_{idx}.mp4"
        duration = clip["end"] - clip["start"]

        # Center crop to 9:16 + burn in styled subtitles
        vf_filter = (
            f"crop=ih*9/16:ih,scale=720:1280,"
            f"subtitles={clip_srt}:force_style="
            f"'FontName=Arial,FontSize=18,PrimaryColour=&H00FFFFFF,"
            f"OutlineColour=&H00000000,BorderStyle=1,Outline=2,Alignment=2,MarginV=40'"
        )

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(clip["start"]),
            "-t", str(duration),
            "-i", str(video_path),
            "-vf", vf_filter,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            str(out_file)
        ]
        run_cmd(cmd)
        print(f"  -> Saved: {out_file}")


def main():
    parser = argparse.ArgumentParser(description="Free On-Device YouTube AI Clipper")
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument("--clips", type=int, default=3, help="Number of clips to generate")
    parser.add_argument("--duration", type=int, default=45, help="Target clip length in seconds")
    args = parser.parse_args()

    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)
    WORK_DIR.mkdir(parents=True)

    video_path = download_video(args.url)
    audio_path = extract_audio(video_path)
    srt_path = transcribe_audio(audio_path)
    segments = parse_srt(srt_path)

    if not segments:
        print("[ERROR] No speech detected in video.")
        sys.exit(1)

    clips = find_viral_clips(segments, args.clips, args.duration)
    render_clips(video_path, clips)
    print(f"\nDone! Check your phone's Downloads/PocketClipper folder.")


if __name__ == "__main__":
    main()
                     
