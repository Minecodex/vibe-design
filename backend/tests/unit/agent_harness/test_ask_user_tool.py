from types import SimpleNamespace

from app.services.agent_harness.capabilities.tools.ask_user import (
    AskUserInput,
    AskUserTool,
    _build_ask_user_payload,
)


def _valid_args(**overrides):
    payload = {
        "title": "Content direction",
        "description": "I will infer the rest from your choices.",
        "submit_label": "Confirm",
        "questions": [
            {
                "id": "service_focus",
                "header": "Service focus",
                "question": "What should this page emphasize?",
                "type": "multiple",
                "required": True,
                "max_selections": 3,
                "options": [
                    {"label": "Brand visual", "value": "branding"},
                    {"label": "Landing page", "value": "landing_page"},
                    {"label": "Portfolio", "value": "portfolio"},
                ],
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_build_ask_user_choice_payload():
    error, payload = _build_ask_user_payload(_valid_args(answers={"service_focus": ["branding"], "ignored": "x"}))

    assert error is None
    assert payload is not None
    assert payload["kind"] == "ask_user"
    assert payload["question"] == "Content direction"
    assert payload["answers"] == {"service_focus": ["branding"]}
    assert payload["schema"] == {
        "title": "Content direction",
        "description": "I will infer the rest from your choices.",
        "submit_label": "Confirm",
        "questions": [
            {
                "id": "service_focus",
                "header": "Service focus",
                "question": "What should this page emphasize?",
                "type": "multiple",
                "required": True,
                "max_selections": 3,
                "options": [
                    {
                        "label": "Brand visual",
                        "value": "branding",
                        "description": None,
                        "preview_url": None,
                        "metadata": None,
                    },
                    {
                        "label": "Landing page",
                        "value": "landing_page",
                        "description": None,
                        "preview_url": None,
                        "metadata": None,
                    },
                    {
                        "label": "Portfolio",
                        "value": "portfolio",
                        "description": None,
                        "preview_url": None,
                        "metadata": None,
                    },
                ],
            }
        ],
    }


def test_build_ask_user_rejects_legacy_schema_fields():
    error, payload = _build_ask_user_payload({
        "question": "Need a few choices",
        "schema": {
            "title": "Quick brief",
            "fields": [
                {
                    "id": "design_system",
                    "label": "Choose a design system",
                    "type": "radio",
                    "options": [
                        {"label": "Atelier Zero", "value": "atelier_zero"},
                        {"label": "Framer", "value": "framer"},
                    ],
                }
            ],
        },
    })

    assert payload is None
    assert error == "Unsupported legacy ask_user interaction: use top-level title, submit_label, and questions[]."


def test_build_ask_user_rejects_top_level_fields():
    error, payload = _build_ask_user_payload({
        "title": "Need a choice",
        "submit_label": "Submit",
        "fields": [
            {"id": "choice", "label": "First?", "type": "radio", "options": [{"label": "A", "value": "a"}]},
        ],
    })

    assert payload is None
    assert error == "Unsupported legacy ask_user interaction: use top-level title, submit_label, and questions[]."


def test_build_ask_user_rejects_invalid_questions_and_options():
    too_many_questions = [
        {
            "id": f"q_{index}",
            "header": "Header",
            "question": "Question?",
            "type": "single",
            "options": [{"label": "A", "value": "a"}, {"label": "B", "value": "b"}],
        }
        for index in range(6)
    ]
    error, payload = _build_ask_user_payload(_valid_args(questions=too_many_questions))
    assert payload is None
    assert error == "ask_user questions must include 1-5 items."

    error, payload = _build_ask_user_payload(_valid_args(questions=[
        {
            "id": "q",
            "header": "Header",
            "question": "Question?",
            "type": "single",
            "options": [{"label": "A", "value": "a"}],
        }
    ]))
    assert payload is None
    assert error == "ask_user question options must include 2-4 items."


def test_build_ask_user_rejects_model_authored_other_and_duplicates():
    error, payload = _build_ask_user_payload(_valid_args(questions=[
        {
            "id": "q",
            "header": "Header",
            "question": "Question?",
            "type": "single",
            "options": [{"label": "Other", "value": "other"}, {"label": "A", "value": "a"}],
        }
    ]))
    assert payload is None
    assert error == "ask_user options must not include Other; the UI provides it automatically."

    error, payload = _build_ask_user_payload(_valid_args(questions=[
        {
            "id": "q",
            "header": "Header",
            "question": "Question?",
            "type": "single",
            "options": [{"label": "A", "value": "a"}, {"label": "A", "value": "b"}],
        }
    ]))
    assert payload is None
    assert error == "ask_user option labels and values must be unique within each question."


def test_build_ask_user_rejects_duplicate_question_ids_and_bad_max_selections():
    question = {
        "id": "q",
        "header": "Header",
        "question": "Question?",
        "type": "single",
        "options": [{"label": "A", "value": "a"}, {"label": "B", "value": "b"}],
    }
    error, payload = _build_ask_user_payload(_valid_args(questions=[question, question]))
    assert payload is None
    assert error == "ask_user question ids must be unique."

    error, payload = _build_ask_user_payload(_valid_args(questions=[{**question, "max_selections": 1}]))
    assert payload is None
    assert error == "ask_user max_selections is only valid for multiple questions."


def test_build_ask_user_accepts_one_short_input_question():
    error, payload = _build_ask_user_payload(_valid_args(questions=[
        {
            "id": "brand_name",
            "header": "Brand",
            "question": "What brand name should I use?",
            "type": "input",
            "options": [],
        },
        {
            "id": "tone",
            "header": "Tone",
            "question": "What tone should the page use?",
            "type": "single",
            "options": [{"label": "Calm", "value": "calm"}, {"label": "Bold", "value": "bold"}],
        },
    ]))

    assert error is None
    assert payload is not None
    assert payload["schema"]["questions"][0]["type"] == "input"
    assert payload["schema"]["questions"][0]["required"] is True
    assert payload["schema"]["questions"][0]["options"] == []


def test_build_ask_user_accepts_optional_input_question():
    error, payload = _build_ask_user_payload(_valid_args(questions=[
        {
            "id": "brand_link",
            "header": "Optional link",
            "question": "Paste a URL if you have one.",
            "type": "input",
            "required": False,
            "options": [],
        },
        {
            "id": "tone",
            "header": "Tone",
            "question": "What tone should the page use?",
            "type": "single",
            "options": [{"label": "Calm", "value": "calm"}, {"label": "Bold", "value": "bold"}],
        },
    ]))

    assert error is None
    assert payload is not None
    assert payload["schema"]["questions"][0]["required"] is False


def test_build_ask_user_rejects_multiple_input_questions_or_input_options():
    input_question = {
        "id": "brand_name",
        "header": "Brand",
        "question": "What brand name should I use?",
        "type": "input",
        "options": [],
    }
    error, payload = _build_ask_user_payload(_valid_args(questions=[
        input_question,
        {**input_question, "id": "brand_url", "question": "What URL should I use?"},
    ]))
    assert payload is None
    assert error == "ask_user input questions must be used sparingly: at most one input question per call."

    error, payload = _build_ask_user_payload(_valid_args(questions=[
        {**input_question, "options": [{"label": "Acme", "value": "acme"}, {"label": "Nova", "value": "nova"}]},
    ]))
    assert payload is None
    assert error == "ask_user input questions must not include options."


def test_ask_user_description_is_choice_question_only():
    description = AskUserTool().description

    assert "Render choice questions" in description
    assert "not a general form tool" in description
    assert "Use ask_user only for the decision UI" in description
    assert "first write complete standalone assistant text" in description
    assert "Do not call ask_user after only a promise or lead-in" in description
    assert "description field must be short UI helper text" in description
    assert "must not imply there is unseen content below the card" in description
    assert "Ask 1-5 questions per call" in description
    assert "Use input sparingly" in description
    assert "never include Other/custom options yourself" in description
    assert "Do not ask users to fill long-form factual fields" in description


def test_planning_phase_blocks_fourth_ask_user(monkeypatch):
    def fake_get_conversation(_user_id, _conversation_id):
        return {"runtime_state": {"phase": "planning", "ask_user_phase_counts": {"planning": 3}}}

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.session_v2.service.get_conversation",
        fake_get_conversation,
    )

    params = AskUserInput.model_validate(_valid_args())
    error = AskUserTool().validate_input(params, SimpleNamespace(user_id=1, conversation_id="conv-1"))

    assert error is not None
    assert "already used ask_user 3 times" in error
    assert "update_planning_draft or request_plan_approval" in error
