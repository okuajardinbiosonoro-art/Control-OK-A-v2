from __future__ import annotations

import mido


def main() -> int:
    mido.set_backend("mido.backends.rtmidi")
    print("[midi] backend=rtmidi")
    print(f"[midi] input_names={mido.get_input_names()}")
    print(f"[midi] output_names={mido.get_output_names()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
