import unittest
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


class TestGetPredictionImage(unittest.TestCase):
    def test_get_prediction_image(self):
        with open("test/beatles.jpeg", "rb") as img:
            uid = client.post("/predict", files={"file": img}).json()["prediction_uid"]
        response = client.get(f"/prediction/{uid}/image", headers={"accept": "image/jpeg"})
        self.assertEqual(response.status_code, 200)


if __name__ == '__main__':
    unittest.main()
