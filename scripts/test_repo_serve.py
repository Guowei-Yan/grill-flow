import json
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))

class TestNormalizeAllowlist(unittest.TestCase):
    def test_normalize_rejects_traversal_and_absolute(self):
        from grill_flow_serve import normalize_repo_relpath
        self.assertIsNone(normalize_repo_relpath("../x"))
        self.assertIsNone(normalize_repo_relpath("/etc/passwd"))
        self.assertIsNone(normalize_repo_relpath(""))
        self.assertIsNone(normalize_repo_relpath("."))
        self.assertIsNone(normalize_repo_relpath("a/\x00b"))
        self.assertEqual(normalize_repo_relpath("./a/b.ts"), "a/b.ts")

    def test_allowlist_from_obligations_and_edge_evidence(self):
        from grill_flow_serve import build_repo_allowlist
        with tempfile.TemporaryDirectory() as td:
            run = Path(td)
            (run / "obligations.json").write_text(json.dumps([
                {"obligationId": "o1", "path": "src/a.ts", "line": 1, "change": "present", "kind": "semantic"},
            ]) + "\n")
            (run / "graph.json").write_text(json.dumps({
                "nodes": {},
                "edges": [{"from": "file:a", "to": "file:b", "edgeKind": "import",
                           "evidenceRef": {"path": "src/b.ts", "oid": None, "source": "worktree", "note": ""}}],
            }) + "\n")
            (run / "ledger.json").write_text(json.dumps({
                "o1": {"state": "covered", "disposition": {
                    "kind": "semantic", "evidenceRef": {"path": "src/c.ts"}}},
            }) + "\n")
            al = build_repo_allowlist(run)
            self.assertIn("src/a.ts", al)
            self.assertIn("src/b.ts", al)
            self.assertIn("src/c.ts", al)

    def test_read_repo_slice_happy_range_binary(self):
        from grill_flow_serve import read_repo_slice, REPO_MAX_LINES
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "f.txt"
            p.write_text("a\nb\nc\nd\ne\n")
            text, err = read_repo_slice(p, 2, 3)
            self.assertIsNone(err)
            self.assertEqual(text, "b\nc")
            _, err = read_repo_slice(p, 3, 2)
            self.assertEqual(err, "range")
            _, err = read_repo_slice(p, 1, REPO_MAX_LINES + 2)
            self.assertEqual(err, "range")
            b = Path(td) / "bin.txt"
            b.write_bytes(b"ok\x00more")
            _, err = read_repo_slice(b, 1, 1)
            self.assertEqual(err, "binary")

    def test_read_only_false_dies(self):
        from grill_flow_serve import run_serve_http
        with tempfile.TemporaryDirectory() as td:
            run = Path(td)
            with self.assertRaises(SystemExit):
                run_serve_http(run, port=0, repo_root=run, instance_id="x", read_only=False)

    def test_handler_pipeline(self):
        import http.client
        import threading
        from http.server import ThreadingHTTPServer
        from grill_flow_serve import make_handler, build_repo_allowlist
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            run = Path(td) / "run"
            root.mkdir(); run.mkdir()
            (root / "src").mkdir()
            (root / "src" / "a.ts").write_text("line1\n")
            (run / "obligations.json").write_text(json.dumps([
                {"obligationId": "o1", "path": "src/a.ts", "line": 1, "change": "present", "kind": "semantic"},
            ]) + "\n")
            (run / "graph.json").write_text(json.dumps({"nodes": {}, "edges": []}) + "\n")
            (run / "ledger.json").write_text("{}\n")
            allow = build_repo_allowlist(run)
            Handler = make_handler(run, root.resolve(), "tok", allow)
            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            port = server.server_address[1]
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                def req(method, path, host="127.0.0.1", headers=None):
                    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                    c.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
                    if host is not None:
                        c.putheader("Host", host)
                    for k, v in (headers or {}).items():
                        c.putheader(k, v)
                    c.endheaders()
                    return c.getresponse()
                def assert_unavail(r, status, reason):
                    self.assertEqual(r.status, status)
                    body = json.loads(r.read().decode())
                    self.assertEqual(body, {"unavailable": True, "reason": reason})
                r = req("GET", "/repo")
                assert_unavail(r, 400, "path")
                r = req("GET", "/repo/")
                assert_unavail(r, 400, "path")
                r = req("DELETE", "/repo?t=tok")
                assert_unavail(r, 400, "path")
                r = req("POST", "/repo/src/a.ts?start=1&end=1&t=tok")
                assert_unavail(r, 405, "method")
                r = req("PUT", "/repo/src/a.ts?start=1&end=1&t=tok")
                assert_unavail(r, 405, "method")
                r = req("PATCH", "/repo/src/a.ts?start=1&end=1&t=tok")
                assert_unavail(r, 405, "method")
                r = req("DELETE", "/repo/src/a.ts?start=1&end=1&t=tok")
                assert_unavail(r, 405, "method")
                r = req("GET", "/repo/src/a.ts?start=1&end=1&t=tok", host="evil.com")
                assert_unavail(r, 403, "host")
                r = req("GET", "/repo/src/a.ts?start=1&end=1")
                assert_unavail(r, 403, "token")
                r = req("GET", "/repo/src/a.ts?start=1&end=1", headers={"X-Grill-Flow-Instance": "tok"})
                self.assertEqual(r.status, 200)
                r = req("GET", "/repo/src/nope.ts?start=1&end=1&t=tok")
                assert_unavail(r, 403, "allowlist")
                r = req("GET", "/repo/src/a.ts?start=1&end=1&t=tok")
                self.assertEqual(r.status, 200)
                self.assertEqual(r.getheader("Cache-Control"), "no-store")
                self.assertIn("application/json", r.getheader("Content-Type"))
                body = json.loads(r.read().decode())
                self.assertEqual(body["text"], "line1")
                r = req("HEAD", "/repo/src/a.ts?start=1&end=1&t=tok")
                self.assertEqual(r.status, 200)
                self.assertEqual(r.read(), b"")
                r = req("GET", "/repo/src/a.ts?start=2&end=1&t=tok")
                assert_unavail(r, 400, "range")
            finally:
                server.shutdown()
                server.server_close()

    def test_handler_symlink_escape(self):
        import http.client
        import threading
        from http.server import ThreadingHTTPServer
        from grill_flow_serve import make_handler, build_repo_allowlist
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            outside = Path(td) / "outside"
            run = Path(td) / "run"
            root.mkdir(); outside.mkdir(); run.mkdir()
            (outside / "secret.txt").write_text("secret\n")
            (root / "src").mkdir()
            (root / "src" / "a.ts").symlink_to(outside / "secret.txt")
            (run / "obligations.json").write_text(json.dumps([
                {"obligationId": "o1", "path": "src/a.ts", "line": 1, "change": "present", "kind": "semantic"},
            ]) + "\n")
            (run / "graph.json").write_text(json.dumps({"nodes": {}, "edges": []}) + "\n")
            (run / "ledger.json").write_text("{}\n")
            allow = build_repo_allowlist(run)
            Handler = make_handler(run, root.resolve(), "tok", allow)
            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            port = server.server_address[1]
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                c.putrequest("GET", "/repo/src/a.ts?start=1&end=1&t=tok", skip_host=True, skip_accept_encoding=True)
                c.putheader("Host", "127.0.0.1")
                c.endheaders()
                r = c.getresponse()
                self.assertEqual(r.status, 403)
                body = json.loads(r.read().decode())
                self.assertEqual(body, {"unavailable": True, "reason": "escape"})
            finally:
                server.shutdown()
                server.server_close()

    def test_serve_http_cli_passes_repo_and_instance(self):
        import importlib.util
        from unittest import mock
        path = Path(__file__).resolve().parent / "grill-flow.py"
        spec = importlib.util.spec_from_file_location("grill_flow_cli_repo", path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"; run = Path(td) / "run"
            root.mkdir(); run.mkdir()
            (run / "run.json").write_text("{}\n")
            with mock.patch.object(mod, "run_serve_http") as spy:
                mod.main([
                    "--repo-root", str(root),
                    "--run-dir", str(run),
                    "--grill-flow-instance=abc",
                    "--read-only",
                    "serve-http",
                    "--port", "0",
                ])
                kwargs = spy.call_args.kwargs
                self.assertEqual(kwargs["instance_id"], "abc")
                self.assertEqual(Path(kwargs["repo_root"]).resolve(), root.resolve())

if __name__ == "__main__":
    unittest.main()
