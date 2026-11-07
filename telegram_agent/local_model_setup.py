"""Download official Ollama layers over IPv4, resume ranges, verify SHA-256."""

import asyncio
import hashlib
import json
import os
import re
import socket
from pathlib import Path

import aiohttp


async def download(model="qwen3:4b-instruct"):
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*:[a-zA-Z0-9._-]+", model):
        raise ValueError("Model nomi: qwen3:4b-instruct shaklida bo'lsin.")
    name, tag = model.split(":")
    base = "https://registry.ollama.ai/v2/library/" + name
    root = Path(os.environ.get("OLLAMA_MODELS") or Path.home() / ".ollama" / "models").resolve()
    blobs = root / "blobs"
    blobs.mkdir(parents=True, exist_ok=True)
    timeout = aiohttp.ClientTimeout(total=None, connect=25, sock_read=60)
    connector = aiohttp.TCPConnector(family=socket.AF_INET, limit=6)
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as client:
        async with client.get(base + "/manifests/" + tag) as response:
            response.raise_for_status()
            manifest_bytes = await response.read()
        manifest = json.loads(manifest_bytes)
        for layer in [manifest["config"], *manifest["layers"]]:
            digest, size = layer["digest"], layer["size"]
            if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest) or not 0 < size < 10_000_000_000:
                raise ValueError("Model manifesti noto'g'ri.")
            target = blobs / digest.replace(":", "-")
            if target.exists() and target.stat().st_size == size:
                continue
            partial = target.with_name(target.name + "-partial")
            parts = []
            for meta in blobs.glob(target.name + "-partial-*"):
                value = json.loads(meta.read_text())
                if (
                    all(isinstance(value.get(k), int) for k in ("Offset", "Size", "Completed"))
                    and 0 <= value["Completed"] <= value["Size"]
                    and 0 <= value["Offset"] < size
                    and value["Offset"] + value["Size"] <= size
                ):
                    parts.append((meta, value))
            parts.sort(key=lambda item: item[1]["Offset"])
            contiguous = sum(v["Size"] for _, v in parts) == size and all(
                v["Offset"] == sum(p["Size"] for _, p in parts[:i])
                for i, (_, v) in enumerate(parts)
            )
            if not contiguous or not partial.exists():
                parts = [
                    (
                        blobs / (target.name + "-partial-0"),
                        {"N": 0, "Offset": 0, "Size": size, "Completed": 0},
                    )
                ]
                with partial.open("wb") as file:
                    file.truncate(size)
            print(
                f"Model layer {digest[7:19]}: {sum(v['Completed'] for _, v in parts) * 100 // size}% mavjud; IPv4 davom etyapti.",
                flush=True,
            )
            semaphore = asyncio.Semaphore(4)

            async def part(meta, value):
                async with semaphore:
                    for attempt in range(4):
                        start = value["Offset"] + value["Completed"]
                        end = value["Offset"] + value["Size"] - 1
                        if start > end:
                            return
                        try:
                            async with client.get(
                                base + "/blobs/" + digest, headers={"Range": f"bytes={start}-{end}"}
                            ) as response:
                                response.raise_for_status()
                                if response.status != 206 and not (start == 0 and end == size - 1):
                                    raise ValueError("Server kutilgan Range javobini bermadi.")
                                if response.status == 206 and not response.headers.get(
                                    "Content-Range", ""
                                ).startswith(f"bytes {start}-"):
                                    raise ValueError("Server Range manzili mos emas.")
                                with partial.open("r+b") as file:
                                    file.seek(start)
                                    async for chunk in response.content.iter_chunked(1024 * 1024):
                                        remaining = value["Size"] - value["Completed"]
                                        if len(chunk) > remaining:
                                            raise ValueError("Model bo'lagi uzunligi mos emas.")
                                        file.write(chunk)
                                        value["Completed"] += len(chunk)
                                    file.flush()
                                meta.write_text(json.dumps(value))
                                if value["Completed"] == value["Size"]:
                                    return
                        except (aiohttp.ClientError, TimeoutError):
                            meta.write_text(json.dumps(value))
                            if attempt == 3:
                                raise RuntimeError(
                                    "Model serveriga IPv4 ulanish uzildi; keyingi ishga tushirish davom ettiradi."
                                ) from None
                            await asyncio.sleep(1 + attempt)
                    raise RuntimeError("Model bo'lagi to'liq yuklanmadi.")

            async def progress():
                while True:
                    await asyncio.sleep(15)
                    print(
                        f"Layer {digest[7:19]}: {sum(v['Completed'] for _, v in parts) * 100 // size}%",
                        flush=True,
                    )

            monitor = asyncio.create_task(progress())
            try:
                await asyncio.gather(*(part(meta, value) for meta, value in parts))
            finally:
                monitor.cancel()
                await asyncio.gather(monitor, return_exceptions=True)

            def checksum():
                with partial.open("rb") as file:
                    return hashlib.file_digest(file, "sha256").hexdigest()

            if await asyncio.to_thread(checksum) != digest[7:]:
                raise ValueError("Model SHA-256 mos kelmadi; model faollashtirilmadi.")
            partial.replace(target)
            for meta, _ in parts:
                meta.unlink(missing_ok=True)
            print("Layer SHA-256: OK", flush=True)
        destination = root / "manifests" / "registry.ollama.ai" / "library" / name / tag
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(manifest_bytes)
        print("Mahalliy model tayyor: " + model, flush=True)


if __name__ == "__main__":
    import sys

    try:
        asyncio.run(download(sys.argv[1] if len(sys.argv) > 1 else "qwen3:4b-instruct"))
    except Exception as exc:
        print(str(exc) if isinstance(exc, (ValueError, RuntimeError)) else type(exc).__name__)
        raise SystemExit(1)
