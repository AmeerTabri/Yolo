import unittest
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


class TestGetPredictionsByLabel(unittest.TestCase):
    def test_get_predictions_by_label(self):
        client.post("/predict", files={"file": open("test/beatles.jpeg", "rb")})
        response = client.get("/predictions/label/person")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)


if __name__ == '__main__':
    unittest.main()
