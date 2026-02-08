import requests
import time
import sys
import json
import logging

# Configure test logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:8001"

# List of papers to test: (ID, Name)
PAPERS_TO_TEST = [
    ("2412.19437", "DeepSeek-V3"),
    ("2412.15115", "Qwen2.5"),
    ("2406.12793", "GLM-4"),
    ("2411.19688", "Yi-Lightning"),
    ("2410.21334", "MiniMax-01"),
]

def test_paper(arxiv_id, name):
    logger.info(f"=== Starting E2E Test for {name} ({arxiv_id}) ===")

    # 1. Cleanup
    logger.info(f"Cleaning up previous run for {arxiv_id}...")
    try:
        requests.delete(f"{BASE_URL}/library/{arxiv_id}")
    except Exception:
        pass

    # 2. Trigger Translation with DeepDive
    payload = {
        "arxiv_url": f"https://arxiv.org/abs/{arxiv_id}",
        "model": "flash",
        "deepdive": True
    }
    logger.info(f"Sending translation request: {payload}")
    
    try:
        resp = requests.post(f"{BASE_URL}/translate", json=payload)
        if resp.status_code != 200:
            logger.error(f"Failed to start translation for {arxiv_id}: {resp.text}")
            return False, f"Start failed: {resp.text}"
    except Exception as e:
        logger.error(f"Failed to connect to backend: {e}")
        return False, f"Connect failed: {e}"
        
    logger.info("Translation started. Polling status...")
    
    # 3. Poll Status
    start_time = time.time()
    deepdive_activity_detected = False
    
    while True:
        try:
            status_res = requests.get(f"{BASE_URL}/status/{arxiv_id}")
            if status_res.status_code != 200:
                logger.warning(f"Status check failed: {status_res.status_code}")
                time.sleep(5)
                continue
                
            status_data = status_res.json()
            
            status = status_data.get("status")
            message = status_data.get("message", "")
            progress = status_data.get("progress", 0)
            
            # Check for DeepDive activity markers
            if "Analyzed" in message or "analyzing" in message.lower():
                if not deepdive_activity_detected:
                    logger.info(f"DeepDive Activity Detected: {message}")
                    deepdive_activity_detected = True
            
            # Reduce log spam by only printing every 10 seconds or on status change
            # For simplicity in this script, just print every time
            # actually let's verify if status changed or it's been 10s
             
            if status == "completed":
                logger.info("Translation Completed!")
                break
                
            if status == "failed":
                logger.error(f"Translation Failed: {message}")
                return False, f"Failed: {message}"
                
            # Timeout (20 minutes per paper - they are large)
            if time.time() - start_time > 1200: 
                logger.error("Timeout waiting for translation")
                return False, "Timeout"
                
            time.sleep(10)
            
        except Exception as e:
            logger.error(f"Polling error: {e}")
            time.sleep(10)

    # 4. Final verification
    if not deepdive_activity_detected:
        logger.warning(f"WARNING: DeepDive activity was NOT explicitly detected for {arxiv_id}.")
        
    # Verify PDF exists
    pdf_res = requests.get(f"{BASE_URL}/paper/{arxiv_id}/translated")
    if pdf_res.status_code == 200:
         logger.info(f"SUCCESS: Translated PDF for {arxiv_id} is accessible.")
         return True, "Success"
    else:
         logger.error(f"ERROR: Translated PDF for {arxiv_id} not found.")
         return False, "PDF missing"

def run_all_tests():
    results = {}
    logger.info(f"Starting batched testing for {len(PAPERS_TO_TEST)} papers.")
    
    for arxiv_id, name in PAPERS_TO_TEST:
        success, reason = test_paper(arxiv_id, name)
        results[name] = "PASS" if success else f"FAIL ({reason})"
        logger.info(f"Finished {name}: {results[name]}\n")
        
        # small pause between papers
        time.sleep(5)

    logger.info("=== Final Results ===")
    all_passed = True
    for name, status in results.items():
        logger.info(f"{name}: {status}")
        if "FAIL" in status:
            all_passed = False
            
    if not all_passed:
        sys.exit(1)

if __name__ == "__main__":
    run_all_tests()
