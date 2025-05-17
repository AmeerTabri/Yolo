import unittest
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


class TestPostPredict(unittest.TestCase):
    def test_post_predict_valid_image(self):
        with open("test/beatles.jpeg", "rb") as img:
            response = client.post("/predict", files={"file": img})
        self.assertEqual(response.status_code, 200)
        self.assertIn("prediction_uid", response.json())
        self.assertIn("labels", response.json())


if __name__ == '__main__':
    unittest.main()
