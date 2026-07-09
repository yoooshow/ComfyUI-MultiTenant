import comfy.text_encoders.qwen3vl
from comfy import sd1_clip


PAD_TOKEN = 151643
CROP_MARKER = {"type": "lingbot_video_crop_start"}

PROMPT_TEMPLATE = (
    "<|im_start|>system\nGiven a user input that may include a text prompt alone, "
    "a text prompt with an image reference, or a text prompt with a video reference "
    "or a video reference alone, generate an \"Enhanced prompt\" that provides detailed "
    "visual descriptions suitable for video generation. Evaluate the level of detail "
    "in the user's input: if it is simple, enrich it by adding specifics about colors, "
    "shapes, sizes, textures, lighting, motion dynamics, camera movement, temporal "
    "progression, and spatial relationships to create vivid, concrete, and temporally "
    "coherent scenes to create vivid and concrete scenes. Please generate only the "
    "enhanced description for the prompt below and avoid including any additional "
    "commentary or evaluations:<|im_end|>\n<|im_start|>user\n{}<|im_end|>\n"
    "<|im_start|>assistant\n"
)
IMAGE_PROMPT_TEMPLATE = "<|vision_start|><|image_pad|><|vision_end|>"


def _marker_tuple(example=None):
    if example is not None and len(example) > 2:
        return (CROP_MARKER, 1.0, None)
    return (CROP_MARKER, 1.0)


class LingBotVideoTokenizer(comfy.text_encoders.qwen3vl.Qwen3VLTokenizer):
    def __init__(self, embedding_directory=None, tokenizer_data={}, model_type="qwen3vl_4b"):
        super().__init__(embedding_directory=embedding_directory, tokenizer_data=tokenizer_data, model_type=model_type)
        self._lingbot_crop_start = None

    def lingbot_crop_start(self):
        if self._lingbot_crop_start is not None:
            return self._lingbot_crop_start
        prefix = PROMPT_TEMPLATE.split("{}")[0]
        tokens = super().tokenize_with_weights(prefix, thinking=True)
        key = next(iter(tokens))
        count = 0
        for token in tokens[key][0]:
            token_id = token[0]
            if isinstance(token_id, int) and token_id == PAD_TOKEN:
                continue
            count += 1
        self._lingbot_crop_start = count
        return count

    def tokenize_with_weights(self, text, return_word_ids=False, images=[], prevent_empty_text=False, thinking=True, **kwargs):
        image = kwargs.get("image", None)
        if image is not None and len(images) == 0:
            images = [image[i:i + 1] for i in range(image.shape[0])]

        prompt_text = text
        if len(images) > 0 and not prompt_text.startswith("<|vision_start|>"):
            prompt_text = IMAGE_PROMPT_TEMPLATE + prompt_text

        tokens = super().tokenize_with_weights(
            prompt_text,
            return_word_ids=return_word_ids,
            llama_template=PROMPT_TEMPLATE,
            images=images,
            prevent_empty_text=prevent_empty_text,
            thinking=thinking,
            **kwargs,
        )
        crop_start = self.lingbot_crop_start()
        for key in tokens:
            for row in tokens[key]:
                example = row[0] if len(row) > 0 else None
                row.insert(crop_start, _marker_tuple(example))
        return tokens


class LingBotVideoClipModel(comfy.text_encoders.qwen3vl.Qwen3VLClipModel):
    def __init__(self, device="cpu", dtype=None, attention_mask=True, model_options={}, model_type="qwen3vl_4b"):
        super().__init__(
            device=device,
            layer="last",
            layer_idx=None,
            dtype=dtype,
            attention_mask=attention_mask,
            model_options=model_options,
            model_type=model_type,
        )
        self.return_attention_masks = False

    @staticmethod
    def _strip_crop_markers(tokens):
        clean_tokens = []
        crop_starts = []
        for row in tokens:
            clean_row = []
            crop_start = None
            for token in row:
                token_value = token[0] if isinstance(token, tuple) else token
                if isinstance(token_value, dict) and token_value.get("type") == CROP_MARKER["type"]:
                    crop_start = len(clean_row)
                    continue
                clean_row.append(token)
            clean_tokens.append(clean_row)
            crop_starts.append(crop_start)
        return clean_tokens, crop_starts

    def forward(self, tokens):
        clean_tokens, crop_starts = self._strip_crop_markers(tokens)
        out = super().forward(clean_tokens)
        crop_starts = [c for c in crop_starts if c is not None]
        if len(crop_starts) == 0:
            return out

        crop_start = min(crop_starts)
        z, pooled_output = out[:2]
        z = z[:, crop_start:]

        return z, pooled_output


class LingBotVideoTEModel(comfy.text_encoders.qwen3vl.Qwen3VLTEModel):
    def __init__(self, device="cpu", dtype=None, model_options={}, model_type="qwen3vl_4b"):
        clip_model = lambda **kw: LingBotVideoClipModel(**kw, model_type=model_type)
        sd1_clip.SD1ClipModel.__init__(
            self,
            device=device,
            dtype=dtype,
            name=model_type,
            clip_model=clip_model,
            model_options=model_options,
        )


def tokenizer(model_type="qwen3vl_4b"):
    class LingBotVideoTokenizer_(LingBotVideoTokenizer):
        def __init__(self, embedding_directory=None, tokenizer_data={}):
            super().__init__(embedding_directory=embedding_directory, tokenizer_data=tokenizer_data, model_type=model_type)
    return LingBotVideoTokenizer_


def te(dtype_llama=None, llama_quantization_metadata=None, model_type="qwen3vl_4b"):
    class LingBotVideoTEModel_(LingBotVideoTEModel):
        def __init__(self, device="cpu", dtype=None, model_options={}):
            if dtype_llama is not None:
                dtype = dtype_llama
            if llama_quantization_metadata is not None:
                model_options = model_options.copy()
                model_options["quantization_metadata"] = llama_quantization_metadata
            super().__init__(device=device, dtype=dtype, model_options=model_options, model_type=model_type)
    return LingBotVideoTEModel_
