"""
Keystroke processor: converts frontend keystroke data to model input format.

Frontend captures: [hold_time_ms, iki_kd_ms, iki_ku_ms, key_code]
Model expects: [HL, IL, PL, RL, KC] (5 features, normalized)

HL: Hold Latency (already have as hold_time_ms)
IL: Inter-Key Latency (from key_up to next key_down)
PL: Press Latency (already have as iki_kd_ms)
RL: Release Latency (already have as iki_ku_ms)
KC: KeyCode (need to normalize)
"""

import numpy as np
from collections import deque


class KeystrokeProcessor:
    """Process keystroke windows and prepare for TypeNet model."""
    
    def __init__(self, window_size: int = 50, initial_enrollment_size: int = 100):
        self.window_size = window_size
        self.initial_enrollment_size = initial_enrollment_size
        self.buffer = deque(maxlen=None)  # Unbounded initially
        self.enrollment_complete = False
    
    @staticmethod
    def convert_keystroke_data(keystroke_data):
        """
        Convert raw keystroke data to 5-feature format.
        
        Input: [hold_time_ms, iki_kd_ms, iki_ku_ms, key_code] (4 features)
        Output: [HL, IL, PL, RL, KC] (5 features, normalized)
        """
        if len(keystroke_data) == 4:
            hold_time_ms, iki_kd_ms, iki_ku_ms, key_code = keystroke_data
            # Normalize to seconds and normalize keycode
            hl = hold_time_ms / 1000.0
            il = iki_kd_ms / 1000.0
            pl = iki_kd_ms / 1000.0
            rl = iki_ku_ms / 1000.0
            kc = key_code / 255.0
            return [hl, il, pl, rl, kc]
        elif len(keystroke_data) == 5:
            # Already in 5-feature format
            return keystroke_data
        else:
            raise ValueError(f"Expected 4 or 5 keystroke features, got {len(keystroke_data)}")
    
    def add_keystroke(self, hold_time_ms: float, iki_kd_ms: float, 
                     iki_ku_ms: float, key_code: int) -> dict:
        """
        Add a keystroke and check if we're ready for enrollment or have a full window.
        
        Returns: {
            'status': 'buffering' | 'enrollment_ready' | 'window_ready',
            'window': [...] or None,
            'enrollment_windows': [...] or None
        }
        """
        # Store raw keystroke
        self.buffer.append({
            'hold_time_ms': hold_time_ms,
            'iki_kd_ms': iki_kd_ms,
            'iki_ku_ms': iki_ku_ms,
            'key_code': key_code,
        })
        
        result = {
            'status': 'buffering',
            'window': None,
            'enrollment_windows': None,
            'keystroke_count': len(self.buffer)
        }
        
        # Check if enrollment is ready (100 keystrokes)
        if not self.enrollment_complete and len(self.buffer) == self.initial_enrollment_size:
            windows = self._create_enrollment_windows()
            self.enrollment_complete = True
            result['status'] = 'enrollment_ready'
            result['enrollment_windows'] = windows
            return result
        
        # Check if we have a full window for continuous monitoring (50 keystrokes)
        if self.enrollment_complete and len(self.buffer) >= self.window_size:
            window = self._get_window(self.window_size)
            result['status'] = 'window_ready'
            result['window'] = window
            return result
        
        return result
    
    def _create_enrollment_windows(self, window_size: int = 50) -> list:
        """Create overlapping windows from initial enrollment keystrokes."""
        buffer_list = list(self.buffer)
        windows = []
        
        # Create 2 overlapping windows from 100 keystrokes
        # Window 1: keystrokes 0-49
        # Window 2: keystrokes 50-99
        for i in range(0, len(buffer_list) - window_size + 1, window_size):
            window = buffer_list[i:i + window_size]
            feature_window = self._keystroke_to_features(window)
            windows.append(feature_window)
        
        return windows
    
    def _get_window(self, size: int) -> list:
        """Get the last N keystrokes as a feature window."""
        buffer_list = list(self.buffer)
        window = buffer_list[-size:]
        return self._keystroke_to_features(window)
    
    def _keystroke_to_features(self, keystroke_list: list) -> list[list[float]]:
        """
        Convert keystroke list to feature list [HL, IL, PL, RL, KC].
        
        Input: list of {'hold_time_ms', 'iki_kd_ms', 'iki_ku_ms', 'key_code'}
        Output: list of [HL, IL, PL, RL, KC] (5 features, normalized)
        """
        n = len(keystroke_list)
        if n == 0:
            return []
        
        features = []
        
        for i, ks in enumerate(keystroke_list):
            # HL: Hold Latency (ms → s)
            hl = ks['hold_time_ms'] / 1000.0
            
            # IL: Inter-Key Latency — for our keystroke capture:
            #     This is the time from key_up to next key_down
            #     We can approximate this as iki_kd since that's the next key down
            #     But for now we'll use iki_kd as a proxy for the interval
            il = ks['iki_kd_ms'] / 1000.0 if i < n - 1 else 0.0
            
            # PL: Press Latency — this is iki_kd_ms from frontend
            pl = ks['iki_kd_ms'] / 1000.0
            
            # RL: Release Latency — this is iki_ku_ms from frontend
            rl = ks['iki_ku_ms'] / 1000.0
            
            # KC: KeyCode (normalize to [0, 1])
            kc = ks['key_code'] / 255.0
            
            features.append([hl, il, pl, rl, kc])
        
        return features
    
    def slide_window(self) -> list[list[float]]:
        """
        Get a sliding window for continuous monitoring.
        Called after enrollment to extract the latest window_size keystrokes.
        """
        if len(self.buffer) < self.window_size:
            return None
        return self._get_window(self.window_size)
    
    def reset(self):
        """Reset for a new session."""
        self.buffer.clear()
        self.enrollment_complete = False
