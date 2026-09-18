import numpy as np
from sklearn.ensemble import IsolationForest

class RiskScorer:
    def __init__(self):
        # We use an Isolation Forest to detect anomalous bid behavior
        # based on historical bid compliance data.
        self.model = IsolationForest(contamination=0.1, random_state=42)
        self.is_trained = False

    def train(self, historical_data: list[list[float]]):
        """
        Train the model on historical bid data.
        Features might include: [turnover_diff_from_average, days_to_submit, missing_docs_count, past_failures]
        """
        X = np.array(historical_data)
        if len(X) > 0:
            self.model.fit(X)
            self.is_trained = True
        
    def calculate_risk_score(self, current_bid_features: list[float]) -> dict:
        """Calculate a risk score (0-100) and flag anomalies for a single bid."""
        if not self.is_trained:
            # Fallback deterministic scoring if no ML model is trained
            return {
                "score": 50.0,
                "risk_level": "MEDIUM",
                "is_anomaly": False,
                "reason": "Model not trained. Default score."
            }
            
        X_test = np.array([current_bid_features])
        # predict returns -1 for outliers and 1 for inliers
        prediction = self.model.predict(X_test)[0]
        # decision_function returns anomaly score (lower means more anomalous)
        anomaly_score = self.model.decision_function(X_test)[0]
        
        # Convert to 0-100 scale (rough heuristic for demonstration)
        normalized_score = max(0, min(100, (anomaly_score + 0.5) * 100))
        risk_level = "HIGH" if prediction == -1 else "LOW" if normalized_score > 70 else "MEDIUM"
        
        return {
            "score": round(100 - normalized_score, 2), # Invert so high score = high risk
            "risk_level": risk_level,
            "is_anomaly": prediction == -1,
            "reason": "Isolation Forest detected structural anomaly in bid profile." if prediction == -1 else "Normal profile."
        }

if __name__ == "__main__":
    scorer = RiskScorer()
    # Mock training data [turnover_variance, submission_delay, missing_docs]
    train_data = [[0.1, 10, 0], [0.2, 5, 0], [0.05, 12, 1], [0.9, 1, 3]] # Last is anomalous
    scorer.train(train_data)
    
    print("Test Normal:", scorer.calculate_risk_score([0.1, 8, 0]))
    print("Test Anomaly:", scorer.calculate_risk_score([0.95, 0, 4]))
