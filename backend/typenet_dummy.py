"""
Dummy TypeNet model.
Accepts keystroke input in the exact format the real model will use.
Returns a constant similarity score.
Replace this file with real TypeNet inference when a trained model is available.
"""

import numpy as np

EMBEDDING_DIM = 128


class TypeNetModel:
    """
    Dummy model that mimics the TypeNet interface.

    Real model: 2-layer LSTM, 128 hidden units, input (1, seq_len, 4), output (1, 128).
    Dummy model: returns a fixed embedding vector regardless of input.
    """

    def __init__(self):
        self.dummy_embedding = np.random.randn(EMBEDDING_DIM).astype(np.float32)
        self.dummy_embedding = self.dummy_embedding / np.linalg.norm(self.dummy_embedding)

    def get_embedding(self, keystroke_window: list[list[float]]) -> np.ndarray:
        """
        Input: keystroke_window — list of 50 keystroke feature vectors.
               Each vector is [hold_time_ms, iki_kd_ms, iki_ku_ms, key_code].

        Output: 128-dimensional L2-normalised embedding vector.
        """
        assert len(keystroke_window) >= 50, "Need at least 50 keystrokes per window"
        noise = np.random.randn(EMBEDDING_DIM).astype(np.float32) * 0.05
        embedding = self.dummy_embedding + noise
        embedding = embedding / np.linalg.norm(embedding)
        return embedding

    def compute_similarity(self, embedding: np.ndarray, baseline: np.ndarray) -> float:
        """
        Cosine similarity between two L2-normalised embeddings.
        Returns float in [-1, 1].
        """
        return float(np.dot(embedding, baseline))


model = TypeNetModel()


def enroll(keystroke_sequences: list[list[list[float]]]) -> np.ndarray:
    """
    Enrollment: takes multiple keystroke windows, returns averaged baseline embedding.

    Input: list of keystroke windows (each window is 50×4).
    Output: 128-dim baseline embedding vector.
    """
    embeddings = [model.get_embedding(window) for window in keystroke_sequences]
    baseline = np.mean(embeddings, axis=0)
    baseline = baseline / np.linalg.norm(baseline)
    return baseline


def score_window(keystroke_window: list[list[float]], baseline: np.ndarray) -> float:
    """
    Score a single 50-keystroke window against the enrolled baseline.

    Input: one 50×4 keystroke window + the enrolled baseline embedding.
    Output: similarity score (float, ~0.85 for dummy).
    """
    embedding = model.get_embedding(keystroke_window)
    return model.compute_similarity(embedding, baseline)
