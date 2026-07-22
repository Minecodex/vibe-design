from __future__ import annotations

OUTPUT_TRUNCATION_MARKER_TEMPLATE = "\n\n[output truncated - exceeded {max_bytes} bytes]"


def truncate_stream_output(data: bytes, max_bytes: int) -> tuple[str, bool]:
    if len(data) <= max_bytes:
        return data.decode("utf-8", errors="replace"), False
    end = max(max_bytes, 0)
    while end > 0:
        try:
            prefix = data[:end].decode("utf-8")
            break
        except UnicodeDecodeError:
            end -= 1
    else:
        prefix = ""
    marker = OUTPUT_TRUNCATION_MARKER_TEMPLATE.format(max_bytes=max_bytes)
    return prefix + marker, True
