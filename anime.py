"""
Anime-style restyling for clips, directed by Claude.

Claude looks at a handful of frames plus the clip transcript and returns a
structured "anime direction": which look to use, how strong the ink lines are,
which moments deserve an impact flash + manga SFX, and an optional opening
title card. The FFmpeg filter graph is then built deterministically from that
plan (Claude never writes raw filter syntax), so a bad answer can't break the
render.
"""
import base64
import os
import re
import shutil
import subprocess
import tempfile
from typing import List, Literal, Optional

import anthropic
from pydantic import BaseModel, Field

MODEL = "claude-opus-5-5"

FONT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "NotoSerif-Bold.ttf")

AnimeStyle = Literal["shonen", "ghibli", "cyberpunk", "manga"]

# Look presets. All numbers are FFmpeg parameters tuned by hand.
STYLE_PRESETS = {
    # Punchy action-anime: saturated, hard ink lines, few colour bands.
    "shonen": dict(saturation=1.7, contrast=1.15, brightness=0.02, gamma=1.0,
                   balance="rm=0.05:bm=-0.03", levels=6, denoise=5, grayscale=False,
                   sfx_color="yellow", border_color="black"),
    # Soft hand-painted feel: warm, gentle lines, more colour bands.
    "ghibli": dict(saturation=1.3, contrast=1.05, brightness=0.04, gamma=1.05,
                   balance="rs=0.04:gs=0.02:bs=-0.05:rh=0.03:bh=-0.03", levels=9, denoise=7,
                   grayscale=False, sfx_color="white", border_color="0x3a2a1a"),
    # Neon night city: magenta highlights, cyan shadows.
    "cyberpunk": dict(saturation=1.6, contrast=1.2, brightness=-0.02, gamma=0.95,
                      balance="rs=-0.08:bs=0.12:rh=0.12:bh=0.08:gh=-0.05", levels=5, denoise=5,
                      grayscale=False, sfx_color="0xff2bd6", border_color="0x00e5ff"),
    # Black-and-white manga page.
    "manga": dict(saturation=0.0, contrast=1.45, brightness=0.03, gamma=1.0,
                  balance=None, levels=4, denoise=4, grayscale=True,
                  sfx_color="white", border_color="black"),
}

LINE_STRENGTH = {
    # edgedetect thresholds (lower = more lines) and how many erosion passes thicken them
    "light": dict(low=0.12, high=0.32, thicken=0),
    "medium": dict(low=0.08, high=0.24, thicken=1),
    "bold": dict(low=0.05, high=0.18, thicken=2),
}


class ImpactMoment(BaseModel):
    time_sec: float = Field(description="When the impact hits, in seconds from the start of the clip.")
    sfx_text: str = Field(description="Short manga sound effect, 1-2 words, Latin letters only, e.g. 'BAM!', 'WHOOSH', 'DOKI DOKI'.")


class AnimeDirection(BaseModel):
    style: AnimeStyle
    line_strength: Literal["light", "medium", "bold"]
    title_card: Optional[str] = Field(description="Optional 2-5 word anime episode-style title shown for the first 2 seconds, Latin letters only. Null for none.")
    impact_moments: List[ImpactMoment] = Field(description="0-4 key dramatic beats (punchlines, reveals, big claims).")
    reasoning: str = Field(description="One sentence on why this look fits the clip.")


SYSTEM_PROMPT = """You are the art director for an anime studio that turns real short-form videos (TikTok, Reels, Shorts) into anime-styled versions.

You get a few frames from a vertical clip plus its transcript. Choose the anime look that fits the clip's mood and content:
- shonen: high-energy, motivational, competitive, sports, hype.
- ghibli: calm, warm, nostalgic, nature, food, storytelling, wholesome.
- cyberpunk: tech, futuristic, night scenes, neon, gaming, AI.
- manga: serious, dramatic, suspenseful, or interview-style talking heads where a black-and-white page reads best.

Pick impact moments only where something genuinely lands (a punchline, a reveal, a bold claim, a sudden action). Fewer is better; an empty list is fine for a calm clip. Times must fall inside the clip duration and be at least 2 seconds apart. SFX text should match the moment and be at most 12 characters.

The title card should read like an anime episode title tied to what is said, for example "The Day I Quit". Use null if nothing fits."""


def _clean_text(text: Optional[str], max_len: int) -> str:
    """Keep only characters that are safe for the bundled Latin font and drawtext."""
    if not text:
        return ""
    text = re.sub(r"[^A-Za-z0-9 !?.,'\-]", "", text).strip()
    return text[:max_len].upper()


def probe_video(path: str) -> dict:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height:format=duration",
        "-of", "default=noprint_wrappers=1", path,
    ]).decode()
    info = dict(line.split("=", 1) for line in out.strip().splitlines() if "=" in line)
    return {
        "width": int(info.get("width", 1080)),
        "height": int(info.get("height", 1920)),
        "duration": float(info.get("duration", 0) or 0),
    }


def extract_frames(path: str, duration: float, count: int = 6) -> List[str]:
    """Grab `count` evenly spaced frames as base64 JPEGs, downscaled for the API."""
    frames = []
    tmpdir = tempfile.mkdtemp(prefix="anime_frames_")
    try:
        for i in range(count):
            t = duration * (i + 0.5) / count if duration > 0 else 0
            frame_path = os.path.join(tmpdir, f"f{i}.jpg")
            subprocess.run([
                "ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", path,
                "-frames:v", "1", "-vf", "scale=-2:768", "-q:v", "4", frame_path,
            ], check=False)
            if os.path.exists(frame_path):
                with open(frame_path, "rb") as f:
                    frames.append(base64.standard_b64encode(f.read()).decode("utf-8"))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return frames


def clip_transcript_text(transcript: Optional[dict], clip_start: float, clip_end: float) -> str:
    """Return clip-relative '[12.3s] words' lines for the words inside the clip window."""
    if not transcript:
        return "Not available."
    lines = []
    for seg in transcript.get("segments", []):
        if seg.get("end", 0) <= clip_start or seg.get("start", 0) >= clip_end:
            continue
        rel = max(0.0, seg["start"] - clip_start)
        lines.append(f"[{rel:.1f}s] {seg.get('text', '').strip()}")
    return "\n".join(lines) or "Not available."


def get_anime_direction(api_key: str, frames: List[str], transcript_text: str,
                        duration: float, style_hint: Optional[str] = None) -> AnimeDirection:
    client = anthropic.Anthropic(api_key=api_key)

    content = []
    for b64 in frames:
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}})
    request = f"Clip duration: {duration:.1f} seconds.\n\nTranscript (times relative to clip start):\n{transcript_text}"
    if style_hint and style_hint != "auto":
        request += f"\n\nThe creator asked for the '{style_hint}' style. Use it."
    content.append({"type": "text", "text": request})

    response = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": content}],
        output_format=AnimeDirection,
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined to style this clip.")
    direction = response.parsed_output
    if direction is None:
        raise RuntimeError("Claude returned no anime direction.")
    if style_hint in STYLE_PRESETS:
        direction.style = style_hint
    return direction


def _posterize_lut(levels: int) -> str:
    step = 256 // levels
    expr = f"trunc(val/{step})*{step}+{step // 2}"
    return f"lutrgb=r='{expr}':g='{expr}':b='{expr}'"


def build_filter_graph(direction: AnimeDirection, width: int, height: int,
                       duration: float, workdir: str) -> str:
    """Turn Claude's plan into an FFmpeg -filter_complex graph ending in [vout]."""
    p = STYLE_PRESETS[direction.style]
    lines = LINE_STRENGTH[direction.line_strength]

    # Colour layer: flatten detail, push colours, quantise into cel-shading bands.
    color = [f"hqdn3d={p['denoise']}:{p['denoise']}:0:0"]
    color.append(f"eq=saturation={p['saturation']}:contrast={p['contrast']}:brightness={p['brightness']}:gamma={p['gamma']}")
    if p["balance"]:
        color.append(f"colorbalance={p['balance']}")
    color.append("format=rgb24")
    color.append(_posterize_lut(p["levels"]))
    if p["grayscale"]:
        color.append("hue=s=0")
    color.append("format=gbrp")

    # Ink layer: edges as black lines on white, optionally thickened.
    ink = ["format=gray", f"edgedetect=low={lines['low']}:high={lines['high']}", "negate"]
    ink += ["erosion"] * lines["thicken"]
    ink.append("format=gbrp")

    graph = [
        "[0:v]split=2[c][e]",
        "[c]" + ",".join(color) + "[col]",
        "[e]" + ",".join(ink) + "[ink]",
        "[col][ink]blend=all_mode=multiply,format=yuv420p,vignette=angle=PI/5[base]",
    ]

    post = []

    def fit(text: str, preferred: int) -> int:
        # Serif caps run ~0.75em wide; keep text inside 90% of the frame width.
        return max(24, min(preferred, int(width * 0.9 / (0.75 * max(1, len(text))))))
    has_font = os.path.exists(FONT_PATH)
    font_opt = f"fontfile='{FONT_PATH}':" if has_font else ""

    def drawtext(text: str, name: str, **opts) -> str:
        # Text goes through a file so no user/model text is ever parsed as filter syntax.
        text_path = os.path.join(workdir, f"{name}.txt")
        with open(text_path, "w", encoding="utf-8") as f:
            f.write(text)
        opt_str = ":".join(f"{k}={v}" for k, v in opts.items())
        return f"drawtext={font_opt}textfile='{text_path}':{opt_str}"

    used = []
    for i, moment in enumerate(sorted(direction.impact_moments, key=lambda m: m.time_sec)[:4]):
        t = moment.time_sec
        if t < 0 or (duration and t > duration - 0.3) or any(abs(t - u) < 1.5 for u in used):
            continue
        used.append(t)
        sfx = _clean_text(moment.sfx_text, 12)
        # Quick white flash, then the SFX pops on screen for a beat.
        post.append(f"eq=brightness=0.35:contrast=1.3:enable='between(t,{t:.2f},{t + 0.12:.2f})'")
        if sfx:
            post.append(drawtext(
                sfx, f"sfx{i}",
                fontsize=fit(sfx, width // 5), fontcolor=p["sfx_color"],
                borderw=max(6, width // 120), bordercolor=p["border_color"],
                x="(w-text_w)/2", y="h*0.28",
                enable=f"'between(t,{t:.2f},{t + 0.9:.2f})'",
            ))

    title = _clean_text(direction.title_card, 32)
    if title:
        post.append(drawtext(
            title, "title",
            fontsize=fit(title, width // 13), fontcolor="white",
            borderw=max(4, width // 200), bordercolor="black",
            box=1, boxcolor="black@0.45", boxborderw=max(16, width // 40),
            x="(w-text_w)/2", y="h*0.12",
            enable="'between(t,0,2.2)'",
        ))

    post.append("setsar=1")
    graph.append("[base]" + ",".join(post) + "[vout]")
    return ";".join(graph)


def render_anime(input_path: str, output_path: str, direction: AnimeDirection) -> None:
    info = probe_video(input_path)
    workdir = tempfile.mkdtemp(prefix="anime_render_")
    try:
        graph = build_filter_graph(direction, info["width"], info["height"], info["duration"], workdir)
        print(f"🎌 Anime filter graph: {graph}")
        env = os.environ.copy()
        env["LANG"] = env["LC_ALL"] = "C.UTF-8"
        subprocess.run([
            "ffmpeg", "-y", "-v", "error", "-i", input_path,
            "-filter_complex", graph,
            "-map", "[vout]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "copy", output_path,
        ], check=True, env=env)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def animefy_clip(api_key: str, input_path: str, output_path: str,
                 transcript: Optional[dict] = None, clip_start: float = 0.0,
                 clip_end: Optional[float] = None, style_hint: Optional[str] = None) -> dict:
    """Full pipeline: probe -> frames -> Claude direction -> FFmpeg render. Returns the plan."""
    info = probe_video(input_path)
    duration = info["duration"]
    if clip_end is None:
        clip_end = clip_start + duration
    frames = extract_frames(input_path, duration)
    transcript_text = clip_transcript_text(transcript, clip_start, clip_end)
    print(f"🎌 Asking Claude for anime direction ({len(frames)} frames)...")
    direction = get_anime_direction(api_key, frames, transcript_text, duration, style_hint)
    print(f"🎌 Direction: {direction.model_dump_json()}")
    render_anime(input_path, output_path, direction)
    return direction.model_dump()
