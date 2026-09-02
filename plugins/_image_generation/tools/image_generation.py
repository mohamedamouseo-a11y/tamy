from __future__ import annotations

import asyncio
import base64
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request
import uuid

from helpers import files
from helpers.plugins import get_plugin_config
from helpers.security import safe_filename
from helpers.tool import Tool, Response


MAX_IMAGE_BYTES = 30 * 1024 * 1024
DEFAULT_OUTPUT_DIR = "usr/workdir/generated_images"


class ImageGenerationTool(Tool):
    async def execute(self, **kwargs):
        prompt = str(kwargs.get("prompt") or "").strip()
        if not prompt:
            return Response(message="Error: image prompt is required.", break_loop=False)

        config = get_plugin_config("_image_generation", agent=self.agent) or {}
        requested_provider = str(kwargs.get("provider") or config.get("provider") or "auto").strip().lower()
        timeout = _positive_int(config.get("timeout_seconds"), 120)
        size = str(kwargs.get("size") or "1024x1024").strip()
        aspect_ratio = str(kwargs.get("aspect_ratio") or "").strip()
        negative_prompt = str(kwargs.get("negative_prompt") or "").strip()

        providers = _provider_sequence(config, requested_provider)
        if not providers:
            return Response(
                message="Error: no image provider is configured. Add an API key for OpenAI, Stability AI, or an OpenAI-compatible image API.",
                break_loop=False,
            )

        failures: list[str] = []
        for provider in providers:
            try:
                self.log.update(progress=f"Generating image with {provider}...")
                image_bytes, extension = await asyncio.to_thread(
                    _generate_with_provider,
                    provider,
                    config,
                    prompt,
                    size,
                    aspect_ratio,
                    negative_prompt,
                    timeout,
                )
                if not image_bytes:
                    raise RuntimeError("provider returned an empty image")
                if len(image_bytes) > MAX_IMAGE_BYTES:
                    raise RuntimeError("generated image exceeded the 30 MB limit")

                relative_path, absolute_path = _output_path(
                    config,
                    kwargs.get("filename"),
                    extension,
                )
                absolute_path.parent.mkdir(parents=True, exist_ok=True)
                absolute_path.write_bytes(image_bytes)

                self.log.update(progress=f"Image saved to {relative_path}")
                return Response(
                    message=(
                        "Image generated successfully.\n"
                        f"Provider: {provider}\n"
                        f"File: {relative_path}\n"
                        "The image is available from Tamy Files."
                    ),
                    break_loop=False,
                )
            except Exception as exc:  # pylint: disable=broad-exception-caught
                failures.append(f"{provider}: {_safe_error(exc)}")
                self.log.update(progress=f"{provider} failed; trying the next configured provider...")

        return Response(
            message="Image generation failed with all configured providers:\n- " + "\n- ".join(failures),
            break_loop=False,
        )


def _provider_sequence(config: dict, requested: str) -> list[str]:
    supported = {"openai", "stability", "openai_compatible"}
    if requested and requested != "auto":
        return [requested] if requested in supported and _provider_available(config, requested) else []

    order = config.get("provider_order") or ["openai", "stability", "openai_compatible"]
    if isinstance(order, str):
        order = [item.strip() for item in order.split(",") if item.strip()]
    result = []
    for provider in order:
        name = str(provider).strip().lower()
        if name in supported and name not in result and _provider_available(config, name):
            result.append(name)
    return result


def _provider_available(config: dict, provider: str) -> bool:
    section = config.get(provider) or {}
    key = _secret(section)
    if not key:
        return False
    if provider == "openai_compatible":
        return bool(_value_or_env(section, "base_url", "base_url_env") and _value_or_env(section, "model", "model_env"))
    return True


def _secret(section: dict) -> str:
    env_name = str(section.get("api_key_env") or "").strip()
    return str(section.get("api_key") or (os.getenv(env_name) if env_name else "") or "").strip()


def _value_or_env(section: dict, value_key: str, env_key: str) -> str:
    env_name = str(section.get(env_key) or "").strip()
    return str((os.getenv(env_name) if env_name else "") or section.get(value_key) or "").strip()


def _generate_with_provider(
    provider: str,
    config: dict,
    prompt: str,
    size: str,
    aspect_ratio: str,
    negative_prompt: str,
    timeout: int,
) -> tuple[bytes, str]:
    if provider == "openai":
        section = config.get("openai") or {}
        return _generate_openai_style(section, prompt, size, timeout)
    if provider == "openai_compatible":
        section = config.get("openai_compatible") or {}
        section = dict(section)
        section["base_url"] = _value_or_env(section, "base_url", "base_url_env")
        section["model"] = _value_or_env(section, "model", "model_env")
        return _generate_openai_style(section, prompt, size, timeout)
    if provider == "stability":
        section = config.get("stability") or {}
        return _generate_stability(section, prompt, size, aspect_ratio, negative_prompt, timeout)
    raise RuntimeError(f"unsupported provider: {provider}")


def _generate_openai_style(section: dict, prompt: str, size: str, timeout: int) -> tuple[bytes, str]:
    api_key = _secret(section)
    base_url = str(section.get("base_url") or "https://api.openai.com/v1").rstrip("/")
    model = str(section.get("model") or "gpt-image-2").strip()
    if not api_key or not model:
        raise RuntimeError("API key or image model is missing")

    payload = {"model": model, "prompt": prompt, "n": 1}
    if size:
        payload["size"] = size

    body, _headers = _request(
        f"{base_url}/images/generations",
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        data=json.dumps(payload).encode("utf-8"),
        timeout=timeout,
    )
    try:
        response = json.loads(body.decode("utf-8"))
        item = (response.get("data") or [])[0]
    except (ValueError, IndexError, KeyError, TypeError) as exc:
        raise RuntimeError("image API returned an unexpected response") from exc

    encoded = item.get("b64_json") or item.get("b64")
    if encoded:
        try:
            return base64.b64decode(encoded), "png"
        except ValueError as exc:
            raise RuntimeError("image API returned invalid base64 data") from exc

    url = str(item.get("url") or "").strip()
    if url:
        image, headers = _request(url, method="GET", headers={}, data=None, timeout=timeout)
        return image, _extension_from_content_type(headers.get("content-type"))

    raise RuntimeError("image API response contained neither image data nor a URL")


def _generate_stability(
    section: dict,
    prompt: str,
    size: str,
    aspect_ratio: str,
    negative_prompt: str,
    timeout: int,
) -> tuple[bytes, str]:
    api_key = _secret(section)
    endpoint = str(section.get("endpoint") or "https://api.stability.ai/v2beta/stable-image/generate/core").strip()
    output_format = str(section.get("output_format") or "png").strip().lower()
    if output_format not in {"png", "jpeg", "webp"}:
        output_format = "png"
    if not api_key:
        raise RuntimeError("Stability API key is missing")

    ratio = aspect_ratio or _aspect_ratio_from_size(size)
    fields = {"prompt": prompt, "output_format": output_format}
    if ratio:
        fields["aspect_ratio"] = ratio
    if negative_prompt:
        fields["negative_prompt"] = negative_prompt

    multipart_body, content_type = _multipart(fields)
    image, headers = _request(
        endpoint,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "image/*",
            "Content-Type": content_type,
            "Stability-Client-ID": "Tamy",
        },
        data=multipart_body,
        timeout=timeout,
    )
    extension = _extension_from_content_type(headers.get("content-type"), output_format)
    return image, extension


def _multipart(fields: dict[str, str]) -> tuple[bytes, str]:
    boundary = f"----TamyBoundary{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}\r\n".encode())
    chunks.append(b'Content-Disposition: form-data; name="none"; filename=""\r\n')
    chunks.append(b"Content-Type: application/octet-stream\r\n\r\n\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _request(
    url: str,
    *,
    method: str,
    headers: dict[str, str],
    data: bytes | None,
    timeout: int,
) -> tuple[bytes, dict[str, str]]:
    request = urllib.request.Request(url=url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310 - URLs are admin-configured provider endpoints
            body = response.read(MAX_IMAGE_BYTES + 1)
            if len(body) > MAX_IMAGE_BYTES:
                raise RuntimeError("provider response exceeded the 30 MB limit")
            response_headers = {key.lower(): value for key, value in response.headers.items()}
            return body, response_headers
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            raw = exc.read(4096).decode("utf-8", errors="replace")
            if raw:
                try:
                    parsed = json.loads(raw)
                    detail = str(parsed.get("error") or parsed.get("errors") or parsed.get("message") or raw)
                except ValueError:
                    detail = raw
        except Exception:  # pylint: disable=broad-exception-caught
            detail = ""
        suffix = f": {detail[:500]}" if detail else ""
        raise RuntimeError(f"provider HTTP {exc.code}{suffix}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"provider connection error: {exc.reason}") from exc


def _output_path(config: dict, requested_filename, extension: str) -> tuple[str, Path]:
    output_dir = str(config.get("output_dir") or DEFAULT_OUTPUT_DIR).replace("\\", "/").strip("/")
    workdir_root = Path(files.get_abs_path("usr", "workdir")).resolve()
    absolute_dir = Path(files.get_abs_path(output_dir)).resolve()
    if not absolute_dir.is_relative_to(workdir_root):
        output_dir = DEFAULT_OUTPUT_DIR
        absolute_dir = Path(files.get_abs_path(output_dir)).resolve()

    extension = extension.lower().lstrip(".")
    if extension not in {"png", "jpg", "jpeg", "webp"}:
        extension = "png"

    raw_name = str(requested_filename or "").strip()
    if raw_name:
        name = safe_filename(Path(raw_name).name)
        stem = Path(name).stem or "tamy_image"
    else:
        stem = f"tamy_image_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    filename = f"{stem}.{extension}"

    relative_path = f"{output_dir}/{filename}"
    return relative_path, absolute_dir / filename


def _aspect_ratio_from_size(size: str) -> str:
    mapping = {
        "1024x1024": "1:1",
        "1536x1024": "3:2",
        "1024x1536": "2:3",
        "1792x1024": "16:9",
        "1024x1792": "9:16",
    }
    return mapping.get(size, "")


def _extension_from_content_type(content_type: str | None, fallback: str = "png") -> str:
    value = str(content_type or "").lower()
    if "jpeg" in value or "jpg" in value:
        return "jpg"
    if "webp" in value:
        return "webp"
    if "png" in value:
        return "png"
    return fallback


def _positive_int(value, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _safe_error(exc: Exception) -> str:
    text = str(exc).replace("\n", " ").strip()
    return text[:600] if text else exc.__class__.__name__
