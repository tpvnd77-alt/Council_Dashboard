"""LLM 엔진 — 모든 sub-agent 호출이 지나가는 단일 관문.

- 구조화 출력(JSON 스키마)으로 응답 형식을 강제하고 pydantic 으로 다시 검증한다.
- 시스템 프롬프트는 고정 부분(Master·Format·Taxonomy)을 앞에 두고 cache_control 을 걸어
  프롬프트 캐싱이 되게 한다. 이슈마다 바뀌는 내용은 user 메시지로만 보낸다.
- 긴 출력이 많아 스트리밍으로 받고 get_final_message() 로 합친다.
- Claude API 에서는 안전 분류기 거절 시 서버가 대체 모델로 재실행하도록 fallbacks 를 켠다.
- 자격 증명이 없거나 CRPR_PROVIDER=offline 이면 OfflineLLM(규칙 기반 모의 분석)으로 동작한다.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Type

from pydantic import BaseModel, ValidationError

from .config import SETTINGS


@dataclass
class CallResult:
    obj: BaseModel
    model: str
    usage: dict
    seconds: float


class LLMError(Exception):
    pass


class ClaudeLLM:
    offline = False

    def __init__(self, settings=SETTINGS):
        import anthropic

        self.anthropic = anthropic
        self.s = settings
        p = settings.provider
        if p == "bedrock":
            self.client = anthropic.AnthropicBedrockMantle(aws_region=os.environ["AWS_REGION"])
            self.prefix = "anthropic."
        elif p == "vertex":
            self.client = anthropic.AnthropicVertex(project_id=os.environ["VERTEX_PROJECT_ID"],
                                                    region=os.environ.get("VERTEX_REGION", "global"))
            self.prefix = ""
        else:
            self.client = anthropic.Anthropic()
            self.prefix = ""
        # 서버측 fallbacks 는 Claude API 에서만 지원
        self.fallbacks = settings.use_fallbacks and p == "anthropic"

    def model_for(self, role: str) -> tuple[str, str]:
        if role == "heavy":
            return self.prefix + self.s.heavy_model, self.s.heavy_effort
        return self.prefix + self.s.light_model, self.s.light_effort

    def run(self, task: str, role: str, system: list[str], user: list[str],
            schema: Type[BaseModel], ctx: dict | None = None, max_tokens: int = 32000) -> CallResult:
        model, effort = self.model_for(role)
        sys_blocks = [{"type": "text", "text": t} for t in system]
        # 고정 prefix 끝에 캐시 지점 (최대 2곳 사용)
        for i in sorted({min(1, len(sys_blocks) - 1), len(sys_blocks) - 1}):
            sys_blocks[i]["cache_control"] = {"type": "ephemeral"}
        content = [{"type": "text", "text": t} for t in user if t]
        kwargs = dict(
            model=model, max_tokens=max_tokens, system=sys_blocks,
            messages=[{"role": "user", "content": content}],
            output_config={"effort": effort,
                           "format": {"type": "json_schema",
                                      "schema": self.anthropic.transform_schema(schema)}},
        )
        if self.fallbacks:
            kwargs["betas"] = ["server-side-fallback-2026-07-01"]
            kwargs["fallbacks"] = "default"
        t0 = time.time()
        try:
            with self.client.beta.messages.stream(**kwargs) as stream:
                msg = stream.get_final_message()
        except self.anthropic.AuthenticationError as e:
            raise LLMError("API 인증 실패 — ANTHROPIC_API_KEY 또는 ant auth login 을 확인하세요.") from e
        except self.anthropic.BadRequestError as e:
            raise LLMError(f"요청 오류({task}): {e.message}") from e
        except self.anthropic.APIConnectionError as e:
            raise LLMError(f"네트워크 오류({task}): {e}") from e
        except self.anthropic.APIStatusError as e:
            raise LLMError(f"API 오류({task}, {e.status_code}): {e.message}") from e

        if msg.stop_reason == "refusal":
            cat = getattr(msg.stop_details, "category", None) if msg.stop_details else None
            raise LLMError(f"모델이 응답을 거절했습니다({task}, category={cat}).")
        if msg.stop_reason == "max_tokens":
            raise LLMError(f"출력 한도 초과({task}) — max_tokens 를 늘리거나 문서를 나눠 주세요.")
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        try:
            obj = schema.model_validate_json(text)
        except ValidationError as e:
            raise LLMError(f"구조화 출력 검증 실패({task}): {e.errors()[:3]}") from e
        u = msg.usage
        usage = {k: getattr(u, k, None) for k in
                 ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")}
        return CallResult(obj=obj, model=msg.model, usage=usage, seconds=round(time.time() - t0, 1))


def _has_credentials() -> bool:
    if SETTINGS.provider in ("bedrock", "vertex"):
        return True
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    # ant auth login 프로필
    home = os.path.expanduser("~/.config/anthropic")
    return os.path.isdir(home) and any(os.scandir(home))


_instance = None


def get_llm():
    """설정에 맞는 LLM 을 돌려준다. 자격 증명이 없으면 오프라인 모의 모드."""
    global _instance
    if _instance is None:
        if SETTINGS.provider == "offline" or not _has_credentials():
            from .offline import OfflineLLM
            _instance = OfflineLLM()
        else:
            _instance = ClaudeLLM()
    return _instance


def set_llm(llm) -> None:
    """테스트·평가에서 LLM 을 갈아끼울 때 쓴다."""
    global _instance
    _instance = llm


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1)
