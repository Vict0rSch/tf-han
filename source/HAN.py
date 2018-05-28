import tensorflow as tf
import numpy as np
from Model import Model
from utils import bidirectional_rnn, task_specific_attention

MultiRNNCell = tf.nn.rnn_cell.MultiRNNCell
GRUCell = tf.nn.rnn_cell.GRUCell


class HAN(Model):

    def __init__(self, hp, graph=None):
        super().__init__(hp, graph)
        self.np_embedding_matrix = None
        self.embedding_matrix = None
        self.batch = None
        self.docs = None
        self.sents = None
        self.sent_cell_fw = MultiRNNCell([GRUCell(self.hp.cell_size)] * 1)
        self.sent_cell_bw = MultiRNNCell([GRUCell(self.hp.cell_size)] * 1)
        self.doc_cell_fw = MultiRNNCell([GRUCell(self.hp.cell_size)] * 1)
        self.doc_cell_bw = MultiRNNCell([GRUCell(self.hp.cell_size)] * 1)
        self.val_ph = None
        self.embedded_inputs = None
        self.embedded_sentences = None
        self.sentence_lengths = None
        self.encoded_sentences = None
        self.attended_sentences = None
        self.sentence_output = None
        self.doc_inputs = None
        self.encoded_docs = None
        self.attended_docs = None
        self.doc_output = None
        self.logits = None
        self.prediction = None
        self.embedding_words = None
        self.doc_lengths = None
        self.is_training = None

    def set_logits(self):
        with tf.variable_scope("unstack-lengths"):
            (self.batch, self.docs, self.sents) = tf.unstack(
                tf.shape(self.input_tensor)
            )

        with tf.variable_scope("set-lengths"):
            self.doc_lengths = tf.count_nonzero(
                tf.reduce_sum(self.input_tensor, axis=-1), axis=-1
            )
            self.sentence_lengths = tf.count_nonzero(self.input_tensor, axis=-1)

        with tf.variable_scope("sentence-level"):
            with tf.variable_scope("embedding-lookup"):
                self.embedded_inputs = tf.nn.embedding_lookup(
                    self.embedding_matrix, self.input_tensor
                )

            with tf.variable_scope("reshape"):
                self.embedded_sentences = tf.reshape(
                    self.embedded_inputs,
                    [self.batch * self.docs, self.sents, self.hp.embedding_dim],
                )

                self.sentence_lengths = tf.reshape(
                    self.sentence_lengths, [self.batch * self.docs]
                )

            with tf.variable_scope("bidir-rnn") as scope:
                self.encoded_sentences, _ = bidirectional_rnn(
                    self.sent_cell_fw,
                    self.sent_cell_bw,
                    self.embedded_sentences,
                    self.sentence_lengths,
                    scope=scope,
                )

            with tf.variable_scope("attention") as scope:
                self.attended_sentences = task_specific_attention(
                    self.encoded_sentences, self.hp.cell_size, scope=scope
                )

            with tf.variable_scope("dropout"):
                self.sentence_output = tf.contrib.layers.dropout(
                    self.attended_sentences,
                    keep_prob=self.hp.dropout,
                    is_training=self.is_training,
                )

        with tf.variable_scope("doc-level"):
            with tf.variable_scope("reshape"):
                self.doc_inputs = tf.reshape(
                    self.sentence_output, [self.batch, self.docs, self.hp.cell_size]
                )

            with tf.variable_scope("bidir-rnn") as scope:
                self.encoded_docs, _ = bidirectional_rnn(
                    self.doc_cell_fw,
                    self.doc_cell_bw,
                    self.doc_inputs,
                    self.doc_lengths,
                    scope=scope,
                )

            with tf.variable_scope("attention") as scope:
                self.attended_docs = task_specific_attention(
                    self.encoded_docs, self.hp.cell_size, scope=scope
                )

            with tf.variable_scope("dropout"):
                self.doc_output = tf.contrib.layers.dropout(
                    self.attended_docs,
                    keep_prob=self.hp.dropout,
                    is_training=self.is_training,
                )

        with tf.variable_scope("classifier"):
            self.logits = tf.layers.dense(
                self.doc_output, self.hp.num_classes, activation=None
            )

            self.prediction = (
                tf.sigmoid(self.logits)
                if self.hp.multilabel
                else tf.argmax(self.logits, axis=1)
            )

    def set_embedding_matrix(self, emb_matrix=None):
        self.np_embedding_matrix = emb_matrix
        if emb_matrix:
            self.embedding_matrix = tf.get_variable(
                "embedding_matrix",
                shape=self.np_embedding_matrix.shape,
                initializer=tf.constant_initializer(self.np_embedding_matrix),
                trainable=self.hp.trainable_embedding_matrix,
            )
        else:
            self.embedding_matrix = tf.get_variable(
                "random_embedding",
                shape=(self.hp.vocab_size, self.hp.embedding_dim),
                initializer=tf.random_normal_initializer,
                trainable=True,
            )
