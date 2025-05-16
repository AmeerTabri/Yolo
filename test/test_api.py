import unittest
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


class TestYoloAPI(unittest.TestCase):
    def test_post_predict_valid_image(self):
        with open("test/beatles.jpeg", "rb") as img:
            response = client.post("/predict", files={"file": img})
        self.assertEqual(response.status_code, 200)
        self.assertIn("prediction_uid", response.json())
        self.assertIn("labels", response.json())
        self.uid = response.json()["prediction_uid"]

    def test_get_prediction_by_uid(self):
        with open("test/beatles.jpeg", "rb") as img:
            predict_resp = client.post("/predict", files={"file": img})
        uid = predict_resp.json()["prediction_uid"]
        response = client.get(f"/prediction/{uid}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("detection_objects", response.json())

    def test_get_predictions_by_label(self):
        client.post("/predict", files={"file": open("test/beatles.jpeg", "rb")})
        response = client.get("/predictions/label/person")  # adjust label if needed
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)

    def test_get_predictions_by_score(self):
        response = client.get("/predictions/score/0.5")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)

    def test_get_prediction_image(self):
        with open("test/beatles.jpeg", "rb") as img:
            uid = client.post("/predict", files={"file": img}).json()["prediction_uid"]
        response = client.get(f"/prediction/{uid}/image", headers={"accept": "image/jpeg"})
        self.assertEqual(response.status_code, 200)

    def test_get_original_image(self):
        with open("test/beatles.jpeg", "rb") as img:
            uid = client.post("/predict", files={"file": img}).json()["prediction_uid"]
        # Extract the saved filename from the DB (simplified approach if stored as full path)
        saved_name = f"{uid}.jpeg"
        response = client.get(f"/image/original/{saved_name}")
        self.assertEqual(response.status_code, 200)

    def test_get_predicted_image(self):
        with open("test/beatles.jpeg", "rb") as img:
            uid = client.post("/predict", files={"file": img}).json()["prediction_uid"]
        saved_name = f"{uid}.jpeg"
        response = client.get(f"/image/predicted/{saved_name}")
        self.assertEqual(response.status_code, 200)


if __name__ == '__main__':
    unittest.main()
