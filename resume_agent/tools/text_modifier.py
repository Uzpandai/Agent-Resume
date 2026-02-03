from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from resume_agent.decision_maker import InputType


@dataclass
class ModifyRequest:
    markdown_text: str
    input_type: InputType
    target_role: Optional[str] = None
    locale: str = "zh-CN"


class DummyLLM:
    """Placeholder LLM. Replace with a real model integration."""

    def rewrite(self, prompt: str) -> str:
        # Simple heuristic: keep content but improve formatting.
        lines = [ln.strip() for ln in prompt.splitlines() if ln.strip()]
        bullet_lines = []
        for line in lines:
            if line.startswith("-") or line.startswith("*"):
                bullet_lines.append(line)
            else:
                bullet_lines.append(f"- {line}")
        return "\n".join(bullet_lines)


class TextModifier:
    """Improve and restructure resume markdown."""

    def __init__(self, llm: Optional[DummyLLM] = None):
        self.llm = llm or DummyLLM()

    def run(self, request: ModifyRequest) -> str:
        prompt = self._build_prompt(request)
        return self.llm.rewrite(prompt)

    def _build_prompt(self, request: ModifyRequest) -> str:
        guidance = {
            InputType.RAW_TEXT: "将描述整理为正式简历条目，补足动词并统一格式。",
            InputType.MATURE_RESUME: "保持结构，微调措辞并增强成果表达。",
            InputType.IMMATURE_RESUME: "重构结构，补足缺失模块并统一风格。",
        }[request.input_type]

        target = f"目标岗位: {request.target_role}" if request.target_role else "目标岗位: 通用"
        return (
            f"{guidance}\n{target}\n\n"
            f"以下是原始简历内容，请整理成更专业的Markdown：\n\n{request.markdown_text}"
        )
