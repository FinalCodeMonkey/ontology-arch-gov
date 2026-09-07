#!/usr/bin/env python3
"""
BO 治理工具 HTTP API 服务
启动后，bo-ontology-graph.html 的两个生成按钮将通过 fetch() 调用本服务。
统一使用 bo-publish-gen.py 和 bo-projection-gen.py 的 generate() 函数。

用法: python bo-api-server.py [--port 8765]
"""

import json
import sys
import traceback
import subprocess
import importlib.util
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable
sys.path.insert(0, str(ROOT))


def _load_module(name: str, path: Path):
    """加载含连字符文件名的 Python 模块。"""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_pub_mod = _load_module("bo_publish_gen", ROOT / "bo-publish-gen.py")
_proj_mod = _load_module("bo_projection_gen", ROOT / "bo-projection-gen.py")
_viz_mod = _load_module("bo_graph_viz", ROOT / "bo-graph-viz.py")
_ddl_mod = _load_module("bo_ddl_gen", ROOT / "bo-ddl-gen.py")
_inspector_mod = _load_module("bo_data_inspector", ROOT / "bo-data-inspector.py")
_onto_pub_mod = _load_module("bo_ontology_publish_gen", ROOT / "bo-ontology-publish-gen.py")
_onto_eval_mod = _load_module("bo_ontology_demo_eval", ROOT / "bo-ontology-demo-eval.py")
_data_graph_mod = _load_module("bo_data_graph_gen", ROOT / "bo-data-graph-gen.py")


class APIHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        """简洁日志"""
        print(f"[{self.command}] {args[0]}")

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, msg, status=400):
        self._send_json({"error": msg}, status)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        """提供静态文件服务 + /api/file 文件下载"""
        # 规范化路径
        path = self.path.split("?")[0]  # 去掉 query string
        if path == "/":
            path = "/bo-ontology-graph.html"

        # /api/file 下载端点
        if path.startswith("/api/file"):
            return self._handle_file()

        # 安全：只允许 tools/ 目录下的文件
        safe_files = {
            "/bo-ontology-graph.html": "text/html; charset=utf-8",
            "/bo-metadata-editor.html": "text/html; charset=utf-8",
            "/graph-data.json": "application/json; charset=utf-8",
            "/crm-link-candidates.json": "application/json; charset=utf-8",
            "/crm-expr-ast-report.json": "application/json; charset=utf-8",
        }

        # 自动识别 css/ 和 js/ 子目录下的静态资源
        MIME_MAP = {
            "css": "text/css; charset=utf-8",
            "js":  "application/javascript; charset=utf-8",
            "json":"application/json; charset=utf-8",
            "html":"text/html; charset=utf-8",
        }

        if path in safe_files:
            file_path = ROOT / path.lstrip("/")
            if file_path.exists():
                content = file_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", safe_files[path])
                self.send_header("Content-Length", len(content))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(content)
                return

        # Fallback: 尝试按扩展名提供 tools/ 下任意文件
        ext = (path.rpartition(".")[2] or "").lower()
        if ext in MIME_MAP and ".." not in path and not path.startswith("/."):
            file_path = ROOT / path.lstrip("/")
            if file_path.exists() and file_path.is_file():
                content = file_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", MIME_MAP[ext])
                self.send_header("Content-Length", len(content))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(content)
                return

        # 列出 demo-data 下的场景目录
        if path == "/api/scenarios":
            demo_dir = ROOT / "demo-data"
            scenarios = []
            if demo_dir.exists():
                for d in sorted(demo_dir.iterdir()):
                    if d.is_dir():
                        scenarios.append(d.name)
            self._send_json({"scenarios": scenarios})
            return

        self._send_error("Not Found", 404)

    def do_POST(self):
        # 读取请求体
        length = int(self.headers.get("Content-Length", 0))
        body = b""
        if length:
            body = self.rfile.read(length)

        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            return self._send_error("Invalid JSON", 400)

        if self.path == "/api/publish":
            self._handle_publish(payload)
        elif self.path == "/api/projection":
            self._handle_projection(payload)
        elif self.path == "/api/projection/merge":
            self._handle_projection_merge(payload)
        elif self.path == "/api/graph":
            self._handle_graph()
        elif self.path == "/api/validate":
            self._handle_validate(payload)
        elif self.path == "/api/ddl":
            self._handle_ddl(payload)
        elif self.path == "/api/inspect":
            self._handle_inspect(payload)
        elif self.path == "/api/fragment":
            self._handle_fragment(payload)
        elif self.path == "/api/save-fragment":
            self._handle_save_fragment(payload)
        elif self.path == "/api/bo-info":
            self._handle_bo_info(payload)
        elif self.path == "/api/schema-version":
            self._handle_schema_version()
        elif self.path.startswith("/api/schema/"):
            self._handle_schema(self.path[len("/api/schema/"):])
        elif self.path == "/api/health":
            self._send_json({"status": "ok", "homepage": "http://127.0.0.1:8765", "tools": ["publish", "projection", "graph", "validate", "ddl", "ontology:publish", "ontology:snapshot", "ontology:links", "ontology:derive", "ontology:temporal", "ontology:action-chain-dry-run", "data-graph"]})
        elif self.path == "/api/ontology/publish":
            self._handle_ontology_publish(payload)
        elif self.path == "/api/ontology/snapshot":
            self._handle_ontology_snapshot()
        elif self.path == "/api/ontology/links":
            self._handle_ontology_links()
        elif self.path == "/api/ontology/derive":
            self._handle_ontology_derive(payload)
        elif self.path == "/api/ontology/temporal":
            self._handle_ontology_temporal(payload)
        elif self.path == "/api/ontology/action-chain-dry-run":
            self._handle_ontology_action_chain_dry_run(payload)
        elif self.path == "/api/ontology/eval-rules":
            self._handle_ontology_eval_rules(payload)
        elif self.path == "/api/data-graph":
            self._handle_data_graph(payload)
        elif self.path == "/api/data/add":
            self._handle_data_add(payload)
        elif self.path == "/api/tools/link-candidates":
            self._handle_link_candidates(payload)
        elif self.path == "/api/tools/expr-ast":
            self._handle_expr_ast(payload)
        elif self.path == "/api/tools/ontology-publish":
            self._handle_ontology_publish_tool(payload)
        elif self.path.startswith("/api/file"):
            self._handle_file()
        else:
            self._send_error(f"Unknown endpoint: {self.path}", 404)

    # ─── 输出文件映射 ──────────────────────────────────────────────
    # publish: metadata/release-time/{boCode}/{boCode}.schema-view.v2.json
    # projection: metadata/projection-run-time/{boCode}/{boCode}.{suffix}
    # ddl: generated-sql/V_{boCode}__create_tables.sql
    _PROJ_SUFFIX_MAP = {
        "authz_bo_meta_model": "authz_bo_meta_model.schema_json.v2.json",
        "api-contract": "api-contract.json",
        "authz_projection": "authz_projection.json",
        "ui-model": "ui-model.json",
    }

    def _handle_file(self):
        """读取已生成的文件内容。支持三种路径格式：
        GET /api/file?type=publish&boCode=customers
        GET /api/file?type=projection&boCode=customers&projType=authz_bo_meta_model
        GET /api/file?type=ddl&boCode=customers
        GET /api/file?type=ddl (全量 _all_tables.sql)
        GET /api/file?path=generated-sql/V_customers__create_tables.sql (原始路径)
        添加 &download=1 直接返回原始文件流用于下载
        """
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        file_type = (params.get("type", [None])[0] or "").strip()
        bo_code = (params.get("boCode", [None])[0] or "").strip()
        proj_type = (params.get("projType", [None])[0] or "").strip()
        raw_path = (params.get("path", [None])[0] or "").strip()
        is_download = (params.get("download", [None])[0] or "").strip() == "1"

        # 安全检查：禁止路径穿越
        def _safe(root: Path, rel: str) -> Path:
            p = (root / rel).resolve()
            if not str(p).startswith(str(root.resolve())):
                raise ValueError("路径穿越拒绝")
            return p

        repo_root = ROOT.parent
        file_path = None

        try:
            if raw_path:
                file_path = _safe(repo_root, raw_path)
            elif file_type == "publish" and bo_code:
                file_path = _safe(repo_root, f"metadata/release-time/{bo_code}/{bo_code}.schema-view.v2.json")
            elif file_type == "projection" and bo_code and proj_type:
                suffix = self._PROJ_SUFFIX_MAP.get(proj_type, f"{proj_type}.json")
                file_path = _safe(repo_root, f"metadata/projection-run-time/{bo_code}/{bo_code}.{suffix}")
            elif file_type == "ddl":
                if bo_code:
                    file_path = _safe(repo_root, f"generated-sql/V_{bo_code}__create_tables.sql")
                else:
                    file_path = _safe(repo_root, "generated-sql/_all_tables.sql")
            else:
                return self._send_error("缺少参数：type + boCode，或 path", 400)

            if not file_path.exists():
                return self._send_error(f"文件不存在: {file_path.relative_to(repo_root)}", 404)

            content = file_path.read_text(encoding="utf-8-sig")

            # 下载模式：返回原始文件流
            if is_download:
                content_bytes = content.encode("utf-8")
                content_type = "application/json" if file_path.suffix == ".json" else "text/plain; charset=utf-8"
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Disposition", f'attachment; filename="{file_path.name}"')
                self.send_header("Content-Length", len(content_bytes))
                self.end_headers()
                self.wfile.write(content_bytes)
                return

            is_json = file_path.suffix == ".json"
            if is_json:
                data = json.loads(content)
                self._send_json(data)
            else:
                # 文本文件 (SQL 等)：返回原始文本
                self._send_json({
                    "ok": True,
                    "path": str(file_path.relative_to(repo_root)),
                    "fileName": file_path.name,
                    "content": content,
                })
        except ValueError as e:
            self._send_error(str(e), 403)
        except Exception as e:
            self._send_error(f"读取文件出错: {str(e)}", 500)

    def _handle_fragment(self, payload):
        """返回指定 BO 的 fragment JSON 文件内容"""
        bo_code = (payload.get("boCode") or "").strip()
        meta_type = (payload.get("metaType") or "").strip().upper()
        if not bo_code or not meta_type:
            return self._send_error("Missing boCode or metaType", 400)
        if meta_type not in ("MODEL","VALIDATION","SECURITY","RULE","VIEW","OPERATION"):
            return self._send_error(f"Invalid metaType: {meta_type}", 400)
        frag_dir = ROOT.parent / "metadata" / "design-time" / bo_code / "fragments"
        frag_file = frag_dir / f"{bo_code}-{meta_type.lower()}.fragment.json"
        if not frag_file.exists():
            return self._send_error(f"Fragment not found: {frag_file.name}", 404)
        try:
            content = frag_file.read_text(encoding="utf-8-sig")
            data = json.loads(content)
            self._send_json(data)
        except Exception as e:
            self._send_error(f"Read error: {str(e)}", 500)

    def _handle_bo_info(self, payload):
        """获取或更新 BO 管理信息 (bo-info.json)"""
        bo_code = (payload.get("boCode") or "").strip()
        if not bo_code:
            return self._send_error("Missing boCode", 400)
        bo_dir = ROOT.parent / "metadata" / "design-time" / bo_code
        info_file = bo_dir / "bo-info.json"
        # If payload has update fields, save the info file
        if "tenantId" in payload or "draftVersion" in payload:
            bo_dir.mkdir(parents=True, exist_ok=True)
            info = {}
            if info_file.exists():
                try:
                    info = json.loads(info_file.read_text(encoding="utf-8-sig"))
                except Exception:
                    pass
            for key in ("tenantId","appCode","boCode","draftVersion","schemaVersion","changeNote"):
                if key in payload:
                    info[key] = payload[key]
            info.setdefault("boCode", bo_code)
            info.setdefault("tenantId", "default")
            info.setdefault("appCode", "government")
            info.setdefault("draftVersion", "0.1")
            info.setdefault("schemaVersion", "2.0")
            info_file.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
            self._send_json({"ok": True, "info": info})
            return
        # GET: return bo-info.json content
        if info_file.exists():
            try:
                info = json.loads(info_file.read_text(encoding="utf-8-sig"))
                self._send_json(info)
            except Exception as e:
                self._send_error(f"Read error: {str(e)}", 500)
        else:
            self._send_error("BO info not found", 404)

    def _handle_schema_version(self):
        """从 bo-meta-fragment.schema.json 读取当前 schemaVersion"""
        import re
        schema_file = ROOT.parent / "schemas" / "design-time" / "bo-meta-fragment.schema.json"
        try:
            schema = json.loads(schema_file.read_text(encoding="utf-8-sig"))
            comment = schema.get("$comment", "")
            m = re.search(r'当前最新[：:]\s*信封\s*v?(\d+\.\d+)', comment)
            version = m.group(1) if m else "2.0"
            self._send_json({"schemaVersion": version})
        except Exception as e:
            self._send_json({"schemaVersion": "2.0", "warning": str(e)})

    def _handle_schema(self, schema_key):
        """返回指定 schema JSON 内容。
        schema_key 可以是:
          - 'envelope' → bo-meta-fragment.schema.json
          - 'MODEL' / 'VALIDATION' / 'SECURITY' / 'RULE' / 'VIEW' / 'OPERATION' → fragments/{type}-fragment.schema.json
        """
        schema_key = schema_key.strip().upper()
        schema_dir = ROOT.parent / "schemas" / "design-time"
        if schema_key == "ENVELOPE":
            schema_file = schema_dir / "bo-meta-fragment.schema.json"
        elif schema_key in ("MODEL","VALIDATION","SECURITY","RULE","VIEW","OPERATION"):
            frag_name = schema_key.lower()
            schema_file = schema_dir / "fragments" / f"{frag_name}-fragment.schema.json"
        else:
            return self._send_error(f"Unknown schema: {schema_key}", 404)
        try:
            schema = json.loads(schema_file.read_text(encoding="utf-8-sig"))
            self._send_json(schema)
        except Exception as e:
            self._send_error(f"Read error: {str(e)}", 500)

    def _read_bo_info(self, bo_code):
        """读取 BO 管理信息，不存在则返回默认值"""
        info_file = ROOT.parent / "metadata" / "design-time" / bo_code / "bo-info.json"
        if info_file.exists():
            try:
                return json.loads(info_file.read_text(encoding="utf-8-sig"))
            except Exception:
                pass
        return {"tenantId": "default", "appCode": "government", "boCode": bo_code,
                "draftVersion": "0.1", "schemaVersion": "2.0"}

    def _handle_save_fragment(self, payload):
        """保存 fragment JSON，信封信息从 bo-info.json 读取"""
        bo_code = (payload.get("boCode") or "").strip()
        meta_type = (payload.get("metaType") or "").strip().upper()
        content = payload.get("content")
        if not bo_code or not meta_type:
            return self._send_error("Missing boCode or metaType", 400)
        if meta_type not in ("MODEL","VALIDATION","SECURITY","RULE","VIEW","OPERATION"):
            return self._send_error(f"Invalid metaType: {meta_type}", 400)
        # Read envelope from bo-info.json
        info = self._read_bo_info(bo_code)
        # Override content.boCode with the one from bo-info
        if isinstance(content, dict):
            content["boCode"] = bo_code
        frag_dir = ROOT.parent / "metadata" / "design-time" / bo_code / "fragments"
        frag_dir.mkdir(parents=True, exist_ok=True)
        draft_ver = info.get("draftVersion", "0.1")
        schema_ver = info.get("schemaVersion", "2.0")
        # If payload specifies a higher version, update bo-info
        payload_dv = payload.get("draftVersion")
        if payload_dv and self._version_cmp(str(payload_dv), str(draft_ver)) > 0:
            draft_ver = str(payload_dv)
            info["draftVersion"] = draft_ver
            info_file = ROOT.parent / "metadata" / "design-time" / bo_code / "bo-info.json"
            info_file.parent.mkdir(parents=True, exist_ok=True)
            info_file.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
        frag_file = frag_dir / f"{bo_code}-{meta_type.lower()}.fragment.json"
        fragment = {
            "$schema": "https://authz.xbac/schemas/gov/bo-meta-fragment.schema.json",
            "tenantId": info.get("tenantId", "default"),
            "appCode": info.get("appCode", "government"),
            "boCode": bo_code,
            "metaType": meta_type,
            "draftVersion": draft_ver,
            "schemaVersion": schema_ver,
            "content": content or {}
        }
        if info.get("changeNote"):
            fragment["changeNote"] = info["changeNote"]
        try:
            json_str = json.dumps(fragment, ensure_ascii=False, indent=2)
            frag_file.write_text(json_str, encoding="utf-8")
            # Sync draftVersion/schemaVersion to all other fragments of this BO
            synced = 0
            for other in frag_dir.glob(f"{bo_code}-*.fragment.json"):
                if other.name == frag_file.name:
                    continue
                try:
                    d = json.loads(other.read_text(encoding="utf-8-sig"))
                    if d.get("draftVersion") != draft_ver or d.get("schemaVersion") != schema_ver:
                        d["draftVersion"] = draft_ver
                        d["schemaVersion"] = schema_ver
                        other.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
                        synced += 1
                except Exception:
                    pass
            result = {"ok": True, "path": str(frag_file.relative_to(ROOT.parent)), "file": frag_file.name,
                       "draftVersion": draft_ver, "schemaVersion": schema_ver}
            if synced > 0:
                result["synced"] = synced
            # Schema 校验（不拒绝保存，仅返回警告提示）
            schema_warnings = self._validate_fragment_schema(fragment)
            if schema_warnings:
                result["schemaWarnings"] = schema_warnings
            self._send_json(result)
        except Exception as e:
            self._send_error(f"Write error: {str(e)}", 500)

    def _validate_fragment_schema(self, fragment: dict) -> list[str]:
        """对已组装的 fragment 做 JSON Schema 校验，返回错误信息列表（不抛异常）。"""
        try:
            _viz_mod._load_schemas()
            errs = _viz_mod.validate_fragment(fragment, Path(""))
            return errs
        except Exception as e:
            return [f"Schema 校验初始化失败: {e}"]

    @staticmethod
    def _version_cmp(a, b):
        """比较两个语义化版本号字符串，返回 -1/0/1"""
        try:
            pa = [int(x) for x in str(a).lstrip("v").split(".")]
            pb = [int(x) for x in str(b).lstrip("v").split(".")]
            while len(pa) < len(pb): pa.append(0)
            while len(pb) < len(pa): pb.append(0)
            for x, y in zip(pa, pb):
                if x < y: return -1
                if x > y: return 1
            return 0
        except Exception:
            return 0

    def _handle_graph(self):
        """重新解析 Fragment 生成 graph-data.json，stderr 输出随响应返回"""
        import io
        stderr_buf = io.StringIO()
        old_stderr = sys.stderr
        sys.stderr = stderr_buf
        try:
            _viz_mod._load_schemas()
            graph = _viz_mod.parse_all()
            output_path = ROOT / "graph-data.json"
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(graph, f, ensure_ascii=False, indent=2)
            sys.stderr = old_stderr
            stderr_output = stderr_buf.getvalue()
            result = {
                "ok": True,
                "boCount": graph["meta"]["boCount"],
                "edgeCount": graph["meta"]["edgeCount"],
                "output": str(output_path),
            }
            if stderr_output.strip():
                result["stderr"] = stderr_output.strip()
            self._send_json(result)
        except Exception as e:
            sys.stderr = old_stderr
            stderr_output = stderr_buf.getvalue()
            traceback.print_exc()
            self._send_json({
                "ok": False,
                "error": str(e),
                "stderr": stderr_output.strip() if stderr_output.strip() else None,
            }, 500)

    def _handle_publish(self, payload):
        bo_code = payload.get("boCode")
        if not bo_code:
            return self._send_error("Missing boCode")

        try:
            result = _pub_mod.generate(bo_code)
            # 写入文件：metadata/release-time/{boCode}/{boCode}.schema-view.v2.json
            release_dir = ROOT.parent / "metadata" / "release-time" / bo_code
            release_dir.mkdir(parents=True, exist_ok=True)
            output_path = release_dir / f"{bo_code}.schema-view.v2.json"
            output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
            self._send_json(result)
        except SystemExit:
            self._send_error(f"BO '{bo_code}' 发布态未生成或不存在", 404)
        except Exception as e:
            traceback.print_exc()
            self._send_error(str(e), 500)

    def _handle_projection(self, payload):
        bo_code = payload.get("boCode")
        if not bo_code:
            return self._send_error("Missing boCode")
        projection_type = payload.get("projectionType", "authz_bo_meta_model")

        try:
            result = _proj_mod.generate(bo_code, projection_type)
            # 写入文件：metadata/projection-run-time/{boCode}/{boCode}.{suffix}
            suffix = self._PROJ_SUFFIX_MAP.get(projection_type, f"{projection_type}.json")
            proj_dir = ROOT.parent / "metadata" / "projection-run-time" / bo_code
            proj_dir.mkdir(parents=True, exist_ok=True)
            output_path = proj_dir / f"{bo_code}.{suffix}"
            output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
            self._send_json(result)
        except SystemExit:
            self._send_error(f"请先生成 '{bo_code}' 的发布态", 404)
        except Exception as e:
            traceback.print_exc()
            self._send_error(str(e), 500)

    def _handle_projection_merge(self, payload):
        """全量投影完成后的自动合并：扫描 merge-manifests/ 对涉及的 BO 执行合并投影。"""
        try:
            result = _proj_mod.generate_auto_merges(requested_bos=None)
            self._send_json(result)
        except Exception as e:
            traceback.print_exc()
            self._send_error(str(e), 500)

    def _run_script(self, script_name: str, *args, timeout: int = 600) -> subprocess.CompletedProcess:
        """运行 Python 脚本并捕获输出（UTF-8 编码）。默认 600s 超时。"""
        env = {**__import__('os').environ, "PYTHONIOENCODING": "utf-8"}
        return subprocess.run(
            [PYTHON, str(ROOT / script_name), *args],
            capture_output=True, text=True, timeout=timeout, cwd=str(ROOT),
            encoding="utf-8", errors="replace", env=env,
        )

    def _handle_validate(self, payload):
        try:
            result1 = self._run_script("bo-consistency-check.py")
            result2 = self._run_script("check_metadata_consistency.py")
            combined_stdout = (
                "════════════════════════════════════════════════════════════════\n"
                "  Phase A: bo-consistency-check.py (JSON Schema + BO 深度检查 + 命名一致性)\n"
                "════════════════════════════════════════════════════════════════\n"
                + result1.stdout
            )
            if result1.stderr.strip():
                combined_stdout += "\n── stderr ──\n" + result1.stderr
            combined_stdout += (
                "\n\n════════════════════════════════════════════════════════════════\n"
                "  Phase B: check_metadata_consistency.py (元数据深度一致性校验)\n"
                "════════════════════════════════════════════════════════════════\n"
                + result2.stdout
            )
            if result2.stderr.strip():
                combined_stdout += "\n── stderr ──\n" + result2.stderr
            self._send_json({
                "ok": result1.returncode == 0 and result2.returncode == 0,
                "exitCode": result1.returncode | result2.returncode,
                "stdout": combined_stdout,
                "stderr": "",
            })
        except subprocess.TimeoutExpired:
            self._send_error("校验超时", 504)
        except Exception as e:
            traceback.print_exc()
            self._send_error(str(e), 500)

    def _handle_ddl(self, payload):
        bo_code = payload.get("boCode")
        try:
            if bo_code:
                result = self._run_script("bo-ddl-gen.py", "--bo", bo_code)
            else:
                result = self._run_script("bo-ddl-gen.py")
            self._send_json({
                "ok": result.returncode == 0,
                "exitCode": result.returncode,
                "boCode": bo_code or "ALL",
                "stdout": result.stdout,
                "stderr": result.stderr,
            })
        except subprocess.TimeoutExpired:
            self._send_error("DDL 生成超时", 504)
        except Exception as e:
            traceback.print_exc()
            self._send_error(str(e), 500)

    def _handle_inspect(self, payload):
        """数据库检查：drift / profile / validate / ref-integrity"""
        bo_code = payload.get("boCode")
        cmd = payload.get("cmd", "all")
        if not bo_code:
            return self._send_error("Missing boCode")

        # 应用运行时数据库配置覆盖
        db_config = payload.get("dbConfig")
        if db_config:
            _inspector_mod.set_config_override(db_config)
        else:
            _inspector_mod.set_config_override(None)

        cmd_map = {
            "drift": _inspector_mod.detect_drift,
            "profile": _inspector_mod.profile_data,
            "validate": _inspector_mod.run_validations,
            "ref-integrity": _inspector_mod.check_ref_integrity,
        }

        try:
            if cmd == "all":
                # 依次执行并收集输出
                import io
                old_stdout = sys.stdout
                buf = io.StringIO()
                sys.stdout = buf
                try:
                    _inspector_mod.detect_drift(bo_code)
                    _inspector_mod.profile_data(bo_code)
                    _inspector_mod.run_validations(bo_code)
                    _inspector_mod.check_ref_integrity(bo_code)
                finally:
                    sys.stdout = old_stdout
                self._send_json({"ok": True, "boCode": bo_code, "cmd": cmd, "output": buf.getvalue()})
            elif cmd in cmd_map:
                import io
                old_stdout = sys.stdout
                buf = io.StringIO()
                sys.stdout = buf
                try:
                    cmd_map[cmd](bo_code)
                finally:
                    sys.stdout = old_stdout
                self._send_json({"ok": True, "boCode": bo_code, "cmd": cmd, "output": buf.getvalue()})
            else:
                self._send_error(f"Unknown inspect cmd: {cmd}. Available: all, {', '.join(cmd_map.keys())}")
        except Exception as e:
            traceback.print_exc()
            self._send_error(str(e), 500)


    # ─── 本体推理原型 API ─────────────────────────────────────────
    def _handle_ontology_publish(self, payload):
        """生成应用级 Ontology 发布产物。"""
        app_code = (payload.get("appCode") or "crm").strip()
        gen_type = (payload.get("type") or "all").strip()
        try:
            _onto_pub_mod.generate_all(app_code) if gen_type == "all" else None
            self._send_json({"ok": True, "appCode": app_code, "type": gen_type})
        except Exception as e:
            self._send_error(str(e), 500)

    def _handle_ontology_snapshot(self):
        """返回当前应用级 Ontology Snapshot。"""
        snapshot_path = ROOT.parent / "metadata" / "release-time" / "_ontology" / "crm.ontology-snapshot.v1.json"
        if not snapshot_path.exists():
            return self._send_error("Ontology snapshot not found. Run /api/ontology/publish first.", 404)
        try:
            data = json.loads(snapshot_path.read_text(encoding="utf-8-sig"))
            self._send_json(data)
        except Exception as e:
            self._send_error(str(e), 500)

    def _handle_ontology_links(self):
        """返回 Link Index。"""
        link_path = ROOT.parent / "metadata" / "release-time" / "_ontology" / "crm.ontology-link-index.v1.json"
        if not link_path.exists():
            return self._send_error("Link index not found. Run /api/ontology/publish first.", 404)
        try:
            data = json.loads(link_path.read_text(encoding="utf-8-sig"))
            self._send_json(data)
        except Exception as e:
            self._send_error(str(e), 500)

    def _handle_ontology_derive(self, payload):
        """执行派生对象 dry-run，调用 bo-ontology-demo-eval.py 获取真实输出。"""
        scenario = (payload.get("scenario") or "customer-360").strip()
        obj_id = (payload.get("obj_id") or "").strip()
        bo_code = (payload.get("boCode") or "").strip()
        # 无具体记录 ID 时：将 boCode 传给脚本，id 用 all 触发全局遍历
        if not obj_id and bo_code:
            obj_id = "all"
        elif not obj_id:
            obj_id = "DEMO_ID"
        llm_config = payload.get("llmConfig") or {}
        scenario_dir = (payload.get("scenarioDir") or "").strip()
        try:
            script_args = ["--scenario", scenario, "--id", obj_id]
            if bo_code:
                script_args.extend(["--bo", bo_code])
            if scenario_dir:
                script_args.extend(["--scenario-dir", scenario_dir])
            if llm_config.get("enabled") is False:
                script_args.append("--llm-disabled")
            if llm_config.get("apiKey"):
                script_args.extend(["--llm-key", llm_config["apiKey"]])
            if llm_config.get("apiBase"):
                script_args.extend(["--llm-base", llm_config["apiBase"]])
            if llm_config.get("model"):
                script_args.extend(["--llm-model", llm_config["model"]])
            # 统一使用默认 500s 超时，批量/单条均可覆盖
            result = self._run_script("bo-ontology-demo-eval.py", *script_args)
            self._send_json({
                "ok": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "scenario": scenario,
                "objectId": obj_id,
            })
        except subprocess.TimeoutExpired:
            self._send_error("派生 dry-run 超时", 504)
        except Exception as e:
            traceback.print_exc()
            self._send_error(str(e), 500)

    def _handle_ontology_temporal(self, payload):
        """执行时态指标 dry-run。"""
        scenario = (payload.get("scenario") or "opportunity-timeline").strip()
        obj_id = (payload.get("id") or "DEMO_ID").strip()
        self._send_json({
            "object": {"id": obj_id},
            "timeline": scenario,
            "metrics": {"_": "DRY_RUN"},
            "_demo": {"mode": "DRY_RUN"}
        })

    def _handle_ontology_action_chain_dry_run(self, payload):
        """执行动作链 dry-run，调用 bo-ontology-demo-eval.py 获取真实输出。"""
        chain_code = (payload.get("chainCode") or "OPPORTUNITY_WIN_POST_ACTIONS").strip()
        bo_code = (payload.get("boCode") or "").strip()
        obj_id = (payload.get("id") or "DEMO_ID").strip()
        operation = (payload.get("operation") or "").strip()
        scenario_dir = (payload.get("scenarioDir") or "").strip()
        try:
            cmd_args = [
                "--dry-run-chain", chain_code,
                "--bo", bo_code, "--id", obj_id, "--operation", operation
            ]
            if scenario_dir:
                cmd_args.extend(["--scenario-dir", scenario_dir])
            result = self._run_script(
                "bo-ontology-demo-eval.py",
                *cmd_args
            )
            self._send_json({
                "ok": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
            })
        except subprocess.TimeoutExpired:
            self._send_error("动作链 dry-run 超时", 504)
        except Exception as e:
            traceback.print_exc()
            self._send_error(str(e), 500)

    def _handle_ontology_eval_rules(self, payload):
        """执行规则 exprAst dry-run 评估，调用 bo-ontology-demo-eval.py。"""
        bo_code = (payload.get("boCode") or "").strip()
        obj_id = (payload.get("id") or "").strip()
        scenario_dir = (payload.get("scenarioDir") or "").strip()
        if not bo_code:
            self._send_error("boCode is required", 400)
            return
        try:
            all_output = ""
            # boCode=all：找出所有有 RULE Fragment 的 BO 逐个评估
            if bo_code == "all":
                design_dir = ROOT.parent / "metadata" / "design-time"
                bo_codes = sorted([
                    d.name for d in design_dir.iterdir()
                    if d.is_dir() and (d / "fragments" / f"{d.name}-rule.fragment.json").exists()
                ])
                for idx, bc in enumerate(bo_codes, 1):
                    sp_args = ["--eval-rules", bc]
                    if scenario_dir:
                        sp_args.extend(["--scenario-dir", scenario_dir])
                    result = self._run_script("bo-ontology-demo-eval.py", *sp_args)
                    all_output += f"\n{'='*60}\n"
                    all_output += f"  [{idx}/{len(bo_codes)}] {bc}\n"
                    all_output += f"{'='*60}\n"
                    all_output += (result.stdout or "") + "\n"
                self._send_json({
                    "ok": True,
                    "stdout": all_output.strip(),
                    "stderr": f"Evaluated {len(bo_codes)} BOs",
                    "boCode": "all",
                })
                return

            args = ["--eval-rules", bo_code]
            if obj_id:
                args.extend(["--id", obj_id])
            if scenario_dir:
                args.extend(["--scenario-dir", scenario_dir])
            result = self._run_script("bo-ontology-demo-eval.py", *args)
            self._send_json({
                "ok": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "boCode": bo_code,
                "objectId": obj_id,
            })
        except subprocess.TimeoutExpired:
            self._send_error("规则评估超时", 504)
        except Exception as e:
            traceback.print_exc()
            self._send_error(str(e), 500)

    def _handle_data_graph(self, payload):
        """生成数据知识图谱（demo-data 实例图谱）。"""
        scenario_dir = (payload.get("scenarioDir") or "education").strip()
        try:
            result = _data_graph_mod.generate(scenario_dir)
            self._send_json(result)
        except Exception as e:
            traceback.print_exc()
            self._send_error(str(e), 500)

    def _handle_data_add(self, payload):
        """向 demo-data/{scenarioDir}/{boCode}.sample.json 追加一条记录。"""
        bo_code = (payload.get("boCode") or "").strip()
        record = payload.get("record")
        scenario_dir = (payload.get("scenarioDir") or "education").strip()
        if not bo_code:
            return self._send_error("Missing boCode", 400)
        if not isinstance(record, dict) or not record:
            return self._send_error("Missing or invalid record", 400)
        sample_file = ROOT / "demo-data" / scenario_dir / f"{bo_code}.sample.json"
        if not sample_file.exists():
            return self._send_error(f"Sample file not found: {sample_file.name}", 404)
        try:
            data = json.loads(sample_file.read_text(encoding="utf-8-sig"))
            if "records" not in data:
                data["records"] = []
            # 自动生成 id
            max_id = max((r.get("id", 0) or 0 for r in data["records"]), default=0)
            new_id = max_id + 1
            record["id"] = record.get("id") or new_id
            data["records"].append(record)
            sample_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self._send_json({"ok": True, "recordId": record["id"], "file": str(sample_file.relative_to(ROOT))})
        except Exception as e:
            traceback.print_exc()
            self._send_error(str(e), 500)

    def _handle_link_candidates(self, payload):
        """生成 LINK 候选清单，调用 bo-link-candidates-gen.py。"""
        try:
            result = self._run_script("bo-link-candidates-gen.py")
            self._send_json({
                "ok": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
            })
        except subprocess.TimeoutExpired:
            self._send_error("LINK 候选生成超时", 504)
        except Exception as e:
            traceback.print_exc()
            self._send_error(str(e), 500)

    def _handle_expr_ast(self, payload):
        """转换表达式为 AST 并回写 RULE Fragment，调用 bo-expression-to-ast.py --write-back。"""
        write_back = payload.get("writeBack", True)
        args = ["--write-back"] if write_back else []
        try:
            result = self._run_script("bo-expression-to-ast.py", *args)
            self._send_json({
                "ok": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
            })
        except subprocess.TimeoutExpired:
            self._send_error("exprAst 转换超时", 504)
        except Exception as e:
            traceback.print_exc()
            self._send_error(str(e), 500)

    def _handle_ontology_publish_tool(self, payload):
        """发布本体 Fragment 到运行时索引，调用 bo-ontology-publish-gen.py。"""
        try:
            result = self._run_script("bo-ontology-publish-gen.py")
            self._send_json({
                "ok": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
            })
        except subprocess.TimeoutExpired:
            self._send_error("本体发布超时", 504)
        except Exception as e:
            traceback.print_exc()
            self._send_error(str(e), 500)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="BO 治理 API 服务")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    server = HTTPServer(("127.0.0.1", args.port), APIHandler)
    print(f"🚀 BO 治理 API 服务已启动: http://127.0.0.1:{args.port}")
    print(f"   端点: GET  /              — 可视化图谱界面")
    print(f"         POST /api/publish   — 生成发布态 schema-view.v2")
    print(f"         POST /api/projection — 生成 PSP 投影 schema_json")
    print(f"         POST /api/graph      — 重构图谱数据")
    print(f"         POST /api/validate   — 深度校验")
    print(f"         POST /api/ddl        — 生成 DDL SQL")
    print(f"         POST /api/inspect    — 数据库检查 (drift/profile/validate/ref-integrity)")
    print(f"         POST /api/health     — 健康检查")
    print(f"   按 Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 已停止")
        server.server_close()


if __name__ == "__main__":
    main()
