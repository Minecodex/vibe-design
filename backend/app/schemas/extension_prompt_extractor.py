from pydantic import BaseModel


class PromptExtractorAnalyzeResponse(BaseModel):
    prompt: str
    prompts: dict[str, str]
    language: str
    model: str
    amount_cents: int
