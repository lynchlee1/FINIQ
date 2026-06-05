from pathlib import Path
import json

SAVED_SETTINGS_KEYS = ("html_parse_result_path", "html_parse_mode")

class Config:
    html_parse_result_path = ""
    html_parse_mode = ""

class Server:
    config = Config()

server = Server()
payload = {"html_parse_result_path": "/my/custom/path"}

for attr in SAVED_SETTINGS_KEYS:
    if attr in payload:
        value = payload.get(attr)
        if attr == "html_parse_mode":
            setattr(server.config, attr, str(value or ""))
        else:
            setattr(server.config, attr, str(Path(str(value or "")).expanduser().resolve()) if value else "")

print("Saved:", server.config.html_parse_result_path)
