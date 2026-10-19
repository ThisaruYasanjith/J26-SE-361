import requests
import json

payload = {
    "old_method": (
        "public void processAccountFile(Account account, Long accountId, java.nio.file.Path path, "
        "java.nio.file.Path backupPath, String message, double amount, int quantity, boolean enabled) "
        "throws java.io.IOException {\n"
        "    accountRepository.findById(accountId);\n"
        "}"
    ),
    "new_method": (
        "public void processAccountFile(Account account, Long accountId, java.nio.file.Path path, "
        "java.nio.file.Path backupPath, String message, double amount, int quantity, boolean enabled) "
        "throws java.io.IOException {\n"
        "    java.nio.file.Files.writeString(path, message);\n"
        "    accountRepository.findById(accountId);\n"
        "}"
    )
}

resp = requests.post("http://127.0.0.1:8000/analyze", json=payload, timeout=30)
print(f"HTTP Status: {resp.status_code}")
print(json.dumps(resp.json(), indent=2))
