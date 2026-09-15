import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from core.workflow import ROOT, STAGES, Workflow


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project_file = self.root / "project.json"
        shutil.copy(ROOT / "examples/project.json", self.project_file)
        self.workflow = Workflow(self.project_file, self.root / "data")

    def result(self, stage):
        result = copy.deepcopy(self.workflow.prepare(stage)["output_template"])
        result["summary"] = "测试结果，不代表真实产品研究"
        result["limitations"] = ["无产品资料，所有栏目待调研"]
        return result

    def test_full_workflow_and_reports(self):
        for stage in STAGES:
            self.workflow.save(stage, self.result(stage))
        self.assertTrue(all(s["status"] == "complete" for s in self.workflow.snapshot()[0].values()))
        self.assertEqual(len(list(self.workflow.directory.glob("*.md"))), 13)
        self.assertIn("测试结果", self.workflow.render_reports().read_text())

    def test_dependency_and_invalid_output_do_not_write(self):
        with self.assertRaises(ValueError):
            self.workflow.prepare("l_dfa")
        for bad in (None, {}, {"summary": "ok"}):
            with self.assertRaises(ValueError):
                self.workflow.save("p_research", bad)
        self.assertFalse(self.workflow.db_file.exists())

    def test_evidence_references_and_finite_numbers(self):
        result = self.result("p_research")
        result["sections"]["positioning"] = [{"value": 1, "evidence_ids": ["missing"]}]
        with self.assertRaises(ValueError):
            self.workflow.save("p_research", result)
        result["evidence"] = [{"id": "missing", "source": "test", "claim": "test", "kind": "assumption"}]
        result["sections"]["positioning"][0]["value"] = float("nan")
        with self.assertRaises(ValueError):
            self.workflow.save("p_research", result)
        self.assertFalse(self.workflow.db_file.exists())

    def test_source_changes_reject_old_packet_and_stale_results(self):
        config = json.loads(self.project_file.read_text())
        config["source_files"] = ["brief.md"]
        self.project_file.write_text(json.dumps(config))
        source = self.root / "brief.md"
        source.write_text("version 1")
        self.workflow = Workflow(self.project_file, self.root / "data")
        old = self.result("p_teardown")
        self.workflow.save("p_teardown", old)
        source.write_text("version 2")
        self.assertEqual(self.workflow.snapshot()[0]["p_teardown"]["status"], "stale")
        with self.assertRaises(ValueError):
            self.workflow.save("p_teardown", old)

    def test_upstream_rerun_invalidates_downstream(self):
        for stage in ("p_teardown", "p_issues", "l_dfa"):
            self.workflow.save(stage, self.result(stage))
        result = self.result("p_teardown")
        result["summary"] = "新拆解结果"
        self.workflow.save("p_teardown", result)
        self.assertEqual(self.workflow.snapshot()[0]["l_dfa"]["status"], "stale")

    def test_ids_cannot_escape_and_projects_are_isolated(self):
        config = json.loads(self.project_file.read_text())
        config["id"] = "../escape"
        self.project_file.write_text(json.dumps(config))
        with self.assertRaises(ValueError):
            Workflow(self.project_file)
        config["id"] = "other"
        self.project_file.write_text(json.dumps(config))
        other = Workflow(self.project_file, self.root / "data")
        with self.assertRaises(ValueError):
            other.save("p_research", self.result("p_research"))

    def test_standalone_export_and_runner(self):
        exported = self.root / "export"
        shutil.copytree(ROOT, exported, ignore=shutil.ignore_patterns("data", "__pycache__"))
        runner = self.root / "runner.py"
        runner.write_text('import json,sys\np=json.load(sys.stdin)\nr=p["output_template"]\n'
                          'r["summary"]="synthetic test"\nr["limitations"]=["test only"]\n'
                          'print(json.dumps(r))\n')
        proc = subprocess.run([sys.executable, str(exported / "agent.py"),
                               "--project", str(exported / "examples/project.json"),
                               "--runner", f'"{sys.executable}" "{runner}"', "/plans"],
                              cwd=self.root, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        records = json.loads((exported / "data/demo-pump/stages.json").read_text())
        self.assertEqual(len(records), 12)

    def test_runner_failure_does_not_mark_stage_complete(self):
        runner = self.root / "failed.py"
        runner.write_text('raise SystemExit(7)\n')
        proc = subprocess.run([sys.executable, str(ROOT / "agent.py"),
                               "--project", str(self.project_file),
                               "--data-dir", str(self.root / "data"),
                               "--runner", f'"{sys.executable}" "{runner}"', "/research"],
                              capture_output=True, text=True)
        self.assertNotEqual(proc.returncode, 0)
        self.assertFalse(self.workflow.db_file.exists())

    def test_registry_dependency_order(self):
        seen = set()
        commands = set()
        for stage, spec in STAGES.items():
            self.assertTrue(set(spec["deps"]).issubset(seen))
            self.assertNotIn(spec["command"], commands)
            self.assertTrue((ROOT / "agents" / stage / "prompt.md").is_file())
            seen.add(stage)
            commands.add(spec["command"])


if __name__ == "__main__":
    unittest.main()
