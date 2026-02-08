import os
import sys
# Add project root to sys.path to allow imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from unittest.mock import patch
from app.backend.main import app

client = TestClient(app)

def test_deepdive_flag_enabled():
    # Verify that passing deepdive=True works
    # We patch run_translation_wrapper which is a background task
    with patch("app.backend.main.run_translation_wrapper") as mock_worker:
        # We also need to mock dependencies like get_current_user depending on auth
        # Assuming app.backend.main has auth disabled or we can bypass?
        # app.dependency_overrides = {}
        # If get_current_user is required, we override it.
        app.dependency_overrides = {
            "get_current_user": lambda: "test_user"
        }
        
        # We also need to mock LibraryManager/StorageService since they are injected
        # But they are injected into the route handler, and FastAPI resolves them.
        # Ideally we override them too to avoid side effects.
        
        response = client.post(
            "/translate",
            json={
                "arxiv_url": "https://arxiv.org/abs/1111.1111",
                "model": "flash",
                "deepdive": True
            }
        )
        # 200 OK
        assert response.status_code == 200
        
        # Verify background task was added with correct args
        # FastAPIs BackgroundTasks add_task is simple but verifying it in TestClient is tricky 
        # because TestClient triggers it? 
        # Actually client.post triggers the handler. The handler calls background_tasks.add_task.
        # If we patch the function being added, we can check if it was called?
        # Only if usage is `background_tasks.add_task(func, *args)`.
        # Yes, main.py does: background_tasks.add_task(run_translation_wrapper, ...)
        # But TestClient executes background tasks after the response is sent.
        # So mock_worker WILL be called.
        
        mock_worker.assert_called_once()
        args, _ = mock_worker.call_args
        # Args: (arxiv_url, model, arxiv_id, deepdive, user_id, storage, library)
        assert args[2] == "1111.1111"
        assert args[3] is True

def test_deepdive_flag_default_disabled():
    # Verify default is False
    with patch("app.backend.main.run_translation_wrapper") as mock_worker:
        app.dependency_overrides = {
            "get_current_user": lambda: "test_user"
        }
        
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

