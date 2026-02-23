"""
Image Generation Service - Stable Diffusion Integration
Nexira / Ultimate AI System v8.0
Created by Xeeker & Claude - February 2026

Gives Sygma the ability to generate images from text prompts.
Uses local Stable Diffusion v1.5 via diffusers.

Images are saved to data/images/generated/YYYY-MM-DD/
and logged to the activity system.

VRAM note: Ollama must unload llama before SD can run.
The service handles this automatically via the Ollama API.
"""

import os
import re
import json
import requests
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Dict


class ImageGenService:
    """
    Manages local Stable Diffusion image generation for Sygma.
    Handles VRAM coordination with Ollama automatically.
    """

    MODEL_ID = "runwayml/stable-diffusion-v1-5"

    def __init__(self, base_dir: str, config: Dict, ollama_url: str = "http://localhost:11434"):
        self.base_dir   = Path(base_dir)
        self.config     = config
        self.ollama_url = ollama_url
        self.pipe       = None  # Loaded on first use, then kept warm

        # Image output directory
        self.output_root = self.base_dir / "data" / "images" / "generated"
        self.output_root.mkdir(parents=True, exist_ok=True)

        print("✓ Image generation service initialised")

    def _today_dir(self) -> Path:
        """Return today's dated output directory, creating if needed."""
        today = datetime.now().strftime("%Y-%m-%d")
        d = self.output_root / today
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _slug(self, prompt: str, max_len: int = 40) -> str:
        """Turn a prompt into a safe filename slug."""
        slug = re.sub(r'[^a-z0-9 ]', '', prompt.lower())
        slug = re.sub(r'\s+', '_', slug.strip())
        return slug[:max_len]

    def _unload_ollama(self):
        """
        Ask Ollama to unload the current model from VRAM
        so Stable Diffusion has room to run.
        """
        try:
            model = self.config.get('ai', {}).get('model', 'llama3.1:8b')
            # Sending keep_alive=0 tells Ollama to immediately unload
            requests.post(
                f"{self.ollama_url}/api/generate",
                json={"model": model, "keep_alive": 0},
                timeout=10
            )
            print("  🔄 Ollama model unloaded from VRAM")
        except Exception as e:
            print(f"  ⚠️  Could not unload Ollama model: {e}")

    def _load_pipeline(self):
        """Load SD pipeline into VRAM. Unloads Ollama first."""
        if self.pipe is not None:
            return  # Already loaded

        print("  🎨 Loading Stable Diffusion pipeline...")
        self._unload_ollama()

        import torch
        from diffusers import StableDiffusionPipeline

        self.pipe = StableDiffusionPipeline.from_pretrained(
            self.MODEL_ID,
            torch_dtype=torch.float16,
            safety_checker=None,         # Disabled — Sygma is a trusted environment
            requires_safety_checker=False
        )
        self.pipe = self.pipe.to("cuda")
        self.pipe.enable_attention_slicing()  # Reduces VRAM usage
        print("  ✓ Stable Diffusion loaded on GPU")

    def unload_pipeline(self):
        """Unload SD from VRAM so Ollama can reload."""
        if self.pipe is None:
            return
        import torch
        del self.pipe
        self.pipe = None
        torch.cuda.empty_cache()
        print("  🔄 Stable Diffusion unloaded from VRAM")

    def generate(self, prompt: str, negative_prompt: str = "",
                 steps: int = 25, guidance: float = 7.5,
                 width: int = 512, height: int = 512) -> Tuple[bool, str, str]:
        """
        Generate an image from a prompt.

        Returns: (success, filepath, message)
        - filepath is relative to base_dir for portability
        - message describes what happened
        """
        try:
            self._load_pipeline()

            print(f"  🖼️  Generating: '{prompt[:60]}...' " if len(prompt) > 60 else f"  🖼️  Generating: '{prompt}'")

            import torch
            with torch.autocast("cuda"):
                result = self.pipe(
                    prompt,
                    negative_prompt=negative_prompt or "blurry, low quality, distorted, ugly, bad anatomy",
                    num_inference_steps=steps,
                    guidance_scale=guidance,
                    width=width,
                    height=height
                )

            image = result.images[0]

            # Save with timestamped filename
            timestamp = datetime.now().strftime("%H%M%S")
            slug      = self._slug(prompt)
            filename  = f"sygma_{timestamp}_{slug}.png"
            filepath  = self._today_dir() / filename
            image.save(str(filepath))

            # Also save metadata alongside the image
            meta = {
                "prompt":          prompt,
                "negative_prompt": negative_prompt,
                "steps":           steps,
                "guidance":        guidance,
                "width":           width,
                "height":          height,
                "generated_at":    datetime.now().isoformat(),
                "model":           self.MODEL_ID
            }
            meta_path = filepath.with_suffix('.json')
            with open(str(meta_path), 'w') as f:
                json.dump(meta, f, indent=2)

            rel_path = str(filepath.relative_to(self.base_dir))
            print(f"  ✓ Image saved: {rel_path}")

            # Unload SD after generation so Ollama can reload quickly
            self.unload_pipeline()

            return True, rel_path, f"Image generated and saved to {rel_path}"

        except Exception as e:
            self.unload_pipeline()  # Always clean up on error
            print(f"  ⚠️  Image generation failed: {e}")
            return False, "", str(e)

    def list_images(self, limit: int = 20) -> list:
        """Return recent generated images with metadata."""
        images = []
        for png in sorted(self.output_root.rglob("*.png"), reverse=True)[:limit]:
            meta_file = png.with_suffix('.json')
            meta = {}
            if meta_file.exists():
                try:
                    with open(str(meta_file)) as f:
                        meta = json.load(f)
                except Exception:
                    pass
            images.append({
                "filename":     png.name,
                "path":         str(png.relative_to(self.base_dir)),
                "date":         png.parent.name,
                "prompt":       meta.get("prompt", ""),
                "generated_at": meta.get("generated_at", ""),
            })
        return images
