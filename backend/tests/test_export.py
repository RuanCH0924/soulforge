"""集成测试：Prompt Pack 导出（tar.gz + MANIFEST.json）。"""
from __future__ import annotations

import io
import json
import tarfile


def test_export_agent_tarball(client):
    res = client.get("/api/export/alpha")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/gzip")
    assert res.content.startswith(b"\x1f\x8b")  # gzip magic
    assert "soulforge-alpha" in res.headers.get("content-disposition", "")


def test_export_agent_contains_manifest(client):
    res = client.get("/api/export/alpha")
    with tarfile.open(fileobj=io.BytesIO(res.content), mode="r:gz") as tf:
        names = tf.getnames()
        # make_archive 写入的条目带 "./" 前缀
        normalized = {n[2:] if n.startswith("./") else n for n in names}
        assert "MANIFEST.json" in normalized
        assert "SOUL.md" in normalized
        manifest = json.loads(tf.extractfile("./MANIFEST.json").read().decode("utf-8"))
    assert manifest["agent_id"] == "alpha"
    assert any(f["path"] == "SOUL.md" for f in manifest["files"])


def test_export_all(client):
    res = client.get("/api/export/all")
    assert res.status_code == 200
    assert res.content.startswith(b"\x1f\x8b")
