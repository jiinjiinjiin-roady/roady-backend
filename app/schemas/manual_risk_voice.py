from pydantic import Field, field_validator

from app.schemas.base import ApiBaseModel, ApiRequestModel


class ManualRiskVoiceOption(ApiRequestModel):
    id: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=160)

    @field_validator("id", "label", mode="before")
    @classmethod
    def normalize_non_empty(cls, value: object) -> str:
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("Manual risk voice option values must not be empty.")
        return normalized


class ManualRiskVoiceMatchRequest(ApiRequestModel):
    transcript: str = Field(min_length=1, max_length=1000)
    options: list[ManualRiskVoiceOption] = Field(min_length=1, max_length=6)

    @field_validator("transcript", mode="before")
    @classmethod
    def normalize_transcript(cls, value: object) -> str:
        transcript = str(value).strip()
        if not transcript:
            raise ValueError("Manual risk voice transcript must not be empty.")
        return transcript

    @field_validator("options")
    @classmethod
    def ensure_unique_option_ids(
        cls, options: list[ManualRiskVoiceOption]
    ) -> list[ManualRiskVoiceOption]:
        if len({option.id for option in options}) != len(options):
            raise ValueError("Manual risk voice option IDs must be unique.")
        return options


class ManualRiskVoiceTranscriptionResponse(ApiBaseModel):
    transcript: str


class ManualRiskVoiceMatchResponse(ApiBaseModel):
    option_id: str | None
