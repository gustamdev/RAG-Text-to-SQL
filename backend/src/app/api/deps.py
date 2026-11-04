from fastapi import Request
from pymongo.asynchronous.database import AsyncDatabase

from app.database.connection import get_database
from app.services.agent_runner import AgentRunner
from app.services.query_runner import QueryRunner


def get_db() -> AsyncDatabase:
    return get_database()


def get_query_runner(request: Request) -> QueryRunner:
    return request.app.state.query_runner


def get_agent_runner(request: Request) -> AgentRunner:
    return request.app.state.agent_runner
