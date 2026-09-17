# AI Shorts Factory

A Windows-first, low-spec-friendly image-to-animation Shorts factory. The app uses cloud APIs for heavy intelligence/image generation and keeps orchestration, image animation and FFmpeg rendering local.

## Current workflow

1. First launch asks for one working Gemini, Hugging Face and Tavily key.
2. Press `TEST & ADD`; a successful live key is automatically registered.
3. First launch then asks for reference Shorts. Upload one or more local videos. The reference profile is saved and reused on later runs.
4. Main UI provides a chat-style instruction box and a duration selector from 1 to 180 seconds.
5. Gemini creates an original silent scene plan from the user request plus saved reference style profile.
6. Hugging Face generates scene images.
7. FFmpeg creates lightweight Ken-Burns-style image animation and renders the vertical MP4.
8. Settings/API Manager can be reopened to add multiple keys per provider; keys are tried as a fallback pool.

## Important

- Reference videos are used for high-level production guidance only. The generator is instructed to create original stories and assets rather than copying protected content shot-for-shot.
- API keys are encrypted in `data/config.enc` and the local encryption key is stored in `data/secrets.key`. Do not commit either file.
- FFmpeg must be installed and available on PATH for reference frame extraction and rendering.
- The current base pipeline focuses on image generation + lightweight animation. Audio/ASMR/SFX/music provider adapters are designed to be added without changing the UI/API manager.

## Windows

Run `setup.bat` once, then `run.bat`.

Or:

```powershell
py -3 -m venv .venv
.venv\\Scripts\\python.exe -m pip install -r requirements.txt
.venv\\Scripts\\python.exe -m app.main
```

## Project layout

```text
app/        desktop UI, storage, providers, reference analyzer, pipeline
assets/     references and generated assets
projects/   per-short plans, images and clips
output/     final MP4 files
data/       encrypted local configuration and profiles
logs/       runtime logs
```
