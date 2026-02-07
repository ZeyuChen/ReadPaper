from fastapi.testclient import TestClient
from unittest.mock import patch
from app.backend.main import app

client = TestClient(app)

def test_deepdive_flag_enabled():
    # Verify that passing deepdive=True works
    with patch("app.backend.main.run_translation_wrapper") as mock_worker:
        response = client.post(
            "/translate",
            json={
                "arxiv_url": "https://arxiv.org/abs/1111.1111",
                "model": "flash",
                "deepdive": True
            }
        )
        assert response.status_code == 200
        
        mock_worker.assert_called_once()
        args, _ = mock_worker.call_args
        # Args: (arxiv_url, model, arxiv_id, deepdive)
        assert args[2] == "1111.1111"
        assert args[3] is True

def test_deepdive_flag_default_disabled():
    # Verify default is False
    with patch("app.backend.main.run_translation_wrapper") as mock_worker:
        response = client.post(
            "/translate",
            json={
                "arxiv_url": "https://arxiv.org/abs/2222.2222",
                "model": "flash"
            }
        )
        assert response.status_code == 200
        
        mock_worker.assert_called_once()
        args, _ = mock_worker.call_args
        assert args[2] == "2222.2222"
        assert args[3] is False
