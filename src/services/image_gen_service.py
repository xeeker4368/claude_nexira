"""
Image Generation Service - Stable Diffusion Integration
Nexira / Nexira v12
Created by Xeeker & Claude - February 2026

Capabilities:
- Text-to-image generation (txt2img)
- Style transfer on existing images (img2img)
- CLIP-based image analysis for Sygma's creativity experiment

Output directories:
  data/images/generated/YYYY-MM-DD/   - txt2img outputs
  data/images/styled/YYYY-MM-DD/      - style transfer outputs
"""

import os
import re
import json
import requests
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Dict, List


class ImageGenService:

    MODEL_ID = "runwayml/stable-diffusion-v1-5"

    def __init__(self, base_dir: str, config: Dict,
                 ollama_url: str = "http://localhost:11434"):
        self.base_dir    = Path(base_dir)
        self.config      = config
        self.ollama_url  = ollama_url
        self.pipe        = None   # txt2img
        self.img2img     = None   # img2img
        self.clip_model  = None
        self.clip_proc   = None

        self.output_root = self.base_dir / "data" / "images" / "generated"
        self.styled_root = self.base_dir / "data" / "images" / "styled"
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.styled_root.mkdir(parents=True, exist_ok=True)

        print("✓ Image generation service initialised")

    # ── Utilities ────────────────────────────────────────────────────

    def _dated_dir(self, root: Path) -> Path:
        d = root / datetime.now().strftime("%Y-%m-%d")
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _slug(self, text: str, max_len: int = 40) -> str:
        s = re.sub(r'[^a-z0-9 ]', '', text.lower())
        s = re.sub(r'\s+', '_', s.strip())
        return s[:max_len]

    def _truncate_prompt(self, prompt: str) -> str:
        """Keep prompts under SD's 77-token limit."""
        words = prompt.split()
        if len(words) > 55:
            prompt = ' '.join(words[:55])
        return prompt

    def _sanitize_prompt(self, prompt: str) -> tuple:
        """
        Detect and clean prompts that contain instruction text rather than
        visual descriptions. Returns (sanitized_prompt, was_dirty).

        Red flags: meta-language, instruction fragments, example text.
        If the prompt is unsalvageable, returns a safe fallback.
        """
        original = prompt

        # Strip common instruction fragments
        bad_phrases = [
            r'for a\b', r'this is\b', r'example of\b', r'description of\b',
            r'prompt in\b', r'in our conversation\b', r'10.?30 words\b',
            r'words works best\b', r'vivid description\b', r'the image\b',
            r'using the\b', r'trigger phrase\b', r'style transfer\b.*?\|',
            r'IMAGE_GEN_NOW[:\s]*', r'STYLE_TRANSFER_NOW[:\s]*',
            r'ANALYZE_IMAGE_NOW[:\s]*',
        ]
        cleaned = prompt
        for pattern in bad_phrases:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

        # Clean up whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        # Check if what's left is still meaningful
        # A valid visual prompt should be at least 4 words and not mostly numbers
        words = cleaned.split()
        word_count = len(words)
        digit_ratio = sum(1 for w in words if w.isdigit()) / max(word_count, 1)

        if word_count < 4 or digit_ratio > 0.3:
            # Prompt is unsalvageable — use a safe artistic fallback
            fallback = "abstract digital art, swirling colors, luminous, ethereal"
            print(f"  ⚠️  Prompt sanitized to fallback. Original: '{original[:60]}'")
            return fallback, True

        was_dirty = cleaned.lower() != original.lower()
        if was_dirty:
            print(f"  ⚠️  Prompt sanitized: '{original[:40]}' → '{cleaned[:40]}'")

        return cleaned, was_dirty

    def _save_meta(self, filepath: Path, meta: Dict):
        with open(str(filepath.with_suffix('.json')), 'w') as f:
            json.dump(meta, f, indent=2)

    # ── VRAM management ──────────────────────────────────────────────

    def _unload_ollama(self):
        try:
            model = self.config.get('ai', {}).get('model', 'llama3.1:8b')
            requests.post(f"{self.ollama_url}/api/generate",
                          json={"model": model, "keep_alive": 0}, timeout=10)
            print("  🔄 Ollama unloaded from VRAM")
        except Exception as e:
            print(f"  ⚠️  Could not unload Ollama: {e}")

    def _load_txt2img(self):
        if self.pipe is not None:
            return
        print("  🎨 Loading SD txt2img pipeline...")
        self._unload_ollama()
        import torch
        from diffusers import StableDiffusionPipeline
        self.pipe = StableDiffusionPipeline.from_pretrained(
            self.MODEL_ID, torch_dtype=torch.float16,
            safety_checker=None, requires_safety_checker=False
        ).to("cuda")
        self.pipe.enable_attention_slicing()
        print("  ✓ txt2img ready")

    def _load_img2img(self):
        if self.img2img is not None:
            return
        print("  🎨 Loading SD img2img pipeline...")
        self._unload_ollama()
        import torch
        from diffusers import StableDiffusionImg2ImgPipeline
        self.img2img = StableDiffusionImg2ImgPipeline.from_pretrained(
            self.MODEL_ID, torch_dtype=torch.float16,
            safety_checker=None, requires_safety_checker=False
        ).to("cuda")
        self.img2img.enable_attention_slicing()
        print("  ✓ img2img ready")

    def _load_clip(self):
        if self.clip_model is not None:
            return
        print("  🔍 Loading CLIP for image analysis...")
        from transformers import CLIPProcessor, CLIPModel
        self.clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
        self.clip_proc  = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
        print("  ✓ CLIP ready")

    def unload_all(self):
        """Unload SD pipelines from VRAM."""
        import torch, gc

        # Delete pipeline objects to release VRAM
        for attr in ('pipe', 'img2img', 'clip_model'):
            obj = getattr(self, attr, None)
            if obj is not None:
                del obj
                setattr(self, attr, None)

        # Aggressive cleanup — multiple passes
        gc.collect()
        torch.cuda.empty_cache()
        gc.collect()
        torch.cuda.empty_cache()

        # Log actual VRAM state
        try:
            free_mb = torch.cuda.mem_get_info()[0] / (1024**2)
            total_mb = torch.cuda.mem_get_info()[1] / (1024**2)
            print(f"  🔄 Image pipelines unloaded — VRAM: {free_mb:.0f}MB free / {total_mb:.0f}MB total")
        except Exception:
            print("  🔄 Image pipelines unloaded from VRAM")

        # Reload Ollama into VRAM so next chat doesn't fail
        self._reload_ollama()

    def _reload_ollama(self):
        """Force Ollama to fully unload and reload the model for a clean CUDA state."""
        try:
            import time
            model = self.config.get('ai', {}).get('model', 'llama3.1:8b')

            # Step 1: Tell Ollama to completely unload the model from memory
            print("  🔄 Forcing Ollama model unload...")
            try:
                requests.post(
                    f"{self.ollama_url}/api/generate",
                    json={"model": model, "keep_alive": 0},
                    timeout=15
                )
            except Exception:
                pass

            # Step 2: Wait for CUDA state to fully clear
            time.sleep(10)

            # Step 3: Force a fresh load by generating a single token
            print(f"  🔄 Reloading {model} into VRAM...")
            resp = requests.post(
                f"{self.ollama_url}/api/generate",
                json={"model": model, "prompt": "hello", "keep_alive": "10m",
                      "options": {"num_predict": 1}},
                timeout=120
            )
            if resp.status_code == 200:
                print(f"  ✓ Ollama ({model}) reloaded into VRAM")
            else:
                print(f"  ⚠️  Ollama reload returned status {resp.status_code}")
                print(f"       Response: {resp.text[:200]}")
        except Exception as e:
            print(f"  ⚠️  Ollama reload failed: {e}")

    # ── Text-to-image ────────────────────────────────────────────────

    def generate(self, prompt: str, negative_prompt: str = "",
                 steps: int = 25, guidance: float = 7.5,
                 width: int = 512, height: int = 512) -> Tuple[bool, str, str]:
        """Generate image from text. Returns (success, rel_path, message)."""
        try:
            self._load_txt2img()
            prompt, was_dirty = self._sanitize_prompt(prompt)
            prompt = self._truncate_prompt(prompt)
            print(f"  🖼️  Generating: '{prompt[:60]}{'...' if len(prompt)>60 else ''}'")

            import torch
            with torch.autocast("cuda"):
                result = self.pipe(
                    prompt,
                    negative_prompt=negative_prompt or
                        "blurry, low quality, distorted, ugly, bad anatomy",
                    num_inference_steps=steps,
                    guidance_scale=guidance,
                    width=width, height=height
                )

            image    = result.images[0]
            ts       = datetime.now().strftime("%H%M%S")
            filename = f"sygma_{ts}_{self._slug(prompt)}.png"
            filepath = self._dated_dir(self.output_root) / filename
            image.save(str(filepath))
            self._save_meta(filepath, {
                "type": "txt2img", "prompt": prompt,
                "negative_prompt": negative_prompt, "steps": steps,
                "guidance": guidance, "width": width, "height": height,
                "generated_at": datetime.now().isoformat(), "model": self.MODEL_ID
            })

            rel = str(filepath.relative_to(self.base_dir))
            print(f"  ✓ Saved: {rel}")
            self.unload_all()
            return True, rel, f"Image saved to {rel}"

        except Exception as e:
            self.unload_all()
            print(f"  ⚠️  Generation failed: {e}")
            return False, "", str(e)

    # ── Style transfer ────────────────────────────────────────────────

    def style_transfer(self, source_path: str, style_prompt: str,
                       strength: float = 0.6, steps: int = 30,
                       guidance: float = 7.5) -> Tuple[bool, str, str]:
        """
        Apply a style to an existing image.

        source_path : relative path to source image from base_dir
        style_prompt: text description of desired style
        strength    : 0.0 = keep original, 1.0 = fully transform
                      0.4-0.7 gives best novelty/constraint balance
        """
        try:
            from PIL import Image as PILImage
            self._load_img2img()

            source_full = self.base_dir / source_path
            if not source_full.exists():
                return False, "", f"Source image not found: {source_path}"

            source_img = PILImage.open(str(source_full)).convert("RGB").resize((512, 512))
            style_prompt, was_dirty = self._sanitize_prompt(style_prompt)
            style_prompt = self._truncate_prompt(style_prompt)

            print(f"  🎨 Style transfer: '{style_prompt[:50]}' strength={strength}")

            import torch
            with torch.autocast("cuda"):
                result = self.img2img(
                    prompt=style_prompt,
                    image=source_img,
                    strength=strength,
                    num_inference_steps=steps,
                    guidance_scale=guidance,
                    negative_prompt="blurry, low quality, distorted"
                )

            image    = result.images[0]
            ts       = datetime.now().strftime("%H%M%S")
            src_stem = Path(source_path).stem[:20]
            filename = f"styled_{ts}_{src_stem}_{self._slug(style_prompt, 20)}.png"
            filepath = self._dated_dir(self.styled_root) / filename
            image.save(str(filepath))
            self._save_meta(filepath, {
                "type": "img2img", "source": source_path,
                "style_prompt": style_prompt, "strength": strength,
                "steps": steps, "guidance": guidance,
                "generated_at": datetime.now().isoformat(), "model": self.MODEL_ID
            })

            rel = str(filepath.relative_to(self.base_dir))
            print(f"  ✓ Styled image saved: {rel}")
            self.unload_all()
            return True, rel, f"Styled image saved to {rel}"

        except Exception as e:
            self.unload_all()
            print(f"  ⚠️  Style transfer failed: {e}")
            return False, "", str(e)

    # ── CLIP analysis ─────────────────────────────────────────────────

    # Default concept vocabulary for Sygma's creativity experiment
    DEFAULT_CONCEPTS = [
        "abstract art", "realistic landscape", "digital art",
        "emotional and expressive", "calm and serene",
        "chaotic and complex", "minimalist", "vibrant and colorful",
        "dark and moody", "nature", "technology and data",
        "geometric patterns", "organic forms", "dreamlike",
        "structured and ordered", "novel and surprising",
        "familiar and conventional"
    ]

    def describe(self, image_path: str,
                 prompt: str = "Describe this image in detail. What do you see? Include objects, colors, mood, composition, and any text visible.",
                 vision_model: str = None) -> Dict:
        """
        Use a vision-capable Ollama model (llava, moondream, etc.) to
        describe what is actually IN an image in natural language.

        This is true image recognition — not CLIP concept scoring.
        Returns dict with description, model used, and image_path.
        """
        try:
            import base64
            import requests as req

            full_path = self.base_dir / image_path
            if not full_path.exists():
                # Try absolute path
                full_path = Path(image_path)
            if not full_path.exists():
                return {"error": f"Image not found: {image_path}"}

            # Encode image as base64
            with open(str(full_path), "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode("utf-8")

            # Determine vision model — prefer config, then auto-detect available
            model = vision_model or self.config.get('ai', {}).get('vision_model', None)
            if not model:
                model = self._detect_vision_model()
            if not model:
                return {"error": "No vision-capable model found. Run: ollama pull llava"}

            # Call Ollama vision API
            payload = {
                "model": model,
                "prompt": prompt,
                "images": [image_b64],
                "stream": False,
                "options": {
                    "num_ctx": self.config.get('hardware', {}).get('context_window', 4096),
                    "num_thread": self.config.get('hardware', {}).get('num_threads', 4),
                }
            }

            # Add GPU option if enabled
            if self.config.get('hardware', {}).get('gpu_enabled', True):
                payload["options"]["num_gpu"] = 999

            response = req.post(
                f"{self.ollama_url}/api/generate",
                json=payload,
                timeout=120
            )
            response.raise_for_status()
            data = response.json()
            description = data.get("response", "").strip()

            # Strip think blocks if using qwen-vl or similar
            import re
            description = re.sub(r'<think>.*?</think>', '', description, flags=re.DOTALL).strip()

            if not description:
                return {"error": "Vision model returned empty response"}

            print(f"  👁️  Vision description ({model}): {description[:80]}...")

            return {
                "description": description,
                "model": model,
                "image_path": image_path
            }

        except Exception as e:
            print(f"  ⚠️  Vision description failed: {e}")
            return {"error": str(e)}

    def _detect_vision_model(self) -> Optional[str]:
        """
        Check which vision-capable models are available in Ollama.
        Returns the first match, or None if none found.
        """
        try:
            import requests as req
            resp = req.get(f"{self.ollama_url}/api/tags", timeout=5)
            models = [m["name"] for m in resp.json().get("models", [])]
            # Priority order: best vision models first
            for preferred in ["llava", "llava:latest", "llava:7b", "llava:13b",
                               "moondream", "moondream:latest",
                               "llava-llama3", "llava-phi3",
                               "minicpm-v", "qwen2-vl", "qwen2.5vl"]:
                for m in models:
                    if m.startswith(preferred):
                        return m
            return None
        except Exception:
            return None

    def analyze(self, image_path: str,
                concepts: List[str] = None) -> Dict:
        """
        Use CLIP to analyze an image against a vocabulary of concepts.

        Returns dict with scores, top concept, and a plain-English description
        suitable for Sygma to read and include in experiment notes.
        """
        try:
            from PIL import Image as PILImage
            import torch

            self._load_clip()

            full_path = self.base_dir / image_path
            if not full_path.exists():
                return {"error": f"Image not found: {image_path}"}

            image    = PILImage.open(str(full_path)).convert("RGB")
            concepts = concepts or self.DEFAULT_CONCEPTS

            inputs = self.clip_proc(
                text=concepts, images=image,
                return_tensors="pt", padding=True
            )
            with torch.no_grad():
                outputs = self.clip_model(**inputs)
                probs   = outputs.logits_per_image[0].softmax(dim=0).tolist()

            scores     = {c: round(p, 4) for c, p in zip(concepts, probs)}
            top_3      = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
            description = (
                f"This image most strongly evokes: "
                f"{top_3[0][0]} ({top_3[0][1]:.1%}), "
                f"{top_3[1][0]} ({top_3[1][1]:.1%}), "
                f"and {top_3[2][0]} ({top_3[2][1]:.1%})."
            )

            # Novelty score: how much does this image lean toward novel/surprising
            # vs familiar/conventional? Higher = more novel.
            novel_score = scores.get("novel and surprising", 0)
            conv_score  = scores.get("familiar and conventional", 0)
            novelty_ratio = novel_score / (novel_score + conv_score + 1e-9)

            print(f"  🔍 {description}")

            return {
                "scores":        scores,
                "top_concept":   top_3[0][0],
                "top_3":         top_3,
                "description":   description,
                "novelty_ratio": round(novelty_ratio, 4),
                "image_path":    image_path
            }

        except Exception as e:
            print(f"  ⚠️  Analysis failed: {e}")
            return {"error": str(e)}

    # ── Image listing ─────────────────────────────────────────────────

    def list_images(self, limit: int = 20,
                    include_styled: bool = True) -> List[Dict]:
        """Return recent images with metadata."""
        all_pngs = list(self.output_root.rglob("*.png"))
        if include_styled:
            all_pngs += list(self.styled_root.rglob("*.png"))

        images = []
        for png in sorted(all_pngs, reverse=True)[:limit]:
            meta = {}
            mf   = png.with_suffix('.json')
            if mf.exists():
                try:
                    meta = json.load(open(str(mf)))
                except Exception:
                    pass
            images.append({
                "filename":     png.name,
                "path":         str(png.relative_to(self.base_dir)),
                "date":         png.parent.name,
                "type":         meta.get("type", "txt2img"),
                "prompt":       meta.get("prompt") or meta.get("style_prompt", ""),
                "generated_at": meta.get("generated_at", ""),
            })
        return images
