import os
from pathlib import Path
import json

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

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
        self.yaml_file = self.workspace_dir / "collections.yaml"
        self.json_file = self.workspace_dir / "collections.json"
        self._init_storage()

    def _init_storage(self):
        if not self.workspace_dir.exists():
            self.workspace_dir.mkdir(parents=True, exist_ok=True)
        if not self.yaml_file.exists() and not self.json_file.exists():
            self.save_collections(DEFAULT_COLLECTIONS)

    def load_collections(self):
        # 1. Try YAML if available and file exists
        if HAS_YAML and self.yaml_file.exists():
            try:
                with open(self.yaml_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if isinstance(data, list) and len(data) > 0:
                        return data
            except Exception:
                pass

        # 2. Try JSON (zero dependencies, works on any Python out of the box)
        if self.json_file.exists():
            try:
                with open(self.json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list) and len(data) > 0:
                        return data
            except Exception:
                pass

        return DEFAULT_COLLECTIONS

    def save_collections(self, collections: list):
        # Always save JSON as reliable fallback
        try:
            with open(self.json_file, "w", encoding="utf-8") as f:
                json.dump(collections, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[Ghostman] Warning: unable to write JSON collections: {e}")

        # Also save YAML if module is available
        if HAS_YAML:
            try:
                with open(self.yaml_file, "w", encoding="utf-8") as f:
                    yaml.dump(collections, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
            except Exception as e:
                print(f"[Ghostman] Warning: unable to write YAML collections: {e}")
