import unittest
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


class TestGetPredictionsByScore(unittest.TestCase):
    def test_get_predictions_by_score(self):
        response = client.get("/predictions/score/0.5")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)


if __name__ == '__main__':
    unittest.main()
