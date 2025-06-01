import unittest
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


class TestGetPredictedImage(unittest.TestCase):
    def test_get_predicted_image(self):
        # Step 1: Upload an image to /predict
        with open("test/beatles.jpeg", "rb") as f:
            response = client.post("/predict", files={"file": f})

        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        uid = json_data.get("prediction_uid")
        self.assertIsNotNone(uid)

        # Step 2: Fetch the predicted image
        image_response = client.get(f"/prediction/{uid}/image", headers={"accept": "image/jpeg"})

        self.assertEqual(image_response.status_code, 200)
        self.assertEqual(image_response.headers["content-type"], "image/jpeg")


if __name__ == '__main__':
    unittest.main()
