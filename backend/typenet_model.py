"""
Real TypeNet-LSTM model wrapper for keystroke biometric authentication.

Loads pre-trained model from TypeNet-LSTM-Torch-main and provides:
- enrollment: create baseline from multiple keystroke windows
- score_window: compute similarity of new window against baseline
- continuous_monitoring: process windows and flag suspicious activity

Features: [HL, IL, PL, RL, KC]
  HL: Hold Latency (release_time - press_time)
  IL: Inter-Key Latency (next_press - current_release)
  PL: Press Latency (next_press - current_press)
  RL: Release Latency (next_release - current_release)
  KC: KeyCode (normalized to [0, 1])
"""

import os
import json
import numpy as np
import torch
import torch.nn as nn
from pathlib import Path

# Attempt to load the real model from the workspace
TYPENET_DIR = os.path.join(os.path.dirname(__file__), "..", "TypeNet-LSTM-Torch-main")
MODEL_DIR = os.path.join(TYPENET_DIR, "models")

# Add TypeNet to path for imports
if os.path.exists(TYPENET_DIR):
    import sys
    sys.path.insert(0, TYPENET_DIR)


class VariationalDropout(nn.Module):
    """Locked dropout for recurrent connections."""
    def __init__(self, p: float = 0.2):
        super().__init__()
        self.p = p

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if not self.training or self.p == 0.0:
            return x
        mask = x.new_empty(x.size(0), 1, x.size(2)).bernoulli_(1.0 - self.p)
        return x * mask / (1.0 - self.p)


class TypeNetBackbone(nn.Module):
    """TypeNet backbone: 2-layer LSTM with batch norm."""
    def __init__(self, M: int = 50):
        super().__init__()
        self.M = M
        self.var_drop1 = VariationalDropout(0.2)
        self.lstm1 = nn.LSTM(5, 128, batch_first=True)
        self.bn = nn.BatchNorm1d(128)
        self.dropout = nn.Dropout(0.5)
        self.var_drop2 = VariationalDropout(0.2)
        self.lstm2 = nn.LSTM(128, 128, batch_first=True)

    def _seq_lengths(self, x: torch.Tensor) -> torch.Tensor:
        """Count real (non-padded) time steps per sequence."""
        return (x[:, :, 0] > 0).sum(dim=1).clamp(min=1).cpu()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence
        
        lengths = self._seq_lengths(x)
        
        # LSTM 1
        packed = pack_padded_sequence(
            self.var_drop1(x), lengths, batch_first=True, enforce_sorted=False
        )
        out, _ = self.lstm1(packed)
        out, _ = pad_packed_sequence(out, batch_first=True, total_length=self.M)
        
        # BatchNorm
        out = self.bn(out.permute(0, 2, 1)).permute(0, 2, 1)
        out = self.dropout(out)
        
        # LSTM 2
        packed = pack_padded_sequence(
            self.var_drop2(out), lengths, batch_first=True, enforce_sorted=False
        )
        _, (h_n, _) = self.lstm2(packed)
        return h_n.squeeze(0)  # (B, 128)


class TypeNetModel:
    """TypeNet model wrapper with enrollment and scoring."""
    
    def __init__(self, model_path: str = None, M: int = 50, device: str = "cpu"):
        self.M = M
        self.device = torch.device(device)
        self.embedding_dim = 128
        
        # Try to load real model
        if model_path is None:
            # Search for best triplet model
            model_path = self._find_best_model()
        
        self.backbone = TypeNetBackbone(M).to(self.device)
        self.backbone.eval()
        
        if model_path and os.path.exists(model_path):
            try:
                state_dict = torch.load(model_path, map_location=self.device)
                self.backbone.load_state_dict(state_dict)
                print(f"✓ Loaded TypeNet model from {model_path}")
                self.model_loaded = True
            except Exception as e:
                print(f"⚠ Failed to load model: {e}. Using untrained backbone.")
                self.model_loaded = False
        else:
            print(f"⚠ Model not found at {model_path}. Using untrained backbone.")
            self.model_loaded = False
    
    def _find_best_model(self) -> str:
        """Find the best trained model in the models directory."""
        candidates = [
            os.path.join(MODEL_DIR, "typenet_triplet_M50_best.pt"),
            os.path.join(MODEL_DIR, "typenet_contrastive_M50_best.pt"),
            os.path.join(MODEL_DIR, "typenet_triplet_M50.pt"),
            os.path.join(MODEL_DIR, "typenet_contrastive_M50.pt"),
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        return None
    
    def get_embedding(self, keystroke_window: list[list[float]]) -> np.ndarray:
        """
        Get embedding for a keystroke window.
        
        Input: keystroke_window — list of keystroke feature vectors
               Each vector is [HL, IL, PL, RL, KC] (5 features)
        Output: 128-dimensional embedding
        """
        # Ensure we have features, pad if needed
        window = np.array(keystroke_window, dtype=np.float32)
        
        # If less than M keystrokes, pad with zeros
        if len(window) < self.M:
            pad = np.zeros((self.M - len(window), 5), dtype=np.float32)
            window = np.concatenate([window, pad], axis=0)
        elif len(window) > self.M:
            window = window[:self.M]
        
        # Add batch dimension and move to device
        x = torch.from_numpy(window).unsqueeze(0).to(self.device)
        
        with torch.no_grad():
            embedding = self.backbone(x)
        
        return embedding[0].cpu().numpy()
    
    def compute_similarity(self, embedding: np.ndarray, baseline: np.ndarray) -> float:
        """Cosine similarity between two embeddings."""
        embedding = embedding / (np.linalg.norm(embedding) + 1e-8)
        baseline = baseline / (np.linalg.norm(baseline) + 1e-8)
        return float(np.dot(embedding, baseline))
    
    def enroll(self, keystroke_sequences: list[list[list[float]]]) -> np.ndarray:
        """
        Enrollment: create baseline embedding from multiple keystroke sequences.
        
        Input: list of keystroke windows
        Output: averaged baseline embedding (128-dim)
        """
        embeddings = []
        for window in keystroke_sequences:
            emb = self.get_embedding(window)
            embeddings.append(emb)
        
        baseline = np.mean(embeddings, axis=0)
        baseline = baseline / (np.linalg.norm(baseline) + 1e-8)
        return baseline
    
    def score_window(self, keystroke_window: list[list[float]], baseline: np.ndarray) -> float:
        """Score a keystroke window against baseline."""
        embedding = self.get_embedding(keystroke_window)
        return self.compute_similarity(embedding, baseline)


# Global model instance
_model_instance = None


def get_model(device: str = "cpu") -> TypeNetModel:
    """Get or create the global TypeNet model instance."""
    global _model_instance
    if _model_instance is None:
        _model_instance = TypeNetModel(device=device)
    return _model_instance


def enroll(keystroke_sequences: list[list[list[float]]]) -> np.ndarray:
    """Enroll a user with multiple keystroke sequences."""
    model = get_model()
    return model.enroll(keystroke_sequences)


def score_window(keystroke_window: list[list[float]], baseline: np.ndarray) -> float:
    """Score a single keystroke window."""
    model = get_model()
    return model.score_window(keystroke_window, baseline)
