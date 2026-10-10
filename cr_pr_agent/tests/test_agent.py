"""오프라인으로 도는 회귀 테스트: python -m unittest discover -s tests"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

TMP = tempfile.mkdtemp(prefix="crpr_test_")
os.environ["CRPR_DATA_DIR"] = TMP
os.environ["CRPR_PROVIDER"] = "offline"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import config, export_xlsx, feedback, pipeline, schema as S, scoring, store  # noqa: E402
from agent.ingest import extract, mask_pii  # noqa: E402
from agent.llm import CallResult, set_llm  # noqa: E402
from agent.offline import OfflineLLM  # noqa: E402
from agent.validate import validate  # noqa: E402

GOLD = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "golden").glob("*.json")}


class TestScoring(unittest.TestCase):
    def test_workbook_samples_reproduce(self):
        # 워크북 04_Decision_Log 샘플: 79점, 35점 (5=치명 기준)
        self.assertEqual(scoring.total_score({"SCORE_REG": 4, "SCORE_FIN": 4, "SCORE_PR": 5, "SCORE_LEG": 2}), 79.0)
        self.assertEqual(scoring.total_score({"SCORE_REG": 2, "SCORE_FIN": 2, "SCORE_PR": 1, "SCORE_LEG": 2}), 35.0)

    def test_levels_and_opportunity_uplift(self):
        self.assertEqual(scoring.risk_level(80)["level"], "CRITICAL")
        self.assertEqual(scoring.risk_level(79.9)["level"], "HIGH")
        self.assertEqual(scoring.risk_level(39.9)["level"], "LOW")
        self.assertEqual(scoring.report_level("LOW", 2), "단순 모니터링")
        self.assertEqual(scoring.report_level("LOW", 5), "부서 간 조율")  # 사례 2: 기회 ≥ 4 → 한 단계 상향
        self.assertEqual(scoring.report_level("CRITICAL", 5), "CEO 보고")


class TestIngest(unittest.TestCase):
    def test_masking(self):
        t, c = mask_pii("연락처 010-1234-5678, a.b@skt.com, 900101-1234567")
        self.assertNotIn("1234-5678", t)
        self.assertNotIn("skt.com", t)
        self.assertEqual(c["전화번호"], 1)

    def test_hwpx(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("Contents/section0.xml",
                       '<hs:sec><hp:p><hp:run><hp:t>요금제 개편 &amp; 고지</hp:t></hp:run></hp:p></hs:sec>')
        self.assertIn("요금제 개편 & 고지", extract("a.hwpx", buf.getvalue()).text)

    def test_docx(self):
        import docx
        d = docx.Document()
        d.add_paragraph("도매대가 사후규제 전환")
        buf = io.BytesIO()
        d.save(buf)
        self.assertIn("도매대가", extract("a.docx", buf.getvalue()).text)


class TestValidator(unittest.TestCase):
    def setUp(self):
        self.case = GOLD["G001-CR1111"]
        ctx = {"title": "t", "source_type": "정부부처", "text": self.case["text"]}
        self.report = OfflineLLM()._synthesize(ctx)

    def test_offline_report_passes(self):
        v = validate(self.report, self.case["text"], {})
        self.assertTrue(v["passed"], v["errors"])

    def test_invented_number_and_fake_quote_fail(self):
        r = self.report.model_copy(deep=True)
        r.key_content.key_facts[0].quote = "원문에 전혀 없는 문장을 지어낸 인용입니다 정말로"
        r.decision.gain = "연간 3,000억원 매출 방어"
        v = validate(r, self.case["text"], {})
        self.assertFalse(v["passed"])
        self.assertTrue(any("인용문" in e for e in v["errors"]))
        self.assertTrue(any("3000억" in e for e in v["errors"]))


class FlakyLLM(OfflineLLM):
    """첫 생성은 CEO 질문이 5개뿐인 불량 초안 → 품질 루프가 피드백을 주고 다시 만들게 한다."""

    def __init__(self):
        self.synth_calls = 0
        self.feedback_seen = None

    def run(self, task, role, system, user, schema, ctx=None, max_tokens=0):
        if task == "synthesize":
            self.synth_calls += 1
            if self.synth_calls == 1:
                r = self._synthesize(ctx)
                r.ceo_qa = r.ceo_qa[:5]
                return CallResult(obj=r, model="flaky", usage={}, seconds=0)
            self.feedback_seen = user[-1]
        return super().run(task, role, system, user, schema, ctx, max_tokens)


class TestPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        store.init()

    def tearDown(self):
        set_llm(OfflineLLM())

    def test_quality_loop_revises(self):
        llm = FlakyLLM()
        set_llm(llm)
        c = GOLD["G001-CR1111"]
        doc = pipeline.ingest(text=c["text"], title=c["title"], source_type="정부부처")
        self.assertEqual(pipeline.run(doc), "review")
        rec = store.get(doc)
        self.assertEqual(llm.synth_calls, 2)
        self.assertIn("CEO 예상 질문", llm.feedback_seen)
        self.assertTrue(rec["LOOP_LOG"]["converged"])
        self.assertEqual(len(rec["LOOP_LOG"]["attempts"]), 2)

    def test_full_flow_gates_feedback_export(self):
        c = GOLD["G001-CR1111"]
        doc = pipeline.ingest(text=c["text"] + "\n문의 010-9999-8888", title=c["title"], source_type="정부부처")
        self.assertEqual(pipeline.run(doc), "review")
        rec = store.get(doc)
        self.assertNotIn("9999-8888", rec["SOURCE_TEXT"])
        self.assertEqual(rec["ISSUE_ID"], "CR-1111")
        self.assertIn("MASTER@", rec["PROMPT_VERSION"])
        with self.assertRaises(ValueError):  # 검수 전에는 게이트 2 불가
            pipeline.decide(doc, "조직장", "승인", "")
        ev = pipeline.review(doc, "김담당", {"SCORE_REG": 4, "SCORE_FIN": 4, "SCORE_PR": 5, "SCORE_LEG": 2},
                             {"SCORE_REG": "의무 부과 임박"}, {"D+1": "홍길동"})
        self.assertEqual(ev["TOTAL_RISK_SCORE"], 79.0)
        self.assertEqual(store.get(doc)["STATUS"], "분석완료")
        res = pipeline.decide(doc, "조직장", "수정 채택", "빅딜 중심", final_text="B 절충")
        self.assertEqual(res["status"], "대응중")
        cand = pipeline.GOLDEN_CANDIDATES / f"{doc}.json"
        self.assertTrue(cand.exists())
        cand.unlink()
        stats = feedback.collect()
        self.assertGreaterEqual(stats["decided"], 1)
        self.assertIn("1110", stats["bias"])
        self.assertTrue(export_xlsx.build().startswith(b"PK"))

    def test_gate1_on_unclassifiable(self):
        doc = pipeline.ingest(text="오늘은 하늘이 맑고 바람이 선선해 산책하기 좋은 날씨라고 기상청이 밝혔다.",
                              title="날씨", source_type="언론")
        self.assertEqual(pipeline.run(doc), "gate1")
        with self.assertRaises(pipeline.GateRequired):
            pipeline.analyze(doc)
        pipeline.confirm_classification(doc, "EXT-4121", [], "김담당", "산업 동향")
        self.assertEqual(pipeline.run(doc), "review")
        self.assertTrue(any(a["field"] == "ISSUE_ID" for a in store.adjustments()))

    def test_eval_offline(self):
        from agent.evals import run_eval
        r = run_eval("dev", save=False)
        self.assertEqual(r["summary"]["n"], 2)
        self.assertEqual(r["summary"]["l3_match"], 1.0)


class TestTaxonomy(unittest.TestCase):
    def test_add_and_deprecate_in_copy(self):
        tmp = Path(tempfile.mkdtemp())
        shutil.copy(config.CONFIG_DIR / "taxonomy.json", tmp / "taxonomy.json")
        orig = config.CONFIG_DIR
        config.CONFIG_DIR = tmp
        try:
            tx = config.Taxonomy()
            issue = tx.add_issue("1310", "신규 조사 대응")
            self.assertEqual(issue["issue_id"], "CR-1312")
            tx.deprecate_issue("CR-1312")
            self.assertEqual(config.Taxonomy().issues["CR-1312"]["status"], "deprecated")
        finally:
            config.CONFIG_DIR = orig


class FakeStream:
    def __init__(self, msg):
        self.msg = msg

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self.msg


class TestClaudeRequest(unittest.TestCase):
    def test_request_shape(self):
        """실제 API 요청 형태: 스트리밍 + JSON 스키마 구조화 출력 + 캐시 지점 + fallbacks."""
        from types import SimpleNamespace

        import anthropic
        from agent.llm import ClaudeLLM

        captured = {}
        obj = S.Classification(primary_issue_id="CR-1111", sub_issue_ids=[], confidence=0.9, evidence=[],
                               new_category_candidate="")
        msg = SimpleNamespace(stop_reason="end_turn", stop_details=None, model="claude-sonnet-5-5",
                              content=[SimpleNamespace(type="text", text=obj.model_dump_json())],
                              usage=SimpleNamespace(input_tokens=1, output_tokens=1, cache_read_input_tokens=0,
                                                    cache_creation_input_tokens=0))

        def stream(**kw):
            captured.update(kw)
            return FakeStream(msg)

        llm = ClaudeLLM.__new__(ClaudeLLM)
        llm.anthropic, llm.s, llm.prefix, llm.fallbacks = anthropic, config.SETTINGS, "", True
        llm.client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=stream)))
        res = llm.run("classify", "light", ["고정1", "고정2", "고정3"], ["입력"], S.Classification)
        self.assertEqual(res.obj.primary_issue_id, "CR-1111")
        self.assertEqual(captured["model"], "claude-sonnet-5-5")
        self.assertEqual(captured["output_config"]["format"]["type"], "json_schema")
        self.assertEqual(captured["fallbacks"], "default")
        self.assertIn("server-side-fallback-2026-07-01", captured["betas"])
        self.assertNotIn("thinking", captured)
        cached = [i for i, b in enumerate(captured["system"]) if "cache_control" in b]
        self.assertEqual(cached, [1, 2])


if __name__ == "__main__":
    unittest.main()
