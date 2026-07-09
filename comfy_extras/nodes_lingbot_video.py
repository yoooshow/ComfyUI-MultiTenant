import math
import nodes
import numpy as np
import torch
from PIL import Image

import comfy.latent_formats
import comfy.model_management
import comfy.utils
from comfy_api.latest import ComfyExtension, io
from typing_extensions import override


IMAGE_MIN_TOKEN_NUM = 4
IMAGE_MAX_TOKEN_NUM = 16384
MAX_RATIO = 200
SPATIAL_MERGE_SIZE = 2
VISION_PATCH_SIZE = 16


def _crop_image(image, width, height):
    image = image[:1].movedim(-1, 1)
    image = comfy.utils.common_upscale(image, width, height, "bilinear", "center")
    return image.movedim(1, -1)[:, :, :, :3]


def _round_by_factor(number, factor):
    return round(number / factor) * factor


def _ceil_by_factor(number, factor):
    return math.ceil(number / factor) * factor


def _floor_by_factor(number, factor):
    return math.floor(number / factor) * factor


def _smart_resize(height, width, factor, min_pixels=None, max_pixels=None):
    max_pixels = max_pixels if max_pixels is not None else IMAGE_MAX_TOKEN_NUM * factor ** 2
    min_pixels = min_pixels if min_pixels is not None else IMAGE_MIN_TOKEN_NUM * factor ** 2
    if max_pixels < min_pixels:
        raise ValueError("max_pixels must be greater than or equal to min_pixels.")
    if max(height, width) / min(height, width) > MAX_RATIO:
        raise ValueError(f"LingBotVideo image aspect ratio must be smaller than {MAX_RATIO}.")

    resized_height = max(factor, _round_by_factor(height, factor))
    resized_width = max(factor, _round_by_factor(width, factor))
    if resized_height * resized_width > max_pixels:
        beta = math.sqrt((height * width) / max_pixels)
        resized_height = _floor_by_factor(height / beta, factor)
        resized_width = _floor_by_factor(width / beta, factor)
    elif resized_height * resized_width < min_pixels:
        beta = math.sqrt(min_pixels / (height * width))
        resized_height = _ceil_by_factor(height * beta, factor)
        resized_width = _ceil_by_factor(width * beta, factor)
    return resized_height, resized_width


def _vlm_image(image):
    factor = VISION_PATCH_SIZE * SPATIAL_MERGE_SIZE
    height, width = image.shape[1:3]
    resized_height, resized_width = _smart_resize(height, width, factor)
    array = image[0].detach().cpu().clamp(0, 1).mul(255).byte().numpy()
    pil_image = Image.fromarray(array, mode="RGB").resize((resized_width, resized_height))
    array = np.asarray(pil_image).astype(np.float32) / 255.0
    return torch.from_numpy(array).unsqueeze(0)


class TextEncodeLingBotVideoI2V(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="TextEncodeLingBotVideoI2V",
            category="model/conditioning/lingbot_video",
            inputs=[
                io.Clip.Input("clip"),
                io.String.Input("prompt", multiline=True, dynamic_prompts=True),
                io.String.Input("negative_prompt", multiline=True, dynamic_prompts=True, default=""),
                io.Int.Input("width", default=480, min=16, max=nodes.MAX_RESOLUTION, step=16),
                io.Int.Input("height", default=480, min=16, max=nodes.MAX_RESOLUTION, step=16),
                io.Image.Input("image", optional=True),
            ],
            outputs=[
                io.Conditioning.Output(display_name="positive"),
                io.Conditioning.Output(display_name="negative"),
            ],
        )

    @classmethod
    def execute(cls, clip, prompt, negative_prompt, width, height, image=None) -> io.NodeOutput:
        if height % 16 != 0 or width % 16 != 0:
            raise ValueError(f"LingBotVideo width and height must be multiples of 16, got {width}x{height}.")
        if image is None:
            images = []
        else:
            image = _crop_image(image, width, height)
            images = [_vlm_image(image)]
        positive = clip.encode_from_tokens_scheduled(clip.tokenize(prompt, images=images))
        negative = clip.encode_from_tokens_scheduled(clip.tokenize(negative_prompt, images=images))
        return io.NodeOutput(positive, negative)


class LingBotImageToVideo(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="LingBotImageToVideo",
            category="model/conditioning/lingbot_video",
            inputs=[
                io.Conditioning.Input("positive"),
                io.Conditioning.Input("negative"),
                io.Vae.Input("vae"),
                io.Int.Input("width", default=480, min=16, max=nodes.MAX_RESOLUTION, step=16),
                io.Int.Input("height", default=480, min=16, max=nodes.MAX_RESOLUTION, step=16),
                io.Int.Input("length", default=81, min=1, max=nodes.MAX_RESOLUTION, step=4),
                io.Int.Input("batch_size", default=1, min=1, max=4096),
                io.Image.Input("start_image", optional=True),
            ],
            outputs=[
                io.Conditioning.Output(display_name="positive"),
                io.Conditioning.Output(display_name="negative"),
                io.Latent.Output(display_name="latent"),
            ],
        )

    @classmethod
    def execute(cls, positive, negative, vae, width, height, length, batch_size, start_image=None) -> io.NodeOutput:
        if length != 1 and (length - 1) % 4 != 0:
            raise ValueError(f"LingBotVideo length must be 1 or 4n+1, got {length}.")
        if height % 16 != 0 or width % 16 != 0:
            raise ValueError(f"LingBotVideo width and height must be multiples of 16, got {width}x{height}.")
        latent_frames = ((length - 1) // 4) + 1
        latent = torch.zeros(
            [batch_size, 16, latent_frames, height // 8, width // 8],
            device=comfy.model_management.intermediate_device(),
        )
        out_latent = {"samples": latent}

        if start_image is not None:
            start_image = _crop_image(start_image, width, height)
            cond_latent = comfy.latent_formats.LingBotVideo().process_in(vae.encode(start_image))
            cond_latent = comfy.utils.resize_to_batch_size(cond_latent, batch_size)
            cond_t = min(cond_latent.shape[2], latent.shape[2])
            latent[:, :, :cond_t] = cond_latent[:, :, :cond_t].to(device=latent.device, dtype=latent.dtype)
            noise_mask = torch.ones(
                (batch_size, 1, latent.shape[2], latent.shape[3], latent.shape[4]),
                device=latent.device,
                dtype=latent.dtype,
            )
            noise_mask[:, :, :cond_t] = 0.0
            out_latent["noise_mask"] = noise_mask

        return io.NodeOutput(positive, negative, out_latent)


class LingBotVideoExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [
            TextEncodeLingBotVideoI2V,
            LingBotImageToVideo,
        ]


async def comfy_entrypoint() -> LingBotVideoExtension:
    return LingBotVideoExtension()
