"""Pydantic models for the OpenAI-compatible surface."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ContentPart(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: str | None = None
    text: str | None = None
    image_url: dict | str | None = None
    source: dict | None = None
    data: str | None = None
    mimeType: str | None = None
    caption: str | None = None


class Message(BaseModel):
    model_config = ConfigDict(extra="allow")
    role: str
    content: str | list[ContentPart] | None = None
    name: str | None = None
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None
    function_call: dict | None = None
    reasoning_content: str | None = None
    signature: str | None = None
    signature_type: str | None = None
    thinking: str | None = None
    is_error: bool | None = None


class FunctionDef(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    description: str | None = None
    parameters: dict | None = None
    strict: bool | None = None


class Tool(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: str = "function"
    function: FunctionDef


class ToolChoice(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: str = "function"
    function: dict | None = None


class ResponseFormat(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: str = "text"
    json_schema: dict | None = None


class StreamOptions(BaseModel):
    model_config = ConfigDict(extra="allow")
    include_usage: bool | None = None


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str | None = None
    messages: list[Message] = []
    temperature: float | None = None
    top_p: float | None = None
    n: int | None = None
    stream: bool = False
    stream_options: StreamOptions | None = None
    stop: str | list[str] | None = None
    max_tokens: int | None = None
    max_completion_tokens: int | None = None
    presence_penalty: float | None = None
    frequency_penalty: float | None = None
    logit_bias: dict | None = None
    logprobs: bool | None = None
    top_logprobs: int | None = None
    seed: int | None = None
    tools: list[Tool] | None = None
    tool_choice: str | ToolChoice | None = None
    response_format: ResponseFormat | None = None
    service_tier: str | None = None
    reasoning_effort: str | None = None
    reasoning: dict | None = None
    thinking: dict | None = None
    enable_thinking: bool | None = None
    chat_template_kwargs: dict | None = None
