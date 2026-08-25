from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from internal.core.agent.entities.queue_entity import AgentThought, QueueEvent
from internal.exception import ValidateErrorException
from internal.service.conversation_service import ConversationService


def create_service(*responses: str | Exception) -> ConversationService:
    manager = MagicMock()
    runnable_responses = iter(responses)

    def create_model(_parameters):
        response = next(runnable_responses)

        def invoke(_prompt):
            if isinstance(response, Exception):
                raise response
            return AIMessage(content=response)

        return RunnableLambda(invoke)

    manager.create_system_chat_model.side_effect = create_model

    def create_structured_model(schema, _parameters, max_attempts=2):
        del max_attempts
        response = next(runnable_responses)

        def invoke(_prompt):
            if isinstance(response, Exception):
                raise response
            return schema.model_validate_json(response)

        return RunnableLambda(invoke)

    manager.create_system_structured_chat_model.side_effect = (
        create_structured_model
    )
    return ConversationService(db=MagicMock(), language_model_manager=manager)


def test_generate_conversation_name_accepts_plain_text_output():
    service = create_service("  询问助手的功能和能力\n")

    assert service.generate_conversation_name("你好，你能做什么") == (
        "询问助手的功能和能力"
    )


def test_generate_conversation_name_falls_back_when_model_fails():
    service = create_service(RuntimeError("model unavailable"))

    assert service.generate_conversation_name("  你好，\n你能做什么  ") == (
        "你好， 你能做什么"
    )


def test_generate_suggested_questions_parses_json_object():
    service = create_service(
        '{"questions":["你支持哪些功能？","如何创建应用？","如何接入模型？"]}'
    )

    assert service.generate_suggested_questions("用户正在了解系统") == [
        "你支持哪些功能？",
        "如何创建应用？",
        "如何接入模型？",
    ]


def test_generate_suggested_questions_falls_back_on_invalid_json():
    service = create_service("问题一、问题二、问题三")

    assert service.generate_suggested_questions("用户正在了解系统") == []


def test_custom_exception_exposes_message_to_python_exception():
    error = ValidateErrorException("模型实体不存在")

    assert str(error) == "模型实体不存在"


def test_summary_failure_does_not_interrupt_message_and_title_updates():
    service = create_service()
    conversation = SimpleNamespace(
        id=uuid4(), summary="旧摘要", is_new=True, name="New Conversation"
    )
    message = SimpleNamespace(id=uuid4(), query="你好", answer="")
    service.get = MagicMock(side_effect=[conversation, message])
    service.create = MagicMock()
    service.update = MagicMock()
    service.summary = MagicMock(side_effect=RuntimeError("summary failed"))
    service.generate_conversation_name = MagicMock(return_value="问候")
    flask_app = MagicMock()
    flask_app.app_context.return_value = nullcontext()
    thought = AgentThought(
        id=uuid4(),
        task_id=uuid4(),
        event=QueueEvent.AGENT_MESSAGE,
        answer="你好，我能帮助你。",
    )

    service.save_agent_thoughts(
        flask_app=flask_app,
        account_id=uuid4(),
        app_id=uuid4(),
        app_config={"long_term_memory": {"enable": True}},
        conversation_id=conversation.id,
        message_id=message.id,
        agent_thoughts=[thought],
    )

    service.update.assert_any_call(conversation, name="问候")
