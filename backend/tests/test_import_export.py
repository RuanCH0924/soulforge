"""集成测试：导入导出（tar.gz + manifest + sha256 校验 + tar bomb 防护）。"""
from __future__ import annotations

import io
import tarfile


def test_export_and_import_roundtrip(client, openclaw_dir):
    """导出 alpha → 改内容 → 导入到 beta（overwrite）→ 验证。"""
    # 1. 导出 alpha
    res = client.get("/api/export/alpha")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/gzip")
    tarball = res.content
    assert tarball.startswith(b"\x1f\x8b")  # gzip magic

    # 2. 修改 alpha 的 SOUL.md（让导入有内容可覆盖）
    client.put("/api/agents/alpha/files/SOUL.md", json={"content": "# alpha SOUL\n\n已被修改。\n"})

    # 3. 预览导入到 beta
    res = client.post(
        "/api/import/preview",
        files={"file": ("pack.tar.gz", io.BytesIO(tarball), "application/gzip")},
        data={"target_agent_id": "beta"},
    )
    assert res.status_code == 200
    preview = res.json()["data"]
    upload_id = preview["upload_id"]
    assert preview["manifest"]["agent_id"] == "alpha"
    conflicts = {c["path"]: c for c in preview["conflicts"]}
    assert "SOUL.md" in conflicts
    assert conflicts["SOUL.md"]["exists_in_target"] is True

    # 4. 执行导入（overwrite 冲突的 SOUL.md；IDENTITY/TOOLS 在 beta 不存在 → 自动 add）
    res = client.post("/api/import/execute", json={
        "upload_id": upload_id,
        "target_agent_id": "beta",
        "conflicts": {"SOUL.md": "overwrite"},
    })
    assert res.status_code == 200
    results = res.json()["data"]["results"]
    actions = {r["file"]: r["action"] for r in results}
    assert actions.get("SOUL.md") == "overwritten"
    assert actions.get("IDENTITY.md") == "added"

    # 5. beta 的 SOUL.md 现在是 alpha 的旧版本
    content = client.get("/api/agents/beta/files/SOUL.md").json()["data"]["content"]
    assert "alpha SOUL" in content


def test_import_skip_by_default(client):
    """冲突文件默认 skip，绝不默认覆盖。"""
    res = client.get("/api/export/alpha")
    tarball = res.content
    res = client.post(
        "/api/import/preview",
        files={"file": ("pack.tar.gz", io.BytesIO(tarball), "application/gzip")},
        data={"target_agent_id": "beta"},
    )
    upload_id = res.json()["data"]["upload_id"]
    before = client.get("/api/agents/beta/files/SOUL.md").json()["data"]["content"]
    res = client.post("/api/import/execute", json={
        "upload_id": upload_id, "target_agent_id": "beta", "conflicts": {},
    })
    actions = {r["file"]: r["action"] for r in res.json()["data"]["results"]}
    assert actions.get("SOUL.md") == "skipped"
    after = client.get("/api/agents/beta/files/SOUL.md").json()["data"]["content"]
    assert after == before


def test_export_all(client):
    res = client.get("/api/export/all")
    assert res.status_code == 200
    assert res.content.startswith(b"\x1f\x8b")


def test_import_rejects_tar_bomb(client):
    """tar 含路径穿越 → 拒绝（tar bomb 防护）。"""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        info = tarfile.TarInfo(name="../../evil.md")
        payload = b"evil"
        info.size = len(payload)
        tf.addfile(info, io.BytesIO(payload))
    res = client.post(
        "/api/import/preview",
        files={"file": ("evil.tar.gz", io.BytesIO(buf.getvalue()), "application/gzip")},
        data={"target_agent_id": "beta"},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "UNSAFE_PATH"


def test_import_rejects_bad_manifest(client):
    """缺 MANIFEST.json → 拒绝。"""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        info = tarfile.TarInfo(name="SOUL.md")
        payload = b"# no manifest"
        info.size = len(payload)
        tf.addfile(info, io.BytesIO(payload))
    res = client.post(
        "/api/import/preview",
        files={"file": ("bad.tar.gz", io.BytesIO(buf.getvalue()), "application/gzip")},
        data={"target_agent_id": "beta"},
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "MANIFEST_CORRUPTED"
