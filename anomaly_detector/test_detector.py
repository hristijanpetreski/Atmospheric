import unittest
from collections import deque
import pandas as pd
from sklearn.ensemble import IsolationForest
import numpy as np

# We import key logic or mock it to test detector's behavior
class TestAnomalyDetector(unittest.TestCase):
    def setUp(self):
        self.min_samples = 30
        self.contamination = 0.05
        self.window_size = 100
        
        # Mock buffer
        self.buffer = deque(maxlen=self.window_size)

    def test_warmup_phase(self):
        # Seed some initial normal data below the threshold
        for i in range(10):
            self.buffer.append({
                "temperature": 20.0 + (i % 3),
                "humidity": 50.0 + (i % 5),
                "pressure": 1012.0
            })
            
        df = pd.DataFrame(list(self.buffer))
        current_keys = ["temperature", "humidity", "pressure"]
        df_features = df[current_keys].dropna()
        
        # Verify that we don't have enough samples to fit the model
        self.assertLess(len(df_features), self.min_samples)
        
    def test_anomaly_detection_logic(self):
        # 1. Add normal samples to satisfy min_samples (30)
        # Generate 30 normal readings with small fluctuations
        np.random.seed(42)
        temps = np.random.normal(22.0, 0.5, 35)
        hums = np.random.normal(55.0, 1.0, 35)
        pressures = np.random.normal(1013.0, 0.2, 35)
        
        for t, h, p in zip(temps, hums, pressures):
            self.buffer.append({
                "temperature": float(t),
                "humidity": float(h),
                "pressure": float(p)
            })
            
        df = pd.DataFrame(list(self.buffer))
        current_keys = ["temperature", "humidity", "pressure"]
        df_features = df[current_keys].dropna()
        
        self.assertEqual(len(df_features), 35)
        
        # 2. Fit the Isolation Forest model
        clf = IsolationForest(contamination=self.contamination, random_state=42)
        clf.fit(df_features)
        
        # Predict on a normal current reading (the last one appended)
        current_row = df_features.iloc[[-1]]
        pred = clf.predict(current_row)[0]
        score = clf.decision_function(current_row)[0]
        
        # Normal reading should not be an anomaly (pred should be 1)
        self.assertEqual(pred, 1)
        is_anomaly = 1 if pred == -1 else 0
        self.assertEqual(is_anomaly, 0)
        
        # 3. Append an anomaly (extreme temperature spike)
        self.buffer.append({
            "temperature": 85.0, # Massive spike
            "humidity": 55.0,
            "pressure": 1013.0
        })
        
        # Re-fetch DataFrame and re-fit
        df_anomaly = pd.DataFrame(list(self.buffer))
        df_anomaly_features = df_anomaly[current_keys].dropna()
        
        # Fit model on the new dataset
        clf_anomaly = IsolationForest(contamination=self.contamination, random_state=42)
        clf_anomaly.fit(df_anomaly_features)
        
        # Predict on the new current reading (the anomaly we just added)
        current_anomaly_row = df_anomaly_features.iloc[[-1]]
        pred_anomaly = clf_anomaly.predict(current_anomaly_row)[0]
        score_anomaly = clf_anomaly.decision_function(current_anomaly_row)[0]
        
        # Outlier reading should be flagged as anomaly (pred should be -1)
        self.assertEqual(pred_anomaly, -1)
        is_anomaly_detected = 1 if pred_anomaly == -1 else 0
        self.assertEqual(is_anomaly_detected, 1)
        
        # Anomaly score should be significantly higher (more positive after inversion) than normal score
        # Remember score_anomaly (decision_function) is negative for anomalies and positive for normal
        self.assertLess(score_anomaly, score)

if __name__ == "__main__":
    unittest.main()
