from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from resume_agent.llm_client import LLMClient


class TaskStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"


class InputType(str, Enum):
    RAW_TEXT = "raw_text"
    MATURE_RESUME = "mature_resume"
    IMMATURE_RESUME = "immature_resume"


@dataclass
class DecisionState:
    input_type: Optional[InputType] = None
    has_markdown: bool = False
    has_polished_markdown: bool = False
    has_output: bool = False
    todo_list: List[str] = field(default_factory=list)


class DecisionMaker:
    """LLM-driven decision maker for plan-and-solve."""

    def __init__(self, input_type: Optional[InputType] = None, llm_client: Optional[LLMClient] = None):
        # Input type classification is intentionally disabled for now.
        self.state = DecisionState(input_type=input_type)
        self.llm = llm_client

    def decide(self, markdown_text: str) -> List[str]:
        todo = self._decide_todo_list(markdown_text)
        self.state.todo_list = todo
        return todo

    def update_progress(self, *, markdown: bool = False, polished: bool = False, output: bool = False) -> None:
        if markdown:
            self.state.has_markdown = True
        if polished:
            self.state.has_polished_markdown = True
        if output:
            self.state.has_output = True

    def decide_status(self) -> TaskStatus:
        if self.state.has_output:
            return TaskStatus.COMPLETE
        return TaskStatus.IN_PROGRESS

    def _decide_todo_list(self, markdown_text: str) -> List[str]:
        if self.llm:
            system_prompt = """You are a task planner for a resume generation pipeline.

Your job is to analyze the current processing state and determine which tasks need to be executed next.

## Available Tasks

1. **run_text_modifier**: Polish and enhance the resume markdown content
   - Improves wording, fixes grammar, enhances descriptions
   - Should run when: has_markdown=True AND has_polished_markdown=False

2. **run_resume_generator**: Generate the final resume output (e.g., PDF)
   - Converts polished markdown to final format
   - Should run when: has_polished_markdown=True AND has_output=False

## Decision Rules

- Tasks should be ordered logically: text_modifier -> resume_generator
- Skip tasks that are already completed (check state flags)
- Set is_complete=True only when has_output=True

## Output Format

Return ONLY valid JSON, no additional text:
{"todo_list": ["task1", "task2"], "is_complete": false}"""

            user_prompt = f"""## Current State
- has_markdown: {self.state.has_markdown}
- has_polished_markdown: {self.state.has_polished_markdown}
- has_output: {self.state.has_output}

## Resume Content
```markdown
{markdown_text[:2000] if len(markdown_text) > 2000 else markdown_text}
```

Based on the current state, determine the next tasks to execute."""
            try:
                response = self.llm.chat(system_prompt, user_prompt)
                data = self._extract_json(response)
                todo_list = data.get("todo_list", [])
                if not isinstance(todo_list, list):
                    todo_list = []
                todo_list = [t for t in todo_list if isinstance(t, str)]
                # Ensure input processor is not re-run after markdown is present.
                if self.state.has_markdown:
                    todo_list = [t for t in todo_list if t != "run_input_processor"]
                # Ensure required steps are present if missing.
                if not self.state.has_polished_markdown and "run_text_modifier" not in todo_list:
                    todo_list.append("run_text_modifier")
                if not self.state.has_output and "run_resume_generator" not in todo_list:
                    todo_list.append("run_resume_generator")
                return todo_list
            except Exception:
                pass

        return self._fallback_todo_list()

    def _fallback_todo_list(self) -> List[str]:
        todo: List[str] = []
        if not self.state.has_markdown:
            todo.append("run_input_processor")
        if not self.state.has_polished_markdown:
            todo.append("run_text_modifier")
        if not self.state.has_output:
            todo.append("run_resume_generator")
        return todo

    @staticmethod
    def _extract_json(text: str) -> dict:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("No JSON found in LLM response.")
        import json

        return json.loads(text[start : end + 1])
