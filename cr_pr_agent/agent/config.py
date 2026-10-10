"""지식 계층 로더 — Taxonomy Master, 코드북, Prompt Registry, 실행 설정.

모든 판단 기준은 파일(config/, prompts/)에 있고 코드에는 없다.
운영자가 파일을 고치면 다음 실행부터 반영된다.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
PROMPT_DIR = ROOT / "prompts"
DATA_DIR = Path(os.environ.get("CRPR_DATA_DIR", ROOT / "data"))

_lock = threading.Lock()


@dataclass
class Settings:
    """환경 변수로 덮어쓸 수 있는 실행 설정."""
    heavy_model: str = os.environ.get("CRPR_HEAVY_MODEL", "claude-opus-5-5")
    light_model: str = os.environ.get("CRPR_LIGHT_MODEL", "claude-sonnet-5-5")
    heavy_effort: str = os.environ.get("CRPR_HEAVY_EFFORT", "high")
    light_effort: str = os.environ.get("CRPR_LIGHT_EFFORT", "medium")
    # anthropic | bedrock | vertex | offline
    provider: str = os.environ.get("CRPR_PROVIDER", "anthropic")
    # Claude API 전용: 안전 분류기에 거절되면 서버가 대체 모델로 재실행
    use_fallbacks: bool = os.environ.get("CRPR_FALLBACKS", "1") == "1"
    max_revisions: int = int(os.environ.get("CRPR_MAX_REVISIONS", "2"))
    # 사내보고서(3000) 외부 API 전송 허용 여부 — Phase 0 정보보호 협의 결과로 설정
    allow_internal_docs: bool = os.environ.get("CRPR_ALLOW_INTERNAL", "1") == "1"
    mask_pii: bool = os.environ.get("CRPR_MASK_PII", "1") == "1"
    port: int = int(os.environ.get("CRPR_PORT", "8787"))


SETTINGS = Settings()


def load_json(name: str) -> dict:
    with open(CONFIG_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def save_json(name: str, data: dict) -> None:
    tmp = CONFIG_DIR / (name + ".tmp")
    with _lock:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CONFIG_DIR / name)


def codebook() -> dict:
    return load_json("codebook.json")


# ---------------------------------------------------------------- Taxonomy
class Taxonomy:
    def __init__(self, data: dict | None = None):
        self.data = data or load_json("taxonomy.json")
        self.l1 = {x["code"]: x for x in self.data["l1"]}
        self.l2 = {x["code"]: x for x in self.data["l2"]}
        self.l3 = {x["code"]: x for x in self.data["l3"]}
        self.issues = {x["issue_id"]: x for x in self.data["issues"]}

    def active_issues(self):
        return [i for i in self.data["issues"] if i.get("status", "active") == "active"]

    def path(self, issue_id: str) -> dict:
        """ISSUE_ID → L1/L2/L3 경로. 모르는 코드면 빈 dict."""
        issue = self.issues.get(issue_id)
        if not issue:
            return {}
        l3 = self.l3[issue["l3"]]
        l2 = self.l2[l3["l2"]]
        l1 = self.l1[l2["l1"]]
        return {"issue": issue, "l3": l3, "l2": l2, "l1": l1}

    def label(self, issue_id: str) -> str:
        p = self.path(issue_id)
        if not p:
            return issue_id
        return f'{issue_id} {p["l1"]["name"]}>{p["l2"]["name"]}>{p["l3"]["name"]} · {p["issue"]["name"]}'

    def master_table(self) -> str:
        """분류 sub-agent 에 넣을 텍스트 표. 순서가 고정이라 프롬프트 캐시가 유지된다."""
        rows = []
        for i in self.active_issues():
            p = self.path(i["issue_id"])
            rows.append(f'{i["issue_id"]} | {p["l1"]["name"]} | {p["l2"]["name"]} | '
                        f'{p["l3"]["code"]} {p["l3"]["name"]} | {i["name"]}')
        return "ISSUE_ID | L1 | L2 | L3 | 세분류 이슈명\n" + "\n".join(rows)

    # 세분류(ISSUE_ID) 추가는 담당자 권한 — 즉시 가능 (VI장 3절)
    def add_issue(self, l3_code: str, name: str) -> dict:
        if l3_code not in self.l3:
            raise ValueError(f"없는 L3 코드: {l3_code}")
        prefix = self.l1[self.l2[self.l3[l3_code]["l2"]]["l1"]]["prefix"]
        base = int(l3_code)
        used = {int(i["issue_id"].split("-")[1]) for i in self.data["issues"]
                if i["l3"] == l3_code}
        n = next(k for k in range(base + 1, base + 10) if k not in used) if len(used) < 9 else None
        if n is None:
            raise ValueError("이 L3 아래 세분류 번호가 가득 찼습니다(최대 9개). L3 신설을 운영자에게 요청하세요.")
        issue = {"issue_id": f"{prefix}-{n}", "l3": l3_code, "name": name, "status": "active"}
        self.data["issues"].append(issue)
        save_json("taxonomy.json", self.data)
        self.__init__(self.data)
        return issue

    # 코드는 삭제하지 않고 폐기 상태로만 전환한다
    def deprecate_issue(self, issue_id: str) -> None:
        if issue_id not in self.issues:
            raise ValueError(f"없는 ISSUE_ID: {issue_id}")
        self.issues[issue_id]["status"] = "deprecated"
        save_json("taxonomy.json", self.data)


# ---------------------------------------------------------- Prompt Registry
_FM = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.S)


@dataclass
class PromptDoc:
    id: str
    version: str
    body: str
    meta: dict = field(default_factory=dict)
    path: Path | None = None

    @property
    def tag(self) -> str:
        return f"{self.id}@{self.version}"

    @property
    def digest(self) -> str:
        return hashlib.sha1(self.body.encode()).hexdigest()[:8]


def parse_prompt(path: Path) -> PromptDoc:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    m = _FM.match(text)
    meta = {}
    body = text
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        body = m.group(2).strip()
    return PromptDoc(id=meta.get("id", path.stem), version=meta.get("version", "0"),
                     body=body, meta=meta, path=path)


class Registry:
    """Layer 1/2/3 Prompt 와 sub-agent Prompt 를 파일에서 읽는다."""

    def __init__(self, prompt_dir: Path = PROMPT_DIR):
        self.dir = prompt_dir
        self.master = parse_prompt(prompt_dir / "master.md")
        self.format = parse_prompt(prompt_dir / "output_format.md")
        self.l3 = {p.stem: parse_prompt(p) for p in sorted((prompt_dir / "l3").glob("*.md"))}
        self.sub = {p.stem: parse_prompt(p) for p in sorted((prompt_dir / "subagents").glob("*.md"))}

    def l3_prompt(self, prompt_id: str) -> PromptDoc:
        return self.l3.get(prompt_id) or self.l3["GEN-0000"]

    def version_tag(self, prompt_id: str) -> str:
        return "|".join([self.master.tag, self.format.tag, self.l3_prompt(prompt_id).tag])

    def listing(self) -> list[dict]:
        out = []
        for layer, docs in (("Layer 1", [self.master]), ("Layer 3", [self.format]),
                            ("Layer 2", list(self.l3.values())), ("Sub-agent", list(self.sub.values()))):
            for d in docs:
                out.append({"layer": layer, "id": d.id, "version": d.version,
                            "name": d.meta.get("name", ""), "applies_to": d.meta.get("applies_to", ""),
                            "digest": d.digest, "body": d.body})
        return out
