### image_generation
Generate an image from a text prompt and save it into Tamy Files.

Use this tool whenever the user asks to create, generate, design, render, visualize, or make a new image, artwork, advertising visual, social post visual, product concept, illustration, logo concept, or other text-to-image output.

Minimal args:
- `prompt`: required image description
- `provider`: optional `auto`, `openai`, `stability`, or `openai_compatible`; default `auto`
- `size`: optional, default `1024x1024`
- `aspect_ratio`: optional, mainly for Stability AI, such as `1:1`, `16:9`, or `9:16`
- `negative_prompt`: optional
- `filename`: optional output filename without trusting user path components

Provider behavior:
- `auto` tries configured providers in order and falls back automatically if one fails.
- Generated files are saved under `usr/workdir/generated_images` and can be opened from Tamy Files.

Do not expose API keys, tokens, or provider secrets in messages or logs. If all providers fail, report only the provider names and concise failure reasons.
