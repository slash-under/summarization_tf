"""Utilities"""
import tensorflow as tf
import numpy as np
import math
from collections import defaultdict
import pickle
from prefetch_generator import BackgroundGenerator


class Node:
    def __init__(self, label="", parent=None, children=[], num=0):
        self.label = label
        self.parent = parent
        self.children = children
        self.num = num


class TreeLSTMNode:
    def __init__(self, h, c=None, parent=None, children=[], num=0):
        self.label = None
        self.h = h
        self.c = c
        self.parent = parent  # TreeLSTMNode
        self.children = children  # list of TreeLSTMNode
        self.num = num


def remove_identifier(root, mark="\"identifier=", replacement="$ID"):
    """remove identifier of all nodes"""
    if mark in root.label:
        root.label = replacement
    for child in root.children:
        remove_identifier(child)
    return(root)


def print_traverse(root, indent=0):
    """print tree structure"""
    print(" " * indent + str(root.label))
    for child in root.children:
        print_traverse(child, indent + 2)


def traverse(root):
    """traverse all nodes"""
    res = [root]
    for child in root.children:
        res = res + traverse(child)
    return(res)


def traverse_leaf(root):
    """traverse all leafs"""
    res = []
    for node in traverse(root):
        if node.children == []:
            res.append(node)
    return(res)


def traverse_label(root):
    """return list of tokens"""
    li = [root.label]
    for child in root.children:
        li += traverse_label(child)
    return(li)


def traverse_leaf_label(root):
    """traverse all leafs"""
    res = []
    for node in traverse(root):
        if node.children == []:
            res.append(node.label)
    return(res)


def partial_traverse(root, kernel_depth, depth=0,
                     children=[], depthes=[], left=[]):
    """indice start from 0 and counts do from 1"""
    children.append(root.num)
    depthes.append(depth)
    if root.parent is None:
        left.append(1.)
    else:
        num_sibs = len(root.parent.children)
        if num_sibs == 1:
            left.append(1.)
        else:
            left.append(
                1 - (root.parent.children.index(root) / (num_sibs - 1)))

    if depth < kernel_depth - 1:
        for child in root.children:
            res = partial_traverse(child, kernel_depth,
                                   depth + 1, children, depthes, left)
            children, depthes, left = res

    return(children, depthes, left)


def read_pickle(path):
    return pickle.load(open(path, "rb"))


def consult_tree(root, dic):
    nodes = traverse(root)
    for n in nodes:
        n.label = dic[n.label]
    return nodes[0]


def depth_split(root, depth=0):
    '''
    root: Node or LSTMNode
    return: dict
    '''
    res = defaultdict(list)
    res[depth].append(root)
    for child in root.children:
        for k, v in depth_split(child, depth + 1).items():
            res[k] += v
    return res


def depth_split_batch(roots):
    '''
    roots: list of Node
    return: dict
    '''
    res = defaultdict(list)
    for root in roots:
        for k, v in depth_split(root).items():
            res[k] += v
    return res


def sequence_apply(func, xs):
    '''
    xs: list of [any, dim]
    return: list of func([any, dim])
    '''
    x_len = [x.shape[0] for x in xs]
    ex = func(tf.concat(xs, axis=0))
    exs = tf.split(ex, x_len, 0)
    return exs


def he_normal():
    return tf.keras.initializers.he_normal()


def get_sequence_mask(xs):
    x_len = tf.constant([x.shape[0] for x in xs], tf.int32)
    mask = tf.tile(tf.reshape(tf.range(0, tf.reduce_max(x_len),
                                       dtype=tf.int32), (1, -1)), (x_len.shape[0], 1))
    mask = mask < tf.reshape(x_len, (-1, 1))
    return mask


def pad_tensor(ys):
    length = [y.shape[0] for y in ys]
    max_length = max(length)
    ys = tf.stack([tf.pad(y, tf.constant([[0, max_length - y.shape[0]], [0, 0]])) for y in ys])
    mask = tf.tile(tf.reshape(tf.range(0, max_length, dtype=tf.int32), (1, -1)), (len(length), 1))
    mask = mask < tf.reshape(tf.constant(length), (-1, 1))
    return ys, mask


def depth_split_batch2(roots):
    '''
    roots: list of Node
    return: dict
    '''
    res = defaultdict(list)
    for root in roots:
        for k, v in depth_split(root).items():
            res[k] += v
    for k, v in res.items():
        for e, n in enumerate(v):
            n.num = e + 1
    return res


class GeneratorLen(object):
    def __init__(self, gen, length):
        self.gen = gen
        self.length = length

    def __len__(self):
        return self.length

    def __iter__(self):
        return self.gen


def ngram(words, n):
    return list(zip(*(words[i:] for i in range(n))))


def bleu4(true, pred):
    c = len(pred)
    r = len(true)
    bp = 1. if c > r else np.exp(1 - r / c)
    score = 0
    for i in range(1, 5):
        true_ngram = set(ngram(true, i))
        pred_ngram = ngram(pred, i)
        length = float(len(pred_ngram)) + 1e-10
        count = sum([1. if t in true_ngram else 0. for t in pred_ngram])
        score += math.log(1e-10 + (count / length))
    score = math.exp(score * .25)
    bleu = bp * score
    return bleu


class Datagen_tree:
    def __init__(self, X, Y, batch_size, code_dic, nl_dic, train=True):
        self.X = X
        self.Y = Y
        self.batch_size = batch_size
        self.code_dic = code_dic
        self.nl_dic = nl_dic
        self.train = train

    def __len__(self):
        return len(range(0, len(self.X), self.batch_size))

    def __call__(self, epoch=0):
        return GeneratorLen(BackgroundGenerator(self.gen(epoch), 2), len(self))

    def gen(self, epoch):
        if self.train:
            np.random.seed(epoch)
            newindex = list(np.random.permutation(len(self.X)))
            X = [self.X[i] for i in newindex]
            Y = [self.Y[i] for i in newindex]
        else:
            X = [x for x in self.X]
            Y = [y for y in self.Y]
        for i in range(0, len(self.X), self.batch_size):
            x = X[i:i + self.batch_size]
            y = Y[i:i + self.batch_size]
            x_raw = [read_pickle(n) for n in x]
            y_raw = [[self.nl_dic[t] for t in s] for s in y]
            x = [consult_tree(n, self.code_dic) for n in x_raw]
            x_raw = [traverse_label(n) for n in x_raw]
            y = tf.constant(
                tf.keras.preprocessing.sequence.pad_sequences(
                    y,
                    min(max([len(s) for s in y]), 100),
                    padding="post", truncating="post", value=-1.))
            yield x, y, x_raw, y_raw
