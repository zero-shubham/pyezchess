from __future__ import annotations

from pathlib import Path


class PromptGetter:
    _instance: PromptGetter | None = None
    
    main: str
    levels: dict[int, str]

    def __new__(cls, prompts_dir: str | Path | None = None) -> PromptGetter:
        if cls._instance is not None:
            return cls._instance
        if prompts_dir is None:
            raise TypeError("PromptGetter() missing required argument: prompts_dir")
        self = super().__new__(cls)
        prompts_dir = Path(prompts_dir)
        main_path = prompts_dir / "main.md"
        if not main_path.exists():
            raise FileNotFoundError(f"main prompt not found: {main_path}")
        self.main = main_path.read_text(encoding="utf-8")
        self.levels = {}
        for level in range(1, 5):
            path = prompts_dir / f"level{level}.md"
            if path.exists():
                self.levels[level] = path.read_text(encoding="utf-8")
        cls._instance = self
        return self

    def main_prompt(self) -> str:
        return self.main

    def level_details(self, level: int) -> str:
        if level < 1 or level > 4 or level not in self.levels:
            return ""
        content = self.levels[level]
        topic = self._extract_topic_id(content)
        if topic:
            content += f"\n\n## Topic ID Reference\nUse topic IDs like '{topic}' when calling mark_topic_started or mark_topic_completed.\n"
        return content

    @staticmethod
    def _extract_topic_id(content: str) -> str:
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("### "):
                rest = line[4:]
                parts = rest.split(" ", 1)
                if "." in parts[0] and parts[0].split(".")[0].isdigit():
                    return parts[0]
        return ""
