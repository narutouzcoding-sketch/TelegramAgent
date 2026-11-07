import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

from telegram_agent.store import utc_now


def test_tool_idempotency_and_invalid_tool(brain):
    args = {
        "title": "Dars",
        "due_at": (utc_now() + timedelta(hours=1)).isoformat(),
        "repeat": "none",
        "mode": "call",
    }
    one = brain.execute_tool("create_reminder", json.dumps(args), "call-1")
    two = brain.execute_tool("create_reminder", json.dumps(args), "call-1")
    assert one == two
    assert one["ok"]
    assert len(brain.store.list_reminders()) == 1
    assert brain.execute_tool("run_shell", "{}", "call-2")["ok"] is False


def test_malformed_arguments_return_failure(brain):
    assert not brain.execute_tool("add_plan", "{bad", "x1")["ok"]
    assert not brain.execute_tool("add_plan", '{"unexpected": 1}', "x2")["ok"]
    assert brain.store.list_plans() == []


async def test_text_function_round_trip(brain):
    call = SimpleNamespace(
        type="function_call",
        name="add_plan",
        call_id="abc",
        arguments='{"title":"Kitob","details":"10 bet"}',
    )
    first = SimpleNamespace(output=[call], output_text="")
    last = SimpleNamespace(output=[], output_text="Reja #1 saqlandi.")
    create = AsyncMock(side_effect=[first, last])
    brain.client = SimpleNamespace(responses=SimpleNamespace(create=create))
    assert await brain.answer("Kitob o'qishni rejamga qo'sh") == "Reja #1 saqlandi."
    assert brain.store.list_plans()[0]["title"] == "Kitob"
    tool_result = create.call_args.kwargs["input"][-1]
    assert tool_result["type"] == "function_call_output"
    assert json.loads(tool_result["output"])["ok"]
    assert brain.store.history()[-1]["role"] == "assistant"
