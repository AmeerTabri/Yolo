import unittest
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


class TestGetPredictionByUID(unittest.TestCase):
    def test_get_prediction_by_uid(self):
        with open("test/beatles.jpeg", "rb") as img:
            predict_resp = client.post("/predict", files={"file": img})
        uid = predict_resp.json()["prediction_uid"]
        response = client.get(f"/prediction/{uid}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("detection_objects", response.json())


if __name__ == '__main__':
    unittest.main()
