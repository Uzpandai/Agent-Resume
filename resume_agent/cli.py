from __future__ import annotations

import argparse
from pathlib import Path

from resume_agent.decision_maker import DecisionMaker, InputType
from resume_agent.llm_client import LLMClient
from resume_agent.tools.input_processor import InputPayload, InputProcessor
from resume_agent.tools.text_modifier import ModifyRequest, TextModifier
from resume_agent.tools.resume_generator import GenerateRequest, ResumeGenerator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resume Assistant Agent")
    parser.add_argument("--input", type=str, help="Path to input file (.txt/.pdf/.docx)")
    parser.add_argument("--text", type=str, help="Raw text input")
    parser.add_argument("--format", type=str, default="pdf", help="Output format: pdf or docx")
    parser.add_argument("--output-dir", type=str, default="output", help="Output directory")
    parser.add_argument("--target-role", type=str, help="Target role")
    parser.add_argument("--name", type=str, default="候选人", help="Candidate name")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = InputPayload(
        source_path=Path(args.input) if args.input else None,
        raw_text=args.text,
    )

    input_processor = InputProcessor()
    markdown, _ = input_processor.run(payload)

    llm_client = LLMClient.from_env()
    decision_maker = DecisionMaker(llm_client=llm_client)
    decision_maker.update_progress(markdown=True)

    todo = decision_maker.decide(markdown)

    polished = markdown
    if "run_text_modifier" in todo:
        modifier = TextModifier(llm_client=llm_client)
        polished = modifier.run(
            ModifyRequest(
                markdown_text=markdown,
                input_type=decision_maker.state.input_type or InputType.RAW_TEXT,
                target_role=args.target_role,
            )
        )
        decision_maker.update_progress(polished=True)

    if "run_resume_generator" in todo:
        generator = ResumeGenerator()
        output_path = generator.run(
            GenerateRequest(
                markdown_text=polished,
                output_dir=Path(args.output_dir),
                output_format=args.format,
                candidate_name=args.name,
            )
        )
        decision_maker.update_progress(output=True)
        print(f"Generated: {output_path}")


if __name__ == "__main__":
    main()
