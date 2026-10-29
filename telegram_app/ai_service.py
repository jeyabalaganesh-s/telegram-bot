
import base64
import json
import logging

from openai import OpenAI
from django.conf import settings

logger = logging.getLogger(__name__)


def get_client():
    api_key = getattr(settings, "OPENAI_API_KEY", "")

    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    return OpenAI(api_key=api_key)


def analyze_complaint_text(user_text):
    """Extract complaint information and detect abusive language."""
    client = get_client()
    model = getattr(settings, "OPENAI_MODEL", "gpt-4.1-mini")

    response = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": """
You are an assistant for a public complaint management system.

Return JSON with these keys:
{
  "is_complaint": true,
  "category": "short category",
  "description": "clear description of the reported problem",
  "location": "location if explicitly provided, otherwise empty",
  "additional_details": "other useful details",
  "abusive_language": false
}

Rules:
- Never invent facts or locations.
- Distinguish ordinary frustration from abusive language.
- Set abusive_language to true for insults, harassment, or
  abusive expressions directed at a person or service.
- Do not reject a genuine complaint merely because the user is angry.
- If the message is not a complaint, set is_complaint to false.
- Return valid JSON only.
""",
            },
            {"role": "user", "content": user_text},
        ],
    )

    content = response.choices[0].message.content

    if not content:
        raise ValueError("AI returned an empty response")

    result = json.loads(content)

    if not isinstance(result, dict):
        raise ValueError("AI returned an invalid JSON object")

    return result


def validate_complaint_photo(
    description,
    image_bytes,
    mime_type="image/jpeg",
):
    """Check whether a photo visually supports a complaint."""
    client = get_client()
    model = getattr(settings, "OPENAI_MODEL", "gpt-4.1-mini")

    encoded_image = base64.b64encode(image_bytes).decode("utf-8")
    image_data_url = f"data:{mime_type};base64,{encoded_image}"

    response = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": """
You validate photo evidence for public complaints.

Return JSON:
{
  "result": "valid",
  "notes": "brief explanation"
}

The result must be exactly one of:
- valid: the visible image clearly supports the complaint
- invalid: the image is unrelated to the reported problem
- unclear: the image is too blurry, dark, distant, or ambiguous
  to make a reliable decision

Do not claim the photo proves facts that cannot be seen.
Do not infer the location or identity of the photographer.
If uncertain, choose unclear.
Return valid JSON only.
""",
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Complaint description: {description}",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": image_data_url},
                    },
                ],
            },
        ],
    )

    content = response.choices[0].message.content

    if not content:
        raise ValueError("AI returned an empty response")

    result = json.loads(content)

    if not isinstance(result, dict):
        raise ValueError("AI returned an invalid JSON object")

    if result.get("result") not in {"valid", "invalid", "unclear"}:
        raise ValueError("AI returned an unsupported evidence result")

    return result
