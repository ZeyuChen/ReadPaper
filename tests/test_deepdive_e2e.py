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

BASE_URL = "http://localhost:8000"
ARXIV_ID = "2602.04705" # DeepSeek-V3/DeepGemini paper? No, let's use the one requested.
# 2602.04705 might be a new paper.

def test_deepdive_e2e():
    logger.info(f"Starting DeepDive E2E Test for {ARXIV_ID}...")

    # 1. Cleanup
    logger.info("Cleaning up previous run...")
    try:
        requests.delete(f"{BASE_URL}/library/{ARXIV_ID}")
    except Exception:
        pass

    # 2. Trigger Translation with DeepDive
    payload = {
        "arxiv_url": f"https://arxiv.org/abs/{ARXIV_ID}",
        "model": "flash",
        "deepdive": True
    }
    logger.info(f"Sending translation request: {payload}")
    
    resp = requests.post(f"{BASE_URL}/translate", json=payload)
    if resp.status_code != 200:
        logger.error(f"Failed to start translation: {resp.text}")
        sys.exit(1)
        
    logger.info("Translation started. Polling status...")
    
    # 3. Poll Status
    start_time = time.time()
    deepdive_activity_detected = False
    
    while True:
        try:
            status_res = requests.get(f"{BASE_URL}/status/{ARXIV_ID}")
            status_data = status_res.json()
            
            status = status_data.get("status")
            message = status_data.get("message", "")
            progress = status_data.get("progress", 0)
            
            # Check for DeepDive activity markers in message
            # e.g. "Analyzed ..."
            if "Analyzed" in message or "analyzing" in message.lower():
                if not deepdive_activity_detected:
                    logger.info(f"DeepDive Activity Detected: {message}")
                    deepdive_activity_detected = True
            
            logger.info(f"Status: {status} | Progress: {progress}% | Msg: {message}")
            
            if status == "completed":
                logger.info("Translation Completed!")
                break
                
            if status == "failed":
                logger.error(f"Translation Failed: {message}")
                sys.exit(1)
                
            # Timeout (10 minutes - DeepDive might take time)
            if time.time() - start_time > 600: 
                logger.error("Timeout waiting for translation")
                sys.exit(1)
                
            time.sleep(2)
            
        except Exception as e:
            logger.error(f"Polling error: {e}")
            time.sleep(2)

    # 4. Final verification
    if deepdive_activity_detected:
        logger.info("SUCCESS: DeepDive activity was detected during processing.")
    else:
        logger.warning("WARNING: DeepDive activity was NOT explicitly detected in status messages (polling might have missed it).")
        
    # Verify PDF exists
    pdf_res = requests.get(f"{BASE_URL}/paper/{ARXIV_ID}/translated")
    if pdf_res.status_code == 200:
         logger.info("SUCCESS: Translated PDF is accessible.")
    else:
         logger.error("ERROR: Translated PDF not found.")
         sys.exit(1)

if __name__ == "__main__":
    test_deepdive_e2e()
