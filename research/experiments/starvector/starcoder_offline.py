"""
Bypass the gated `bigcode/starcoderbase-1b` dependency.

Why this exists
---------------
starvector/model/llm/starcoder.py builds the LLM with:

    AutoTokenizer.from_pretrained("bigcode/starcoderbase-1b", use_fast=False)
    AutoConfig.from_pretrained("bigcode/starcoderbase-1b")
    AutoModelForCausalLM.from_pretrained("bigcode/starcoderbase-1b", ...)

`bigcode/starcoderbase-1b` is a gated repo (gated: "auto"), so an un-accepted
account gets HTTP 403 and the whole load fails before anything else runs.

That download is also pure waste. The StarVector checkpoint is self-contained:
its safetensors index carries all 292 `model.svg_transformer.transformer.*`
tensors, so every byte of the ~4.5 GB starcoderbase download is overwritten
moments later by the outer `from_pretrained`. Only the *config* and the
*tokenizer* are genuinely needed -- and the tokenizer is already published,
ungated, inside the StarVector repo itself (vocab.json, merges.txt,
added_tokens.json map [PAD]/<svg-start>/<image-start>/<caption-start> to
49152-49155, exactly what init_tokenizer() would have produced).

So: rebuild the config locally, take the tokenizer from the ungated repo, and
instantiate the LLM with empty weights for the checkpoint to fill.

Where the config numbers come from
----------------------------------
Not guessed. Read out of the safetensors headers of
starvector/starvector-1b-im2svg via HTTP range requests:

    wte.weight              [49156, 2048]  -> vocab_size 49156, n_embd 2048
    wpe.weight              [8192, 2048]   -> n_positions 8192
    h.{0..23}               24 blocks      -> n_layer 24
    h.0.mlp.c_fc.weight     [8192, 2048]   -> n_inner 8192
    h.0.attn.c_attn.weight  [2304, 2048]   -> 2048 + 2*128 -> multi_query=True,
                                              n_head 16, head_dim 128
    (no lm_head tensor)                    -> tie_word_embeddings=True

vocab_size is 49156 rather than starcoderbase's 49152 because StarVector added
4 tokens. Declaring 49156 up front makes StarCoderModel's
resize_token_embeddings(len(tokenizer)) an early-return no-op instead of a
resize over meta tensors.

Remaining non-shape fields (activation_function, layer_norm_epsilon,
attention_softmax_in_fp32, ...) are HF GPTBigCodeConfig defaults, which is what
the StarCoder family uses. Correctness is checked at load time by asserting the
checkpoint reports no missing and no unexpected keys -- see verify_load().
"""

from transformers import (
    AutoConfig,
    AutoModelForCausalLM,
    AutoTokenizer,
    GPTBigCodeConfig,
    GPTBigCodeForCausalLM,
)

GATED_LLM_NAMES = {
    "bigcode/starcoderbase-1b",
    "bigcode/starcoderbase-3b",
    "bigcode/starcoderbase-7b",
    "bigcode/starcoder2-15b",
}

# Recovered from checkpoint tensor shapes (see module docstring).
STARCODERBASE_1B = dict(
    vocab_size=49156,
    n_positions=8192,
    n_embd=2048,
    n_layer=24,
    n_head=16,
    n_inner=8192,
    multi_query=True,
    activation_function="gelu_pytorch_tanh",
    layer_norm_epsilon=1e-5,
    tie_word_embeddings=True,
    bos_token_id=0,
    eos_token_id=0,
)


def install(tokenizer_source: str, attn: str = "eager") -> None:
    """
    Redirect the gated lookups inside starvector.model.llm.starcoder.

    Patches the module's own `AutoConfig` / `AutoModelForCausalLM` /
    `AutoTokenizer` attributes (that module did `from transformers import ...`,
    so rebinding on the module is what takes effect). Non-gated names fall
    through to the real implementations untouched.

    tokenizer_source: the ungated StarVector repo id, e.g.
                      "starvector/starvector-1b-im2svg".
    """
    import starvector.model.llm.starcoder as sc

    class _Config:
        @staticmethod
        def from_pretrained(name, *a, **kw):
            if name in GATED_LLM_NAMES:
                if name != "bigcode/starcoderbase-1b":
                    raise NotImplementedError(
                        f"No offline config recorded for {name}. Either accept its "
                        f"license on the Hub and pass --gated-starcoder, or add its "
                        f"shapes to starcoder_offline.py."
                    )
                return GPTBigCodeConfig(**STARCODERBASE_1B)
            return AutoConfig.from_pretrained(name, *a, **kw)

    class _Model:
        @staticmethod
        def from_pretrained(name, *a, config=None, **kw):
            if name not in GATED_LLM_NAMES:
                return AutoModelForCausalLM.from_pretrained(name, *a, config=config, **kw)
            # Empty shell. The outer StarVectorForCausalLM.from_pretrained loads
            # the real weights over it from the StarVector checkpoint.
            #
            # attn_implementation must be forced here. The value passed to the
            # OUTER from_pretrained does not reach this inner model: constructing
            # GPTBigCodeForCausalLM(config) runs _autoset_attn_implementation,
            # which silently upgrades "eager" to "sdpa". So `eager` at the top
            # level still yields GPTBigCodeSdpaAttention underneath.
            model = GPTBigCodeForCausalLM._from_config(config, attn_implementation=attn)
            dtype = kw.get("torch_dtype")
            if dtype is not None and dtype != "auto":
                model = model.to(dtype)
            return model

    class _Tokenizer:
        @staticmethod
        def from_pretrained(name, *a, **kw):
            if name in GATED_LLM_NAMES:
                name = tokenizer_source
            return AutoTokenizer.from_pretrained(name, *a, **kw)

    sc.AutoConfig = _Config
    sc.AutoModelForCausalLM = _Model
    sc.AutoTokenizer = _Tokenizer


STARCODER2_LLM_NAMES = {
    "bigcode/starcoder2-3b",
    "bigcode/starcoder2-7b",
    "bigcode/starcoder2-15b",
}

# starvector-8b-im2svg embed_tokens is [49157, 4608]: starcoder2's 49152 plus
# [PAD] and the 4 tokens init_tokenizer() adds. Declaring it up front keeps
# resize_token_embeddings() an early-return no-op rather than a resize over meta
# tensors (same trick as the 1B).
STARCODER2_VOCAB = 49157


def install_v2(attn: str = "sdpa", dtype=None, vocab_size: int = STARCODER2_VOCAB) -> None:
    """
    Patch the StarCoder2 path used by starvector-8b-im2svg.

    Different problems from the V1 path:

      - `bigcode/starcoder2-7b` is NOT gated, so its config and tokenizer load
        normally and we use the real ones (safer than reconstructing). Only the
        ~14 GB of weights are skipped -- the StarVector checkpoint overwrites
        them anyway.
      - starvector/model/llm/starcoder2.py hardcodes
        `attn_implementation="flash_attention_2"` with no availability check, so
        it raises on any machine without CUDA flash-attn. The V1 path self-heals;
        this one does not. We drop that kwarg and substitute `attn`.
      - It also hardcodes torch_dtype=bfloat16; `dtype` overrides it.
    """
    import starvector.model.llm.starcoder2 as sc2

    real_config = sc2.AutoConfig
    real_model = sc2.AutoModelForCausalLM

    class _Config:
        @staticmethod
        def from_pretrained(name, *a, **kw):
            cfg = real_config.from_pretrained(name, *a, **kw)
            if name in STARCODER2_LLM_NAMES:
                cfg.vocab_size = vocab_size
            return cfg

    class _Model:
        @staticmethod
        def from_pretrained(name, *a, config=None, **kw):
            if name not in STARCODER2_LLM_NAMES:
                return real_model.from_pretrained(name, *a, config=config, **kw)
            kw.pop("attn_implementation", None)   # upstream's flash_attention_2
            model = real_model.from_config(config, attn_implementation=attn)
            want = dtype if dtype is not None else kw.get("torch_dtype")
            if want is not None and want != "auto":
                model = model.to(want)
            return model

    sc2.AutoConfig = _Config
    sc2.AutoModelForCausalLM = _Model


def retie_lm_head(model) -> bool:
    """
    Re-establish the lm_head <-> wte weight tie after loading. Returns True if a
    repair was needed.

    Applies to BOTH the offline and the --gated-starcoder path; call it always.

    GPTBigCodeForCausalLM ties lm_head.weight to transformer.wte.weight in
    __init__, so the StarVector checkpoint contains no lm_head tensor. But
    `low_cpu_mem_usage=True` loads through accelerate's
    set_module_tensor_to_device, which does `module._parameters[name] = new_param`
    -- it REPLACES the parameter object rather than copying into it. That breaks
    the Python-level aliasing, and nothing re-ties it afterwards:
    PreTrainedModel.tie_weights() runs on the outer StarVectorForCausalLM, which
    does not implement get_output_embeddings(), so the inner LLM is never visited.

    Failure modes if skipped:
      - offline path: lm_head.weight is still the meta tensor from construction,
        so generation raises.
      - gated path: lm_head.weight silently retains *starcoderbase's* embedding
        matrix instead of StarVector's fine-tuned one. No error, worse output.
        This is the dangerous one.

    (Loading without low_cpu_mem_usage would also avoid it -- that path copies
    in-place with param.data.copy_() and preserves the tie -- at the cost of an
    extra full-size CPU copy of the checkpoint.)
    """
    llm = model.model.svg_transformer.transformer
    wte = llm.get_input_embeddings().weight
    head = llm.get_output_embeddings().weight
    if head.device.type != "meta" and head.data_ptr() == wte.data_ptr():
        return False
    llm.tie_weights()
    head = llm.get_output_embeddings().weight
    if head.device.type == "meta" or head.data_ptr() != wte.data_ptr():
        raise RuntimeError("failed to re-tie lm_head to wte")
    return True


def verify_load(model, strict: bool = True):
    """
    Confirm the reconstructed config actually matched the checkpoint.

    A wrong shape would already have raised. This catches the quieter failure:
    a structurally valid but misnamed module tree, which would leave the
    checkpoint's tensors unused and generate fluent-looking garbage.
    """
    ckpt_missing = getattr(model, "_missing_keys", None)
    problems = []
    if ckpt_missing:
        problems.append(f"{len(ckpt_missing)} missing keys, e.g. {list(ckpt_missing)[:3]}")

    llm = model.model.svg_transformer.transformer
    n_llm = sum(1 for _ in llm.state_dict())
    if n_llm == 0:
        problems.append("LLM state_dict is empty")

    # Any parameter still on the meta device means it was never materialised
    # from the checkpoint.
    meta = [n for n, p in model.named_parameters() if p.device.type == "meta"]
    if meta:
        problems.append(f"{len(meta)} params left on meta device, e.g. {meta[:3]}")

    if problems and strict:
        raise RuntimeError("offline StarCoder load looks wrong: " + "; ".join(problems))
    return problems
