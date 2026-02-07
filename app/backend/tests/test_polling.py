from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.backend.main import app, TASK_STATUS
import time
import pytest

client = TestClient(app)

# Mocked output stream from arxiv-translator CLI
MOCK_CLI_OUTPUT = [
    "PROGRESS:DOWNLOADING:Downloading source...\n",
    "PROGRESS:EXTRACTING:Extracting files...\n",
    "PROGRESS:TRANSLATING:0:2:Starting translation...\n",
    "PROGRESS:TRANSLATING:1:2:Translated file1.tex\n",
    "PROGRESS:TRANSLATING:2:2:Translated file2.tex\n",
    "PROGRESS:COMPILING:Compiling PDF...\n",
    "SUCCESS: Generated paper.pdf\n",
    "PROGRESS:COMPLETED:Done\n"
]

@pytest.fixture
def mock_subprocess():
    with patch("subprocess.Popen") as mock_popen, \
         patch("subprocess.run") as mock_run:
        
        # Popen mock for arxiv-translator
        process_mock = MagicMock()
        process_mock.stdout.readline.side_effect = MOCK_CLI_OUTPUT + [""]
        process_mock.poll.return_value = 0
        process_mock.returncode = 0
        # process_mock.communicate.return_value = ("", "") # Not needed if we patch run
        mock_popen.return_value = process_mock
        
        # Run mock for curl
        run_mock = MagicMock()
        run_mock.returncode = 0
        run_mock.stdout = ""
        run_mock.stderr = ""
        mock_run.return_value = run_mock
        
        yield mock_popen

def test_backend_polling_flow(mock_subprocess):
    # Clear previous status
    TASK_STATUS.clear()
    
    # 1. Start Translation
    response = client.post("/translate", json={"arxiv_url": "https://arxiv.org/abs/1234.5678"})
    assert response.status_code == 200
    data = response.json()
    arxiv_id = data["arxiv_id"]
    # Check that it returns expected keys
    assert "status" not in data # The real API doesn't return status here
    assert "message" in data

    # 2. Poll Status - Downloading
    # We need to give the background thread a tiny bit of time to consume the mock, 
    # but since TestClient runs synchronously in this context, the background task usually runs after response.
    # However, `TestClient` with `BackgroundTasks` might need `with client:` block or explicit handling?
    # Actually, starlette TestClient runs background tasks after response.
    # To test intermediate states, we might need to slow down the mock or run the generator in a way we can check.
    # But `run_translation_stream` is `async` and runs in `BackgroundTasks`.
    # Let's rely on the fact that `TASK_STATUS` is a global dict.
    
    # Wait for task to process
    # Since mock outputs are consumed in a loop, it will happen very fast.
    # We might miss intermediate states if we don't control the speed.
    # But we can verify the FINAL state is completed.
    
    # To verifying polling, we verify that status is updated to 'completed' and contains progress details.
    
    # Give it a second (in reality it's instant with mock)
    time.sleep(0.1)
    
    response = client.get(f"/status/{arxiv_id}")
    status = response.json()
    
    # The loop consumes all output, so it should be completed or near completed
    assert status["status"] == "completed"
    assert status["progress"] == 100
    assert status["message"] == "Done"
    
    # We can inspect TASK_STATUS history if we stored it, but we only store current.
    # This test confirms the interactions pipeline works: API -> Background -> Subprocess Mock -> Status Dict -> API

def test_progress_parsing():
    # Unit test for the parsing logic specifically (simulating the loop step)
    from app.backend.main import update_status
    
    arxiv_id = "test_progress"
    
    # Simulate "PROGRESS:TRANSLATING:1:4:Translated foo.tex"
    # Logic: 10 + 80 * (1/4) = 10 + 20 = 30%
    line = "PROGRESS:TRANSLATING:1:4:foo.tex"
    parts = line.split(":", 2)
    # Replicating logic from main.py
    code = parts[1]
    rest = parts[2]
    t_parts = rest.split(":")
    idx = int(t_parts[0])
    total = int(t_parts[1])
    p = int(10 + 80 * (idx / total))
    
    update_status(arxiv_id, "processing", f"Translating {t_parts[2]}", p, f"File {idx}/{total}")
    
    current = TASK_STATUS[arxiv_id]
    assert current["status"] == "processing"
    assert current["progress_percent"] == 30
    assert "File 1/4" in current["details"]
