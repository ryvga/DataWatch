"""Export the real action recording and its synchronized spoken rehearsal script."""
import json
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[2]
work = root / "tmp/pfe/action-video"
manifest = json.loads((work / "recording-manifest.json").read_text())
out = root / "output/pfe/Demo_Panopta_PFE_Action.mp4"
ass = work / "captions.ass"

def stamp(s):
    n = round(s * 100)
    return f"{n//360000}:{n//6000%60:02}:{n//100%60:02}.{n%100:02}"

header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,27,&H00FFFFFF,&H00FFFFFF,&H00251C11,&H00251C11,0,0,0,0,100,100,0,0,1,0,0,2,70,70,24,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
events = []
for i, c in enumerate(manifest["chapters"]):
    end = manifest["chapters"][i+1]["start"] if i+1 < len(manifest["chapters"]) else manifest["duration"]
    events.append(f"Dialogue: 0,{stamp(c['start'])},{stamp(end)},Default,,0,0,0,,{c['caption']}")
ass.write_text(header + "\n".join(events), encoding="utf-8")

def clock(seconds):
    total = max(0, int(seconds))
    return f"{total // 60:02}:{total % 60:02}"

script_lines = [
    "# Panopta action demo, timed English narration",
    "",
    f"Video duration: {clock(manifest['duration'])}. The recording is silent. Speak the text below while it plays.",
    "",
    "The timestamps follow the final recording. Start speaking when each caption appears. Keep a measured pace. If an action finishes before your sentence, continue speaking and let the screen remain visible.",
    "",
]
for i, c in enumerate(manifest["chapters"]):
    end = manifest["chapters"][i + 1]["start"] if i + 1 < len(manifest["chapters"]) else manifest["duration"]
    script_lines += [
        f"## {clock(c['start'])} to {clock(end)}. {c['caption']}",
        "",
        c["narration"],
        "",
        f"Screen: `{c['name']}`. Route: `{c['url']}`.",
        "",
    ]
(root / "docs/pfe/DEMO_SCRIPT_EN.md").write_text("\n".join(script_lines), encoding="utf-8")
subprocess.run([os.environ.get("FFMPEG", "ffmpeg"), "-y", "-i", manifest["rawVideo"], "-vf", f"scale=1792:1008,pad=1920:1080:64:0:color=0x111c25,ass={ass}", "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart", str(out)],check=True)
print(out)
