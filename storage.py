import os
from pathlib import Path
import yaml

DEFAULT_COLLECTIONS = [
    {
        "name": "General API Tests",
        "requests": [
            {
                "name": "Fetch Sample Post",
                "method": "GET",
                "url": "https://jsonplaceholder.typicode.com/posts/1",
                "headers": {"Accept": "application/json"},
                "body": ""
            },
            {
                "name": "Create Post (JSON)",
                "method": "POST",
                "url": "https://jsonplaceholder.typicode.com/posts",
                "headers": {"Content-Type": "application/json"},
                "body": '{\n  "title": "Ghostman Test",\n  "body": "Fast TUI API client",\n  "userId": 42\n}'
            },
            {
                "name": "GitHub Public User",
                "method": "GET",
                "url": "https://api.github.com/users/octocat",
                "headers": {"User-Agent": "Ghostman"},
                "body": ""
            }
        ]
    }
]

class StorageManager:
    def __init__(self, workspace_path: str = None):
        self.workspace_dir = Path(workspace_path or os.getcwd()) / ".ghostman"
        self.file_path = self.workspace_dir / "collections.yaml"
        self._init_storage()

    def _init_storage(self):
        if not self.workspace_dir.exists():
            self.workspace_dir.mkdir(parents=True, exist_ok=True)
        if not self.file_path.exists():
            self.save_collections(DEFAULT_COLLECTIONS)

    def load_collections(self):
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                return data if isinstance(data, list) else DEFAULT_COLLECTIONS
        except Exception:
            return DEFAULT_COLLECTIONS

    def save_collections(self, collections: list):
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                yaml.dump(collections, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        except Exception as e:
            print(f"[Ghostman] Warning: unable to write collections: {e}")
