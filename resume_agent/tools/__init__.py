"""Toolbox for the resume agent."""

from resume_agent.tools.input_processor import InputProcessor, InputPayload
from resume_agent.tools.text_modifier import TextModifier, ModifyRequest
from resume_agent.tools.resume_generator import ResumeGenerator, GenerateRequest
from resume_agent.tools.magic_resume_builder import (
    MagicResumeBuilder,
    MagicResumeDocxBuilder,
    ResumeData,
)

__all__ = [
    "InputProcessor",
    "InputPayload",
    "TextModifier",
    "ModifyRequest",
    "ResumeGenerator",
    "GenerateRequest",
    "MagicResumeBuilder",
    "MagicResumeDocxBuilder",
    "ResumeData",
]
