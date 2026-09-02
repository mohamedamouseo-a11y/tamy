# Tamy Image Generation

Built-in Tamy plugin for text-to-image generation with automatic provider fallback.

## Providers

1. OpenAI Images API
   - Environment key: `OPENAI_API_KEY`
   - Default model: `gpt-image-2`

2. Stability AI Stable Image Core
   - Environment key: `STABILITY_API_KEY`

3. OpenAI-compatible image API
   - API key: `TAMY_IMAGE_API_KEY`
   - Base URL: `TAMY_IMAGE_API_BASE`
   - Model: `TAMY_IMAGE_MODEL`

The default provider is `auto`, which tries configured providers in the order above and automatically continues to the next provider when one fails.

## Usage

Ask Tamy normally, for example:

`Generate a premium perfume advertising image on a black and gold background.`

Tamy calls `image_generation` automatically and saves the result under:

`usr/workdir/generated_images/`

The image can then be opened from Tamy Files.

## Notes

- API keys should be supplied through environment variables or runtime plugin configuration, never committed to Git.
- This phase supports text-to-image generation only. Video generation is intentionally out of scope.
