import os

from google import genai
from google.genai import types

from citywheels.agent import ModelReply, ToolCall, ToolSpec

DEFAULT_MODEL = "gemini-3.5-flash"


class MissingApiKey(Exception):
    pass


def _to_contents(messages: list[dict]) -> list[types.Content]:
    contents: list[types.Content] = []
    for message in messages:
        if message["role"] == "user":
            contents.append(types.Content(role="user", parts=[types.Part(text=message["text"])]))
        elif message["role"] == "assistant":
            # Replay Gemini's own content when we have it: it carries thought signatures that a
            # rebuilt function_call part would lose.
            if message.get("raw") is not None:
                contents.append(message["raw"])
                continue
            parts = [
                types.Part(function_call=types.FunctionCall(name=c.name, args=c.args, id=c.id))
                for c in message["tool_calls"]
            ]
            contents.append(types.Content(role="model", parts=parts))
        else:
            # function_response.response must be a dict; search_policies returns a list.
            part = types.Part(
                function_response=types.FunctionResponse(
                    name=message["name"], id=message["id"], response={"result": message["result"]}
                )
            )
            previous = contents[-1] if contents else None
            if previous is not None and previous.role == "user" and previous.parts[0].function_response:
                previous.parts.append(part)
            else:
                contents.append(types.Content(role="user", parts=[part]))
    return contents


def _config(system_prompt: str, tools: list[ToolSpec]) -> types.GenerateContentConfig:
    declarations = [
        types.FunctionDeclaration(
            name=t.name, description=t.description, parameters_json_schema=t.parameters
        )
        for t in tools
    ]
    return types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=[types.Tool(function_declarations=declarations)],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        temperature=0,
    )


def _to_reply(response: types.GenerateContentResponse) -> ModelReply:
    content = response.candidates[0].content if response.candidates else None
    if content is None or not content.parts:
        return ModelReply()
    text = "".join(p.text for p in content.parts if p.text and not p.thought)
    calls = tuple(
        ToolCall(p.function_call.name, dict(p.function_call.args or {}), p.function_call.id)
        for p in content.parts
        if p.function_call
    )
    return ModelReply(text=text or None, tool_calls=calls, raw=content)


class GeminiModel:
    def __init__(self, client, model_name: str = DEFAULT_MODEL):
        self.client = client
        self.model_name = model_name

    @classmethod
    def from_env(cls) -> "GeminiModel":
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise MissingApiKey
        model_name = os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL
        return cls(genai.Client(api_key=api_key), model_name)

    def generate(self, system_prompt: str, messages: list[dict], tools: list[ToolSpec]) -> ModelReply:
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=_to_contents(messages),
            config=_config(system_prompt, tools),
        )
        return _to_reply(response)
