import subprocess
import json

cmd = [
    "/opt/homebrew/share/google-cloud-sdk/bin/gcloud", "logging", "read",
    'resource.labels.service_name="readpaper-backend" AND textPayload:"Traceback"',
    "--project=gen-lang-client-0098594892",
    "--format=json",
    "--limit=50"
]

res = subprocess.run(cmd, capture_output=True, text=True)
if res.returncode == 0:
    logs = json.loads(res.stdout)
    for i, log in enumerate(logs):
        text = log.get("textPayload", "")
        if "main.py" in text and "arxiv_translator" in text:
            print(f"--- Traceback {i} ---")
            print(text)
else:
    print("Failed to run gcloud:")
    print(res.stderr)
