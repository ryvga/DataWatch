"""Convert the real Playwright recording into a captioned silent H.264 MP4.

Requires ffmpeg on PATH, or set FFMPEG to a compatible binary.
Run after node scripts/pfe/record_demo.mjs from the repository root.
"""
import json
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[2]
manifest = json.loads((root / "tmp/pfe/demo-video/recording-manifest.json").read_text())
ffmpeg = os.environ.get("FFMPEG", "ffmpeg")
out = root / "output/pfe/Demo_Panopta_Mounir_Gaiby.mp4"
ass = root / "tmp/pfe/demo-video/captions.ass"


def timestamp(seconds):
    centis = round(seconds * 100)
    return f"{centis // 360000}:{centis // 6000 % 60:02}:{centis // 100 % 60:02}.{centis % 100:02}"


header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,28,&H00FFFFFF,&H00FFFFFF,&H00202126,&H00202126,0,0,0,0,100,100,0,0,3,12,0,2,45,45,22,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
events = []
chapters = manifest["chapters"]
for i, chapter in enumerate(chapters):
    end = chapters[i + 1]["start"] if i + 1 < len(chapters) else manifest["duration"]
    caption = chapter["caption"].replace("\n", "\\N")
    events.append(f"Dialogue: 0,{timestamp(chapter['start'])},{timestamp(end)},Default,,0,0,0,,{caption}")
ass.write_text(header + "\n".join(events), encoding="utf-8")
subprocess.run([
    ffmpeg, "-y", "-i", manifest["rawVideo"], "-vf", f"ass={ass}",
    "-c:v", "libx264", "-crf", "19", "-preset", "medium", "-pix_fmt", "yuv420p",
    "-an", "-movflags", "+faststart", str(out),
], check=True)
print(out)
