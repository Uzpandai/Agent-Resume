# Agent-Resume

This project implements a **job resume assistant agent** with a plan-and-solve workflow. It supports three input types:

1. **Pure text**: Only plain descriptions of experience/project history (possibly informal language).
2. **Mature resume**: An existing resume that needs small tweaks or an additional project.
3. **Immature resume**: Needs major restructuring and rewriting.

It outputs a **polished resume** in **PDF** (LaTeX) or **Word** (`.docx`) format.

## How It Works (Plan-and-Solve)
The agent uses a **Decision Maker** to:

- Determine current status and whether the task is complete
- Build a to-do list
- Choose which tools to run

**Toolbox** (always invoked via the Decision Maker):

- `InputProcessor`: Converts text/PDF/Word input to Markdown (always called for every input)
- `TextModifier`: Rewrites and improves the resume text
- `ResumeGenerator`: Generates a PDF via LaTeX (and optionally Word)

## LLM Configuration (DeepSeek)

Set environment variables to enable LLM-based decisions:

- `DEEPSEEK_API_KEY`: required
- `DEEPSEEK_BASE_URL`: optional, default `https://api.deepseek.com`
- `DEEPSEEK_MODEL`: optional, default `deepseek-chat`
- `DEEPSEEK_TIMEOUT`: optional, default `30`

If `DEEPSEEK_API_KEY` is not set, the Decision Maker falls back to the default to-do list.

## Quick Start

```bash
python -m resume_agent --input ./data/input.txt --format pdf
```

### Direct Text Input

```bash
python -m resume_agent --text "我做过..." --format pdf
```

## Output

- `output/resume.md`: normalized and polished resume content
- `output/resume.tex`: LaTeX source
- `output/resume.pdf`: PDF output (if `pdflatex` is available)
- `output/resume.docx`: Word output (if `python-docx` is available)

## Notes
- This implementation is dependency-light; if a tool is unavailable, it falls back and logs a warning.
- You can integrate a real LLM by replacing the dummy model in `resume_agent/text_modifier.py`.
