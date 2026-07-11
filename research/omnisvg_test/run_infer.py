"""OmniSVG1.1_4B image-to-svg on Apple MPS (M3 Max).

Adapted from OmniSVG/inference.py:
- float16 instead of bfloat16, no device_map="auto" (CPU load -> .to("mps"))
- state-dict key remap for transformers>=4.52 Qwen2.5-VL layout
- progress + timebox stopping criteria
- no cairosvg dependency (validity/rendering handled by project tooling)
"""
import os, sys, time, gc, argparse, tempfile

ROOT = '/Users/arrz/Documents/Github/image-to-svg'
OMNI = ROOT + '/research/omnisvg_test/OmniSVG'
QWEN_DIR = ROOT + '/research/omnisvg_test/weights/Qwen2.5-VL-3B-Instruct'
OMNI_BIN = ROOT + '/research/omnisvg_test/weights/OmniSVG1.1_4B/pytorch_model.bin'

os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')
os.environ.setdefault('PYTORCH_ENABLE_MPS_FALLBACK', '1')

sys.path.insert(0, OMNI)
os.chdir(OMNI)

import numpy as np
import torch
from PIL import Image
from transformers import AutoProcessor, StoppingCriteria, StoppingCriteriaList
from qwen_vl_utils import process_vision_info

from decoder import SketchDecoder
from tokenizer import SVGTokenizer

DEVICE = 'mps'
DTYPE = torch.float16  # overridden by --lm-dtype
DTYPES = {'fp16': torch.float16, 'bf16': torch.bfloat16, 'fp32': torch.float32}

SYSTEM_PROMPT = """You are an expert SVG code generator.
Generate precise, valid SVG path commands that accurately represent the described scene or object.
Focus on capturing key shapes, spatial relationships, and visual composition."""

TARGET_IMAGE_SIZE = 448
BOS_TOKEN_ID, EOS_TOKEN_ID, PAD_TOKEN_ID = 196998, 196999, 151643
BLACK_COLOR_TOKEN = 40012


# ---------- image preprocessing (verbatim logic from inference.py) ----------
def detect_and_replace_background(image, threshold=240, edge_sample_ratio=0.1,
                                  color_similarity_threshold=30, min_edge_samples=10):
    img_array = np.array(image)
    if image.mode == 'RGBA':
        bg = Image.new('RGBA', image.size, (255, 255, 255, 255))
        composite = Image.alpha_composite(bg, image)
        return composite.convert('RGB'), True
    h, w = img_array.shape[:2]
    edge_pixels = []
    sample_count = max(min_edge_samples, int(min(h, w) * edge_sample_ratio))
    for i in range(0, w, max(1, w // sample_count)):
        edge_pixels.append(img_array[0, i]); edge_pixels.append(img_array[h-1, i])
    for i in range(0, h, max(1, h // sample_count)):
        edge_pixels.append(img_array[i, 0]); edge_pixels.append(img_array[i, w-1])
    edge_pixels = np.array(edge_pixels)
    if len(edge_pixels) > 0:
        mean_edge = edge_pixels.mean(axis=0)
        if np.all(mean_edge > threshold):
            return image, False
    if len(img_array.shape) == 3 and img_array.shape[2] >= 3:
        edge_colors = []
        for i in range(w):
            edge_colors.append(tuple(img_array[0, i, :3])); edge_colors.append(tuple(img_array[h-1, i, :3]))
        for i in range(h):
            edge_colors.append(tuple(img_array[i, 0, :3])); edge_colors.append(tuple(img_array[i, w-1, :3]))
        from collections import Counter
        bg_color = Counter(edge_colors).most_common(1)[0][0]
        color_diff = np.sqrt(np.sum((img_array[:, :, :3].astype(float) - np.array(bg_color)) ** 2, axis=2))
        bg_mask = color_diff < color_similarity_threshold
        result = img_array.copy()
        if result.shape[2] == 4:
            result[bg_mask] = [255, 255, 255, 255]
        else:
            result[bg_mask] = [255, 255, 255]
        return Image.fromarray(result).convert('RGB'), True
    return image, False


def preprocess_image_for_svg(path, replace_background=True, target_size=TARGET_IMAGE_SIZE):
    raw_img = Image.open(path)
    if raw_img.mode == 'RGBA':
        bg = Image.new('RGBA', raw_img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, raw_img).convert('RGB')
    elif raw_img.mode in ('LA', 'PA'):
        raw_img = raw_img.convert('RGBA')
        bg = Image.new('RGBA', raw_img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, raw_img).convert('RGB')
    elif raw_img.mode != 'RGB':
        img = raw_img.convert('RGB')
    else:
        img = raw_img
    if replace_background:
        img, _ = detect_and_replace_background(img)
    return img.resize((target_size, target_size), Image.Resampling.LANCZOS)


# ---------- progress / timebox ----------
class ProgressCriteria(StoppingCriteria):
    def __init__(self, start_len, timeout_s=1500.0, min_tok_s=1.5, grace_tokens=128):
        self.start_len = start_len
        self.t0 = None
        self.timeout_s = timeout_s
        self.min_tok_s = min_tok_s
        self.grace = grace_tokens
        self.n = 0
        self.aborted = None

    def __call__(self, input_ids, scores, **kw):
        if self.t0 is None:
            self.t0 = time.time()   # first call ~ right after prefill
        self.n = input_ids.shape[1] - self.start_len
        el = max(time.time() - self.t0, 1e-9)
        if self.n % 128 == 0:
            print(f'    {self.n} tok  {el:6.0f}s  {self.n/el:5.2f} tok/s', flush=True)
        if el > self.timeout_s:
            self.aborted = f'TIMEOUT after {el:.0f}s at {self.n} tokens ({self.n/el:.2f} tok/s)'
            print('    ' + self.aborted, flush=True)
            return True
        if self.n >= self.grace and self.n / el < self.min_tok_s:
            self.aborted = f'TOO SLOW: {self.n/el:.2f} tok/s at {self.n} tokens'
            print('    ' + self.aborted, flush=True)
            return True
        return False


def load_model():
    print('[1/3] processor/tokenizer ...', flush=True)
    processor = AutoProcessor.from_pretrained(QWEN_DIR, padding_side='left')
    processor.tokenizer.padding_side = 'left'

    print('[2/3] SketchDecoder (Qwen2.5-VL-3B fp16, CPU) ...', flush=True)
    t0 = time.time()
    sketch_decoder = SketchDecoder(config_path='./config.yaml', model_path=QWEN_DIR,
                                   model_size='4B', torch_dtype=DTYPE)
    sketch_decoder.transformer.resize_token_embeddings(197000)
    print(f'    built in {time.time()-t0:.0f}s', flush=True)

    print('[3/3] OmniSVG weights ...', flush=True)
    t0 = time.time()
    sd = torch.load(OMNI_BIN, map_location='cpu', mmap=True)
    model_keys = list(sketch_decoder.state_dict().keys())
    new_layout = any(k.startswith('transformer.model.language_model.') for k in model_keys)
    if new_layout:
        remapped = {}
        for k, v in sd.items():
            if k.startswith('transformer.visual.'):
                nk = 'transformer.model.visual.' + k[len('transformer.visual.'):]
            elif k.startswith('transformer.model.'):
                nk = 'transformer.model.language_model.' + k[len('transformer.model.'):]
            else:
                nk = k
            remapped[nk] = v
        sd = remapped
        print('    remapped keys to transformers>=4.52 layout', flush=True)
    missing, unexpected = sketch_decoder.load_state_dict(sd, strict=False)
    missing = [m for m in missing if 'rotary' not in m and 'inv_freq' not in m]
    print(f'    loaded in {time.time()-t0:.0f}s; missing={missing[:8]} unexpected={unexpected[:8]}', flush=True)
    assert not missing, f'missing keys: {missing[:20]}'
    del sd
    gc.collect()

    t0 = time.time()
    sketch_decoder = sketch_decoder.eval()
    sketch_decoder.transformer.to(DEVICE)
    print(f'    moved to {DEVICE} in {time.time()-t0:.0f}s', flush=True)

    svg_tokenizer = SVGTokenizer('./config.yaml', model_size='4B')
    return processor, sketch_decoder, svg_tokenizer


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--image', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--max-new', type=int, default=1536)
    ap.add_argument('--nseq', type=int, default=2)
    ap.add_argument('--temperature', type=float, default=0.3)
    ap.add_argument('--top-p', type=float, default=0.90)
    ap.add_argument('--top-k', type=int, default=50)
    ap.add_argument('--rep-penalty', type=float, default=1.05)
    ap.add_argument('--timeout', type=float, default=1500.0)
    ap.add_argument('--visual-fp32', action='store_true')
    ap.add_argument('--lm-dtype', choices=list(DTYPES), default='fp16')
    ap.add_argument('--seed', type=int, default=0)
    args = ap.parse_args()

    global DTYPE
    DTYPE = DTYPES[args.lm_dtype]

    torch.manual_seed(args.seed)

    processor, sketch_decoder, svg_tokenizer = load_model()
    if args.visual_fp32:
        sketch_decoder.transformer.model.visual.float()
        print('vision tower -> fp32', flush=True)

    img = preprocess_image_for_svg(args.image)
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tf:
        img.save(tf.name, format='PNG')
        tmp_path = tf.name

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": [
            {"type": "text", "text": "Generate SVG code that accurately represents this image:"},
            {"type": "image", "image": tmp_path},
        ]}
    ]
    text_input = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    image_inputs, _ = process_vision_info(messages)
    inputs = processor(text=[text_input], images=image_inputs, padding=True,
                       truncation=True, return_tensors='pt')
    os.unlink(tmp_path)

    input_ids = inputs['input_ids'].to(DEVICE)
    attention_mask = inputs['attention_mask'].to(DEVICE)
    model_inputs = {'input_ids': input_ids, 'attention_mask': attention_mask}
    if 'pixel_values' in inputs:
        visual = sketch_decoder.transformer.model.visual if hasattr(sketch_decoder.transformer, 'model') else sketch_decoder.transformer.visual
        pv_dtype = next(visual.parameters()).dtype
        model_inputs['pixel_values'] = inputs['pixel_values'].to(DEVICE, dtype=pv_dtype)
    if 'image_grid_thw' in inputs:
        model_inputs['image_grid_thw'] = inputs['image_grid_thw'].to(DEVICE)

    print(f'prompt tokens: {input_ids.shape[1]}', flush=True)

    prog = ProgressCriteria(input_ids.shape[1], timeout_s=args.timeout)
    gen_cfg = dict(do_sample=True, temperature=args.temperature, top_p=args.top_p,
                   top_k=args.top_k, repetition_penalty=args.rep_penalty,
                   no_repeat_ngram_size=0, eos_token_id=EOS_TOKEN_ID,
                   pad_token_id=PAD_TOKEN_ID, bos_token_id=BOS_TOKEN_ID)

    t_gen0 = time.time()
    with torch.no_grad():
        results = sketch_decoder.transformer.generate(
            **model_inputs, max_new_tokens=args.max_new,
            num_return_sequences=args.nseq, use_cache=True,
            stopping_criteria=StoppingCriteriaList([prog]), **gen_cfg)
    t_gen = time.time() - t_gen0
    gen_tokens = results.shape[1] - input_ids.shape[1]
    print(f'GENERATION: {gen_tokens} steps x {args.nseq} seq in {t_gen:.0f}s '
          f'({gen_tokens/t_gen:.2f} steps/s); aborted={prog.aborted}', flush=True)

    generated = results[:, input_ids.shape[1]:].cpu()

    saved = 0
    for i in range(generated.shape[0]):
        ids = generated[i:i+1]
        # trim at EOS if present
        row = ids[0].tolist()
        if EOS_TOKEN_ID in row:
            row = row[:row.index(EOS_TOKEN_ID)]
        ids = torch.tensor([row])
        wrapper = torch.cat([torch.full((1, 1), BOS_TOKEN_ID), ids,
                             torch.full((1, 1), EOS_TOKEN_ID)], dim=1)
        try:
            xy = svg_tokenizer.process_generated_tokens(wrapper)
            if len(xy) == 0:
                print(f'candidate {i}: no decodable tokens'); continue
            svg_tensors, color_tensors = svg_tokenizer.raster_svg(xy)
            if not svg_tensors or not svg_tensors[0]:
                print(f'candidate {i}: no paths'); continue
            n_paths = len(svg_tensors[0])
            while len(color_tensors) < n_paths:
                color_tensors.append(BLACK_COLOR_TOKEN)
            svg = svg_tokenizer.apply_colors_to_svg(svg_tensors[0], color_tensors)
            svg_str = svg.to_str()
            if 'width=' not in svg_str:
                svg_str = svg_str.replace('<svg', f'<svg width="{TARGET_IMAGE_SIZE}" height="{TARGET_IMAGE_SIZE}"', 1)
            out = args.out if saved == 0 else args.out.replace('.svg', f'_cand{i}.svg')
            with open(out, 'w') as f:
                f.write(svg_str)
            print(f'candidate {i}: {n_paths} paths, {len(row)} tokens, saved -> {out}', flush=True)
            saved += 1
        except Exception as e:
            print(f'candidate {i}: ERROR {e}')

    print(f'DONE saved={saved} gen_wall={t_gen:.0f}s tok_s={gen_tokens/t_gen:.2f}')


if __name__ == '__main__':
    main()
