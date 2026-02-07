from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.backend.main import app

client = TestClient(app)

def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "ReadPaper Backend is running"}

@patch("app.backend.main.run_translation_task")
def test_translate_endpoint(mock_task):
    # Mock the background task
    mock_task.return_value = None
    
    response = client.post("/translate", json={"arxiv_url": "https://arxiv.org/abs/2510.26692"})
    assert response.status_code == 200
    data = response.json()
    assert "arxiv_id" in data
    assert data["status"] == "processing"
    
    # Verify task called
    mock_task.assert_called_once()
