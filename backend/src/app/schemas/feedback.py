from pydantic import BaseModel, Field

MAX_ANSWER_CHARS = 8000


class FeedbackRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    question: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1, max_length=MAX_ANSWER_CHARS)
    is_approved: bool


class FeedbackResponse(BaseModel):
    chat_range_id: str
