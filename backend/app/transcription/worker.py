import argparse
import json
import sys
import time
from importlib.metadata import version
from pathlib import Path
from typing import Any, cast

from app.transcription.contracts import (
    RawTranscriptionNote,
    TranscriptionProvenance,
    WorkerTranscriptionOutput,
)


def _runtime_details() -> dict[str, str]:
    import tensorflow as tf  # type: ignore[import-untyped]
    from basic_pitch import ICASSP_2022_MODEL_PATH  # type: ignore[import-not-found]

    model_path = Path(ICASSP_2022_MODEL_PATH)
    return {
        "model_name": "basic_pitch",
        "model_version": version("basic-pitch"),
        "runtime": "tensorflow",
        "runtime_version": str(tf.__version__),
        "model_serialization": str(Path("icassp_2022") / model_path.name),
    }


def _probe() -> int:
    print(json.dumps(_runtime_details(), sort_keys=True))
    return 0


def _transcribe(args: argparse.Namespace) -> int:
    from basic_pitch.inference import predict  # type: ignore[import-not-found]

    input_path = Path(args.input)
    events_output = Path(args.events_output)
    midi_output = Path(args.midi_output)
    configuration: dict[str, float | bool] = {
        "onset_threshold": args.onset_threshold,
        "frame_threshold": args.frame_threshold,
        "minimum_note_length_ms": args.minimum_note_length_ms,
        "minimum_frequency_hz": args.minimum_frequency_hz,
        "maximum_frequency_hz": args.maximum_frequency_hz,
        "multiple_pitch_bends": False,
        "melodia_trick": True,
        "midi_tempo": 120.0,
    }
    started = time.perf_counter()
    _model_output, midi_data, raw_events = cast(
        tuple[dict[str, Any], Any, list[tuple[float, float, int, float, list[int] | None]]],
        predict(
            input_path,
            onset_threshold=args.onset_threshold,
            frame_threshold=args.frame_threshold,
            minimum_note_length=args.minimum_note_length_ms,
            minimum_frequency=args.minimum_frequency_hz,
            maximum_frequency=args.maximum_frequency_hz,
            multiple_pitch_bends=False,
            melodia_trick=True,
            midi_tempo=120.0,
        ),
    )
    notes = [
        RawTranscriptionNote(
            start_seconds=float(start),
            end_seconds=float(end),
            pitch=int(pitch),
            velocity=max(1, min(127, round(float(confidence) * 127))),
            confidence=float(confidence),
            pitch_bends=[int(value) for value in pitch_bends] if pitch_bends else None,
        )
        for start, end, pitch, confidence, pitch_bends in raw_events
    ]
    runtime = _runtime_details()
    configuration["inference_seconds"] = round(time.perf_counter() - started, 6)
    output = WorkerTranscriptionOutput(
        provenance=TranscriptionProvenance(
            model_name=runtime["model_name"],
            model_version=runtime["model_version"],
            model_runtime=runtime["runtime"],
            runtime_version=runtime["runtime_version"],
            model_serialization=runtime["model_serialization"],
            configuration=configuration,
        ),
        notes=notes,
    )
    events_output.write_text(output.model_dump_json(indent=2), encoding="utf-8")
    midi_data.write(str(midi_output))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pianova Basic Pitch worker")
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--input")
    parser.add_argument("--events-output")
    parser.add_argument("--midi-output")
    parser.add_argument("--onset-threshold", type=float, default=0.5)
    parser.add_argument("--frame-threshold", type=float, default=0.3)
    parser.add_argument("--minimum-note-length-ms", type=float, default=127.7)
    parser.add_argument("--minimum-frequency-hz", type=float, default=27.5)
    parser.add_argument("--maximum-frequency-hz", type=float, default=4186.01)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.probe:
            return _probe()
        required = (args.input, args.events_output, args.midi_output)
        if any(value is None for value in required):
            raise ValueError("--input, --events-output, and --midi-output are required.")
        return _transcribe(args)
    except Exception as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
