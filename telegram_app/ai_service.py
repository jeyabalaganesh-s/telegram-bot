
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
You are JEMI, an assistant for a public complaint management system.

Return a JSON object with these keys:
{
  "is_complaint": false,
  "category": "",
  "description": "",
  "location": "",
  "additional_details": "",
  "abusive_language": false
}

Rules:
- A genuine report of a damaged or broken item is a complaint.
- Examples include damaged dustbins, broken streetlights,
  damaged roads, broken chairs, and overflowing waste bins.
- A short greeting such as "Hi", "Hello", or "Hey" is not a complaint.
- Thanks, casual conversation, and ordinary questions are not complaints.
- Do not classify a message as a complaint just because it mentions an object.
- Never invent facts or locations.
- Extract a location only if the user explicitly provides one.
- Put the main problem in description.
- Put follow-up details or specific damage in additional_details
  when appropriate.
- Distinguish ordinary frustration from abusive language.
- Set abusive_language to true for insults, harassment, or
  abusive expressions directed at a person or service.
- Do not reject a genuine complaint merely because the user is angry.
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
    """
    Check whether an image is consistent with the reported problem.

    The description should include the original complaint and any
    additional details supplied by the user.
    """
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
You are JEMI's photo-evidence assessment assistant.

Your task is to decide whether a submitted photo is relevant to
the problem described by the user.

Return JSON in this exact structure:
{
  "result": "valid",
  "notes": "Brief explanation of the visible evidence."
}

The result must be exactly one of:
- valid
- invalid
- unclear

Decision rules:

1. VALID:
   The image shows the object or scene described in the complaint,
   and the visible evidence is reasonably consistent with the reported
   problem. Accept a relevant image even if the exact damage is subtle,
   partially hidden, or not perfectly visible.

2. INVALID:
   The image is clearly unrelated to the reported complaint.
   For example, a photo of a road is submitted for a complaint about
   a broken office chair, with no relevant connection.

3. UNCLEAR:
   The image is too blurry, dark, distant, or obstructed to determine
   whether it is relevant, or the complaint lacks enough detail to
   make a reasonable comparison.

Additional rules:
- Consider the entire complaint context, including the original
  description, category, and any follow-up details.
- A follow-up such as "the chair handle is broken and missing"
  is important evidence context even if the original description
  only says "damaged chair."
- If the photo shows the correct object and the reported damage is
  plausible, do not reject it merely because every detail cannot
  be seen clearly.
- A torn, cracked, broken, or visibly damaged object can support
  a complaint about that object when the details are consistent.
- Do not require proof of the exact location from the image.
- Do not infer the identity of the photographer or claim facts
  that are not visible.
- Do not automatically accept every image. Clearly unrelated images
  should be marked invalid.
- Be fair and practical. This is preliminary evidence screening,
  not a final administrative decision.
- Keep notes short, factual, and respectful.
- Return valid JSON only.
""",
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Review the following complaint context and "
                            "compare it with the attached photo:\n\n"
                            f"{description}"
                        ),
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

    if not isinstance(result.get("notes", ""), str):
        raise ValueError("AI returned invalid evidence notes")

    return result
