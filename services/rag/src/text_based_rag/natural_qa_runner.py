"""Caption natural data, compare text encoders/answer models, and export retrieval."""

import argparse
import base64
import gc
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import random
import re
import socket
import subprocess
import threading
import time
import traceback
import unicodedata
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from functools import lru_cache


SPLITS = {
    'train': ('train data', 'vlsp_2025_train.json', 'train_images'),
    'public_test': ('public_test data', 'vlsp_2025_public_test.json', 'public_test_images'),
    'private_test': ('private_test data (post submission)', 'vlsp_2025_private_test.json', 'private_test_images'),
}
PRE_CAPTION_FIX_SHA256 = 'dcf71c0e312443d704b494bd0a3cec1ac559c03b7a54fe1902e1fb9379731690'
TOKEN_RETRY_FIX_SHA256 = '3fa8dfacda2d86377423116c8bea516828327cb3914a9e01e9545c1df0875e6b'
ANTI_REPETITION_FIX_SHA256 = '33a76c10a85b78b1d747022d69318b764e4b29c0a37ca9f1a07527ee366200d4'
DEDUP_FIX_SHA256 = '814ecba9005a5a7f7dfbac8190901e440ff69e96ea60156dca33a8ea2872427c'
UNBOUNDED_FIX_SHA256 = 'd77b1db2faf5d970c8a84b14a52cff30d8035d002fa15c151e713dca42e75f98'
PRE_CONTEXT_FIX_SHA256 = 'b9f74574bf0df80a3d21582a815a24f7b07e19a2f127bde4ec612bf26c4be975'
CAPTION_RETRY_MAX_TOKENS = 12288
# Optional subset of a test split (--ids): only these question ids are loaded. Train is never filtered.
ID_FILTER = None


def set_id_filter(path):
    """Restrict test-split rows to the ids in `path` (JSON list, or one id per line). Returns provenance."""
    global ID_FILTER
    text = Path(path).read_text(encoding='utf-8-sig').strip()
    ids = json.loads(text) if text.startswith('[') else [line.strip() for line in text.splitlines() if line.strip()]
    if not ids or len(set(ids)) != len(ids) or not all(isinstance(i, str) and i for i in ids):
        raise ValueError(f'--ids must list distinct, non-empty question ids: {path}')
    ID_FILTER = frozenset(ids)
    return {'ids_file_sha256': hashlib.sha256(Path(path).read_bytes()).hexdigest(), 'count': len(ids),
            'policy': 'test_split_subset_by_id_v1'}
ANSWER_IMAGE_MAX_TOKENS = 4096
CAPTION_RETRY_RULES = '''
YÊU CẦU CHO LẦN SINH LẠI: Lần trước đã thất bại vì output quá dài hoặc lặp item.
- Mỗi đối tượng quan sát được chỉ xuất hiện MỘT LẦN. Không lặp item để kéo dài mảng.
- Mô tả ngắn gọn; mỗi trường một câu ngắn, giữ chữ/số/đơn vị quan trọng đọc được.
- Đưa đối tượng liên quan trực tiếp đến câu hỏi lên đầu, rồi các đối tượng còn lại.
- Không viết lại các bước phân tích, không trả lời câu hỏi, không thêm ví dụ pháp lý.
- Khi đã liệt kê hết đối tượng phân biệt được, đóng mảng items và đóng JSON ngay.
'''


def can_resume_caption_fix(folder, previous, config):
    """Migrate known caption fixes only, with unchanged data and no embeddings."""
    if (folder.name != 'train' or previous.get('status') != 'FAILED'
            or not any(message in previous.get('error', '') for message in (
                'Generation incomplete: length', 'Caption repeats an identical item',
                'Caption reached a retry schema bound'))
            or any(p.name not in {'run_config.json', 'captions.jsonl', 'errors.jsonl', 'caption_server.log'}
                   for p in folder.iterdir())):
        return False
    expected = dict(config)
    expected.pop('caption_failure_policy', None)
    expected['source_files_sha256'] = dict(config['source_files_sha256'])
    old_sha = previous.get('source_files_sha256', {}).get('src/text_based_rag/natural_qa_runner.py')
    if old_sha not in (PRE_CAPTION_FIX_SHA256, TOKEN_RETRY_FIX_SHA256, ANTI_REPETITION_FIX_SHA256, DEDUP_FIX_SHA256, UNBOUNDED_FIX_SHA256):
        return False
    expected['source_files_sha256']['src/text_based_rag/natural_qa_runner.py'] = old_sha
    if old_sha not in (DEDUP_FIX_SHA256, UNBOUNDED_FIX_SHA256):
        expected.pop('caption_duplicate_policy', None)
    if old_sha != PRE_CAPTION_FIX_SHA256:
        expected['caption_retry_max_tokens'] = CAPTION_RETRY_MAX_TOKENS
    if old_sha == UNBOUNDED_FIX_SHA256:
        expected['caption_retry_policy'] = {
            'rules': CAPTION_RETRY_RULES, 'version': 'anti_repetition_original_schema_v2', 'schema': cap.QUERY_SCHEMA,
        }
    elif old_sha in (ANTI_REPETITION_FIX_SHA256, DEDUP_FIX_SHA256):
        expected['caption_retry_policy'] = {
            'rules': CAPTION_RETRY_RULES, 'version': 'anti_repetition_v1',
            'max_items': 32, 'max_string_length': 512, 'reject_at_bound': True,
        }
    else:
        expected.pop('caption_retry_policy', None)
    if old_sha == PRE_CAPTION_FIX_SHA256:
        expected.pop('caption_retry_max_tokens', None)
    return digest(expected) == previous.get('configuration_sha256', previous.get('cache_fingerprint'))


def can_resume_context_fix(folder, previous, config):
    """Accept only the known context-failure version, preserving verified outputs."""
    if previous.get('source_files_sha256', {}).get('src/text_based_rag/natural_qa_runner.py') != PRE_CONTEXT_FIX_SHA256:
        return False
    expected = dict(config)
    expected['source_files_sha256'] = dict(config['source_files_sha256'])
    expected['source_files_sha256']['src/text_based_rag/natural_qa_runner.py'] = PRE_CONTEXT_FIX_SHA256
    if folder.name == 'train':
        if previous.get('status') != 'COMPLETED':
            return False
    else:
        if previous.get('status') != 'FAILED' or 'Answer context exceeded:' not in previous.get('error', ''):
            return False
        expected.pop('answer_context_policy', None)
        train_folder = folder.parent / 'train'
        train_meta = json.loads((train_folder / 'run_config.json').read_text(encoding='utf-8'))
        test_keys = {'answer_context', 'answer_context_policy', 'answer_max_tokens', 'test_source_sha256',
                     'test_image_sha256', 'example_bank_fingerprint', 'example_bank_files_sha256'}
        old_train_config = {k: v for k, v in expected.items() if k not in test_keys}
        old_train_config.update(split='train', samples=train_meta['samples'])
        expected['example_bank_fingerprint'] = digest(old_train_config)
        expected['example_bank_files_sha256'] = {
            name: file_hash(train_folder / name) for name in ('captions.jsonl', 'embeddings.jsonl')
        }
    return digest(expected) == previous.get('configuration_sha256', previous.get('cache_fingerprint'))


class GenerationIncomplete(ValueError):
    def __init__(self, choice, usage):
        super().__init__(f"Generation incomplete: {choice['finish_reason']}")
        self.finish_reason = choice['finish_reason']
        self.partial_content = choice['message'].get('content')
        self.usage = usage


def load_rows(root, split):
    """Discard reference answers/options before any model or prediction processing."""
    folder, name, images = SPLITS[split]
    source = root / folder / name
    raw = json.loads(source.read_text(encoding='utf-8-sig'))
    if not isinstance(raw, list) or not raw:
        raise ValueError(f'Expected a non-empty JSON array: {source}')
    rows = []
    image_root = (source.parent / images).resolve()
    for item in raw:
        if not isinstance(item, dict) or not all(
            isinstance(item.get(k), str) and item[k].strip() for k in ('id', 'image_id', 'question')
        ):
            raise ValueError(f'Invalid id/image_id/question in {source}')
        image = (image_root / (item['image_id'] + '.jpg')).resolve()
        if image.parent != image_root or not image.is_file():
            raise ValueError(f'Missing or invalid image: {image}')
        row = {k: item[k] for k in ('id', 'image_id', 'question')}
        row['image'] = str(image)
        if split == 'train':
            labels = item.get('relevant_articles')
            if not isinstance(labels, list) or not labels or any(
                not isinstance(c, dict) or not all(isinstance(c.get(k), str) and c[k] for k in ('law_id', 'article_id'))
                for c in labels
            ):
                raise ValueError(f"Train citation missing or malformed: {row['id']}")
            row['relevant_articles'] = [{k: c[k] for k in ('law_id', 'article_id')} for c in labels]
        rows.append(row)
    if len({r['id'] for r in rows}) != len(rows):
        raise ValueError(f'Duplicate sample IDs: {source}')
    if ID_FILTER is not None and split != 'train':
        missing = ID_FILTER - {r['id'] for r in rows}
        if missing:
            raise ValueError(f'{len(missing)} --ids are not in {split}')
        rows = [r for r in rows if r['id'] in ID_FILTER]
    return source, rows


def classify_question_type(question):
    """Match Lowcost's answer-blind Yes/No filter using question text only."""
    text = unicodedata.normalize('NFC', question).casefold().strip()
    text = re.sub(r'[?.!\s]+$', '', text)
    if re.search(r'đúng\s*(?:hay|hoặc|/)\s*sai|đúng\s*,?\s*sai', text):
        return 'Yes/No'
    if re.search(r'(?:không|chưa|đúng chứ|đúng không)$', text):
        return 'Yes/No'
    if re.match(r'^(?:có phải|liệu)\b', text):
        return 'Yes/No'
    return 'NaturalQA'


def load_fewshot_answers(train_source, bank_rows):
    """Load gold answers only for training rows allowed in the example bank."""
    raw = json.loads(train_source.read_text(encoding='utf-8-sig'))
    if not isinstance(raw, list) or not raw:
        raise ValueError(f'Expected a non-empty training array: {train_source}')
    by_id = {item.get('id'): item for item in raw if isinstance(item, dict)}
    if len(by_id) != len(raw) or any(not isinstance(key, str) or not key for key in by_id):
        raise ValueError(f'Train IDs are missing or duplicated: {train_source}')
    answers = {}
    for row in bank_rows:
        item = by_id.get(row['id'])
        if (item is None or item.get('image_id') != row['image_id']
                or item.get('question') != row['question']
                or not isinstance(item.get('answer'), str) or not item['answer'].strip()):
            raise ValueError(f'Train few-shot answer does not match the example bank: {row["id"]}')
        answers[row['id']] = item['answer'].strip()
    if set(answers) != {row['id'] for row in bank_rows}:
        raise ValueError('Few-shot answer IDs do not exactly match the allowed training bank.')
    return answers


def select_fewshot_neighbors(query_vector, query_question, bank, example_data, count, query_id):
    """Select typed, text-caption neighbors; this does not change law retrieval."""
    if count == 0:
        return []
    query_type = classify_question_type(query_question)
    candidates = [
        index for index, row in enumerate(bank['queries'])
        if row['query_id'] != query_id
        and classify_question_type(row['question']) == query_type
        and row['query_id'] in example_data
    ]
    if not candidates:
        return []
    scores = bank['vectors'][candidates] @ query_vector
    order = sorted(range(len(candidates)), key=lambda pos: (-float(scores[pos]), bank['queries'][candidates[pos]]['query_id']))
    return [
        {'rank': rank, 'query_id': bank['queries'][candidates[pos]]['query_id'],
         'score': float(scores[pos]), 'question_type': query_type}
        for rank, pos in enumerate(order[:count], 1)
    ]


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def installed_package_versions(names):
    versions = {}
    for name in names:
        try:
            versions[name] = version(name)
        except PackageNotFoundError:
            versions[name] = None
    return versions


def verified_run_cache(folder, required_files):
    manifest_path = folder / 'run_config.json'
    if not manifest_path.is_file():
        raise FileNotFoundError(f'Precomputed embedding manifest missing: {manifest_path}')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    hashes = manifest.get('output_sha256', {})
    if manifest.get('status') != 'COMPLETED':
        raise ValueError(f'Precomputed embedding cache is not COMPLETED: {manifest_path}')
    for name in required_files:
        target = folder / name
        if not target.is_file() or hashes.get(name) != file_hash(target):
            raise ValueError(f'Precomputed cache hash mismatch: {target}')
    return manifest


def save_json(path, value):
    # Replace atomically so interruption does not destroy the resume manifest.
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


class Run:
    def __init__(self, folder, config):
        self.folder = folder
        self.previous = {}
        self.fingerprint = digest(config)
        self.config = {**config, 'cache_fingerprint': self.fingerprint, 'configuration_sha256': self.fingerprint,
                       'status': 'RUNNING', 'started_at': datetime.now(timezone.utc).isoformat()}
        manifest = folder / 'run_config.json'
        if folder.exists() and any(folder.iterdir()):
            if not manifest.is_file():
                raise ValueError(f'Output has no resume manifest: {folder}; choose a new --output-dir.')
            previous = json.loads(manifest.read_text(encoding='utf-8'))
            self.previous = previous
            context_migration = can_resume_context_fix(folder, previous, config)
            migrated = context_migration or can_resume_caption_fix(folder, previous, config)
            if previous.get('configuration_sha256', previous.get('cache_fingerprint')) != self.fingerprint and not migrated:
                raise ValueError(f'Input/config/code/model/artifacts changed: {folder}; choose a new --output-dir. Existing files preserved.')
            if previous.get('status') == 'COMPLETED' or migrated:
                for name, expected in previous.get('output_sha256', {}).items():
                    if file_hash(folder / name) != expected:
                        raise ValueError(f'Completed cache changed: {folder / name}')
            # Preserve existing record identities while recording the new configuration.
            self.fingerprint = previous['cache_fingerprint']
            self.config['cache_fingerprint'] = self.fingerprint
            self.config['resume_history'] = previous.get('resume_history', [])
            if migrated:
                self.config['resume_history'] = [*self.config['resume_history'], {
                    'reason': 'context_truncation_fix' if context_migration else 'caption_length_retry_fix', 'previous_manifest': previous,
                    'migrated_at': datetime.now(timezone.utc).isoformat(),
                }]
                print('[resume] Verified cache preserved; applying ' + ('context truncation fix.' if context_migration else 'caption batch fix.'), flush=True)
        folder.mkdir(parents=True, exist_ok=True)
        self.started = time.monotonic()
        save_json(manifest, self.config)

    def read(self, name, rows):
        path = self.folder / name
        if not path.exists():
            return {}
        records = [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if s.strip()]
        by_id = {r['id']: r for r in records}
        if (len(by_id) != len(records) or not set(by_id).issubset({r['id'] for r in rows})
                or any(r.get('cache_fingerprint') != self.fingerprint for r in records)):
            raise ValueError(f'Cache IDs/fingerprint invalid: {path}; existing files preserved.')
        if any(r.get('record_sha256') != digest({k: v for k, v in r.items() if k != 'record_sha256'}) for r in records):
            raise ValueError(f'Cache record content changed: {path}')
        for row in rows:
            cached = by_id.get(row['id'])
            if cached is not None and cached.get('sample_sha256') != digest(row):
                raise ValueError(f"Cache does not match sample: {path}/{row['id']}")
        return by_id

    def append(self, name, row, record):
        record = {**record, 'id': row['id'], 'sample_sha256': digest(row), 'cache_fingerprint': self.fingerprint}
        record['record_sha256'] = digest(record)
        with (self.folder / name).open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        return record

    def store_caption(self, row, record, captions):
        if row['id'] not in captions:
            return self.append('captions.jsonl', row, record)
        record = {**record, 'id': row['id'], 'sample_sha256': digest(row), 'cache_fingerprint': self.fingerprint}
        record['record_sha256'] = digest(record)
        updated = {**captions, row['id']: record}
        path = self.folder / 'captions.jsonl'
        temporary = path.with_suffix('.jsonl.tmp')
        with temporary.open('w', encoding='utf-8') as stream:
            for saved in updated.values():
                stream.write(json.dumps(saved, ensure_ascii=False) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
        return record

    def finish(self, status, **extra):
        self.config.update(status=status, elapsed_seconds=time.monotonic() - self.started,
                           ended_at=datetime.now(timezone.utc).isoformat(), **extra)
        self.config['output_sha256'] = {p.name: file_hash(p) for p in self.folder.iterdir()
                                        if p.is_file() and p.name != 'run_config.json'}
        save_json(self.folder / 'run_config.json', self.config)


class Progress:
    def __init__(self):
        self.state = ('init', 0, 0, time.monotonic(), 0)
        self.stop = threading.Event()
        self.worker = threading.Thread(target=self.heartbeat, daemon=True)
        self.worker.start()

    def set(self, phase, done, total):
        self.state = (phase, done, total, time.monotonic(), done)
        self.report()

    def advance(self, done):
        phase, _, total, started, initial = self.state
        self.state = (phase, done, total, started, initial)
        self.report()

    def report(self):
        phase, done, total, started, initial = self.state
        elapsed = time.monotonic() - started
        eta = f'{elapsed * (total - done) / (done - initial):.0f}s' if done > initial else 'unknown'
        percent = f'{done / total:.1%}' if total else 'N/A'
        print(f'[{phase}] {done}/{total} ({percent}) elapsed={elapsed:.0f}s ETA={eta}', flush=True)

    def heartbeat(self):
        while not self.stop.wait(30):
            self.report()


class Server:
    def __init__(self, model_path=None, projector_path=None):
        self.process = None
        self.model_path = Path(model_path) if model_path else None
        self.projector_path = Path(projector_path) if projector_path else None

    def close(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(15)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.process = None

    def launch(self, run, vision, context):
        self.close()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        self.url = f'http://127.0.0.1:{port}'
        cmd = [str(qa.SERVER), '-m', str(self.model_path or qa.CORPUS_MODEL),
               '--host', '127.0.0.1', '--port', str(port),
               '-c', str(context), '-ngl', 'all', '--parallel', '1', '--jinja', '--reasoning', 'off']
        if vision:
            projector = self.projector_path or cap.PROJECTOR
            if not projector.is_file():
                raise FileNotFoundError(f'Missing multimodal projector: {projector}')
            cmd += ['--mmproj', str(projector), '--image-max-tokens', str(ANSWER_IMAGE_MAX_TOKENS)]
        else:
            cmd += ['--no-mmproj', '--no-context-shift']
        log_path = run.folder / ('caption_server.log' if vision else 'answer_server.log')
        with log_path.open('a', encoding='utf-8') as log:
            self.process = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f'llama-server exited {self.process.returncode}; see {log_path}')
            try:
                if requests.get(self.url + '/health', timeout=2).ok:
                    return
            except requests.ConnectionError:
                pass
            time.sleep(1)
        raise TimeoutError(f'Server startup timeout; see {log_path}')

    def post(self, endpoint, payload):
        result = requests.post(self.url + endpoint, json=payload, timeout=(10, 900))
        result.raise_for_status()
        return result.json()

    def complete(self, messages, schema, max_tokens):
        result = self.post('/v1/chat/completions', {
            'messages': messages, 'temperature': 0, 'seed': 2025, 'max_tokens': max_tokens,
            'chat_template_kwargs': {'enable_thinking': False},
            'response_format': {'type': 'json_object', 'schema': schema},
        })
        return result['choices'][0], result.get('usage')

    def generate(self, messages, schema, max_tokens):
        choice, usage = self.complete(messages, schema, max_tokens)
        if choice['finish_reason'] != 'stop':
            raise GenerationIncomplete(choice, usage)
        return json.loads(choice['message']['content']), usage


class TransformerAnswerer:
    """Hugging Face answer generation with optional multimodal model inputs."""
    MODELS = {
        'qwen3.5-9b-transformers': ('Qwen/Qwen3.5-9B', 'qwen'),
        'gemma-3-12b-it': ('google/gemma-3-12b-it', 'gemma'),
    }

    def __init__(self, name, dtype, gpu_memory_limit_gib=None):
        self.name = name
        self.model_id, self.family = self.MODELS[name]
        self.dtype_name = dtype
        default_limit = 23 if self.family == 'gemma' else 27
        self.gpu_memory_limit = f'{gpu_memory_limit_gib or default_limit}GiB'
        self.tokenizer = None
        self.processor = None
        self.model = None

    def launch(self, run, vision, context):
        import torch
        from transformers import AutoTokenizer
        if not torch.cuda.is_available():
            raise RuntimeError('Transformers answer generation requires a CUDA GPU.')
        if self.dtype_name == 'bf16' and not torch.cuda.is_bf16_supported():
            raise RuntimeError('GPU không hỗ trợ BF16; chọn --answer-dtype fp16.')
        import transformers
        if vision:
            from transformers import AutoProcessor
            self.processor = AutoProcessor.from_pretrained(self.model_id)
            self.tokenizer = self.processor.tokenizer
            if self.family == 'qwen':
                from transformers import Qwen3_5ForConditionalGeneration
                model_class_name = 'Qwen3_5ForConditionalGeneration'
                max_pixels = ANSWER_IMAGE_MAX_TOKENS * 28 * 28
                self.processor.image_processor.max_pixels = max_pixels
                model_class = Qwen3_5ForConditionalGeneration
            else:
                from transformers import Gemma3ForConditionalGeneration
                model_class_name = 'Gemma3ForConditionalGeneration'
                model_class = Gemma3ForConditionalGeneration
        else:
            model_class_name = 'Qwen3_5ForCausalLM' if self.family == 'qwen' else 'Gemma3ForConditionalGeneration'
            model_class = getattr(transformers, model_class_name, None)
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_id, use_fast=True)
        if model_class is None:
            raise RuntimeError(f'Transformers thiếu {model_class_name}; cần Transformers mới có hỗ trợ model này.')
        dtype = torch.bfloat16 if self.dtype_name == 'bf16' else torch.float16
        self.tokenizer.padding_side = 'left'
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        self.model = model_class.from_pretrained(
            self.model_id, torch_dtype=dtype, device_map='auto', low_cpu_mem_usage=True,
            max_memory={0: self.gpu_memory_limit, 'cpu': '64GiB'})
        self.model.eval()
        run.config['answer_model_runtime'] = {
            'model_id': self.model_id, 'model_class': model_class_name,
            'dtype': self.dtype_name, 'device_map': 'auto', 'context_window': context,
            'gpu': torch.cuda.get_device_name(0), 'gpu_memory_limit': self.gpu_memory_limit,
            'vision': vision,
            'processor_max_pixels': ANSWER_IMAGE_MAX_TOKENS * 28 * 28
            if vision and self.family == 'qwen' else None,
            'revision': getattr(self.model.config, '_commit_hash', None),
        }
        print(f'[answer-model] loaded {self.model_id} ({self.dtype_name}); context={context}', flush=True)

    @staticmethod
    def _processor_messages(messages):
        from PIL import Image
        converted = []
        for message in messages:
            content = message['content']
            if not isinstance(content, list):
                converted.append(message)
                continue
            pieces = []
            for part in content:
                if part.get('type') == 'text':
                    pieces.append({'type': 'text', 'text': part['text']})
                elif part.get('type') == 'image_url':
                    url = part['image_url']['url']
                    if not url.startswith('data:image/png;base64,'):
                        raise ValueError('Transformers vision expects an in-memory PNG image.')
                    image_bytes = base64.b64decode(url.split(',', 1)[1])
                    with Image.open(BytesIO(image_bytes)) as image:
                        pieces.append({'type': 'image', 'image': image.convert('RGB')})
                else:
                    raise ValueError(f'Unsupported multimodal prompt item: {part.get("type")}')
            converted.append({**message, 'content': pieces})
        return converted

    def post(self, endpoint, payload):
        if self.tokenizer is None:
            raise RuntimeError('Answer tokenizer is not loaded.')
        if endpoint == '/apply-template':
            template_args = {'tokenize': False, 'add_generation_prompt': True}
            if self.family == 'qwen':
                template_args['enable_thinking'] = False
            prompt = self.tokenizer.apply_chat_template(payload['messages'], **template_args)
            return {'prompt': prompt}
        if endpoint == '/tokenize':
            return {'tokens': self.tokenizer.encode(payload['content'], add_special_tokens=False)}
        raise ValueError(f'Unsupported Transformers answer endpoint: {endpoint}')

    def complete(self, messages, schema, max_tokens):
        import torch
        kwargs = {'tokenize': True, 'add_generation_prompt': True, 'return_dict': True,
                  'return_tensors': 'pt'}
        if self.family == 'qwen':
            kwargs['enable_thinking'] = False
        else:
            kwargs['do_pan_and_scan'] = False
        if self.processor is not None:
            messages = self._processor_messages(messages)
            inputs = self.processor.apply_chat_template(messages, **kwargs)
        else:
            inputs = self.tokenizer.apply_chat_template(messages, **kwargs)
        inputs = inputs.to(self.model.device)
        with torch.inference_mode():
            output = self.model.generate(**inputs, max_new_tokens=max_tokens, do_sample=False,
                                         use_cache=True, pad_token_id=self.tokenizer.pad_token_id)
        generated = output[0, inputs['input_ids'].shape[-1]:]
        content = (self.processor.decode(generated, skip_special_tokens=True) if self.processor is not None
                   else self.tokenizer.decode(generated, skip_special_tokens=True))
        eos = self.tokenizer.eos_token_id
        eos_ids = set(eos if isinstance(eos, (list, tuple)) else ([] if eos is None else [eos]))
        ended = bool(generated.numel() and int(generated[-1]) in eos_ids)
        return {'choices': [{'finish_reason': 'stop' if ended else 'length',
                             'message': {'content': content}}]}, {
            'completion_tokens': int(generated.numel())}

    def generate(self, messages, schema, max_tokens):
        response, usage = self.complete(messages, schema, max_tokens)
        choice = response['choices'][0]
        try:
            payload = json.loads(choice['message']['content'])
        except json.JSONDecodeError:
            if choice['finish_reason'] != 'stop':
                partial = choice['message']['content']
                extracted = {}
                for field in ('visual_matching', 'legal_rule_extraction', 'option_evaluation', 'final_answer'):
                    match = re.search(r'"' + field + r'"\s*:\s*("(?:\\.|[^"\\])*")', partial, re.DOTALL)
                    if match:
                        try:
                            extracted[field] = json.loads(match.group(1))
                        except json.JSONDecodeError:
                            pass
                if extracted.get('final_answer', '').strip():
                    missing = 'Không trích xuất được từ phần JSON bị cắt.'
                    return {field: extracted.get(field, missing) for field in
                            ('visual_matching', 'legal_rule_extraction', 'option_evaluation', 'final_answer')}, usage
                raise GenerationIncomplete(choice, usage)
            raise
        if choice['finish_reason'] != 'stop' and not isinstance(payload, dict):
            raise GenerationIncomplete(choice, usage)
        return payload, usage

    def close(self):
        if getattr(self, 'model', None) is not None:
            del self.model
        if getattr(self, 'processor', None) is not None:
            del self.processor
        if getattr(self, 'tokenizer', None) is not None:
            del self.tokenizer
        import torch
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


class HFCaptioner:
    """Full-precision-family Qwen3.5 captioner loaded directly through Transformers."""
    def __init__(self, model_id, dtype):
        import torch
        from transformers import AutoProcessor, Qwen3_5ForConditionalGeneration
        self.torch = torch
        self.dtype = {'bf16': torch.bfloat16, 'fp16': torch.float16}[dtype]
        if not torch.cuda.is_available():
            raise RuntimeError('Qwen3.5 captioning requires a CUDA GPU.')
        if dtype == 'bf16' and not torch.cuda.is_bf16_supported():
            raise RuntimeError('GPU không hỗ trợ BF16; chọn --caption-dtype fp16.')
        self.processor = AutoProcessor.from_pretrained(model_id)
        self.model = Qwen3_5ForConditionalGeneration.from_pretrained(
            model_id, torch_dtype=self.dtype, device_map='auto')
        self.model.eval()
        self.model_id = model_id
        self.revision = getattr(self.model.config, '_commit_hash', None)

    def generate(self, image_path, prompt, max_tokens):
        from PIL import Image
        with Image.open(image_path) as source:
            image = source.convert('RGB')
            messages = [{'role': 'user', 'content': [
                {'type': 'image', 'image': image}, {'type': 'text', 'text': prompt}]}]
            inputs = self.processor.apply_chat_template(
                messages, tokenize=True, add_generation_prompt=True, return_dict=True,
                return_tensors='pt', enable_thinking=False)
            inputs = inputs.to(self.model.device)
            with self.torch.inference_mode():
                output = self.model.generate(**inputs, max_new_tokens=max_tokens, do_sample=False)
            generated = output[0, inputs['input_ids'].shape[1]:]
            content = self.processor.decode(generated, skip_special_tokens=True)
            eos = self.model.generation_config.eos_token_id
            eos_ids = set(eos if isinstance(eos, (list, tuple)) else ([] if eos is None else [eos]))
            ended = bool(generated.numel() and int(generated[-1]) in eos_ids)
            return {'message': {'content': content}, 'finish_reason': 'stop' if ended else 'length'}, {
                'completion_tokens': int(generated.numel())}

    def close(self):
        del self.model, self.processor
        self.torch.cuda.empty_cache()
        gc.collect()


EMBEDDERS = {
    'bge-m3': ('BAAI/bge-m3', None),
    'jina-v5-retrieval': ('jinaai/jina-embeddings-v5-text-small-retrieval', 'jina'),
    'f2llm-v2-0.6b': ('codefuse-ai/F2LLM-v2-0.6B', None),
    'f2llm-v2-1.7b': ('codefuse-ai/F2LLM-v2-1.7B', None),
}


class NaturalEncoder:
    def __init__(self, name, dtype):
        import torch
        self.name = name
        self.model_id, self.family = EMBEDDERS[name]
        self.dtype = {'bf16': torch.bfloat16, 'fp16': torch.float16}[dtype]
        if name == 'bge-m3':
            self.tokenizer, self.model, self.resources = load_encoder()
            self.dimension = 1024
            self.pooling = 'CLS'
            self.revision = REVISION
        else:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(self.model_id, device='cuda', model_kwargs={'dtype': self.dtype})
            self.tokenizer = None
            self.dimension = int(self.model.get_sentence_embedding_dimension())
            self.pooling = 'model_default'
            self.resources = {'gpu': torch.cuda.get_device_name(0)}
            first = self.model._first_module()
            base_model = getattr(first, 'auto_model', None)
            self.revision = getattr(getattr(base_model, 'config', None), '_commit_hash', None)

    def encode(self, texts, role='query'):
        if self.name == 'bge-m3':
            return embed_batch(texts, self.tokenizer, self.model)
        prompt_name = 'query' if role == 'query' and self.family == 'jina' else (
            'document' if role == 'document' and self.family == 'jina' else None)
        values = self.model.encode(texts, batch_size=8, normalize_embeddings=True,
                                   convert_to_numpy=True, prompt_name=prompt_name)
        vectors = np.asarray(values, dtype=np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.maximum(norms, 1e-12)

    def metadata(self):
        metadata = {'model': self.model_id, 'revision': self.revision,
                'dimension': self.dimension, 'normalize': 'L2', 'pooling': self.pooling,
                'query_prompt': 'query' if self.family == 'jina' else None,
                'document_prompt': 'document' if self.family == 'jina' else None,
                'inference_dtype': str(self.dtype), 'representation': 'question_relevant_items_v1'}
        if self.name == 'bge-m3' and hasattr(self, 'baseline_meta'):
            for key in ('model_files_sha256', 'pooling', 'normalize', 'dimension', 'stored_dtype', 'inference_dtype', 'input_prefix'):
                metadata[key] = self.baseline_meta.get(key)
        return metadata

    def close(self):
        del self.model
        if self.tokenizer is not None:
            del self.tokenizer
        import torch
        gc.collect()
        torch.cuda.empty_cache()


class CachedNaturalEncoder:
    """Expose metadata for a verified cache without loading encoder weights."""
    def __init__(self, name, metadata):
        self.name = name
        self._metadata = metadata
        self.dimension = int(metadata['dimension'])
        self.resources = {'embedding_source': 'verified_precomputed_cache'}

    def metadata(self):
        return self._metadata

    def close(self):
        pass


def embed_corpus(chunks, encoder, progress):
    vectors = []
    batch_size = 8
    progress.set('corpus-embedding-' + encoder.name, 0, len(chunks))
    for start in range(0, len(chunks), batch_size):
        texts = [chunk['text'] for chunk in chunks[start:start + batch_size]]
        vectors.extend(encoder.encode(texts, role='document'))
        progress.advance(min(start + batch_size, len(chunks)))
    return np.asarray(vectors, dtype=np.float32)


def caption_rows(run, rows, captioner, progress, name, allow_incomplete=False):
    captions = run.read('captions.jsonl', rows)
    reusable = set()
    for row in rows:
        saved = captions.get(row['id'])
        if saved is None:
            continue
        if saved.get('status') == 'COMPLETED':
            qa.query_representation(row['question'].strip(), saved, row['id'])
            reusable.add(row['id'])
        elif saved.get('status') == 'INCOMPLETE':
            if allow_incomplete:
                reusable.add(row['id'])
            elif (run.folder / 'embeddings.jsonl').exists():
                raise ValueError('Incomplete captions have existing embeddings. Keep --allow-incomplete-captions '
                                 'to resume, or use a new --output-dir before regenerating captions.')
        else:
            raise ValueError(f"Unknown caption status: {row['id']}")
    processed = len(reusable)
    progress.set(name + '-caption', processed, len(rows))
    if processed < len(rows):
        for row in rows:
            if row['id'] in reusable:
                continue
            started = time.monotonic()
            choice, usage = captioner.generate(
                row['image'], cap.QUERY_PROMPT.replace('{question_text}', row['question'].strip()),
                cap.MAX_NEW_TOKENS)
            raw_description = choice['message']['content']
            description = raw_description.strip()
            if description.startswith('```'):
                lines = description.splitlines()
                if lines and lines[0].startswith('```'):
                    lines = lines[1:]
                if lines and lines[-1].strip() == '```':
                    lines = lines[:-1]
                description = '\n'.join(lines).strip()
            record = {'query_id': row['id'], 'image_id': row['image_id'],
                      'question_text': row['question'].strip(), 'description': description,
                      'raw_generation': raw_description,
                      'status': 'INCOMPLETE', 'finish_reason': choice.get('finish_reason'), 'usage': usage,
                      'elapsed_seconds': time.monotonic() - started, 'attempt': 1,
                      'max_tokens': cap.MAX_NEW_TOKENS, 'prompt_policy': 'original_batch',
                      'response_schema_sha256': digest(cap.QUERY_SCHEMA)}
            try:
                representation = qa.query_representation(row['question'].strip(), record, row['id'])
                record['representation_duplicate_item_indices'] = representation['duplicate_item_indices']
                if choice.get('finish_reason') == 'stop':
                    record['status'] = 'COMPLETED'
            except (json.JSONDecodeError, ValueError, TypeError, KeyError) as exc:
                record['validation_error'] = str(exc)
            captions[row['id']] = run.store_caption(row, record, captions)
            if record['status'] == 'INCOMPLETE':
                print(f"[warning] {row['id']}: caption INCOMPLETE; finish_reason={record['finish_reason']}; continue next query", flush=True)
            processed += 1
            progress.advance(processed)
        captioner.close()
    incomplete = [r['id'] for r in rows if captions[r['id']]['status'] == 'INCOMPLETE']
    print(f'[{name}-caption-summary] completed={len(rows) - len(incomplete)}/{len(rows)} '
          f'incomplete={len(incomplete)} ids={incomplete}', flush=True)
    run.config['incomplete_queries'] = incomplete
    run.config['allow_incomplete_captions'] = allow_incomplete
    if allow_incomplete and incomplete:
        run.config['accepted_incomplete_queries'] = incomplete
        print(f'[caption-acceptance] --allow-incomplete-captions: recover complete items for {len(incomplete)} queries; keep raw INCOMPLETE status.', flush=True)
    return captions


def captions_ready(run, rows, captions, allow_incomplete):
    incomplete = [r['id'] for r in rows if captions[r['id']]['status'] == 'INCOMPLETE']
    if incomplete and not allow_incomplete:
        run.finish('INCOMPLETE', completed=len(rows) - len(incomplete), incomplete_queries=incomplete)
        print('[INCOMPLETE] Caption batch finished; no embedding for this split. '
              'Rerun to regenerate incomplete captions, or pass --allow-incomplete-captions '
              'to explicitly recover complete items using the original pipeline.', flush=True)
        return False
    # Validate recovery for EVERY query before loading the embedding model.
    for row in rows:
        try:
            qa.query_representation(row['question'].strip(), captions[row['id']], row['id'],
                                    allow_incomplete=allow_incomplete)
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError(f"Cannot recover caption {row['id']}: {exc}") from exc
    return True


def load_existing_captions(rows, root, qa_module, cap_module):
    """Reuse original train/dev captions without copying them into natural-QA outputs."""
    caption_root = qa_module.ROOT / 'artifacts/experiments/text_based_rag/query'
    by_query = {}
    provenance = {}
    for split in ('train', 'dev'):
        folder = caption_root / f'query_image_captioning_{split}'
        maps_path = folder / 'query_image_mapping.jsonl'
        captions_path = folder / 'image_captions.jsonl'
        embeddings_path = qa_module.ROOT / f'artifacts/experiments/text_based_rag/query/query_embedding_{split}/queries.jsonl'
        if not maps_path.is_file() or not captions_path.is_file():
            raise FileNotFoundError(f'Existing {split} caption cache is missing: {folder}')
        mappings = [json.loads(line) for line in maps_path.read_text(encoding='utf-8').splitlines() if line.strip()]
        cached = {item['query_id']: item for item in
                  (json.loads(line) for line in captions_path.read_text(encoding='utf-8').splitlines() if line.strip())}
        accepted = {}
        if embeddings_path.is_file():
            accepted = {item['query_id']: item for item in
                        (json.loads(line) for line in embeddings_path.read_text(encoding='utf-8').splitlines()
                         if line.strip()) if item.get('accepted_caption') is True}
        for mapping in mappings:
            item = cached.get(mapping['query_id'])
            if item is None or item.get('status') != 'COMPLETED':
                continue
            if mapping['image_id'] != item.get('image_id'):
                raise ValueError(f"Caption/cache image hash mismatch: {mapping['query_id']}")
            if mapping['query_id'] in by_query:
                raise ValueError(f"Duplicate cached caption query ID: {mapping['query_id']}")
            record = {
                'image_id': mapping['image_id'], 'description': item['description'],
                'status': 'COMPLETED', 'finish_reason': item.get('finish_reason'),
                'source_caption_query_id': mapping['query_id'],
                'source_image_id': mapping['source_image_id'],
            }
            if mapping['query_id'] in accepted:
                record.update(accepted_by_user=True, original_status='INCOMPLETE')
            by_query[mapping['query_id']] = record
        provenance[split] = {str(maps_path.relative_to(qa_module.ROOT)): file_hash(maps_path),
                             str(captions_path.relative_to(qa_module.ROOT)): file_hash(captions_path)}
        if embeddings_path.is_file():
            provenance[str(embeddings_path.relative_to(qa_module.ROOT))] = file_hash(embeddings_path)
    result = {}
    for row in rows:
        caption = by_query.get(row['id'])
        if caption is None:
            raise ValueError(f"No existing train/dev caption for query {row['id']}; "
                             'this run is configured to reuse captions and will not generate new ones.')
        if caption['source_image_id'] != row['image_id']:
            raise ValueError(f"Cached caption query/image mapping differs for {row['id']}")
        actual_hash = 'sha256:' + file_hash(Path(row['image']))
        if actual_hash != caption['image_id']:
            raise ValueError(f"Cached caption belongs to a different image: {row['id']}")
        # Validate with the current natural question; the cached description text itself remains unchanged.
        qa_module.query_representation(row['question'].strip(), caption, row['id'])
        result[row['id']] = caption
    return result, provenance


def embed_rows(run, rows, captions, progress, name, encoder, allow_incomplete=False,
               precomputed_path=None, precomputed_manifest=None):
    records = run.read('embeddings.jsonl', rows)
    progress.set(name + '-embedding', len(records), len(rows))
    representations = {r['id']: qa.query_representation(r['question'].strip(), captions[r['id']], r['id'],
                                                       allow_incomplete=allow_incomplete) for r in rows}
    for row in rows:
        if row['id'] in records and records[row['id']]['representation'] != representations[row['id']]:
            raise ValueError(f"Embedding/caption mismatch: {row['id']}")
    if len(records) < len(rows):
        run.config['embedding_resources'] = encoder.resources
        cached = None
        if precomputed_path is not None:
            if not precomputed_manifest or precomputed_manifest.get('status') != 'COMPLETED':
                raise ValueError(f'Precomputed embeddings lack a COMPLETED manifest: {precomputed_path}')
            expected_hash = precomputed_manifest.get('output_sha256', {}).get('embeddings.jsonl')
            if not expected_hash or file_hash(precomputed_path) != expected_hash:
                raise ValueError(f'Precomputed embedding file hash mismatch: {precomputed_path}')
            cached_rows = [json.loads(line) for line in precomputed_path.read_text(encoding='utf-8').splitlines() if line.strip()]
            cached = {record['id']: record for record in cached_rows}
            if (len(cached) != len(cached_rows) or not {row['id'] for row in rows}.issubset(cached)
                    or any(record.get('cache_fingerprint') != precomputed_manifest.get('cache_fingerprint')
                           for record in cached_rows)
                    or any(record.get('record_sha256') != digest({k: v for k, v in record.items()
                                                                  if k != 'record_sha256'})
                           for record in cached_rows)):
                raise ValueError(f'Precomputed embedding records do not match their manifest or sample IDs: {precomputed_path}')
        for row in rows:
            if row['id'] in records:
                continue
            if cached is not None:
                source_record = cached[row['id']]
                vector = np.asarray(source_record.get('vector'), dtype=np.float32)
                # The sample digest includes an absolute image path. Across machines,
                # verify the cache/file hashes and exact model input representation instead.
                if (source_record.get('representation') != representations[row['id']]
                        or vector.shape != (encoder.dimension,) or not np.isfinite(vector).all()
                        or not np.isclose(np.linalg.norm(vector), 1.0, atol=1e-5)):
                    raise ValueError(f'Precomputed embedding does not match current input: {row["id"]}')
            else:
                vector = encoder.encode([representations[row['id']]['text']], role='query')[0]
            records[row['id']] = run.append('embeddings.jsonl', row, {
                'representation': representations[row['id']], 'vector': vector.tolist(),
            })
            progress.advance(len(records))
    vectors = np.asarray([records[r['id']]['vector'] for r in rows], dtype=np.float32)
    if (vectors.shape != (len(rows), encoder.dimension) or not np.isfinite(vectors).all()
            or not np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5)):
        raise ValueError(f'Invalid {encoder.name} vectors in {run.folder}')
    return representations, vectors


def embed_natural_captions(args, root, qa_module, cap_module):
    """Create standalone embeddings from the natural-QA caption artifacts."""
    split_output = {
        'train': qa_module.ROOT / 'artifacts/experiments/text_based_rag/natural_qa/query_embeddings',
        'public_test': qa_module.ROOT / 'artifacts/public-test/text_based_rag/natural_qa/query_embeddings',
        'private_test': qa_module.ROOT / 'artifacts/private_test/text_based_rag/natural_qa/query_embeddings',
    }
    caption_default = {
        'train': qa_module.ROOT / 'artifacts/experiments/text_based_rag/natural_qa/image_captioning/train',
        'public_test': qa_module.ROOT / 'artifacts/public-test/text_based_rag/natural_qa/image_captioning',
        'private_test': qa_module.ROOT / 'artifacts/private_test/text_based_rag/natural_qa/image_captioning',
    }
    source, rows = load_rows(root, args.split)
    caption_dir = (args.caption_dir or caption_default[args.split]).expanduser().resolve()
    output = (args.output_dir or split_output[args.split] / args.embedding_model).expanduser().resolve()
    caption_manifest_path = caption_dir / 'manifest.json'
    mapping_path = caption_dir / 'query_image_mapping.jsonl'
    caption_manifest = json.loads(caption_manifest_path.read_text(encoding='utf-8-sig'))
    if (caption_manifest.get('status') not in {'COMPLETED', 'INCOMPLETE'}
            or caption_manifest.get('split') != args.split
            or caption_manifest.get('input_sha256') != file_hash(source)):
        raise ValueError('Caption manifest chưa hoàn tất hoặc không khớp split/nguồn query.')
    mapping = [json.loads(line) for line in mapping_path.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    by_id = {item['query_id']: item for item in mapping}
    if len(by_id) != len(mapping) or set(by_id) != {row['id'] for row in rows}:
        raise ValueError('Query không khớp query_image_mapping.jsonl.')
    representations, caption_hashes, image_hashes, statuses = {}, {}, {}, {}
    progress = Progress()
    encoder = None
    run = None
    try:
        progress.set('validate-natural-captions', 0, len(rows))
        for row in rows:
            item = by_id[row['id']]
            caption_path = (caption_dir / item['caption_file']).resolve()
            if (caption_path.parent != (caption_dir / 'captions').resolve()
                    or item.get('source_image_id') != row['image_id']
                    or item.get('filename') != row['image_id'] + '.jpg'
                    or item.get('image_id') != 'sha256:' + file_hash(Path(row['image']))):
                raise ValueError(f"Caption/image mapping không hợp lệ: {row['id']}")
            caption = json.loads(caption_path.read_text(encoding='utf-8-sig'))
            if (caption.get('query_id') != row['id'] or caption.get('image_id') != item['image_id']
                    or caption.get('question_text') != row['question']
                    or caption.get('status') not in {'COMPLETED', 'INCOMPLETE'}
                    or not isinstance(caption.get('description'), str) or not caption['description'].strip()):
                raise ValueError(f"Caption không hợp lệ: {row['id']}")
            representations[row['id']] = qa_module.query_representation(
                row['question'].strip(), caption, row['id'], allow_incomplete=True)
            caption_hashes[item['caption_file']] = file_hash(caption_path)
            image_hashes[item['filename']] = item['image_id']
            statuses[row['id']] = caption['status']
            progress.advance(len(representations))
        from text_based_rag.corpus_embedding import REVISION as BGE_REVISION
        source_files = {str(p.relative_to(qa_module.ROOT)): file_hash(p)
                        for p in sorted((qa_module.ROOT / 'src').rglob('*.py'))}
        config = {
            'pipeline': 'natural_caption_query_embedding_only', 'split': args.split,
            'samples': len(rows), 'embedding_model': args.embedding_model,
            'embedding_dtype': args.embedding_dtype, 'representation': 'question_relevant_items_v1',
            'incomplete_caption_policy': 'recover_complete_items_and_keep_question_only_fallback',
            'accepted_incomplete_ids': [qid for qid, status in statuses.items() if status == 'INCOMPLETE'],
            'source_sha256': file_hash(source), 'caption_manifest_sha256': file_hash(caption_manifest_path),
            'caption_mapping_sha256': file_hash(mapping_path), 'caption_files_sha256': caption_hashes,
            'image_files_sha256': image_hashes, 'source_files_sha256': source_files,
            'packages': installed_package_versions(('numpy', 'torch', 'transformers', 'sentence-transformers', 'Pillow')),
            'bge_reference_revision': BGE_REVISION if args.embedding_model == 'bge-m3' else None,
        }
        if getattr(args, 'id_filter', None):
            config['id_filter'] = args.id_filter
        run = Run(output, config)
        records = run.read('embeddings.jsonl', rows)
        encoder = NaturalEncoder(args.embedding_model, args.embedding_dtype)
        if args.embedding_model == 'bge-m3':
            corpus_manifest = json.loads((qa_module.CORPUS.parent / 'corpus_embedding/manifest.json').read_text(encoding='utf-8-sig'))
            encoder.baseline_meta = corpus_manifest
        run.config['encoder'] = encoder.metadata()
        run.config['gpu'] = subprocess.check_output(
            ['nvidia-smi', '--query-gpu=name,memory.total,driver_version', '--format=csv,noheader'], text=True).strip()
        for row in rows:
            existing = records.get(row['id'])
            if existing and existing.get('representation') != representations[row['id']]:
                raise ValueError(f"Cached embedding/caption mismatch: {row['id']}")
        progress.set(args.split + '-embedding-' + args.embedding_model, len(records), len(rows))
        pending = [row for row in rows if row['id'] not in records]
        for start in range(0, len(pending), 8):
            batch = pending[start:start + 8]
            vectors = encoder.encode([representations[row['id']]['text'] for row in batch], role='query')
            if vectors.shape != (len(batch), encoder.dimension) or not np.isfinite(vectors).all():
                raise ValueError('Encoder sinh vector sai shape hoặc chứa giá trị không hữu hạn.')
            for row, vector in zip(batch, vectors):
                records[row['id']] = run.append('embeddings.jsonl', row, {
                    'representation': representations[row['id']], 'vector': vector.tolist()})
                progress.advance(len(records))
        vectors = np.asarray([records[row['id']]['vector'] for row in rows], dtype=np.float32)
        if (vectors.shape != (len(rows), encoder.dimension) or not np.isfinite(vectors).all()
                or not np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5)):
            raise ValueError(f'Embedding không hợp lệ: {output}')
        run.finish('COMPLETED', completed=len(rows), question_only_fallbacks=[
            qid for qid, value in representations.items() if value['representation_mode'] == 'question_only'])
        print(f'[COMPLETED] {len(rows)} embeddings; {output / "embeddings.jsonl"}', flush=True)
    except BaseException:
        if run is not None and run.config['status'] == 'RUNNING':
            run.finish('FAILED', error=traceback.format_exc())
        raise
    finally:
        if encoder is not None:
            encoder.close()
        progress.stop.set()
        progress.worker.join()


def load_fresh_caption_artifacts(rows, root, split, args, qa_module):
    """Load and validate the new per-query natural captions for a runner split."""
    folders = {
        'train': qa_module.ROOT / 'artifacts/experiments/text_based_rag/natural_qa/image_captioning/train',
        'public_test': qa_module.ROOT / 'artifacts/public-test/text_based_rag/natural_qa/image_captioning',
        'private_test': qa_module.ROOT / 'artifacts/private_test/text_based_rag/natural_qa/image_captioning',
    }
    if split == args.split and args.caption_dir:
        caption_dir = args.caption_dir.expanduser().resolve()
    elif split == 'train' and getattr(args, 'train_caption_dir', None):
        caption_dir = args.train_caption_dir.expanduser().resolve()
    else:
        caption_dir = folders[split].expanduser().resolve()
    source, source_rows = load_rows(root, split)
    manifest_path, mapping_path = caption_dir / 'manifest.json', caption_dir / 'query_image_mapping.jsonl'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    if (manifest.get('status') not in {'COMPLETED', 'INCOMPLETE'} or manifest.get('split') != split
            or manifest.get('input_sha256') != file_hash(source)
            or manifest.get('settings', {}).get('caption_unit') != 'query_id'):
        raise ValueError(f'Natural caption manifest không khớp nguồn/split/schema: {caption_dir}')
    mapping = [json.loads(line) for line in mapping_path.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    by_id = {item['query_id']: item for item in mapping}
    if (len(by_id) != len(mapping) or set(by_id) != {row['id'] for row in source_rows}
            or not {row['id'] for row in rows}.issubset(by_id)):
        raise ValueError(f'Natural caption mapping không khớp query IDs: {caption_dir}')
    captions, provenance = {}, {'manifest_sha256': file_hash(manifest_path),
                                'mapping_sha256': file_hash(mapping_path), 'caption_files_sha256': {}}
    allowed = {'COMPLETED', 'INCOMPLETE'} if args.allow_incomplete_captions else {'COMPLETED'}
    for row in rows:
        item = by_id[row['id']]
        caption_path = (caption_dir / item['caption_file']).resolve()
        image_hash = 'sha256:' + file_hash(Path(row['image']))
        if (caption_path.parent != (caption_dir / 'captions').resolve()
                or item.get('source_image_id') != row['image_id']
                or item.get('filename') != row['image_id'] + '.jpg'
                or item.get('image_id') != image_hash):
            raise ValueError(f'Natural caption/image mapping sai: {row["id"]}')
        caption = json.loads(caption_path.read_text(encoding='utf-8-sig'))
        if (caption.get('query_id') != row['id'] or caption.get('image_id') != image_hash
                or caption.get('question_text') != row['question'] or caption.get('status') not in allowed
                or not isinstance(caption.get('description'), str) or not caption['description'].strip()):
            raise ValueError(f'Natural caption không hợp lệ hoặc chưa được chấp nhận: {row["id"]}')
        qa_module.query_representation(row['question'].strip(), caption, row['id'],
                                       allow_incomplete=args.allow_incomplete_captions)
        captions[row['id']] = caption
        provenance['caption_files_sha256'][item['caption_file']] = file_hash(caption_path)
    return captions, provenance


@lru_cache(maxsize=8)
def answer_image_content(image_path):
    """Encode the source image for llama.cpp, preserving pixels in PNG form."""
    from PIL import Image

    path = Path(image_path)
    with Image.open(path) as original, BytesIO() as buffer:
        original.convert('RGB').save(buffer, format='PNG', optimize=True)
        encoded = base64.b64encode(buffer.getvalue()).decode('ascii')
    return {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + encoded}}


def attach_answer_images(messages, examples, query_image):
    """Attach each retrieved example image to its user turn and the query image last."""
    result = [dict(message) for message in messages]
    for index, example in enumerate(examples):
        message_index = index * 2
        result[message_index]['content'] = [
            {'type': 'text', 'text': result[message_index]['content']},
            answer_image_content(example['image']),
        ]
    result[-1]['content'] = [
        {'type': 'text', 'text': result[-1]['content'] + '\n\nẢnh gốc của câu hỏi hiện tại:'},
        answer_image_content(query_image),
    ]
    return result


def fit_answer_context(server, question, visual_description, laws, hits, context, answer_max_tokens,
                       fewshot_examples=None, current_context_budget=20000, query_image=None,
                       answer_with_images=False):
    """Keep current query evidence within its cap, then pack relevant examples into remaining context."""
    budget = context - answer_max_tokens - 128
    fewshot_examples = list(fewshot_examples or [])
    image_reserve = ANSWER_IMAGE_MAX_TOKENS if answer_with_images else 0
    current_budget = min(current_context_budget, budget - image_reserve * (1 + len(fewshot_examples)))
    if current_budget < 1:
        raise ValueError('Image token reserve leaves no space for current question context.')
    laws, used_hits, dropped, shortened = list(laws), list(hits), [], []

    def current_messages(parts):
        prompt_template = (qa.OPEN_PROMPT_QWEN_TRANSFORMERS
                           if getattr(server, 'name', None) == 'qwen3.5-9b-transformers'
                           else qa.OPEN_PROMPT)
        prompt = prompt_template.format(retrieved_laws='\n\n'.join(parts),
                                      visual_description='' if answer_with_images else visual_description,
                                      question=question)
        prompt += ('\n\nYÊU CẦU ĐỘ DÀI: Mỗi trường phân tích tối đa một câu ngắn; '
                   'final_answer tối đa hai câu. Chỉ nêu căn cứ và kết luận cần thiết, '
                   'không lặp lại quy định hoặc liệt kê giả định không cần thiết.')
        if answer_with_images:
            prompt += ('\n\nẢNH GỐC được đính kèm: hãy quan sát trực tiếp hình dạng, màu sắc, chữ, số, '
                       'biển phụ và vị trí; căn cứ vào ảnh và điều luật được truy xuất, không dùng mô tả caption.')
        return [{'role': 'user', 'content': prompt}]

    def token_count(messages):
        template = server.post('/apply-template', {'messages': messages, 'chat_template_kwargs': {'enable_thinking': False}})
        count = len(server.post('/tokenize', {'content': template['prompt'], 'add_special': True, 'parse_special': True})['tokens'])
        return count

    messages = current_messages(laws)
    count = token_count(messages)
    original_tokens = count
    while count > current_budget and len(laws) > 1:
        laws.pop()
        dropped.append(used_hits.pop())
        messages = current_messages(laws)
        count = token_count(messages)
    if count > current_budget:
        original = laws[0]
        note = '\n[Phần cuối điều luật đã được cắt để vừa context; không suy đoán nội dung bị thiếu.]'
        low, high = 0, len(original)
        best_messages = current_messages([note])
        best_count = token_count(best_messages)
        if best_count > current_budget:
            raise ValueError('Question and visual description exceed context even with all law text removed.')
        # Runtime tokenization includes the template and note at every candidate.
        while low < high:
            mid = (low + high + 1) // 2
            candidate_messages = current_messages([original[:mid] + note])
            candidate_count = token_count(candidate_messages)
            if candidate_count <= current_budget:
                low = mid
                best_messages, best_count = candidate_messages, candidate_count
            else:
                high = mid - 1
        laws[0] = original[:low] + note
        messages, count = best_messages, best_count
        shortened.append({'law_id': used_hits[0]['law_id'], 'article_id': used_hits[0]['article_id'],
                          'original_characters': len(original), 'kept_characters': low,
                          'kept_text_sha256': hashlib.sha256(original[:low].encode()).hexdigest()})
        if low == 0:
            dropped.append(used_hits.pop())
    query_messages = current_messages(laws)
    query_count = token_count(query_messages)
    selected = list(fewshot_examples)
    messages = []
    for example in selected:
        messages.extend([
            {'role': 'user', 'content': (
                'Ví dụ tham khảo (chỉ để học cách trả lời; không dùng sự kiện, luật hoặc kết luận của ví dụ '
                'làm bằng chứng cho câu hỏi hiện tại).'
                + ('  Mỗi ví dụ có ảnh gốc kèm theo.\n' if answer_with_images else '\n')
                + ('' if answer_with_images else f'Mô tả hình: {example["visual_description"]}\n')
                + f'Câu hỏi: {example["question"]}'
            )},
            {'role': 'assistant', 'content': example['answer']},
        ])
    messages.extend(query_messages)
    while selected and token_count(messages) + image_reserve * (1 + len(selected)) > budget:
        selected.pop()
        messages = []
        for example in selected:
            messages.extend([
                {'role': 'user', 'content': (
                    'Ví dụ tham khảo (chỉ để học cách trả lời; không dùng sự kiện, luật hoặc kết luận của ví dụ '
                    'làm bằng chứng cho câu hỏi hiện tại).'
                    + ('  Mỗi ví dụ có ảnh gốc kèm theo.\n' if answer_with_images else '\n')
                    + ('' if answer_with_images else f'Mô tả hình: {example["visual_description"]}\n')
                    + f'Câu hỏi: {example["question"]}'
                )},
                {'role': 'assistant', 'content': example['answer']},
            ])
        messages.extend(query_messages)
    image_tokens_reserved = image_reserve * (1 + len(selected))
    text_tokens = token_count(messages)
    total_tokens = text_tokens + image_tokens_reserved
    if answer_with_images:
        if query_image is None:
            raise ValueError('Query image is required for --answer-with-images.')
        messages = attach_answer_images(messages, selected, query_image)
    return messages, total_tokens, laws, used_hits, {
        'context_truncated': bool(dropped or shortened or len(selected) < len(fewshot_examples)),
        'original_input_tokens': original_tokens,
        'input_token_budget': budget, 'current_context_budget': current_budget,
        'current_query_tokens': query_count,
        'image_tokens_reserved': image_tokens_reserved,
        'answer_image_count': (1 + len(selected)) if answer_with_images else 0,
        'dropped_citations': dropped, 'shortened_citations': shortened,
        'fewshot_requested': len(fewshot_examples), 'fewshot_used_ids': [e['query_id'] for e in selected],
        'fewshot_dropped_ids': [e['query_id'] for e in fewshot_examples[len(selected):]],
        'input_tokens': total_tokens,
    }


def load_kb_articles(path):
    """Option C (experiment): per question id, the law articles a knowledge base names for
    its photo, in priority order. JSONL lines {"id", "articles": [{"law_id", "article_id", ...}]}."""
    out = {}
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if line.strip():
            record = json.loads(line)
            out[str(record['id'])] = [{'law_id': str(a['law_id']), 'article_id': str(a['article_id'])}
                                      for a in record.get('articles', [])]
    return out


def with_kb_hits(hits, articles, registry, limit=1):
    """Append up to `limit` knowledge-base articles that retrieval did not already return, after
    the retrieved hits (so context packing drops them first). Articles the law registry cannot
    resolve are skipped. Returns (hits, added)."""
    from text_based_rag import inference as kb_qa

    present = {(str(h['law_id']), str(h['article_id'])) for h in hits}
    out, added = list(hits), []
    for article in articles:
        if len(added) >= limit:
            break
        key = (article['law_id'], article['article_id'])
        if key in present:
            continue
        try:
            kb_qa.resolve_citation(article, registry)
        except (KeyError, ValueError):
            continue
        present.add(key)
        hit = {'law_id': key[0], 'article_id': key[1], 'rank': len(out) + 1, 'score': 0.0, 'sources': ['kb']}
        out.append(hit)
        added.append(hit)
    return out, added


def answer_rows(run, rows, representations, retrievals, registry, server, progress, context, answer_max_tokens,
                fewshot_data, current_context_budget, answer_with_images=False, kb=None, kb_limit=1):
    answers = run.read('predictions.jsonl', rows)
    progress.set('answer', len(answers), len(rows))
    if len(answers) == len(rows):
        return answers
    server.launch(run, answer_with_images, context)
    schema = {'type': 'object', 'additionalProperties': False, 'required': list(qa.FIELDS),
              'properties': {k: {'type': 'string', 'minLength': 1} for k in qa.FIELDS}}
    for row in rows:
        if row['id'] in answers:
            continue
        started = time.monotonic()
        retrieval = retrievals[row['id']]['retrieval']
        selected_examples = [
            {'query_id': neighbor['query_id'], **fewshot_data[neighbor['query_id']]}
            for neighbor in retrieval.get('fewshot_neighbors', [])
            if neighbor['query_id'] in fewshot_data
        ]
        hits, laws = sorted(retrieval['results'], key=lambda hit: hit['rank']), []
        retrieved_hits = list(hits)
        kb_added = []
        if kb is not None:
            hits, kb_added = with_kb_hits(hits, kb.get(str(row['id']), []), registry, kb_limit)
        for hit in hits:
            text, _ = qa.resolve_citation(hit, registry)
            laws.append(f"[Hạng {hit['rank']}; điểm {hit['score']:.4f}]\n{text}")
        usage, nt, attempt = None, 0, 0
        truncation = {'context_truncated': False, 'original_input_tokens': 0,
            'input_token_budget': context - answer_max_tokens - 128,
            'current_context_budget': min(current_context_budget, context - answer_max_tokens - 128),
            'current_query_tokens': 0, 'fewshot_requested': len(selected_examples),
            'fewshot_used_ids': [], 'fewshot_dropped_ids': [], 'dropped_citations': [], 'shortened_citations': []}
        if not hits and not answer_with_images:
            payload = {k: '' for k in qa.FIELDS}
            payload['final_answer'] = 'Mình chưa tìm thấy điều luật phù hợp để trả lời câu hỏi này.'
        else:
            messages, nt, laws, hits, truncation = fit_answer_context(
                server, row['question'].strip(), representations[row['id']]['text'], laws, hits, context,
                answer_max_tokens, selected_examples, current_context_budget,
                query_image=row['image'] if answer_with_images else None,
                answer_with_images=answer_with_images)
            if truncation['context_truncated']:
                print(f"[context-pack] {row['id']} current={truncation['original_input_tokens']}->"
                      f"{truncation['current_query_tokens']} total={nt} "
                      f"current_budget={truncation['current_context_budget']} total_budget={truncation['input_token_budget']} "
                      f"dropped_laws={len(truncation['dropped_citations'])} "
                      f"shortened={len(truncation['shortened_citations'])} "
                      f"fewshot_dropped={len(truncation['fewshot_dropped_ids'])}", flush=True)
            skipped_oom = False
            for attempt in range(1, 4):
                try:
                    payload, usage = server.generate(messages, schema, answer_max_tokens)
                    if set(payload) != set(qa.FIELDS) or any(not isinstance(payload[k], str) or not payload[k].strip() for k in qa.FIELDS):
                        raise ValueError('Invalid answer schema')
                    break
                except Exception as exc:
                    run.append('errors.jsonl', row, {'phase': 'answer', 'attempt': attempt, 'error': str(exc)})
                    if 'out of memory' in str(exc).lower():
                        import torch
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                        skipped_oom = True
                        break
                    if attempt == 3:
                        raise
            if skipped_oom:
                saved = run.append('predictions.jsonl', row, {
                    **row, 'status': 'SKIPPED_OOM', 'answer': '', 'analysis_summary': {},
                    'citations': hits, 'gate': retrieval['gate'], 's_max': retrieval['s_max'],
                    'retrieved_citations': retrieved_hits, 'answer_context': context, **truncation,
                    'input_tokens': nt, 'usage': usage, 'elapsed_seconds': time.monotonic() - started,
                    'attempt': attempt, 'skip_reason': 'cuda_out_of_memory',
                    'retrieved_laws_sha256': hashlib.sha256('\n\n'.join(laws).encode()).hexdigest(),
                    'fewshot_requested': truncation.get('fewshot_requested', 0),
                    'fewshot_used_ids': truncation.get('fewshot_used_ids', []),
                    'fewshot_dropped_ids': truncation.get('fewshot_dropped_ids', []),
                    'current_query_tokens': truncation.get('current_query_tokens', 0),
                })
                answers[row['id']] = saved
                progress.advance(len(answers))
                continue
        answers[row['id']] = run.append('predictions.jsonl', row, {
            **row, 'status': 'COMPLETED', 'answer': qa.normalized(payload['final_answer']),
            'analysis_summary': payload, 'citations': hits, 'gate': retrieval['gate'], 's_max': retrieval['s_max'],
            'retrieved_citations': retrieved_hits, 'answer_context': context, **truncation,
            'input_tokens': nt, 'usage': usage, 'elapsed_seconds': time.monotonic() - started, 'attempt': attempt,
            'retrieved_laws_sha256': hashlib.sha256('\n\n'.join(laws).encode()).hexdigest(),
            'fewshot_requested': truncation.get('fewshot_requested', 0),
            'fewshot_used_ids': truncation.get('fewshot_used_ids', []),
            'fewshot_dropped_ids': truncation.get('fewshot_dropped_ids', []),
            'current_query_tokens': truncation.get('current_query_tokens', 0),
            **({'kb_added_citations': kb_added} if kb is not None else {}),
        })
        progress.advance(len(answers))
    server.close()
    return answers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-root', type=Path, required=True, help='Natural dataset/ directory containing train data/ and test folders.')
    parser.add_argument('--split', choices=('validation', 'public_test', 'private_test', 'train'), default='validation')
    parser.add_argument('--output-dir', type=Path, help='Default: artifacts/experiments/text_based_rag/natural_qa/<embedding-model>/')
    parser.add_argument('--embedding-model', choices=tuple(EMBEDDERS), default='bge-m3')
    answer_models = ('qwen3.5-9b-gguf', 'qwen3.5-9b-gguf-bf16',
                     'gemma-3-12b-it-gguf-f16', *TransformerAnswerer.MODELS)
    parser.add_argument('--answer-model', choices=answer_models, default='qwen3.5-9b-gguf',
                        help='Answer generator: Qwen/Gemma GGUF via llama.cpp or a full Transformers checkpoint.')
    parser.add_argument('--answer-dtype', choices=('bf16', 'fp16'), default='bf16',
                        help='Inference dtype for full Transformers answer models.')
    parser.add_argument('--answer-gpu-memory-limit', type=int, default=None,
                        help='Maximum VRAM assigned to the Transformers answer model, in GiB; remaining weights may be offloaded to system RAM.')
    parser.add_argument('--corpus-chunks', type=Path, help='Chunk output directory; defaults to the project corpus_chunking artifact.')
    parser.add_argument('--embedding-dtype', choices=('bf16', 'fp16'), default='bf16')
    parser.add_argument('--reuse-precomputed-embeddings', action='store_true',
                        help='Reuse hash-verified corpus/train/query embedding artifacts for this encoder and split.')
    parser.add_argument('--retrieval-only', action='store_true', help='Stop after saving corpus/example/hybrid retrieval; do not generate answers.')
    parser.add_argument('--prepare-bank-only', action='store_true', help='Caption/embed natural train and stop before test processing.')
    parser.add_argument('--context-size', type=int, default=65536)
    parser.add_argument('--fewshot-k', type=int, choices=(0, 1, 3, 5, 7), default=0,
                        help='Number of question-type-matched train examples to prepend.')
    parser.add_argument('--answer-with-images', action='store_true',
                        help='Attach the original query image and selected few-shot train images to multimodal answer prompts.')
    parser.add_argument('--current-context-budget', type=int, default=20000,
                        help='Token cap for current laws + caption text + question; remaining input space is for examples.')
    parser.add_argument('--answer-max-tokens', type=int, default=2048,
                        help='Maximum generated answer tokens; input context budget reserves this plus 128 overhead tokens.')
    parser.add_argument('--allow-incomplete-captions', action='store_true',
                        help='Explicitly recover complete items from saved INCOMPLETE captions using the original pipeline.')
    parser.add_argument('--embedding-only', action='store_true', help='Embed natural caption query representations; skip corpus retrieval and answers.')
    parser.add_argument('--caption-dir', type=Path, help='Natural-QA image-caption artifact directory; defaults by split.')
    parser.add_argument('--fresh-captions', action='store_true',
                        help='Use the new per-query natural caption artifacts for train and query splits.')
    parser.add_argument('--corpus-k', type=int, default=5)
    parser.add_argument('--examples-k', type=int, default=5)
    parser.add_argument('--high-examples-k', type=int, default=3)
    parser.add_argument('--gate-low', type=float, default=0.70)
    parser.add_argument('--gate-high', type=float, default=0.82)
    parser.add_argument('--weight-high', type=float, default=0.9)
    parser.add_argument('--weight-middle', type=float, default=0.6)
    parser.add_argument('--weight-low', type=float, default=0.3)
    parser.add_argument('--kb-articles', type=Path, default=None,
                        help='Experiment (option C): JSONL of knowledge-base articles per question id, appended after retrieval.')
    parser.add_argument('--kb-limit', type=int, default=1, help='At most this many knowledge-base articles per question.')
    parser.add_argument('--ids', type=Path, default=None,
                        help='Run only these question ids of the test split (JSON list or one per line).')
    parser.add_argument('--train-caption-dir', type=Path, default=None,
                        help='With --fresh-captions: the train (example-bank) caption artifacts to read instead of the default.')
    parser.add_argument('--query-embeddings-dir', type=Path, default=None,
                        help='With --reuse-precomputed-embeddings: the query-embedding cache to read instead of the split default.')
    args = parser.parse_args()
    id_filter = None
    if args.ids:
        if args.split not in {'public_test', 'private_test'}:
            parser.error('--ids applies to public_test or private_test.')
        id_filter = set_id_filter(args.ids)
    if args.query_embeddings_dir and not args.reuse_precomputed_embeddings:
        parser.error('--query-embeddings-dir requires --reuse-precomputed-embeddings.')
    if args.answer_max_tokens < 1:
        parser.error('--answer-max-tokens must be positive.')
    if args.answer_gpu_memory_limit is not None:
        if args.answer_gpu_memory_limit < 1:
            parser.error('--answer-gpu-memory-limit must be positive.')
        if args.answer_model not in TransformerAnswerer.MODELS:
            parser.error('--answer-gpu-memory-limit applies only to Transformers answer models.')
    if args.current_context_budget < 1:
        parser.error('--current-context-budget must be positive.')
    if args.context_size < args.answer_max_tokens + 128 and not args.retrieval_only:
        parser.error('--context-size must leave space for --answer-max-tokens and 128 overhead tokens.')
    # Keep --help usable before GPU/model dependencies are installed.
    global np, requests, qa, cap, load_encoder, embed_batch, file_hash, REVISION
    import numpy as np
    import requests
    from text_based_rag import inference as qa
    from text_based_rag import query_image_captioning as cap
    from text_based_rag.corpus_embedding import REVISION, load_encoder, embed_batch, file_hash
    from text_based_rag.query_retrieval import retrieve_user_query, TOP_K

    qwen_gguf_models = ('qwen3.5-9b-gguf', 'qwen3.5-9b-gguf-bf16')
    llama_cpp_gguf_models = (*qwen_gguf_models, 'gemma-3-12b-it-gguf-f16')
    qwen_bf16_gguf = qa.ROOT / 'models/huggingface/Qwen3.5-9B-GGUF/Qwen3.5-9B-BF16.gguf'
    gemma_f16_gguf = qa.ROOT / 'models/huggingface/Gemma-3-12B-IT-GGUF/gemma-3-12b-it-f16.gguf'
    gemma_f16_mmproj = qa.ROOT / 'models/huggingface/Gemma-3-12B-IT-GGUF/mmproj-model-f16.gguf'
    if args.answer_model == 'qwen3.5-9b-gguf-bf16' and not qwen_bf16_gguf.is_file():
        parser.error(f'Qwen BF16 GGUF is missing: {qwen_bf16_gguf}')
    if args.answer_model == 'gemma-3-12b-it-gguf-f16':
        for model_file in (gemma_f16_gguf, gemma_f16_mmproj):
            if not model_file.is_file():
                parser.error(f'Gemma F16 GGUF or multimodal projector is missing: {model_file}')
    if args.answer_with_images and args.answer_model in qwen_gguf_models and not cap.PROJECTOR.is_file():
        parser.error(f'--answer-with-images requires the Qwen multimodal projector at {cap.PROJECTOR}.')

    if args.embedding_only:
        if args.reuse_precomputed_embeddings:
            parser.error('--reuse-precomputed-embeddings cannot be combined with --embedding-only.')
        if args.split not in {'train', 'public_test', 'private_test'}:
            parser.error('--embedding-only supports train, public_test, or private_test.')
        if not args.allow_incomplete_captions:
            parser.error('--embedding-only requires --allow-incomplete-captions for the accepted incomplete captions.')
        root = args.dataset_root.expanduser().resolve()
        args.id_filter = id_filter
        return embed_natural_captions(args, root, qa, cap)
    if args.split == 'train':
        parser.error("--split train chỉ dùng được cùng --embedding-only.")
    if args.reuse_precomputed_embeddings and not args.corpus_chunks:
        parser.error('--reuse-precomputed-embeddings requires --corpus-chunks pointing to a completed encoder train cache.')

    if args.fresh_captions and not args.allow_incomplete_captions:
        parser.error('--fresh-captions requires --allow-incomplete-captions for the accepted caption artifacts.')
    retrieval_settings = {
        'corpus_k': args.corpus_k, 'examples_k': args.examples_k,
        'high_examples_k': args.high_examples_k, 'low_threshold': args.gate_low,
        'high_threshold': args.gate_high, 'weight_high': args.weight_high,
        'weight_middle': args.weight_middle, 'weight_low': args.weight_low,
    }
    if not (args.gate_low < args.gate_high and 1 <= args.corpus_k <= 20
            and 1 <= args.examples_k <= 20 and 1 <= args.high_examples_k <= args.examples_k
            and all(0 <= retrieval_settings[f'weight_{gate}'] <= 1 for gate in ('high', 'middle', 'low'))):
        parser.error('Retrieval k/threshold/weight values are outside supported ranges.')
    progress = Progress()
    if args.answer_model in TransformerAnswerer.MODELS:
        server = TransformerAnswerer(args.answer_model, args.answer_dtype, args.answer_gpu_memory_limit)
    elif args.answer_model == 'qwen3.5-9b-gguf-bf16':
        server = Server(qwen_bf16_gguf, cap.PROJECTOR)
    elif args.answer_model == 'gemma-3-12b-it-gguf-f16':
        server = Server(gemma_f16_gguf, gemma_f16_mmproj)
    else:
        server = Server()
    captioner = None
    encoder = None
    runs = []
    try:
        progress.set('validate-inputs-models-artifacts', 0, 0)
        root = args.dataset_root.expanduser().resolve()
        if args.output_dir:
            output = args.output_dir.expanduser().resolve()
        elif args.answer_model == 'qwen3.5-9b-gguf':
            output = (qa.ROOT / 'artifacts/experiments/text_based_rag/natural_qa' / args.embedding_model).resolve()
        else:
            output = (qa.ROOT / 'artifacts/experiments/text_based_rag/natural_qa/answer_comparison'
                      / args.answer_model / args.embedding_model).resolve()
        train_source, train = load_rows(root, 'train')
        if args.split == 'validation' and not args.prepare_bank_only:
            image_ids = sorted({str(row['image_id']) for row in train})
            random.Random(2025).shuffle(image_ids)
            dev_images = set(image_ids[:max(1, round(len(image_ids) * 0.2))])
            rows = [row for row in train if str(row['image_id']) in dev_images]
            bank_source_rows = [row for row in train if str(row['image_id']) not in dev_images]
            test_source = train_source
        else:
            test_source, rows = (None, []) if args.prepare_bank_only else load_rows(root, args.split)
            bank_source_rows = train
        if args.split != 'validation' and {r['id'] for r in train} & {r['id'] for r in rows}:
            raise ValueError('Train/test IDs overlap.')
        natural_law = root / 'law_db/vlsp2025_law.json'
        if json.loads(natural_law.read_text(encoding='utf-8-sig')) != json.loads(qa.LAW_SOURCE.read_text(encoding='utf-8-sig')):
            raise ValueError('Natural law content differs from the indexed corpus; corpus must be prepared explicitly.')
        corpus_root = qa.CORPUS.parent
        corpus_meta = json.loads((corpus_root / 'corpus_embedding/manifest.json').read_text(encoding='utf-8-sig'))
        chunking_folder = corpus_root / 'corpus_chunking'
        chunk_dir = args.corpus_chunks.expanduser().resolve() if args.corpus_chunks else chunking_folder
        chunk_file = chunk_dir / 'chunks.jsonl'
        chunk_manifest_file = chunk_dir / 'manifest.json'
        if not chunk_file.is_file() and (chunk_dir / 'corpus_chunks.jsonl').is_file():
            chunk_file = chunk_dir / 'corpus_chunks.jsonl'
            chunk_manifest_file = chunk_dir / 'run_config.json'
        chunk_manifest = json.loads(chunk_manifest_file.read_text(encoding='utf-8-sig'))
        if chunk_manifest.get('status') != 'COMPLETED':
            raise ValueError(f'Chunk input chưa COMPLETED: {chunk_manifest_file}')
        expected_chunk_hash = chunk_manifest.get('output_sha256', {}).get(chunk_file.name)
        if expected_chunk_hash and file_hash(chunk_file) != expected_chunk_hash:
            raise ValueError(f'Chunk input hash sai: {chunk_file}')
        precomputed_corpus_manifest = precomputed_train_manifest = precomputed_query_manifest = None
        precomputed_train_path = None
        precomputed_query_path = None
        precomputed_corpus_path = None
        cache_provenance = None
        if args.reuse_precomputed_embeddings:
            if chunk_dir.name != 'train':
                raise ValueError('--reuse-precomputed-embeddings expects --corpus-chunks to point to an encoder train cache folder.')
            precomputed_corpus_manifest = verified_run_cache(
                chunk_dir, ('corpus_vectors.npy', 'corpus_chunks.jsonl'))
            train_cache_dir = qa.ROOT / 'artifacts/experiments/text_based_rag/natural_qa/query_embeddings' / args.embedding_model
            precomputed_train_manifest = verified_run_cache(train_cache_dir, ('embeddings.jsonl',))
            query_root = {
                'public_test': qa.ROOT / 'artifacts/public-test/text_based_rag/natural_qa/query_embeddings',
                'private_test': qa.ROOT / 'artifacts/private_test/text_based_rag/natural_qa/query_embeddings',
            }.get(args.split)
            if query_root is None:
                raise ValueError('Precomputed query embedding cache supports public_test or private_test.')
            query_cache_dir = (args.query_embeddings_dir.expanduser().resolve() if args.query_embeddings_dir
                               else query_root / args.embedding_model)
            precomputed_query_manifest = verified_run_cache(query_cache_dir, ('embeddings.jsonl',))
            expected_model = EMBEDDERS[args.embedding_model][0]
            for label, manifest in (('corpus', precomputed_corpus_manifest),
                                    ('train', precomputed_train_manifest), ('query', precomputed_query_manifest)):
                metadata = manifest.get('encoder', {})
                if (manifest.get('embedding_model') != args.embedding_model
                        or metadata.get('model') != expected_model
                        or manifest.get('embedding_dtype') != args.embedding_dtype
                        or int(metadata.get('dimension', 0)) < 1):
                    raise ValueError(f'Precomputed {label} embedding metadata does not match {args.embedding_model}.')
            if precomputed_query_manifest.get('split') != args.split:
                raise ValueError(f'Precomputed query embeddings are for {precomputed_query_manifest.get("split")}, not {args.split}.')
            if precomputed_train_manifest.get('split') != 'train':
                raise ValueError('Precomputed training embeddings do not have split=train.')
            precomputed_train_path = train_cache_dir / 'embeddings.jsonl'
            precomputed_query_path = query_cache_dir / 'embeddings.jsonl'
            precomputed_corpus_path = chunk_dir / 'corpus_vectors.npy'
            cache_provenance = {
                'policy': 'reuse hash-verified corpus/train/query embeddings',
                'corpus_cache_dir': str(chunk_dir),
                'train_query_cache_dir': str(train_cache_dir),
                'query_cache_dir': str(query_cache_dir),
                'corpus_manifest_sha256': file_hash(chunk_dir / 'run_config.json'),
                'train_manifest_sha256': file_hash(train_cache_dir / 'run_config.json'),
                'query_manifest_sha256': file_hash(query_cache_dir / 'run_config.json'),
                'corpus_vectors_sha256': file_hash(precomputed_corpus_path),
                'train_embeddings_sha256': file_hash(precomputed_train_path),
                'query_embeddings_sha256': file_hash(precomputed_query_path),
            }
        natural_chunks = qa.read_lines(chunk_file)
        registry = qa.user_corpus_registry()
        chunks = qa.read_lines(corpus_root / 'corpus_embedding/chunks.jsonl')
        valid = {(str(c['document_id']), str(c['id'])) for c in chunks}
        kept, excluded = [], []
        for row in train:
            invalid = [c for c in row['relevant_articles'] if (c['law_id'], c['article_id']) not in valid]
            if invalid:
                excluded.append({'id': row['id'], 'reason': 'citation_not_in_corpus', 'invalid_citations': invalid})
            else:
                kept.append(row)
        if len(kept) < TOP_K:
            raise ValueError('Not enough natural train examples with valid citations.')
        print(f'[natural-bank] source={len(train)} kept={len(kept)} excluded={excluded}', flush=True)
        train = kept
        bank_source_rows = [row for row in bank_source_rows if row in train]
        rows = [row for row in rows if row in train] if args.split == 'validation' else rows
        if args.fresh_captions:
            train_captions, train_caption_provenance = load_fresh_caption_artifacts(
                train, root, 'train', args, qa)
            query_captions, query_caption_provenance = load_fresh_caption_artifacts(
                rows, root, args.split, args, qa) if rows else ({}, {})
            caption_source = 'new_natural_per_query_captions'
            caption_provenance = {'train': train_caption_provenance, 'query': query_caption_provenance}
        else:
            train_captions, caption_provenance = load_existing_captions(train, root, qa, cap)
            query_captions = load_existing_captions(rows, root, qa, cap)[0] if rows else {}
            caption_source = 'existing_query_image_captioning_train_and_dev'
        common = {
            'pipeline': 'natural question + selected caption artifacts + selected encoder + gated hybrid + selected answer model',
            'caption_source': caption_source,
            'reused_caption_files_sha256': caption_provenance,
            'embedding_model': args.embedding_model, 'embedding_dtype': args.embedding_dtype,
            'precomputed_embedding_cache': cache_provenance,
            'answer_model': args.answer_model,
            'answer_model_id': (TransformerAnswerer.MODELS[args.answer_model][0]
                                if args.answer_model in TransformerAnswerer.MODELS else
                                'Qwen/Qwen3.5-9B (BF16 GGUF)' if args.answer_model == 'qwen3.5-9b-gguf-bf16'
                                else 'google/gemma-3-12b-it (F16 GGUF)' if args.answer_model == 'gemma-3-12b-it-gguf-f16'
                                else 'Qwen/Qwen3.5-9B-Q4_K_M GGUF'),
            'answer_dtype': (args.answer_dtype if args.answer_model in TransformerAnswerer.MODELS else
                             'BF16' if args.answer_model == 'qwen3.5-9b-gguf-bf16' else
                             'F16' if args.answer_model == 'gemma-3-12b-it-gguf-f16' else 'Q4_K_M'),
            'answer_prompt_policy': ('naturalqa_open_qwen_final_first_short_analysis_v1'
                                     if args.answer_model == 'qwen3.5-9b-transformers'
                                     else 'naturalqa_open_v1'),
            'answer_gpu_memory_limit_gib': (int(server.gpu_memory_limit.removesuffix('GiB'))
                                            if args.answer_model in TransformerAnswerer.MODELS else None),
            'answer_image_policy': ('original_query_plus_selected_fewshot_train_images' if args.answer_with_images
                                    else 'text_only'),
            'answer_image_encoding': 'source_pixels_to_rgb_png' if args.answer_with_images else None,
            'answer_image_max_tokens_each': ANSWER_IMAGE_MAX_TOKENS if args.answer_with_images else None,
            'answer_image_max_pixels_transformers': (
                ANSWER_IMAGE_MAX_TOKENS * 28 * 28
                if args.answer_with_images and args.answer_model == 'qwen3.5-9b-transformers' else None),
            'answer_image_text_policy': ('omit_captions_from_answer_prompt' if args.answer_with_images
                                         else 'caption_text_available'),
            'answer_model_file': (str(server.model_path or qa.CORPUS_MODEL)
                                  if args.answer_model in llama_cpp_gguf_models and not args.retrieval_only else None),
            'answer_model_file_sha256': (file_hash(server.model_path or qa.CORPUS_MODEL)
                                         if args.answer_model in llama_cpp_gguf_models and not args.retrieval_only else None),
            'answer_projector_sha256': (file_hash(server.projector_path or cap.PROJECTOR)
                                        if args.answer_with_images and args.answer_model in llama_cpp_gguf_models
                                        else None),
            'fresh_captions': args.fresh_captions,
            'corpus_chunk_manifest_sha256': (chunk_manifest.get('corpus_chunk_manifest_sha256')
                                             if chunk_manifest_file.name == 'run_config.json'
                                             else file_hash(chunk_manifest_file)),
            'corpus_chunk_file_sha256': file_hash(chunk_file),
            'representation': 'question_relevant_items_v1',
            'train_source_sha256': file_hash(train_source), 'excluded_train_samples': excluded,
            'law_files_sha256': {'natural': file_hash(natural_law), 'indexed_source': file_hash(qa.LAW_SOURCE)},
            'train_image_sha256': {r['image_id']: file_hash(Path(r['image'])) for r in train},
            'source_files_sha256': {str(p.relative_to(qa.ROOT)): file_hash(p) for p in sorted((qa.ROOT / 'src').rglob('*.py'))},
            'corpus_files_sha256': {str(p.relative_to(corpus_root)): file_hash(p) for p in sorted(corpus_root.rglob('*')) if p.is_file()},
            'packages': installed_package_versions(('numpy', 'torch', 'transformers', 'sentence-transformers', 'Pillow')),
            'retrieval': {**retrieval_settings, 'final_top_k': TOP_K,
                          'same_image_policy': 'allow_shared_images_as_existing_pipeline'},
        }
        gpu = ('not used: retrieval-only with verified precomputed embeddings'
               if args.retrieval_only and args.reuse_precomputed_embeddings else
               subprocess.check_output(['nvidia-smi', '--query-gpu=name,memory.total,driver_version',
                                        '--format=csv,noheader'], text=True).strip())
        train_config = {**common, 'split': 'train', 'samples': len(train)}
        # Validate BOTH destinations before loading embedding models.
        targets = [(output / 'train', train_config)]
        if not args.prepare_bank_only:
            test_config = {**common, 'split': args.split, 'samples': len(rows), 'answer_context': args.context_size,
                           'answer_context_policy': ('current_query_cap_then_pack_fewshot_images_v1'
                                                     if args.answer_with_images
                                                     else 'current_query_cap_then_pack_fewshot_v1'),
                           'fewshot_k': args.fewshot_k,
                           'fewshot_policy': 'cosine_neighbors_same_lowcost_question_type_train_bank_v1',
                           'fewshot_answer_source_sha256': file_hash(train_source) if args.fewshot_k else None,
                           'current_context_budget': args.current_context_budget,
                           'answer_max_tokens': args.answer_max_tokens, 'test_source_sha256': file_hash(test_source),
                           'test_image_sha256': {r['image_id']: file_hash(Path(r['image'])) for r in rows},
                           'example_bank_fingerprint': digest(train_config)}
            if id_filter:
                test_config['id_filter'] = id_filter
            if args.kb_articles:
                test_config['kb_articles'] = {'sha256': file_hash(args.kb_articles), 'limit': args.kb_limit,
                                              'policy': 'append_after_retrieval_skip_present_v1'}
            targets.append((output / args.split, test_config))
        for folder, config in targets:
            manifest = folder / 'run_config.json'
            if folder.exists() and any(folder.iterdir()):
                previous = json.loads(manifest.read_text()) if manifest.is_file() else {}
                if (digest({key: previous.get(key) for key in config}) != digest(config)
                        and not can_resume_caption_fix(folder, previous, config)
                        and not can_resume_context_fix(folder, previous, config)):
                    raise ValueError(f'Output/config mismatch: {folder}; use a new --output-dir. Existing results preserved.')
                if previous.get('status') == 'COMPLETED':
                    for name, expected in previous.get('output_sha256', {}).items():
                        if file_hash(folder / name) != expected:
                            raise ValueError(f'Completed cache changed: {folder / name}')
        train_run = Run(*targets[0])
        runs.append(train_run)
        train_run.config['gpu'] = gpu
        captions = train_captions
        progress.set('train-caption-reuse', len(train), len(train))
        encoder = (CachedNaturalEncoder(args.embedding_model, precomputed_train_manifest['encoder'])
                   if args.reuse_precomputed_embeddings
                   else NaturalEncoder(args.embedding_model, args.embedding_dtype))
        if args.embedding_model == 'bge-m3':
            encoder.baseline_meta = corpus_meta
        previous_encoder_revision = train_run.previous.get('encoder', {}).get('revision')
        if previous_encoder_revision and previous_encoder_revision != encoder.metadata()['revision']:
            raise ValueError('Embedding model revision changed; choose a new --output-dir to preserve prior results.')
        train_run.config['encoder'] = encoder.metadata()
        if args.reuse_precomputed_embeddings:
            progress.set('reuse-precomputed-corpus-embedding', len(natural_chunks), len(natural_chunks))
            corpus_vectors = np.load(precomputed_corpus_path, allow_pickle=False)
        else:
            corpus_vectors = embed_corpus(natural_chunks, encoder, progress)
        if corpus_vectors.shape != (len(natural_chunks), encoder.dimension):
            raise ValueError('Alternate corpus embeddings have unexpected shape.')
        if (not np.isfinite(corpus_vectors).all()
                or not np.allclose(np.linalg.norm(corpus_vectors, axis=1), 1, atol=1e-5)):
            raise ValueError('Corpus embedding cache contains invalid or non-normalized vectors.')
        corpus_index = {'chunks': natural_chunks, 'vectors': corpus_vectors, 'encoder': encoder.metadata()}
        np.save(train_run.folder / 'corpus_vectors.npy', corpus_vectors, allow_pickle=False)
        with (train_run.folder / 'corpus_chunks.jsonl').open('w', encoding='utf-8') as stream:
            for index, chunk in enumerate(natural_chunks):
                stream.write(json.dumps({**chunk, 'vector_row': index}, ensure_ascii=False) + '\n')
        train_representations, vectors = embed_rows(
            train_run, train, captions, progress, 'train', encoder, args.allow_incomplete_captions,
            precomputed_path=precomputed_train_path,
            precomputed_manifest=precomputed_train_manifest)
        train_position = {row['id']: index for index, row in enumerate(train)}
        bank_vectors = vectors[[train_position[row['id']] for row in bank_source_rows]]
        bank = {'queries': [{'query_id': r['id'], 'source_image_id': r['image_id'], 'question': r['question'], 'vector_row': i}
                            for i, r in enumerate(bank_source_rows)],
                'labels': {r['id']: r for r in bank_source_rows}, 'vectors': bank_vectors,
                'encoder': encoder.metadata()}
        fewshot_answers = load_fewshot_answers(train_source, bank_source_rows) if args.fewshot_k else {}
        fewshot_data = {}
        for row in bank_source_rows:
            if row['id'] not in fewshot_answers:
                continue
            encoded_text = train_representations[row['id']]['text']
            question_text = row['question'].strip()
            question_prefix = 'Câu hỏi:\n' + question_text
            if not encoded_text.startswith(question_prefix):
                raise ValueError(f'Unexpected train representation format for few-shot sample {row["id"]}.')
            fewshot_data[row['id']] = {
                'question': question_text,
                'visual_description': encoded_text[len(question_prefix):].strip(),
                'answer': fewshot_answers[row['id']],
                'image': row['image'],
            }
        train_run.finish('COMPLETED', completed=len(train))
        if args.prepare_bank_only:
            return
        test_config['example_bank_files_sha256'] = {
            name: file_hash(train_run.folder / name) for name in ('embeddings.jsonl',)
        }
        test_run = Run(*targets[1])
        runs.append(test_run)
        test_run.config['gpu'] = gpu
        captions = query_captions
        progress.set(args.split + '-caption-reuse', len(rows), len(rows))
        representations, query_vectors = embed_rows(
            test_run, rows, captions, progress, args.split, encoder, args.allow_incomplete_captions,
            precomputed_path=precomputed_query_path,
            precomputed_manifest=precomputed_query_manifest)
        retrievals = test_run.read('retrievals.jsonl', rows)
        corpus_branch_rows = test_run.read('retrieval_corpus.jsonl', rows)
        example_branch_rows = test_run.read('retrieval_examples.jsonl', rows)
        progress.set('gated-hybrid-natural-bank', len(retrievals), len(rows))
        for i, row in enumerate(rows):
            if row['id'] in retrievals:
                retrieval = retrievals[row['id']]['retrieval']
            else:
                retrieval = retrieve_user_query(query_vectors[i], representations[row['id']]['text'],
                                                example_bank=bank, corpus_index=corpus_index,
                                                settings=retrieval_settings)
                retrieval_record = {'retrieval': retrieval}
                if args.split == 'validation':
                    retrieval_record['gold_citations'] = row['relevant_articles']
                retrievals[row['id']] = test_run.append('retrievals.jsonl', row, retrieval_record)
            if row['id'] not in corpus_branch_rows:
                corpus_branch_rows[row['id']] = test_run.append('retrieval_corpus.jsonl', row, {
                    'query_text': retrieval['query_text'], 'results': retrieval['branches']['corpus']})
            if row['id'] not in example_branch_rows:
                example_branch_rows[row['id']] = test_run.append('retrieval_examples.jsonl', row, {
                    'query_text': retrieval['query_text'], 'neighbors': retrieval['neighbors'],
                    'results': retrieval['branches']['examples']})
            retrievals[row['id']]['retrieval']['fewshot_neighbors'] = select_fewshot_neighbors(
                query_vectors[i], row['question'], bank, fewshot_data, args.fewshot_k, row['id'])
            progress.advance(len(retrievals))
        if args.retrieval_only:
            test_run.finish('COMPLETED', completed=len(retrievals), retrieval_only=True,
                            validation_split={'seed': 2025, 'dev_ratio': 0.2, 'group_key': 'image_id'}
                            if args.split == 'validation' else None, evaluation_available=False)
            print(f'[COMPLETED] {len(retrievals)}/{len(rows)} retrievals; {test_run.folder / "retrievals.jsonl"}', flush=True)
        else:
            answers = answer_rows(test_run, rows, representations, retrievals, registry, server, progress,
                                  args.context_size, args.answer_max_tokens, fewshot_data,
                                  args.current_context_budget, args.answer_with_images,
                                  kb=load_kb_articles(args.kb_articles) if args.kb_articles else None,
                                  kb_limit=args.kb_limit)
            skipped_oom = [qid for qid, answer in answers.items() if answer.get('status') == 'SKIPPED_OOM']
            fewshot_distribution = {
                str(count): sum(len(answer.get('fewshot_used_ids', [])) == count for answer in answers.values())
                for count in range(args.fewshot_k + 1)
            }
            test_run.finish('COMPLETED', completed=len(answers) - len(skipped_oom), skipped_oom=len(skipped_oom),
                            skipped_oom_ids=skipped_oom, evaluation_available=False,
                            context_truncated_queries=[qid for qid, answer in answers.items() if answer.get('context_truncated')],
                            fewshot_used_count_distribution=fewshot_distribution)
            print(f'[COMPLETED] {len(answers) - len(skipped_oom)} completed, {len(skipped_oom)} skipped OOM; '
                  f'{test_run.folder / "predictions.jsonl"}', flush=True)
    except BaseException:
        for run in runs:
            if run.config['status'] == 'RUNNING':
                run.finish('FAILED', error=traceback.format_exc())
        raise
    finally:
        server.close()
        if captioner is not None:
            captioner.close()
        if encoder is not None:
            encoder.close()
        progress.stop.set()
        progress.worker.join()


if __name__ == '__main__':
    main()
