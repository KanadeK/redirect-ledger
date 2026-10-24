from __future__ import annotations

import contextlib
import io
import json
import random
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, build_opener

from redirect_ledger import __version__
from redirect_ledger.cli import main
from redirect_ledger.core import (
    MAX_BYTES,
    InputError,
    Rule,
    audit,
    local_path,
    parse_inventory,
    parse_rules,
    plan_csv,
    read_text,
    target_url,
    write_new,
)


class Paths(unittest.TestCase):
    def test_canonical_unreserved_and_escape_case(self):
        self.assertEqual(local_path("/a/%7e/%c3%a9"), "/a/~/%C3%A9")

    def test_case_and_trailing_slash_stay_distinct(self):
        self.assertEqual(local_path("/A/"), "/A/")
        self.assertNotEqual(local_path("/A/"), local_path("/a"))

    def test_ambiguous_local_inputs_rejected(self):
        values = [
            "",
            "a",
            "//x",
            "/a//b",
            "/a/../b",
            "/%2e",
            "/%2F",
            "/%5c",
            "/%00",
            "/%25",
            "/%20",
            "/%7f",
            "/%zz",
            "/%",
            "/x?y",
            "/x#y",
            "/x\\y",
            "/x*y",
            "/[x]",
            "/{x}",
            "/é",
            "/<x>",
            "/x\ny",
            "/" + "x" * 4096,
        ]
        for value in values:
            with self.subTest(value=value), self.assertRaises(InputError):
                local_path(value)

    def test_absolute_targets_are_explicit_terminals(self):
        self.assertEqual(target_url("HTTPS://Example.ORG/a/%7e"), "https://example.org/a/~")
        self.assertEqual(target_url("http://[::1]:8080"), "http://[::1]:8080/")

    def test_external_invalid_targets(self):
        values = [
            "ftp://example.org/a",
            "javascript:alert(1)",
            "https://u:p@example.org/x",
            "https://@example.org/x",
            "https://example.org/x?q",
            "https://example.org/x#f",
            "https://example.org:65536/x",
            "https://example.org:0/x",
            "https://[invalid]/x",
            "https:///x",
            "https://ex_ample.org/x",
            "https://example.org/a\\b",
            "https://example.org/é",
        ]
        for value in values:
            with self.subTest(value=value), self.assertRaises(InputError):
                target_url(value)


class Parsing(unittest.TestCase):
    def test_limits_count_records_and_ignore_blank_inventory_lines(self):
        with patch("redirect_ledger.core.MAX_RULES", 1):
            self.assertEqual(parse_inventory("/a\n\n\n"), {"/a"})
            with self.assertRaisesRegex(InputError, "exceeds"):
                parse_inventory("/a\n/b\n")
            with self.assertRaisesRegex(InputError, "exceeds"):
                parse_rules("source,target,status\n/a,/b,301\n/c,/d,301\n")

    def test_rules_and_inventory(self):
        rules = parse_rules('source,target,status\r\n"/a,b","/c,d",301\r\n')
        self.assertEqual(rules, [Rule("/a,b", "/c,d", 301, 2)])
        self.assertEqual(parse_inventory("/a\r\n\r\n/b/\n"), {"/a", "/b/"})

    def test_duplicate_canonical_source_is_an_error(self):
        with self.assertRaisesRegex(InputError, "duplicate source"):
            parse_rules("source,target,status\n/%7e,/b,301\n/~,/c,302\n")

    def test_malformed_csv_and_status(self):
        values = [
            "",
            "target,source,status\n",
            "source,target,status\n",
            "source,target,status\n/a,/b\n",
            "source,target,status\n/a,/b,301,extra\n",
            'source,target,status\n"/a,/b,301',
            "source,target,status\n/a,/b,200\n",
            "source,target,status\n/a,/b, 301\n",
            "source,target,status\n/a,./b,301\n",
        ]
        for value in values:
            with self.subTest(value=value), self.assertRaises(InputError):
                parse_rules(value)

    def test_inventory_rejects_empty_duplicate_and_bad_path(self):
        for text in ["\n", "/a\n/a\n", "/a\n../x\n"]:
            with self.subTest(text=text), self.assertRaises(InputError):
                parse_inventory(text)

    def test_bounded_utf8_file_and_bom(self):
        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch) / "input"
            path.write_bytes(b"\xef\xbb\xbf/a\r\n")
            self.assertEqual(read_text(path), "/a\r\n")
            path.write_bytes(b"\xff")
            with self.assertRaisesRegex(InputError, "UTF-8"):
                read_text(path)
            with path.open("wb") as stream:
                stream.truncate(MAX_BYTES + 1)
            with self.assertRaisesRegex(InputError, "16 MiB"):
                read_text(path)


class Graph(unittest.TestCase):
    def test_simple_chain_plan_and_inventory(self):
        report = audit([Rule("/a", "/b", 301), Rule("/b", "/c", 301)], {"/c"})
        self.assertEqual(
            report["summary"], {"rules": 2, "errors": 0, "warnings": 1, "shortenable": 1}
        )
        self.assertEqual(report["rules"][0]["hops"], 2)
        self.assertEqual(report["rules"][0]["plan_target"], "/c")
        fixed = audit(parse_rules(plan_csv(report)), {"/c"})
        self.assertEqual(fixed["summary"]["warnings"], 0)

    def test_mixed_and_temporary_statuses_not_shortened(self):
        for left, right in [(301, 308), (308, 301), (302, 302), (301, 302), (307, 307), (303, 303)]:
            with self.subTest(statuses=(left, right)):
                report = audit([Rule("/a", "/b", left), Rule("/b", "/c", right)])
                self.assertEqual(report["rules"][0]["plan_target"], "/b")

    def test_uniform_308_can_be_shortened(self):
        report = audit([Rule("/a", "/b", 308), Rule("/b", "/c", 308)])
        self.assertEqual(report["rules"][0]["plan_target"], "/c")

    def test_self_loop_cycle_and_upstream(self):
        report = audit(
            [
                Rule("/self", "/self", 301),
                Rule("/b", "/c", 301),
                Rule("/c", "/b", 302),
                Rule("/a", "/b", 308),
            ]
        )
        self.assertEqual(report["cycles"], {"/b": ["/b", "/c"], "/self": ["/self"]})
        self.assertTrue(all(item["terminal"] is None for item in report["rules"]))
        self.assertEqual(report["rules"][0]["cycle_id"], "/b")
        with self.assertRaisesRegex(InputError, "plan refused"):
            plan_csv(report)

    def test_missing_and_shadowed_inventory_errors(self):
        report = audit([Rule("/a", "/missing", 301)], {"/a"})
        self.assertEqual(
            {f["code"] for f in report["findings"]}, {"missing_terminal", "inventory_shadowed"}
        )

    def test_external_target_not_fetched_or_inventory_verified(self):
        report = audit([Rule("/a", "https://nonexistent.invalid/a", 301)], {"/elsewhere"})
        self.assertEqual(report["rules"][0]["outcome"], "external_unchecked")
        self.assertEqual(report["summary"]["errors"], 0)

    def test_without_inventory_is_explicitly_unchecked(self):
        report = audit([Rule("/a", "/b", 301)])
        self.assertFalse(report["inventory_checked"])
        self.assertEqual(report["rules"][0]["outcome"], "internal_unchecked")

    def test_api_rejects_invalid_rules(self):
        for rules in [
            [],
            [Rule("/a", "/b", 200)],
            [Rule("/a", "/b", 301), Rule("/%61", "/c", 301)],
        ]:
            with self.subTest(rules=rules), self.assertRaises(InputError):
                audit(rules)
        with self.assertRaises(InputError):
            audit([Rule("/a", "/b", 301)], set())

    def test_long_graph_uses_no_recursion(self):
        rules = [Rule(f"/{i:05}", f"/{i + 1:05}", 301) for i in range(20_000)]
        report = audit(rules, {"/20000"})
        self.assertEqual(report["rules"][0]["hops"], 20_000)
        self.assertEqual(report["summary"]["errors"], 0)

    def test_random_graphs_match_independent_naive_walk(self):
        rng = random.Random(10424)
        for _ in range(150):
            count = rng.randint(1, 45)
            graph = {f"/{i}": f"/{rng.randrange(count + 3)}" for i in range(count)}
            rules = [
                Rule(source, target, rng.choice([301, 308, 302]))
                for source, target in graph.items()
            ]
            report = audit(rules)
            self.assertEqual(report, audit(list(reversed(rules))))
            for result in report["rules"]:
                visited = set()
                cursor, hops = result["source"], 0
                while cursor in graph and cursor not in visited:
                    visited.add(cursor)
                    cursor = graph[cursor]
                    hops += 1
                if cursor in visited:
                    self.assertIsNotNone(result["cycle_id"])
                else:
                    self.assertEqual((result["terminal"], result["hops"]), (cursor, hops))


class CommandLine(unittest.TestCase):
    def invoke(self, args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(args)
        return code, out.getvalue(), err.getvalue()

    def test_version(self):
        with (
            contextlib.redirect_stdout(io.StringIO()) as out,
            self.assertRaises(SystemExit) as caught,
        ):
            main(["--version"])
        self.assertEqual(caught.exception.code, 0)
        self.assertIn(__version__, out.getvalue())

    def test_full_workflow_plan_audit_and_no_clobber(self):
        with tempfile.TemporaryDirectory() as scratch:
            base = Path(scratch)
            source, inventory, output = base / "map.csv", base / "paths.txt", base / "plan.csv"
            original = b"source,target,status\n/a,/b,301\n/b,/c,301\n"
            source.write_bytes(original)
            inventory.write_text("/c\n", encoding="utf-8")
            args = [
                str(source),
                "--inventory",
                str(inventory),
                "--format",
                "json",
                "--plan",
                str(output),
                "--strict",
            ]
            code, out, err = self.invoke(args)
            self.assertEqual((code, err), (1, ""))
            self.assertEqual(json.loads(out)["summary"]["shortenable"], 1)
            self.assertEqual(source.read_bytes(), original)
            plan = output.read_bytes()
            code, _, err = self.invoke(args)
            self.assertEqual(code, 2)
            self.assertIn("file access failed", err)
            self.assertEqual(output.read_bytes(), plan)
            code, _, _ = self.invoke([str(output), "--inventory", str(inventory), "--strict"])
            self.assertEqual(code, 0)

    def test_errors_and_text_status(self):
        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch) / "map"
            path.write_text("source,target,status\n/a,/a,301\n", encoding="utf-8")
            self.assertEqual(self.invoke([str(path)])[0], 1)
            self.assertEqual(self.invoke([str(path), "--plan", str(path.parent / "out")])[0], 2)
            path.write_text("invalid", encoding="utf-8")
            code, _, err = self.invoke([str(path), "--format", "json"])
            self.assertEqual(code, 2)
            self.assertIn("error", json.loads(err))
            self.assertEqual(self.invoke([str(path.parent / "missing")])[0], 2)

    def test_new_file_writer(self):
        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch) / "out"
            write_new(path, "value\n")
            with self.assertRaises(FileExistsError):
                write_new(path, "changed")
            self.assertEqual(path.read_text(), "value\n")


class ActualHTTP(unittest.TestCase):
    def test_csv_graph_agrees_with_observed_http_hops_before_and_after_plan(self):
        rules = parse_rules("source,target,status\n/old,/middle,301\n/middle,/live,301\n")
        graph = {rule.source: rule for rule in rules}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path in graph:
                    rule = graph[self.path]
                    self.send_response(rule.status)
                    self.send_header("Location", rule.target)
                elif self.path == "/live":
                    self.send_response(200)
                else:
                    self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *_args):
                pass

        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None

        def observe(base, source):
            opener = build_opener(NoRedirect)
            path, hops = source, 0
            while hops < 10:
                try:
                    response = opener.open(base + path, timeout=5)  # noqa: S310
                except HTTPError as response_error:
                    response = response_error
                with response:
                    if response.code == 200:
                        return path, hops
                    self.assertIn(response.code, [301, 308])
                    path = response.headers["Location"]
                hops += 1
            self.fail("observed unexpected redirect loop")

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            report = audit(rules, {"/live"})
            self.assertEqual(observe(base, "/old"), ("/live", report["rules"][1]["hops"]))
            graph.clear()
            graph.update({rule.source: rule for rule in parse_rules(plan_csv(report))})
            self.assertEqual(observe(base, "/old"), ("/live", 1))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
