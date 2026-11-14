"""Tune natural-QA retrieval from saved validation candidates (CPU only)."""

import argparse
import csv
import hashlib
import itertools
import json
import numpy as np
import random
import time
from pathlib import Path
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[2]
CHUNKS = ('t768_o64', 't1024_o128', 't1280_o128')
ENCODERS = ('bge-m3', 'jina-v5-retrieval', 'f2llm-v2-0.6b', 'f2llm-v2-1.7b')
MODEL_FOLDER = {'t1024_o128': {'bge-m3': 'bge-m3_reused_captions'}}
DEFAULTS = {'corpus_k': 5, 'examples_k': 5, 'high_examples_k': 3,
            'low_threshold': 0.70, 'high_threshold': 0.82,
            'weight_high': 0.9, 'weight_middle': 0.6, 'weight_low': 0.3}
FINAL_K = 5


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def json_lines(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]


def load_input(artifact_root, dataset_root):
    dataset_file = dataset_root / 'train data/vlsp_2025_train.json'
    source_rows = json.loads(dataset_file.read_text(encoding='utf-8-sig'))
    source = {row['id']: row for row in source_rows}
    if len(source) != len(source_rows):
        raise ValueError('Natural train data contains duplicate IDs.')

    # Recreate the original image-group validation split to verify IDs and avoid image leakage.
    image_ids = sorted({str(row['image_id']) for row in source_rows})
    random.Random(2025).shuffle(image_ids)
    validation_images = set(image_ids[:max(1, round(len(image_ids) * 0.2))])
    expected_validation_ids = {row['id'] for row in source_rows if str(row['image_id']) in validation_images}

    variants = {}
    input_hashes = {str(dataset_file): sha256(dataset_file)}
    load_started = time.monotonic()
    done, total = 0, len(CHUNKS) * len(ENCODERS)
    for chunk in CHUNKS:
        variants[chunk] = {}
        for encoder in ENCODERS:
            folder_name = MODEL_FOLDER.get(chunk, {}).get(encoder, encoder)
            folder = artifact_root / chunk / folder_name / 'validation'
            run_path = folder / 'run_config.json'
            candidates_path = folder / 'retrievals.jsonl'
            manifest = json.loads(run_path.read_text(encoding='utf-8'))
            if manifest.get('status') != 'COMPLETED' or manifest.get('completed') != 112:
                raise ValueError(f'Run is not complete or has an unexpected query count: {run_path}')
            if manifest.get('caption_source') != 'existing query_image_captioning_train_and_dev':
                raise ValueError(f'Unexpected caption provenance: {run_path}')
            expected_hash = manifest.get('output_sha256', {}).get('retrievals.jsonl')
            if not expected_hash or sha256(candidates_path) != expected_hash:
                raise ValueError(f'Retrieval candidate file does not match its manifest: {candidates_path}')
            records = json_lines(candidates_path)
            by_id = {record['id']: record for record in records}
            if len(records) != len(by_id) or set(by_id) != expected_validation_ids:
                raise ValueError(f'Validation IDs do not match the seed-2025 image-group split: {candidates_path}')
            for qid, record in by_id.items():
                source_row = source[qid]
                expected_gold = {(str(x['law_id']), str(x['article_id'])) for x in source_row['relevant_articles']}
                actual_gold = {(str(x['law_id']), str(x['article_id'])) for x in record['gold_citations']}
                retrieval = record['retrieval']
                if expected_gold != actual_gold:
                    raise ValueError(f'Validation gold differs from source data: {qid}')
                if len(retrieval.get('branches', {}).get('corpus', [])) != 20:
                    raise ValueError(f'Expected 20 corpus candidates for {qid}.')
                if len(retrieval.get('candidate_neighbors', [])) != 20:
                    raise ValueError(f'Expected 20 example candidates for {qid}.')
            train_folder = folder.parent / 'train'
            vector_path = train_folder / 'corpus_vectors.npy'
            chunk_path = train_folder / 'corpus_chunks.jsonl'
            train_manifest_path = train_folder / 'run_config.json'
            embedding_path = folder / 'embeddings.jsonl'
            train_manifest = json.loads(train_manifest_path.read_text(encoding='utf-8'))
            for name, path in (('corpus_vectors.npy', vector_path), ('corpus_chunks.jsonl', chunk_path)):
                if train_manifest.get('output_sha256', {}).get(name) != sha256(path):
                    raise ValueError(f'Corpus vector/chunk file does not match its manifest: {path}')
            if manifest.get('output_sha256', {}).get('embeddings.jsonl') != sha256(embedding_path):
                raise ValueError(f'Query vector file does not match its manifest: {embedding_path}')
            corpus_vectors = np.load(vector_path, mmap_mode='r', allow_pickle=False)
            chunk_rows = json_lines(chunk_path)
            if corpus_vectors.ndim != 2 or corpus_vectors.shape[0] != len(chunk_rows):
                raise ValueError(f'Corpus vector/chunk dimensions do not match: {train_folder}')
            query_rows = json_lines(embedding_path)
            query_vectors = {row['id']: np.asarray(row['vector'], dtype=np.float32) for row in query_rows}
            if set(query_vectors) != expected_validation_ids or any(
                vector.shape != (corpus_vectors.shape[1],) for vector in query_vectors.values()
            ):
                raise ValueError(f'Query vector IDs/dimensions do not match the validation records: {embedding_path}')
            similarity_matrix = np.stack([query_vectors[qid] for qid in by_id]) @ np.asarray(corpus_vectors).T
            citation_chunks = {}
            for index, chunk_row in enumerate(chunk_rows):
                citation_chunks.setdefault((str(chunk_row['document_id']), str(chunk_row['id'])), []).append(index)
            all_corpus_scores = {}
            for row_index, qid in enumerate(by_id):
                scores = {citation: float(np.max(similarity_matrix[row_index, indices]))
                          for citation, indices in citation_chunks.items()}
                all_corpus_scores[qid] = scores
                exact_top20 = sorted(scores, key=lambda key: (-scores[key], key))[:20]
                saved_top20 = [citation_key(hit) for hit in by_id[qid]['retrieval']['branches']['corpus']]
                if exact_top20 != saved_top20:
                    raise ValueError(f'Recomputed corpus top-20 differs from saved candidates: {chunk}/{encoder}/{qid}')
                for hit in by_id[qid]['retrieval']['branches']['corpus']:
                    if abs(scores[citation_key(hit)] - float(hit['score'])) > 1e-5:
                        raise ValueError(f'Recomputed corpus score differs from saved candidate: {chunk}/{encoder}/{qid}')
            variants[chunk][encoder] = {
                'folder': folder, 'manifest': manifest, 'records': by_id,
                'groups': {qid: source[qid]['image_id'] for qid in by_id},
                'corpus_scores': all_corpus_scores,
                'corpus_chunk_count': len(json_lines(folder.parent / 'train/corpus_chunks.jsonl')),
            }
            input_hashes[str(run_path)] = sha256(run_path)
            input_hashes[str(candidates_path)] = sha256(candidates_path)
            input_hashes[str(train_manifest_path)] = sha256(train_manifest_path)
            input_hashes[str(vector_path)] = sha256(vector_path)
            input_hashes[str(chunk_path)] = sha256(chunk_path)
            input_hashes[str(embedding_path)] = sha256(embedding_path)
            done += 1
            elapsed = time.monotonic() - load_started
            eta = elapsed * (total - done) / done if done else 0
            print(f'[load-candidates] {done}/{total} ({done / total:.0%}) '
                  f'elapsed={elapsed:.0f}s ETA={eta:.0f}s', flush=True)
    return variants, input_hashes, source, expected_validation_ids


def citation_key(item):
    return str(item['law_id']), str(item['article_id'])


def rank_examples(neighbors, count):
    scores = {}
    for neighbor in neighbors[:count]:
        for label in neighbor['citations']:
            key = citation_key(label)
            scores[key] = max(scores.get(key, -1.0), float(neighbor['score']))
    return sorted(scores, key=lambda key: (-scores[key], key))[:20], scores


def make_predictions(records, params, all_corpus_scores):
    predictions, branch_corpus, branch_examples, gates = {}, {}, {}, {'high': 0, 'middle': 0, 'low': 0}
    for qid, saved in records.items():
        retrieval = saved['retrieval']
        corpus_scores = all_corpus_scores[qid]
        corpus_keys = sorted(corpus_scores, key=lambda key: (-corpus_scores[key], key))[:params['corpus_k']]
        neighbors = retrieval['candidate_neighbors']
        example_order, example_scores = rank_examples(neighbors, params['examples_k'])
        branch_corpus[qid] = corpus_keys[:FINAL_K]
        branch_examples[qid] = example_order[:FINAL_K]

        s_max = float(neighbors[0]['score'])
        gate = 'high' if s_max >= params['high_threshold'] else (
            'low' if s_max < params['low_threshold'] else 'middle')
        gates[gate] += 1
        if gate == 'high':
            high_n = min(params['high_examples_k'], params['examples_k'])
            candidate_keys = {citation_key(label) for neighbor in neighbors[:high_n]
                              for label in neighbor['citations']}
        else:
            candidate_keys = set(corpus_scores) | set(example_scores)

        weight = params[f'weight_{gate}']
        fused = []
        for key in candidate_keys:
            corpus_score = corpus_scores.get(key)
            example_score = example_scores.get(key)
            normalized_corpus = (corpus_score + 1.0) / 2.0 if corpus_score is not None else 0.0
            normalized_example = (example_score + 1.0) / 2.0 if example_score is not None else 0.0
            score = weight * normalized_example + (1.0 - weight) * normalized_corpus
            fused.append((key, score))
        fused.sort(key=lambda item: (-item[1], item[0]))
        predictions[qid] = [key for key, _ in fused[:FINAL_K]]
    return predictions, branch_corpus, branch_examples, gates


def metric_report(records, predictions):
    per_query = {}
    totals = {'tp': 0, 'predicted': 0, 'gold': 0}
    for qid, record in records.items():
        gold = {citation_key(item) for item in record['gold_citations']}
        predicted = set(predictions[qid])
        tp = len(gold & predicted)
        p = tp / len(predicted) if predicted else 0.0
        r = tp / len(gold) if gold else 0.0
        f1 = 2 * tp / (len(predicted) + len(gold)) if predicted or gold else 0.0
        f2 = 5 * tp / (len(predicted) + 4 * len(gold)) if predicted or gold else 0.0
        per_query[qid] = {'precision': p, 'recall': r, 'f1': f1, 'f2': f2, 'hit': int(tp > 0),
                          'tp': tp, 'predicted': len(predicted), 'gold': len(gold)}
        totals['tp'] += tp
        totals['predicted'] += len(predicted)
        totals['gold'] += len(gold)
    n = len(per_query)
    macro = {key: sum(row[key] for row in per_query.values()) / n for key in ('precision', 'recall', 'f1', 'f2', 'hit')}
    tp, predicted, gold = totals['tp'], totals['predicted'], totals['gold']
    micro = {'precision': tp / predicted if predicted else 0.0,
             'recall': tp / gold if gold else 0.0,
             'f1': 2 * tp / (predicted + gold) if predicted + gold else 0.0,
             'f2': 5 * tp / (predicted + 4 * gold) if predicted + 4 * gold else 0.0}
    return {'macro': macro, 'micro': micro, 'per_query': per_query}


def evaluate(records, params, all_corpus_scores):
    predictions, corpus, examples, gates = make_predictions(records, params, all_corpus_scores)
    hybrid_metrics = metric_report(records, predictions)
    corpus_metrics = metric_report(records, corpus)
    example_metrics = metric_report(records, examples)
    return {'params': dict(params), 'metrics': {
        'hybrid': {k: v for k, v in hybrid_metrics.items() if k != 'per_query'},
        'corpus': {k: v for k, v in corpus_metrics.items() if k != 'per_query'},
        'examples': {k: v for k, v in example_metrics.items() if k != 'per_query'},
        'gate_counts': gates,
    }, 'per_query': hybrid_metrics['per_query'], 'predictions': predictions}


def candidate_score(result):
    m = result['metrics']['hybrid']['macro']
    return (round(m['f2'], 8), round(m['f1'], 8), round(m['hit'], 8))


def select_trial(trials, defaults=None):
    defaults = defaults or {}
    def tie_penalty(row):
        return sum(abs(float(row['params'][key]) - float(value)) for key, value in defaults.items()
                   if key in row['params'])
    return max(trials, key=lambda row: (*candidate_score(row), -tie_penalty(row),
                                        json.dumps(row['params'], sort_keys=True)))


def add_trial(all_trials, stage, chunk, encoder, result):
    row = {'stage': stage, 'chunk': chunk, 'encoder': encoder,
           'params': dict(result['params']), 'metrics': result['metrics']}
    all_trials.append(row)
    return result


def group_diagnostics(per_query, group_by, seed=2025, bootstrap_samples=2000):
    group_map = {}
    for qid, group in group_by.items():
        group_map.setdefault(str(group), []).append(per_query[qid])
    group_ids = sorted(group_map)
    rng = random.Random(seed)
    shuffled = list(group_ids)
    rng.shuffle(shuffled)
    fold_groups = [shuffled[i::5] for i in range(5)]
    folds = []
    for i, ids in enumerate(fold_groups, 1):
        sample = [item for group in ids for item in group_map[group]]
        folds.append({'fold': i, 'image_groups': len(ids), 'queries': len(sample),
                      'macro_f2': sum(x['f2'] for x in sample) / len(sample) if sample else None})
    boot = []
    for _ in range(bootstrap_samples):
        selected = [rng.choice(group_ids) for _ in group_ids]
        sample = [item for group in selected for item in group_map[group]]
        boot.append(sum(x['f2'] for x in sample) / len(sample))
    boot.sort()
    return {'group_key': 'image_id', 'groups': len(group_ids), 'queries': len(per_query),
            'five_fold_grouped_diagnostic': folds,
            'cluster_bootstrap': {'samples': bootstrap_samples, 'seed': seed,
                                  'macro_f2_ci95': [boot[int(0.025 * (len(boot) - 1))],
                                                    boot[int(0.975 * (len(boot) - 1))]],
                                  'interpretation': 'Validation resampling after model/parameter selection; descriptive, not an independent test estimate.'}}


def trial_csv_row(trial_id, stage, chunk, encoder, result):
    p = result['params']
    m = result['metrics']
    row = {'trial_id': trial_id, 'stage': stage, 'chunk': chunk, 'encoder': encoder,
           **p, 'queries': 112}
    for branch in ('corpus', 'examples', 'hybrid'):
        for avg in ('macro', 'micro'):
            for metric, value in m[branch][avg].items():
                row[f'{branch}_{avg}_{metric}'] = value
    row.update({f'gate_count_{gate}': count for gate, count in m['gate_counts'].items()})
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-root', type=Path, required=True,
                        help='VLSP2025-MLQA-Natural/dataset folder used to verify validation labels and image groups.')
    parser.add_argument('--artifact-root', type=Path,
                        default=ROOT / 'artifacts/experiments/text_based_rag/natural_qa')
    parser.add_argument('--output-dir', type=Path,
                        default=ROOT / 'artifacts/experiments/text_based_rag/natural_qa/tuning')
    parser.add_argument('--bootstrap-samples', type=int, default=2000)
    args = parser.parse_args()
    artifact_root = args.artifact_root.expanduser().resolve()
    dataset_root = args.dataset_root.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    if args.bootstrap_samples < 100:
        parser.error('--bootstrap-samples must be at least 100.')

    variants, input_hashes, source, expected_ids = load_input(artifact_root, dataset_root)
    all_trials, trial_rows = [], []
    defaults = dict(DEFAULTS)

    # Stage 0: full factorial model/chunk comparison under the existing retrieval settings.
    baseline_results = {}
    for chunk in CHUNKS:
        for encoder in ENCODERS:
            data = variants[chunk][encoder]
            result = evaluate(data['records'], defaults, data['corpus_scores'])
            add_trial(all_trials, '00_encoder_chunk_baseline', chunk, encoder, result)
            baseline_results[(chunk, encoder)] = result
    best_pair = max(baseline_results, key=lambda key: (
        candidate_score(baseline_results[key]), key == ('t1024_o128', 'bge-m3'), key[0], key[1]))
    selected_chunk, selected_encoder = best_pair
    selected_records = variants[selected_chunk][selected_encoder]['records']
    selected_corpus_scores = variants[selected_chunk][selected_encoder]['corpus_scores']
    current = dict(DEFAULTS)
    stage_winners = [{'stage': '00_encoder_chunk_baseline', 'chunk': selected_chunk,
                      'encoder': selected_encoder, 'params': dict(current),
                      'metrics': baseline_results[best_pair]['metrics']}]

    def search(stage, params_iter, tie_defaults=None):
        nonlocal current
        trials = []
        params_list = list(params_iter)
        started = time.monotonic()
        total = len(params_list)
        print(f'[{stage}] 0/{total} (0%) elapsed=0s ETA=unknown', flush=True)
        interval = max(1, total // 10)
        for index, params in enumerate(params_list, 1):
            result = evaluate(selected_records, params, selected_corpus_scores)
            trials.append(add_trial(all_trials, stage, selected_chunk, selected_encoder, result))
            if index % interval == 0 or index == total:
                elapsed = time.monotonic() - started
                eta = elapsed * (total - index) / index if index else 0
                print(f'[{stage}] {index}/{total} ({index / total:.0%}) '
                      f'elapsed={elapsed:.0f}s ETA={eta:.0f}s', flush=True)
        winner = select_trial(trials, tie_defaults)
        current = dict(winner['params'])
        stage_winners.append({'stage': stage, 'chunk': selected_chunk, 'encoder': selected_encoder,
                              'params': dict(current), 'metrics': winner['metrics']})
        return winner

    # Stage 1: coarse search of corpus citation count and neighbor count, preserving gate defaults.
    coarse_k = (1, 2, 3, 5, 8, 10, 15, 20)
    search('01_candidate_depth_coarse', (
        {**DEFAULTS, 'corpus_k': kc, 'examples_k': ke, 'high_examples_k': min(3, ke)}
        for kc, ke in itertools.product(coarse_k, coarse_k)
    ), DEFAULTS)

    # Stage 2: refine counts around the coarse winner; high-gate support count is tuned separately.
    k_grid = sorted({max(1, min(20, current['corpus_k'] + delta)) for delta in range(-2, 3)})
    e_grid = sorted({max(1, min(20, current['examples_k'] + delta)) for delta in range(-2, 3)})
    search('02_candidate_depth_refine', (
        {**current, 'corpus_k': kc, 'examples_k': ke,
         'high_examples_k': kh}
        for kc, ke in itertools.product(k_grid, e_grid)
        for kh in range(1, min(5, ke) + 1)
    ), {'corpus_k': DEFAULTS['corpus_k'], 'examples_k': DEFAULTS['examples_k'],
        'high_examples_k': DEFAULTS['high_examples_k']})

    # Stage 3: tune low/high gate boundaries using score quantiles plus the existing thresholds.
    s_values = sorted(float(row['retrieval']['candidate_neighbors'][0]['score'])
                      for row in selected_records.values())
    threshold_grid = {0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.82, 0.85, 0.90, 0.95}
    for q in range(0, 21):
        threshold_grid.add(s_values[round(q * (len(s_values) - 1) / 20)])
    threshold_grid = sorted(threshold_grid)
    search('03_gate_thresholds', (
        {**current, 'low_threshold': low, 'high_threshold': high}
        for low, high in itertools.combinations(threshold_grid, 2)
    ), {'low_threshold': DEFAULTS['low_threshold'], 'high_threshold': DEFAULTS['high_threshold']})

    # Stage 4: tune per-gate example weights on a 0.1 grid, then refine locally on a 0.02 grid.
    weight_coarse = [round(i / 10, 2) for i in range(11)]
    search('04_fusion_weights_coarse', (
        {**current, 'weight_high': wh, 'weight_middle': wm, 'weight_low': wl}
        for wh, wm, wl in itertools.product(weight_coarse, repeat=3)
    ), {key: DEFAULTS[key] for key in ('weight_high', 'weight_middle', 'weight_low')})
    weight_grids = {}
    for key in ('weight_high', 'weight_middle', 'weight_low'):
        center = current[key]
        weight_grids[key] = sorted({round(max(0.0, min(1.0, center + delta)), 2)
                                    for delta in (-0.10, -0.08, -0.06, -0.04, -0.02, 0.0,
                                                  0.02, 0.04, 0.06, 0.08, 0.10)})
    search('05_fusion_weights_refine', (
        {**current, 'weight_high': wh, 'weight_middle': wm, 'weight_low': wl}
        for wh, wm, wl in itertools.product(weight_grids['weight_high'],
                                            weight_grids['weight_middle'],
                                            weight_grids['weight_low'])
    ), {key: current[key] for key in ('weight_high', 'weight_middle', 'weight_low')})

    # Stage 5: one coordinate-refinement pass so count, gate, and weight choices can interact.
    k_grid = sorted({max(1, min(20, current['corpus_k'] + delta)) for delta in range(-2, 3)})
    e_grid = sorted({max(1, min(20, current['examples_k'] + delta)) for delta in range(-2, 3)})
    search('06_joint_refine_depth', (
        {**current, 'corpus_k': kc, 'examples_k': ke,
         'high_examples_k': kh}
        for kc, ke in itertools.product(k_grid, e_grid)
        for kh in range(1, min(5, ke) + 1)
    ), {key: current[key] for key in ('corpus_k', 'examples_k', 'high_examples_k')})
    search('07_joint_refine_gates', (
        {**current, 'low_threshold': low, 'high_threshold': high}
        for low, high in itertools.combinations(threshold_grid, 2)
    ), {key: current[key] for key in ('low_threshold', 'high_threshold')})
    search('08_joint_refine_weights', (
        {**current, 'weight_high': wh, 'weight_middle': wm, 'weight_low': wl}
        for wh, wm, wl in itertools.product(weight_grids['weight_high'],
                                            weight_grids['weight_middle'],
                                            weight_grids['weight_low'])
    ), {key: current[key] for key in ('weight_high', 'weight_middle', 'weight_low')})

    final = evaluate(selected_records, current, selected_corpus_scores)
    default_result = baseline_results[best_pair]
    groups = variants[selected_chunk][selected_encoder]['groups']
    diagnostics = group_diagnostics(final['per_query'], groups, bootstrap_samples=args.bootstrap_samples)

    # Check the replay of the original defaults against the saved runner predictions.
    saved_mismatches = []
    for qid, record in selected_records.items():
        saved = [citation_key(item) for item in record['retrieval']['results'][:FINAL_K]]
        replay = default_result['predictions'][qid]
        if saved != replay:
            saved_mismatches.append(qid)
    if saved_mismatches:
        raise ValueError(f'Default replay differed from saved retrieval for {len(saved_mismatches)} queries; first={saved_mismatches[:5]}')

    output_dir.mkdir(parents=True, exist_ok=True)
    prediction_path = output_dir / 'tuning_predictions.jsonl'
    with prediction_path.open('w', encoding='utf-8') as f:
        for qid in sorted(selected_records):
            retrieval = selected_records[qid]['retrieval']
            s_max = float(retrieval['candidate_neighbors'][0]['score'])
            gate = 'high' if s_max >= current['high_threshold'] else (
                'low' if s_max < current['low_threshold'] else 'middle')
            row = {'id': qid, 'image_id': source[qid]['image_id'], 'gate': gate,
                   's_max': s_max, 'gold_citations': selected_records[qid]['gold_citations'],
                   'predicted_citations': [{'law_id': law, 'article_id': article}
                                            for law, article in final['predictions'][qid]],
                   'metrics': final['per_query'][qid]}
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
    for i, row in enumerate(all_trials, 1):
        trial_rows.append(trial_csv_row(i, row['stage'], row['chunk'], row['encoder'],
                                        {'params': row['params'], 'metrics': row['metrics']}))
    columns = sorted({key for row in trial_rows for key in row})
    with (output_dir / 'tuning_trials.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(trial_rows)

    summary = {
        'status': 'COMPLETED', 'created_at': datetime.now(timezone.utc).isoformat(),
        'purpose': 'Validation-only staged tuning of chunk configuration, embedding model, branch candidate depth, gate thresholds, and fusion weights.',
        'data_policy': {'split': 'validation derived from natural train', 'validation_queries': len(expected_ids),
                        'split_seed': 2025, 'group_key': 'image_id',
                        'public_test_used_for_tuning': False, 'private_test_used_for_tuning': False,
                        'caption_policy': 'reuse existing train/dev caption cache; no new captions'},
        'selection_policy': {'primary_metric': 'macro F2@5',
                             'tie_break': 'macro F1@5, hit rate, then closeness to previous/default parameters',
                             'final_citation_count': FINAL_K,
                             'candidate_limit': 20,
                             'limitations': ['All choices are selected on the same 112 validation queries; the final validation score is a tuning score, not an unbiased test estimate.',
                                             'Caption item relevance was produced for the original benchmark questions and remains fixed for natural-question tuning.',
                                             'One training sample is excluded because its citation is absent from the corpus.']},
        'search_plan': [
            {'stage': '00_encoder_chunk_baseline', 'configs': '12 combinations, all four encoders × three chunk settings',
             'params': DEFAULTS},
            {'stage': '01_candidate_depth_coarse', 'corpus_k': list(coarse_k), 'examples_k': list(coarse_k),
             'high_examples_k': 'min(3, examples_k)'},
            {'stage': '02_candidate_depth_refine', 'range': '±2 around coarse winner; high_examples_k 1..min(5, examples_k)'},
            {'stage': '03_gate_thresholds', 'thresholds': threshold_grid},
            {'stage': '04_fusion_weights_coarse', 'weights': weight_coarse, 'per_gate': ['high', 'middle', 'low']},
            {'stage': '05_fusion_weights_refine', 'range': '±0.10 around coarse winner in 0.02 increments'},
            {'stage': '06_joint_refine_depth', 'range': '±2 around selected depth; high_examples_k 1..min(5, examples_k)'},
            {'stage': '07_joint_refine_gates', 'thresholds': threshold_grid},
            {'stage': '08_joint_refine_weights', 'range': '±0.10 around selected weights in 0.02 increments'},
        ],
        'chosen_encoder_chunk': {'encoder': selected_encoder, 'chunk': selected_chunk,
                                 'chunk_count': variants[selected_chunk][selected_encoder]['corpus_chunk_count']},
        'default_config_metrics': default_result['metrics'],
        'selected_config': current,
        'selected_metrics': final['metrics'],
        'validation_uncertainty_diagnostics': diagnostics,
        'baseline_replay_mismatches': saved_mismatches,
        'prediction_output': str(prediction_path),
        'trial_count': len(all_trials), 'input_sha256': input_hashes,
        'script_path': str(Path(__file__).resolve()), 'script_sha256': sha256(__file__),
        'dataset_root': str(dataset_root), 'output_dir': str(output_dir),
        'environment': {'python': __import__('sys').version.split()[0], 'numpy': np.__version__, 'device': 'CPU'},
        'reproduce_command': f'PYTHONPATH=src .venv/bin/python -u -m text_based_rag.natural_qa_tuning --dataset-root "{dataset_root}" --bootstrap-samples {args.bootstrap_samples}',
        'stages': stage_winners,
        'top_baseline_pairs': [
            {'chunk': chunk, 'encoder': encoder,
             'macro_f2': baseline_results[(chunk, encoder)]['metrics']['hybrid']['macro']['f2'],
             'macro_f1': baseline_results[(chunk, encoder)]['metrics']['hybrid']['macro']['f1']}
            for chunk, encoder in sorted(baseline_results,
                key=lambda key: candidate_score(baseline_results[key]), reverse=True)[:5]
        ],
    }
    summary['output_sha256'] = {
        'tuning_trials.csv': sha256(output_dir / 'tuning_trials.csv'),
        'tuning_predictions.jsonl': sha256(prediction_path),
    }
    summary_path = output_dir / 'tuning_summary.json'
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[COMPLETED] trials={len(all_trials)} selected={selected_encoder}/{selected_chunk}')
    print('[DEFAULT]', json.dumps(default_result['metrics']['hybrid']['macro'], ensure_ascii=False))
    print('[SELECTED]', json.dumps(final['metrics']['hybrid']['macro'], ensure_ascii=False))
    print(f'[OUTPUT] {summary_path}')
    print(f'[OUTPUT] {output_dir / "tuning_trials.csv"}')


if __name__ == '__main__':
    main()
