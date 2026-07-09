import math
from typing import Optional, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F

from comfy.ldm.flux.math import apply_rope1, rope
from comfy.ldm.flux.layers import timestep_embedding
from comfy.ldm.modules.attention import optimized_attention


class LingBotVideoRMSNorm(nn.Module):
    def __init__(self, dim: int, eps: float = 1e-6, device=None, dtype=None, operations=None):
        super().__init__()
        self.weight = nn.Parameter(torch.empty(dim, device=device, dtype=dtype))
        self.variance_epsilon = eps

    def forward(self, hidden_states: torch.Tensor) -> torch.Tensor:
        variance = hidden_states.pow(2).mean(-1, keepdim=True)
        hidden_states = hidden_states * torch.rsqrt(variance + self.variance_epsilon)
        return self.weight * hidden_states


class LingBotVideoRotaryEmbedding(nn.Module):
    def __init__(self, axes_dims: Tuple[int, ...], axes_lens: Tuple[int, ...], theta: float):
        super().__init__()
        self.axes_dims = tuple(axes_dims)
        self.theta = theta

    def forward(self, position_ids: torch.Tensor) -> torch.Tensor:
        return torch.cat(
            [rope(position_ids[None, :, i], self.axes_dims[i], self.theta) for i in range(len(self.axes_dims))],
            dim=-3,
        ).squeeze(0)


def make_joint_position_ids(
    text_len: int, grid_t: int, grid_h: int, grid_w: int, device: torch.device, padded_text_len: Optional[int] = None
) -> torch.Tensor:
    """3D positions in [video; text] order. Text t-axis is 1..text_len; video t-axis starts at text_len+1.

    Matches patchify_and_embed: cap start (1,0,0); vision start (cap_len+1,0,0);
    freqs ordered with x first and cap second (same order as cat_interleave).
    """
    tt = torch.arange(grid_t, device=device, dtype=torch.int32) + (text_len + 1)
    hh = torch.arange(grid_h, device=device, dtype=torch.int32)
    ww = torch.arange(grid_w, device=device, dtype=torch.int32)
    grid = torch.stack(torch.meshgrid(tt, hh, ww, indexing="ij"), dim=-1).flatten(0, 2)
    if padded_text_len is None:
        padded_text_len = text_len
    text_t = torch.arange(padded_text_len, device=device, dtype=torch.int32) + 1
    text_pos = torch.stack(
        [text_t, torch.zeros_like(text_t), torch.zeros_like(text_t)], dim=-1
    )
    return torch.cat([grid, text_pos], dim=0)  # (Nx + L, 3)


class LingBotVideoTimestepEmbedding(nn.Module):
    def __init__(self, in_channels, time_embed_dim, bias=True, device=None, dtype=None, operations=None):
        super().__init__()
        self.linear_1 = operations.Linear(in_channels, time_embed_dim, bias=bias, device=device, dtype=dtype)
        self.act = nn.SiLU()
        self.linear_2 = operations.Linear(time_embed_dim, time_embed_dim, bias=bias, device=device, dtype=dtype)

    def forward(self, sample):
        return self.linear_2(self.act(self.linear_1(sample)))


class LingBotVideoTextEmbedder(nn.Module):
    """Matches CondProjection: RMSNorm(text_dim, eps=1e-6 fixed) -> Linear-SiLU-Linear."""

    def __init__(self, text_dim: int, hidden_size: int, device=None, dtype=None, operations=None):
        super().__init__()
        self.norm = LingBotVideoRMSNorm(text_dim, eps=1e-6, device=device, dtype=dtype, operations=operations)
        self.linear_1 = operations.Linear(text_dim, hidden_size, bias=True, device=device, dtype=dtype)
        self.linear_2 = operations.Linear(hidden_size, hidden_size, bias=True, device=device, dtype=dtype)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.norm(x)
        return self.linear_2(F.silu(self.linear_1(x)))


class LingBotVideoAttention(nn.Module):
    def __init__(self, hidden_size, num_heads, norm_eps, qkv_bias, out_bias, device=None, dtype=None, operations=None):
        super().__init__()
        self.num_heads = num_heads
        self.head_dim = hidden_size // num_heads
        self.to_q = operations.Linear(hidden_size, hidden_size, bias=qkv_bias, device=device, dtype=dtype)
        self.to_k = operations.Linear(hidden_size, hidden_size, bias=qkv_bias, device=device, dtype=dtype)
        self.to_v = operations.Linear(hidden_size, hidden_size, bias=qkv_bias, device=device, dtype=dtype)
        self.norm_q = LingBotVideoRMSNorm(self.head_dim, norm_eps, device=device, dtype=dtype, operations=operations)
        self.norm_k = LingBotVideoRMSNorm(self.head_dim, norm_eps, device=device, dtype=dtype, operations=operations)
        self.to_out = operations.Linear(hidden_size, hidden_size, bias=out_bias, device=device, dtype=dtype)

    def forward(
        self,
        x,
        rotary_emb,
        attention_mask=None,
        transformer_options={},
    ):
        q = self.to_q(x).unflatten(2, (self.num_heads, self.head_dim))
        k = self.to_k(x).unflatten(2, (self.num_heads, self.head_dim))
        v = self.to_v(x).unflatten(2, (self.num_heads, self.head_dim))
        q = apply_rope1(self.norm_q(q), rotary_emb)
        k = apply_rope1(self.norm_k(k), rotary_emb)
        out = optimized_attention(
            q.transpose(1, 2),
            k.transpose(1, 2),
            v.transpose(1, 2),
            heads=self.num_heads,
            mask=attention_mask,
            skip_reshape=True,
            transformer_options=transformer_options,
        )
        return self.to_out(out)


class LingBotVideoMLP(nn.Module):
    def __init__(self, hidden_size, intermediate_size, device=None, dtype=None, operations=None):
        super().__init__()
        self.gate_proj = operations.Linear(hidden_size, intermediate_size, bias=False, device=device, dtype=dtype)
        self.up_proj = operations.Linear(hidden_size, intermediate_size, bias=False, device=device, dtype=dtype)
        self.down_proj = operations.Linear(intermediate_size, hidden_size, bias=False, device=device, dtype=dtype)

    def forward(self, x):
        return self.down_proj(F.silu(self.gate_proj(x)) * self.up_proj(x))


class LingBotVideoRouter(nn.Module):
    """Matches the TokenChoiceTopKRouter inference path (no capacity/jitter/load stats).

    The asymmetry must be preserved: selection uses the bias-added score, while gating
    weights gather the bias-free score.
    """

    def __init__(self, hidden_size, num_experts, top_k, score_func, norm_topk_prob,
                 n_group, topk_group, route_scale, device=None, dtype=None, operations=None):
        super().__init__()
        self.num_experts = num_experts
        self.top_k = top_k
        self.score_func = score_func
        self.norm_topk_prob = norm_topk_prob
        self.n_group = n_group
        self.topk_group = topk_group
        self.route_scale = route_scale
        self.weight = nn.Parameter(torch.empty(num_experts, hidden_size, device=device, dtype=dtype))
        self.register_buffer("e_score_correction_bias", torch.zeros(num_experts, device=device, dtype=dtype), persistent=True)

    def _group_limited_topk(self, scores_for_choice):
        seq_len = scores_for_choice.shape[0]
        experts_per_group = self.num_experts // self.n_group
        grouped = scores_for_choice.view(seq_len, self.n_group, experts_per_group)
        group_scores = grouped.topk(2, dim=-1)[0].sum(dim=-1)
        group_idx = torch.topk(group_scores, k=self.topk_group, dim=-1, sorted=False)[1]
        group_mask = torch.zeros_like(group_scores)
        group_mask.scatter_(1, group_idx, 1)
        score_mask = (
            group_mask.unsqueeze(-1)
            .expand(seq_len, self.n_group, experts_per_group)
            .reshape(seq_len, -1)
        )
        masked = scores_for_choice.masked_fill(~score_mask.bool(), float("-inf"))
        return torch.topk(masked, k=self.top_k, dim=-1, sorted=False)[1]

    def forward(self, tokens: torch.Tensor):
        logits = F.linear(tokens, self.weight)
        if self.score_func == "softmax":
            scores = F.softmax(logits, dim=-1)
        else:
            scores = logits.sigmoid()
        scores_for_choice = scores + self.e_score_correction_bias.unsqueeze(0)
        if self.n_group is not None and self.n_group > 1:
            top_indices = self._group_limited_topk(scores_for_choice)
        else:
            top_indices = torch.topk(scores_for_choice, k=self.top_k, dim=-1, sorted=False)[1]
        top_scores = scores.gather(1, top_indices)
        if self.top_k > 1 and self.norm_topk_prob:
            top_scores = top_scores / (top_scores.sum(dim=-1, keepdim=True) + 1e-20)
        top_scores = top_scores * self.route_scale
        return top_indices, top_scores.to(tokens.dtype), logits, scores, scores_for_choice


class LingBotVideoGroupedExperts(nn.Module):
    """Weight layout matches GroupedExperts: w1 [E,I,H], w2 [E,H,I], w3 [E,I,H]. Eager per-expert compute."""

    def __init__(self, num_experts, hidden_size, intermediate_size, device=None, dtype=None):
        super().__init__()
        self.num_experts = num_experts
        self.w1 = nn.Parameter(torch.empty(num_experts, intermediate_size, hidden_size, device=device, dtype=dtype))
        self.w2 = nn.Parameter(torch.empty(num_experts, hidden_size, intermediate_size, device=device, dtype=dtype))
        self.w3 = nn.Parameter(torch.empty(num_experts, intermediate_size, hidden_size, device=device, dtype=dtype))


class LingBotVideoSparseMoeBlock(nn.Module):
    def __init__(self, hidden_size, intermediate_size, num_experts, top_k,
                 moe_intermediate_size, score_func, norm_topk_prob, n_group, topk_group,
                 routed_scaling_factor, n_shared_experts, device=None, dtype=None, operations=None):
        super().__init__()
        self.hidden_size = hidden_size
        self.num_experts = num_experts
        self.router = LingBotVideoRouter(
            hidden_size, num_experts, top_k, score_func, norm_topk_prob,
            n_group, topk_group, routed_scaling_factor, device=device, dtype=dtype, operations=operations,
        )
        self.experts = LingBotVideoGroupedExperts(num_experts, hidden_size, moe_intermediate_size, device=device, dtype=dtype)
        self.shared_experts = None
        if n_shared_experts is not None and n_shared_experts > 0:
            self.shared_experts = LingBotVideoMLP(
                hidden_size, moe_intermediate_size * n_shared_experts, device=device, dtype=dtype, operations=operations
            )

    def _run_expert(self, expert_idx: int, tokens: torch.Tensor) -> torch.Tensor:
        h = F.silu(tokens @ self.experts.w1[expert_idx].transpose(-2, -1))
        h = h * (tokens @ self.experts.w3[expert_idx].transpose(-2, -1))
        return h @ self.experts.w2[expert_idx].transpose(-2, -1)

    def _run_selected_experts(
        self,
        tokens: torch.Tensor,
        top_scores: torch.Tensor,
        top_indices: torch.Tensor,
    ) -> torch.Tensor:
        out = tokens.new_zeros(tokens.shape)
        for expert_idx in range(self.num_experts):
            selected = top_indices == expert_idx
            if not bool(selected.any()):
                continue
            token_indices, choice_indices = torch.where(selected)
            expert_tokens = tokens[token_indices]
            expert_output = self._run_expert(expert_idx, expert_tokens)
            expert_output = expert_output * top_scores[token_indices, choice_indices].unsqueeze(-1)
            out.index_add_(0, token_indices, expert_output)
        return out

    def forward(self, hidden_states: torch.Tensor, padding_mask: Optional[torch.Tensor] = None):
        # hidden_states: (B, S, H); padding_mask: (B*S,) with 1=valid (only needed when B>1)
        B = hidden_states.shape[0]
        tokens = hidden_states.view(-1, self.hidden_size)
        top_indices, top_scores, logits, scores, scores_for_choice = self.router(tokens)
        del logits, scores, scores_for_choice
        if padding_mask is not None:
            pm = padding_mask.unsqueeze(-1).to(top_scores.dtype)
            top_scores = top_scores * pm
            top_scores = top_scores / (top_scores.sum(dim=-1, keepdim=True) + 1e-9)
            top_scores = top_scores * self.router.route_scale

        out = self._run_selected_experts(tokens, top_scores, top_indices)

        out = out.view(B, -1, self.hidden_size)
        if self.shared_experts is not None:
            shared_output = self.shared_experts(hidden_states)
            out = out + shared_output
        return out


class LingBotVideoBlock(nn.Module):
    def __init__(
        self,
        hidden_size,
        num_attention_heads,
        intermediate_size,
        norm_eps,
        qkv_bias,
        out_bias,
        num_experts,
        num_experts_per_tok,
        moe_intermediate_size,
        decoder_sparse_step,
        mlp_only_layers,
        n_shared_experts,
        score_func,
        norm_topk_prob,
        n_group,
        topk_group,
        routed_scaling_factor,
        layer_idx: int,
        device=None,
        dtype=None,
        operations=None,
    ):
        super().__init__()
        self.layer_idx = layer_idx
        h = hidden_size
        self.scale_shift_table = nn.Parameter(torch.empty(1, 6 * h, device=device, dtype=dtype))
        self.norm1 = LingBotVideoRMSNorm(h, norm_eps, device=device, dtype=dtype, operations=operations)
        self.attn = LingBotVideoAttention(
            h, num_attention_heads, norm_eps, qkv_bias, out_bias, device=device, dtype=dtype, operations=operations
        )
        self.norm_post_attn = LingBotVideoRMSNorm(h, norm_eps, device=device, dtype=dtype, operations=operations)
        self.norm2 = LingBotVideoRMSNorm(h, norm_eps, device=device, dtype=dtype, operations=operations)
        # Sparsity decision matches MoEBlock: mlp_only_layers + decoder_sparse_step + num_experts
        if layer_idx not in mlp_only_layers and (
            num_experts > 0 and (layer_idx + 1) % decoder_sparse_step == 0
        ):
            self.ffn = LingBotVideoSparseMoeBlock(
                h, intermediate_size, num_experts, num_experts_per_tok,
                moe_intermediate_size, score_func, norm_topk_prob,
                n_group, topk_group, routed_scaling_factor,
                n_shared_experts, device=device, dtype=dtype, operations=operations,
            )
        else:
            self.ffn = LingBotVideoMLP(h, intermediate_size, device=device, dtype=dtype, operations=operations)
        self.norm_post_ffn = LingBotVideoRMSNorm(h, norm_eps, device=device, dtype=dtype, operations=operations)

    def forward(
        self,
        x,
        temb6,
        rotary_emb,
        attention_mask=None,
        moe_padding_mask=None,
        transformer_options={},
    ):
        expected_tokens = x.shape[0] * x.shape[1]
        if temb6.ndim != 2 or temb6.shape[0] != expected_tokens:
            raise ValueError(
                "LingBotVideoBlock expects token-level temb6 with shape "
                f"(B*S, 6D); got {tuple(temb6.shape)} for hidden states {tuple(x.shape)}."
            )
        mod = temb6.view(x.shape[0], x.shape[1], -1) + self.scale_shift_table.unsqueeze(0)
        shift_msa, scale_msa, gate_msa, shift_mlp, scale_mlp, gate_mlp = mod.chunk(6, dim=-1)
        gate_msa, gate_mlp = gate_msa.tanh(), gate_mlp.tanh()
        scale_msa, scale_mlp = 1.0 + scale_msa, 1.0 + scale_mlp

        attn_in = self.norm1(x) * scale_msa + shift_msa
        attn_out = self.attn(
            attn_in,
            rotary_emb,
            attention_mask,
            transformer_options=transformer_options,
        )
        x = x + (gate_msa * self.norm_post_attn(attn_out)).to(x.dtype)

        ffn_in = self.norm2(x) * scale_mlp + shift_mlp
        if isinstance(self.ffn, LingBotVideoSparseMoeBlock):
            ffn_out = self.ffn(ffn_in, padding_mask=moe_padding_mask)
        else:
            ffn_out = self.ffn(ffn_in)
        ffn_normed = self.norm_post_ffn(ffn_out)
        x = x + (gate_mlp * ffn_normed).to(x.dtype)
        return x


class LingBotVideo(nn.Module):
    _no_split_modules = ["LingBotVideoBlock"]

    def __init__(
        self,
        image_model=None,
        patch_size: Tuple[int, int, int] = (1, 2, 2),
        in_channels: int = 16,
        out_channels: int = 16,
        hidden_size: int = 2048,
        num_attention_heads: int = 16,
        depth: int = 24,
        intermediate_size: int = 6144,
        text_dim: int = 2560,
        freq_dim: int = 256,
        norm_eps: float = 1e-6,
        rope_theta: float = 256.0,
        axes_dims: Tuple[int, int, int] = (32, 48, 48),
        axes_lens: Tuple[int, int, int] = (8192, 1024, 1024),
        qkv_bias: bool = False,
        out_bias: bool = True,
        patch_embed_bias: bool = True,
        timestep_mlp_bias: bool = True,
        num_experts: int = 0,
        num_experts_per_tok: int = 8,
        moe_intermediate_size: int = 512,
        decoder_sparse_step: int = 1,
        mlp_only_layers: Tuple[int, ...] = (),
        n_shared_experts: Optional[int] = None,
        score_func: str = "sigmoid",
        norm_topk_prob: bool = True,
        n_group: Optional[int] = None,
        topk_group: Optional[int] = None,
        routed_scaling_factor: float = 1.0,
        dtype=None,
        device=None,
        operations=None,
    ):
        super().__init__()
        self.dtype = dtype
        self.patch_size = tuple(patch_size)
        self.out_channels = out_channels
        head_dim = hidden_size // num_attention_heads
        assert head_dim == sum(axes_dims), f"head_dim {head_dim} != sum(axes_dims) {sum(axes_dims)}"
        mlp_only_layers = tuple(mlp_only_layers)

        self.patch_embedder = operations.Linear(
            in_channels * math.prod(patch_size), hidden_size, bias=patch_embed_bias, device=device, dtype=dtype
        )
        self.freq_dim = freq_dim
        self.time_embedder = LingBotVideoTimestepEmbedding(
            freq_dim, hidden_size, bias=timestep_mlp_bias, device=device, dtype=dtype, operations=operations
        )
        self.time_modulation = nn.Sequential(
            nn.SiLU(),
            operations.Linear(hidden_size, 6 * hidden_size, device=device, dtype=dtype),
        )
        self.text_embedder = LingBotVideoTextEmbedder(text_dim, hidden_size, device=device, dtype=dtype, operations=operations)
        self.rope = LingBotVideoRotaryEmbedding(axes_dims, axes_lens, rope_theta)
        self.blocks = nn.ModuleList(
            [
                LingBotVideoBlock(
                    hidden_size=hidden_size,
                    num_attention_heads=num_attention_heads,
                    intermediate_size=intermediate_size,
                    norm_eps=norm_eps,
                    qkv_bias=qkv_bias,
                    out_bias=out_bias,
                    num_experts=num_experts,
                    num_experts_per_tok=num_experts_per_tok,
                    moe_intermediate_size=moe_intermediate_size,
                    decoder_sparse_step=decoder_sparse_step,
                    mlp_only_layers=mlp_only_layers,
                    n_shared_experts=n_shared_experts,
                    score_func=score_func,
                    norm_topk_prob=norm_topk_prob,
                    n_group=n_group,
                    topk_group=topk_group,
                    routed_scaling_factor=routed_scaling_factor,
                    layer_idx=i,
                    device=device,
                    dtype=dtype,
                    operations=operations,
                )
                for i in range(depth)
            ]
        )
        self.norm_out = operations.LayerNorm(hidden_size, elementwise_affine=False, eps=norm_eps, device=device, dtype=dtype)
        self.norm_out_modulation = nn.Sequential(
            nn.SiLU(),
            operations.Linear(hidden_size, 2 * hidden_size, device=device, dtype=dtype),
        )
        self.proj_out = operations.Linear(hidden_size, math.prod(patch_size) * out_channels, device=device, dtype=dtype)

    def forward(
        self,
        hidden_states: torch.Tensor,             # (B, C, T, H, W)
        timestep: torch.Tensor,                  # (B,) ∈ [0, 1000](= sigma*1000)
        context: torch.Tensor = None,            # (B, L, text_dim)
        encoder_attention_mask: Optional[torch.Tensor] = None,  # (B, L) 1=valid
        attention_mask: Optional[torch.Tensor] = None,
        transformer_options={},
        **kwargs,
    ):
        encoder_hidden_states = context
        if encoder_hidden_states is None:
            raise ValueError("LingBotVideo requires text conditioning.")
        if encoder_attention_mask is None:
            encoder_attention_mask = attention_mask
        B, C, T, H, W = hidden_states.shape
        pF, pH, pW = self.patch_size
        gt, gh, gw = T // pF, H // pH, W // pW
        n_video = gt * gh * gw
        L = encoder_hidden_states.shape[1]
        device = hidden_states.device
        if encoder_attention_mask is not None:
            text_lens = encoder_attention_mask.sum(dim=-1).long()
        else:
            text_lens = torch.full((B,), L, dtype=torch.long, device=device)
        text_lens_list = [int(v) for v in text_lens.detach().cpu().tolist()]

        # patchify: token order (f h w), feature order (pf ph pw c) -- matches patchify_and_embed
        patch_tokens = hidden_states.reshape(B, C, gt, pF, gh, pH, gw, pW)
        patch_tokens = patch_tokens.permute(0, 2, 4, 6, 3, 5, 7, 1).reshape(
            B,
            n_video,
            pF * pH * pW * C,
        )
        x = self.patch_embedder(patch_tokens)
        text = self.text_embedder(encoder_hidden_states)
        joint = torch.cat([x, text], dim=1)  # [video; text]
        joint_seq_len = joint.shape[1]

        # Per-sample RoPE: video t-axis start = real text length of this sample + 1
        rotary_parts = [
            self.rope(make_joint_position_ids(text_lens_list[i], gt, gh, gw, device, L))
            for i in range(B)
        ]
        rotary = torch.stack(rotary_parts, dim=0).unsqueeze(2)  # (B, S, 1, head_dim/2, 2, 2)

        attention_mask = None
        moe_padding_mask = None
        has_padding = encoder_attention_mask is not None and bool((text_lens < L).any())
        if has_padding:
            key_mask = torch.cat(
                [torch.ones(B, n_video, dtype=torch.bool, device=device),
                 encoder_attention_mask.bool()],
                dim=1,
            )
            attention_mask = key_mask[:, None, None, :]      # (B,1,1,S) → SDPA broadcast
            moe_padding_mask = key_mask.reshape(-1)  # (B*S,)

        timestep_proj = timestep_embedding(timestep.to(hidden_states.dtype), self.freq_dim, time_factor=1.0)
        t_emb = self.time_embedder(timestep_proj)                            # (B, D)
        temb_input = t_emb.unsqueeze(1).expand(B, joint_seq_len, -1)       # (B, S, D)
        temb6 = self.time_modulation(temb_input.reshape(B * joint_seq_len, -1))
        temb6 = temb6.reshape(B, joint_seq_len, -1)                        # (B, S, 6D)

        temb6 = temb6.reshape(temb6.shape[0] * temb6.shape[1], -1)

        for block in self.blocks:
            joint = block(
                joint,
                temb6,
                rotary,
                attention_mask,
                moe_padding_mask,
                transformer_options=transformer_options,
            )

        final_mod = self.norm_out_modulation(temb_input.reshape(joint.shape[0] * joint.shape[1], -1))
        shift, scale = final_mod.reshape(joint.shape[0], joint.shape[1], -1).chunk(2, dim=-1)
        final_hidden = self.norm_out(joint) * (1.0 + scale) + shift
        projected = self.proj_out(final_hidden)
        x = projected[:, :n_video]

        # unpatchify (matches the rearrange in postprocess)
        Cout = self.out_channels
        x = x.reshape(B, gt, gh, gw, pF, pH, pW, Cout)
        x = x.permute(0, 7, 1, 4, 2, 5, 3, 6).reshape(B, Cout, T, H, W)

        return x


LingBotVideoTransformer3DModel = LingBotVideo
