import time
import requests


def main():
    with open(r"e:/Dev/translate_agent/_tmp_smoke/smoke.docx", "rb") as f:
        files = {"file": f}
        data = {"target_lang": "Japanese", "speed_mode": "balanced"}
        resp = requests.post("http://127.0.0.1:5000/translate", files=files, data=data, timeout=30)

    print("SUBMIT_STATUS", resp.status_code)
    print("SUBMIT_BODY", resp.text)
    if resp.status_code != 200:
        return

    task_id = resp.json().get("task_id")
    print("TASK_ID", task_id)

    for _ in range(80):
        status_resp = requests.get(f"http://127.0.0.1:5000/status/{task_id}", timeout=20)
        payload = status_resp.json()
        status = payload.get("status")
        if status in ("completed", "failed"):
            print("FINAL_STATUS", status)
            print("DOWNLOAD_NAME", payload.get("download_name"))
            print("FILENAME_QA_OK", payload.get("filename_translation_ok"))
            print("FILENAME_QA_ISSUE", payload.get("filename_translation_issue"))
            return
        time.sleep(0.5)

    print("FINAL_STATUS", "timeout")


if __name__ == "__main__":
    main()