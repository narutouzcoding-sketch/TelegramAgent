"""Small mono WAV payloads for native multilingual audio understanding."""

import audioop
import io
import wave


def wav_bytes(pcm16):
    output = io.BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(pcm16)
    return output.getvalue()


def pcm48_to_wav(pcm):
    converted, _ = audioop.ratecv(pcm, 2, 1, 48000, 16000, None)
    return wav_bytes(converted)


def file_to_wav(path):
    import numpy as np
    from faster_whisper.audio import decode_audio

    audio = decode_audio(str(path), sampling_rate=16000)
    if len(audio) > 16000 * 90:
        raise ValueError("Ovozli xabar 90 soniyadan qisqa bo'lsin.")
    return wav_bytes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
