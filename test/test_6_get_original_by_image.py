import unittest
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


class TestGetOriginalImage(unittest.TestCase):
    def test_get_original_image(self):
        with open("test/beatles.jpeg", "rb") as img:
            uid = client.post("/predict", files={"file": img}).json()["prediction_uid"]
        saved_name = f"{uid}.jpeg"
        response = client.get(f"/image/original/{saved_name}")
        self.assertEqual(response.status_code, 200)


if __name__ == '__main__':
    unittest.main()
