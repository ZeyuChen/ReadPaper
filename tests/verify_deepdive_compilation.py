import requests
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:8000"

# Configuration
TEST_CASES = [
    {
        "id": "2412.15115", # Qwen2.5
        "name": "Qwen2.5 Technical Report",
        "deepdive": True
    }
    # {
    #     "id": "2406.12793", # GLM-4
    #     "name": "GLM-4 Technical Report",
    #     "deepdive": False 
    # }
]

def trigger_translation(paper):
    url = f"{BASE_URL}/translate"
    payload = {
        "arxiv_url": f"https://arxiv.org/abs/{paper['id']}",
        "model": "flash",
        "deepdive": paper['deepdive']
    }
    
    try:
        # cleanup first
        requests.delete(f"{BASE_URL}/library/{paper['id']}")
    except:
        pass
        
    logger.info(f"Triggering translation for {paper['name']} (DeepDive={paper['deepdive']})...")
    resp = requests.post(url, json=payload)
    if resp.status_code == 200:
        logger.info(f"Successfully started {paper['id']}")
        return True
    else:
        logger.error(f"Failed start {paper['id']}: {resp.text}")
        return False

def check_status(paper_id):
    try:
        resp = requests.get(f"{BASE_URL}/status/{paper_id}")
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.warning(f"Status check failed for {paper_id}: {e}")
    return None

def run_verification():
    # Start both
    active_papers = []
    for paper in TEST_CASES:
        if trigger_translation(paper):
            active_papers.append(paper)
            
    # Poll
    max_wait = 1200 # 20 mins
    start_time = time.time()
    
    completed = set()
    failed = set() # (id, reason)
    
    while len(completed) + len(failed) < len(active_papers):
        if time.time() - start_time > max_wait:
            logger.error("Timeout reached.")
            break
            
        for paper in active_papers:
            pid = paper['id']
            if pid in completed or pid in [x[0] for x in failed]:
                continue
                
            status = check_status(pid)
            if not status:
                continue
                
            s = status.get("status")
            msg = status.get("message", "")
            progress = status.get("progress", 0)
            
            if s == "completed":
                logger.info(f"[{pid}] COMPLETED: {msg}")
                completed.add(pid)
            elif s == "failed":
                logger.error(f"[{pid}] FAILED: {msg}")
                failed.add((pid, msg))
            else:
                 # Periodic log?
                 pass

        time.sleep(10)
        
    # Summary
    logger.info("=== Verification Summary ===")
    for paper in TEST_CASES:
        pid = paper['id']
        res = "UNKNOWN"
        if pid in completed: res = "SUCCESS"
        elif pid in [x[0] for x in failed]: res = "FAILED"
        
        logger.info(f"{paper['name']} (DeepDive={paper['deepdive']}): {res}")

if __name__ == "__main__":
    run_verification()
