#!/usr/bin/python3

import os
os.environ['TF_CPP_MIN_LOG_LEVEL']='2'
import tensorflow as tf
tf.logging.set_verbosity(tf.logging.ERROR)
#tf.logging.set_verbosity(tf.logging.INFO)

from extract_features import *
import modeling
import tokenization
import numpy as np

LAYER_INDEXES = [-1, -2, -3, -4]
MAX_SEQ_LENGTH=128
BATCH_SIZE=8

def load_BERT_estimator(bert_model_dir):
    bert_config_file = bert_model_dir+"/bert_config.json"
    bert_config = modeling.BertConfig.from_json_file(bert_config_file)
    init_checkpoint = bert_model_dir+"/bert_model.ckpt"
    model_fn = model_fn_builder(
        bert_config=bert_config,
        init_checkpoint=init_checkpoint,
        layer_indexes=LAYER_INDEXES,
        use_tpu=False,
        use_one_hot_embeddings=False)

    estimator = tf.contrib.tpu.TPUEstimator(
        use_tpu=False,
        model_fn=model_fn,
        config=tf.contrib.tpu.RunConfig(),
        predict_batch_size=BATCH_SIZE)

    return estimator

def load_tokenizer(bert_model_dir):
    vocab_file = bert_model_dir+"/vocab.txt"
    tokenizer = tokenization.FullTokenizer(vocab_file=vocab_file, do_lower_case=False)
    return tokenizer

unique_id = 0
# sents is a list of ether normal sentences or (sentenceA, sentenceB)
def embed_sent_pairs(estimator, tokenizer, sents):
    global unique_id
    sents = list(sents)

    examples = []
    unique_id_to_example = dict()
    for sent in sents:
        unique_id += 1
        if isinstance(sent, str):
            example = InputExample(unique_id=unique_id, text_a=sent, text_b=None)
        else:
            example = InputExample(unique_id=unique_id, text_a=sent[0], text_b=sent[1])
        examples.append(example)
        unique_id_to_example[unique_id] = example
    features = convert_examples_to_features(examples=examples, seq_length=MAX_SEQ_LENGTH, tokenizer=tokenizer)

    unique_id_to_feature = dict()
    for feature in features:
        unique_id_to_feature[feature.unique_id] = feature

    input_fn = input_fn_builder( features=features, seq_length=MAX_SEQ_LENGTH)

    all_results = dict()

    for result in estimator.predict(input_fn, yield_single_examples=True):
        unique_id = int(result["unique_id"])
        feature = unique_id_to_feature[unique_id]
        all_tokens = []
        all_features = []
        for (i, token) in enumerate(feature.tokens):
            all_layers = None
            for j, layer_index in enumerate(LAYER_INDEXES):
                layer_output = result["layer_output_%d" % j]
                # layer_output = [ round(float(x), 6) for x in layer_output[i:(i + 1)].flat ]
                layer_output = [ round(x, 6) for x in layer_output[i:(i + 1)].flat ]
                if all_layers is None:
                    all_layers = layer_output
                else:
                    all_layers = np.add(all_layers, layer_output)
            all_tokens.append(token)
            all_features.append(all_layers)
        all_results[unique_id] = revert_tokenization(tokenizer, unique_id_to_example[unique_id], all_features)
    all_results = [y[1] for y in sorted(list(all_results.items()), key=lambda z:z[0])]
    assert len(all_results) == len(sents)
    return all_results

def normalize_embedings_dict(res_dict):
    return {
        "CLS": res_dict["CLS"]/np.linalg.norm(res_dict["CLS"], 2),
        "SEP": res_dict["SEP"]/np.linalg.norm(res_dict["SEP"], 2),
        "MID_SEP": res_dict["MID_SEP"]/np.linalg.norm(res_dict["MID_SEP"], 2),
        "A": normalize_embedings_list(res_dict["A"]),
        "B": normalize_embedings_list(res_dict["B"])
    }

def normalize_embedings_list(embeddings):
    if embeddings is None:
        return None
    else:
        embeddings_new = []
        for e in embeddings:
            embeddings_new.append(e/np.linalg.norm(e, 2))
        return embeddings_new

def revert_tokenization(tokenizer, example, all_features):

    res = dict()

    res["CLS"] = all_features[0]
    res["SEP"] = all_features[-1]

    final_vecs = []
    words = example.text_a.split()
    i = 1
    for word in words:
        j = i+len(tokenizer.tokenize(word))

        for k in range(i, j):
            if k == i:
                final_vecs.append(all_features[k])
            else:
                final_vecs[-1] = np.add(final_vecs[-1], all_features[k])
        i=j
    res["A"] = final_vecs

    res["MID_SEP"] = all_features[i]

    if example.text_b is not None:
        final_vecs = []
        words = example.text_b.split()
        i += 1
        for word in words:
            j = i+len(tokenizer.tokenize(word))

            for k in range(i, j):
                if k == i:
                    final_vecs.append(all_features[k])
                else:
                    final_vecs[-1] = np.add(final_vecs[-1], all_features[k])
            i=j
        res["B"] = final_vecs
    else:
        res["B"] = None

    return res




# bert_model_dir = "/home/milos/Desktop/BERT_playground/multi_cased_L-12_H-768_A-12"
#
# input = [
#     "This is a sentence that contains some input about some city somewhere",
#     "This is a sentence that contains maaaaaanny some input about some city somewhere",
#     ("A new sentence", "B new sentence")
# ]
#
# tokenizer = load_tokenizer(bert_model_dir)
# estimator = load_BERT_estimator(bert_model_dir)
#
# res = embed_sent_pairs(estimator, tokenizer, input)
# res = list(map(normalize_embedings_dict, res))
# print(res[0]["A"])
# print(type(res[0]["A"]))
#
# print("DONE")

