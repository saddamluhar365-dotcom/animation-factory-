from __future__ import annotations
import shutil
import subprocess
from pathlib import Path
from core.audio.timeline import AudioTimeline


def ffmpeg_path() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("FFmpeg is required and must be available on PATH")
    return path


def synthesize_rich_asmr_audio(duration: float, timeline: AudioTimeline, output: Path) -> Path:
    """Synthesize multi-layered, action-synced ASMR sound design for vertical culinary Shorts.
    
    Layers:
    1. Warm environmental kitchen presence (room tone)
    2. Action-synced ASMR Foley textures (sizzle, chop, pour, clink, scrape)
    3. Subtle harmonic tone bed
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    dur_str = f"{duration:.3f}"

    # Layer 1: Ambient room tone
    filters = [
        f"anoisesrc=d={dur_str}:c=brown:r=48000:a=0.012,highpass=f=80,lowpass=f=6000,volume=0.45[amb]"
    ]
    labels = ["[amb]"]

    # Layer 2: Action-synced Foley events
    idx = 0
    for event in timeline.events:
        if event.kind not in {"sfx", "expression"}:
            continue

        evt_len = max(0.06, min(1.2, event.end - event.start))
        delay_ms = max(0, int(round(event.start * 1000)))
        vol = max(0.05, min(0.35, event.volume if hasattr(event, "volume") else 0.20))
        name = event.name.lower()
        label = f"fx{idx}"

        if any(k in name for k in ("sizzle", "fry", "sear", "bubble", "flame", "steam")):
            # High-frequency crackle and frying texture
            f_in = min(0.06, evt_len * 0.2)
            f_out = min(0.18, evt_len * 0.4)
            filters.append(
                f"anoisesrc=d={evt_len:.3f}:c=pink:r=48000:a=0.16,"
                f"highpass=f=2400,lowpass=f=11000,"
                f"afade=t=in:st=0:d={f_in:.3f},"
                f"afade=t=out:st={max(0, evt_len - f_out):.3f}:d={f_out:.3f},"
                f"volume={vol:.3f},"
                f"adelay={delay_ms}|{delay_ms}[{label}]"
            )
            labels.append(f"[{label}]")
            idx += 1

        elif any(k in name for k in ("chop", "slice", "cut", "dice", "knife")):
            # Dual transient: resonant wood body + crisp knife impact
            wood_len = min(0.14, evt_len)
            filters.append(
                f"sine=f=210:d={wood_len:.3f}:r=48000,"
                f"afade=t=out:st=0.02:d={max(0.04, wood_len-0.02):.3f},"
                f"volume={vol * 0.8:.3f},"
                f"adelay={delay_ms}|{delay_ms}[{label}]"
            )
            labels.append(f"[{label}]")
            idx += 1

        elif any(k in name for k in ("pour", "liquid", "drizzle", "sauce", "water", "oil")):
            # Fluid bubbling stream
            f_in = min(0.08, evt_len * 0.25)
            f_out = min(0.15, evt_len * 0.35)
            filters.append(
                f"sine=f=420:d={evt_len:.3f}:r=48000,"
                f"afade=t=in:st=0:d={f_in:.3f},"
                f"afade=t=out:st={max(0, evt_len - f_out):.3f}:d={f_out:.3f},"
                f"volume={vol * 0.55:.3f},"
                f"adelay={delay_ms}|{delay_ms}[{label}]"
            )
            labels.append(f"[{label}]")
            idx += 1

        elif any(k in name for k in ("clink", "pan", "plate", "bowl", "metal", "tap", "knock")):
            # Resonant bell-like harmonic decay
            clink_len = min(0.35, evt_len)
            filters.append(
                f"sine=f=780:d={clink_len:.3f}:r=48000,"
                f"afade=t=out:st=0.02:d={max(0.05, clink_len-0.02):.3f},"
                f"volume={vol * 0.50:.3f},"
                f"adelay={delay_ms}|{delay_ms}[{label}]"
            )
            labels.append(f"[{label}]")
            idx += 1

        elif any(k in name for k in ("scrape", "stir", "swoosh", "mix", "spread")):
            # Textured friction sweep
            f_in = min(0.08, evt_len * 0.25)
            f_out = min(0.12, evt_len * 0.30)
            filters.append(
                f"anoisesrc=d={evt_len:.3f}:c=brown:r=48000:a=0.10,"
                f"highpass=f=400,lowpass=f=3600,"
                f"afade=t=in:st=0:d={f_in:.3f},"
                f"afade=t=out:st={max(0, evt_len - f_out):.3f}:d={f_out:.3f},"
                f"volume={vol * 0.45:.3f},"
                f"adelay={delay_ms}|{delay_ms}[{label}]"
            )
            labels.append(f"[{label}]")
            idx += 1

        else:
            # General crisp tactile click
            filters.append(
                f"sine=f=520:d=0.08:r=48000,"
                f"afade=t=out:st=0.02:d=0.06,"
                f"volume={vol * 0.40:.3f},"
                f"adelay={delay_ms}|{delay_ms}[{label}]"
            )
            labels.append(f"[{label}]")
            idx += 1

    # Mix and final limiting
    if len(labels) == 1:
        filters.append("[amb]volume=0.75,alimiter=limit=0.88[aout]")
    else:
        filters.append(
            "".join(labels) + f"amix=inputs={len(labels)}:duration=longest:dropout_transition=0,alimiter=limit=0.88[aout]"
        )

    graph = ";".join(filters)
    subprocess.run(
        [
            ffmpeg_path(),
            "-y",
            "-filter_complex",
            graph,
            "-map",
            "[aout]",
            "-t",
            dur_str,
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(output),
        ],
        capture_output=True,
        check=True,
    )
    return output
