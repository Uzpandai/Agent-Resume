from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any

from resume_agent.llm_client import LLMClient


class TaskStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"


class InputType(str, Enum):
    RAW_TEXT = "raw_text"
    MATURE_RESUME = "mature_resume"
    IMMATURE_RESUME = "immature_resume"


# 可用的简历模板配置
RESUME_TEMPLATES = {
    "classic": {
        "name": "经典模板",
        "description": "传统简约的简历布局，适合大多数求职场景",
        "best_for": [
            "传统行业（金融、制造、医疗等）",
            "国企、事业单位、政府机关",
            "中高层管理岗位",
            "需要稳重专业形象的场景",
        ],
        "style": "单栏布局，标题居中，结构清晰",
    },
    "modern": {
        "name": "两栏布局",
        "description": "经典两栏设计，突出个人特色",
        "best_for": [
            "互联网/科技公司",
            "创业公司、新兴行业",
            "产品、运营、市场类岗位",
            "需要展示多维度能力的场景",
        ],
        "style": "左右分栏，信息密度高，现代感强",
    },
    "left-right": {
        "name": "模块标题背景色",
        "description": "模块标题带背景色，视觉效果突出",
        "best_for": [
            "设计、创意类岗位",
            "市场营销、品牌类岗位",
            "需要展示个性和创意的场景",
            "外企、合资企业",
        ],
        "style": "标题带背景色块，美观大方，吸引眼球",
    },
    "timeline": {
        "name": "时间线风格",
        "description": "时间线布局，强调职业发展轨迹",
        "best_for": [
            "有丰富工作经验的求职者",
            "职业发展路径清晰的候选人",
            "需要突出时间连续性的场景",
            "项目管理、咨询类岗位",
        ],
        "style": "时间线贯穿，经历按时间顺序排列，逻辑清晰",
    },
}


@dataclass
class DecisionState:
    input_type: Optional[InputType] = None
    has_markdown: bool = False
    has_polished_markdown: bool = False
    has_output: bool = False
    todo_list: List[str] = field(default_factory=list)
    template_id: str = "classic"  # 选择的模板
    template_reason: str = ""  # 选择该模板的原因


class DecisionMaker:
    """LLM-driven decision maker for plan-and-solve."""

    def __init__(self, input_type: Optional[InputType] = None, llm_client: Optional[LLMClient] = None):
        # Input type classification is intentionally disabled for now.
        self.state = DecisionState(input_type=input_type)
        self.llm = llm_client

    def decide(self, markdown_text: str, target_role: str = "", job_description: str = "") -> List[str]:
        """
        分析简历内容并决定执行计划
        
        Args:
            markdown_text: 简历的 Markdown 内容
            target_role: 目标岗位（可选）
            job_description: 职位描述/JD（可选）
            
        Returns:
            待执行的任务列表
        """
        todo = self._decide_todo_list(markdown_text, target_role, job_description)
        self.state.todo_list = todo
        return todo
    
    def get_template_decision(self) -> Dict[str, str]:
        """
        获取模板选择决策
        
        Returns:
            包含 template_id, template_name, template_reason 的字典
        """
        template_info = RESUME_TEMPLATES.get(self.state.template_id, RESUME_TEMPLATES["classic"])
        return {
            "template_id": self.state.template_id,
            "template_name": template_info["name"],
            "template_reason": self.state.template_reason,
            "template_description": template_info["description"],
        }
    
    @staticmethod
    def list_available_templates() -> Dict[str, Dict[str, Any]]:
        """列出所有可用模板"""
        return RESUME_TEMPLATES

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

    def _decide_todo_list(self, markdown_text: str, target_role: str = "", job_description: str = "") -> List[str]:
        if self.llm:
            # 构建模板信息
            template_info = self._build_template_prompt()
            
            system_prompt = f"""You are a task planner for a resume generation pipeline.

Your job is to:
1. Analyze the current processing state and determine which tasks need to be executed next
2. Select the most appropriate resume template based on the resume content and target job

## Available Tasks

1. **run_text_modifier**: Polish and enhance the resume markdown content
   - Improves wording, fixes grammar, enhances descriptions
   - Should run when: has_markdown=True AND has_polished_markdown=False

2. **run_resume_generator**: Generate the final resume output (e.g., PDF)
   - Converts polished markdown to final format
   - Should run when: has_polished_markdown=True AND has_output=False

## Available Resume Templates

{template_info}

## Template Selection Guidelines

根据以下因素选择最合适的模板：
1. **目标行业**：传统行业用 classic，互联网/科技用 modern，创意类用 left-right
2. **求职岗位**：管理岗用 classic，技术岗用 modern，设计/营销用 left-right
3. **工作经验**：经验丰富且发展路径清晰用 timeline
4. **公司类型**：国企/事业单位用 classic，外企用 left-right/modern，创业公司用 modern

## Decision Rules

- Tasks should be ordered logically: text_modifier -> resume_generator
- Skip tasks that are already completed (check state flags)
- Set is_complete=True only when has_output=True
- ALWAYS select a template_id and provide a brief reason

## Output Format

Return ONLY valid JSON, no additional text:
{{
  "todo_list": ["task1", "task2"],
  "template_id": "classic",
  "template_reason": "选择该模板的简短原因",
  "is_complete": false
}}"""

            # 构建用户提示
            target_info = ""
            if target_role:
                target_info += f"\n- 目标岗位: {target_role}"
            if job_description:
                target_info += f"\n- 职位描述: {job_description[:500]}"

            user_prompt = f"""## Current State
- has_markdown: {self.state.has_markdown}
- has_polished_markdown: {self.state.has_polished_markdown}
- has_output: {self.state.has_output}{target_info}

## Resume Content
```markdown
{markdown_text[:2000] if len(markdown_text) > 2000 else markdown_text}
```

Based on the current state and resume content:
1. Determine the next tasks to execute
2. Select the most appropriate template for this resume"""

            try:
                response = self.llm.chat(system_prompt, user_prompt)
                data = self._extract_json(response)
                
                # 提取 todo_list
                todo_list = data.get("todo_list", [])
                if not isinstance(todo_list, list):
                    todo_list = []
                todo_list = [t for t in todo_list if isinstance(t, str)]
                
                # 提取模板选择
                template_id = data.get("template_id", "classic")
                if template_id not in RESUME_TEMPLATES:
                    template_id = "classic"
                self.state.template_id = template_id
                self.state.template_reason = data.get("template_reason", "")
                
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

    def _build_template_prompt(self) -> str:
        """构建模板信息的提示词"""
        lines = []
        for tid, info in RESUME_TEMPLATES.items():
            lines.append(f"### {tid}: {info['name']}")
            lines.append(f"- 描述: {info['description']}")
            lines.append(f"- 风格: {info['style']}")
            lines.append(f"- 适用场景:")
            for scene in info['best_for']:
                lines.append(f"  - {scene}")
            lines.append("")
        return "\n".join(lines)

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
