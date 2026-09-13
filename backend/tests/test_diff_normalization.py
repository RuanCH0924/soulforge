"""测试：对比工具的归一化与准确性修复。

覆盖三类场景：
1. 完全相同的文本内容 → 必须判定为「一致」；
2. 仅存在无关格式噪声的相同内容（BOM / CRLF / 零宽字符 / 全角空格 / Tab /
   行尾空白 / 连续空行 / 文末换行）→ 必须判定为「有效内容一致」；
3. 存在真实业务差异的内容 → 必须仍然判定为「不一致」，且不能被归一化吞掉。

另含性能压测：快路径（内容一致）必须远快于完整 diff，大文本必须在预算内完成。
"""
from __future__ import annotations

import time

import pytest

from app.services.diff_service import (
    MODE_IGNORE_WHITESPACE,
    MODE_STRICT,
    build_diff,
    canonical,
    detect_noise,
    similarity,
)

BASE = "# 标题\n\n- 项目一\n- 项目二\n\n正文内容。\n"

# 视觉上与 BASE 完全相同、但字符层面不同的「格式噪声」变体
# 注意：全角空格 / NBSP / Tab 变体是「把原有普通空格换成等价字符」，
# 而不是新增一个空格——后者在视觉上确有差异，不属于格式噪声。
NOISE_VARIANTS: dict[str, str] = {
    "crlf_line_ending": BASE.replace("\n", "\r\n"),
    "cr_only_line_ending": BASE.replace("\n", "\r"),
    "no_final_newline": BASE.rstrip("\n"),
    "trailing_spaces": BASE.replace("- 项目一", "- 项目一   "),
    "fullwidth_space": BASE.replace("- 项目一", "-\u3000项目一"),
    "nbsp": BASE.replace("- 项目一", "-\u00a0项目一"),
    "zero_width_space": BASE.replace("项目一", "项目\u200b一"),
    "zero_width_joiner_inline": BASE.replace("项目一", "项目\u200d一"),
    # 真实数据中实际出现过的形态：文件末尾多出「空行 + 零宽连接符」
    "zero_width_joiner_at_eof": BASE + "\n\n\u200d",
    "tab_indent": BASE.replace("- 项目一", "-\t项目一"),
    "extra_blank_lines": BASE.replace("\n\n", "\n\n\n"),
    "utf8_bom": "\ufeff" + BASE,
    "utf8_bom_and_crlf": "\ufeff" + BASE.replace("\n", "\r\n"),
}

# strict 口径下「应当忽略」的噪声（绝对无意义，与空白量无关）
STRICT_IGNORED_NOISE = (
    "utf8_bom",
    "crlf_line_ending",
    "cr_only_line_ending",
    "zero_width_space",
    "zero_width_joiner_inline",
)

# strict 口径下「应当保留」的差异（涉及空白量/空行数，属可见格式差异）
STRICT_KEPT_NOISE = (
    "no_final_newline",
    "trailing_spaces",
    "extra_blank_lines",
    "fullwidth_space",
    "nbsp",
    "tab_indent",
)

# 真实业务差异：必须被判为「不一致」
REAL_DIFF_VARIANTS: dict[str, str] = {
    "word_changed": BASE.replace("正文内容。", "正文内容已修改。"),
    "line_added": BASE + "- 项目三\n",
    "line_removed": BASE.replace("- 项目二\n", ""),
    "heading_changed": BASE.replace("# 标题", "# 新的标题"),
    "lines_reordered": "# 标题\n\n- 项目二\n- 项目一\n\n正文内容。\n",
    "trailing_sentence_appended": BASE + "补充说明。\n",
}


# ------------------------------------------------------------ 场景 1：完全相同

def test_byte_identical_content():
    out = build_diff(BASE, BASE)
    assert out.identical is True
    assert out.raw_identical is True
    assert out.similarity == 1.0
    assert out.unified_diff == ""
    assert out.html_diff == ""
    assert out.noise_kinds == []
    assert out.similarity_mode == "none"


# ------------------------------------------------------------ 场景 2：仅格式噪声

@pytest.mark.parametrize("name", sorted(NOISE_VARIANTS))
def test_noise_only_content_is_identical(name: str):
    variant = NOISE_VARIANTS[name]
    out = build_diff(BASE, variant)
    assert out.identical is True, f"{name} 应被判定为有效内容一致"
    assert out.raw_identical is False, f"{name} 的原始内容确实不同"
    assert out.similarity == 1.0, f"{name} 的相似度应为 1.0（旧实现会给出 0.9x）"
    assert out.unified_diff == ""
    assert out.html_diff == ""
    assert out.noise_only is True
    assert out.noise_kinds, f"{name} 应给出被忽略的噪声类型"


def test_noise_detection_reports_expected_kinds():
    """噪声归因应指向真实的噪声来源。"""
    assert "invisible_char" in detect_noise(BASE, BASE + "\n\n\u200d")
    assert "bom" in detect_noise(BASE, "\ufeff" + BASE)
    assert "line_ending" in detect_noise(BASE, BASE.replace("\n", "\r\n"))
    assert "space_like_char" in detect_noise(BASE, BASE.replace("- 项目一", "-\u00a0项目一"))
    assert "multiple_spaces" in detect_noise(BASE, BASE.replace("- 项目一", "-\t项目一"))
    assert "trailing_whitespace" in detect_noise(BASE, BASE.replace("- 项目一", "- 项目一  "))
    assert "blank_lines" in detect_noise(BASE, BASE.replace("\n\n", "\n\n\n"))
    # 真实差异不应被归因为噪声
    assert detect_noise(BASE, REAL_DIFF_VARIANTS["word_changed"]) == []


def test_strict_mode_only_ignores_meaningless_noise():
    """strict 口径只忽略「绝对无意义」的噪声，用于严格场景。"""
    for name in STRICT_IGNORED_NOISE:
        assert build_diff(BASE, NOISE_VARIANTS[name], mode=MODE_STRICT).identical is True, name
    for name in STRICT_KEPT_NOISE:
        assert build_diff(BASE, NOISE_VARIANTS[name], mode=MODE_STRICT).identical is False, name


def test_canonical_is_idempotent():
    for variant in NOISE_VARIANTS.values():
        once = canonical(variant)
        assert canonical(once) == once


def test_unknown_mode_falls_back_to_default():
    out = build_diff(BASE, NOISE_VARIANTS["utf8_bom"], mode="not-a-mode")
    assert out.mode == MODE_IGNORE_WHITESPACE
    assert out.identical is True


# ------------------------------------------------------------ 场景 3：真实差异

@pytest.mark.parametrize("name", sorted(REAL_DIFF_VARIANTS))
def test_real_differences_are_not_swallowed(name: str):
    variant = REAL_DIFF_VARIANTS[name]
    out = build_diff(BASE, variant)
    assert out.identical is False, f"{name} 是真实差异，必须判为不一致"
    assert out.similarity < 1.0
    assert out.unified_diff, f"{name} 应给出差异内容"
    assert "diff-view" in out.html_diff
    assert out.noise_kinds == [], f"{name} 的差异不能被归因为格式噪声"


def test_real_difference_with_noise_is_still_different():
    """同时存在真实差异与格式噪声时，仍须判为不一致。"""
    noisy_and_changed = ("\ufeff" + BASE.replace("\n", "\r\n")).replace("正文内容。", "正文内容已修改。")
    out = build_diff(BASE, noisy_and_changed)
    assert out.identical is False
    assert out.similarity < 1.0
    assert "正文内容已修改" in out.unified_diff


def test_html_diff_marks_add_and_del():
    out = build_diff(BASE, REAL_DIFF_VARIANTS["word_changed"])
    assert "diff-del" in out.html_diff
    assert "diff-add" in out.html_diff
    assert "diff-hunk" in out.html_diff


def test_html_diff_escapes_html():
    out = build_diff("a\n", "<script>alert(1)</script>\n")
    assert "<script>" not in out.html_diff
    assert "&lt;script&gt;" in out.html_diff


# ------------------------------------------------------------ 准确率汇总

def test_identification_accuracy_is_100_percent():
    """准确率：噪声变体全部判一致、真实差异全部判不一致。"""
    total = len(NOISE_VARIANTS) + len(REAL_DIFF_VARIANTS)
    correct = 0
    for variant in NOISE_VARIANTS.values():
        if build_diff(BASE, variant).identical is True:
            correct += 1
    for variant in REAL_DIFF_VARIANTS.values():
        if build_diff(BASE, variant).identical is False:
            correct += 1
    assert correct == total, f"识别准确率 {correct}/{total}"


# ------------------------------------------------------------ 性能压测

def _big_text(lines: int = 2000) -> str:
    parts = ["# 大文档\n"]
    for i in range(lines):
        parts.append(f"- 第 {i} 行：这是一段用于压测的内容，包含中文与 ASCII 混排 text {i}。\n")
    return "\n".join(parts)


def test_fast_path_identical_is_fast():
    """内容完全相同时必须走快路径，不做 diff 计算。"""
    big = _big_text(3000)
    start = time.perf_counter()
    out = build_diff(big, big)
    elapsed = time.perf_counter() - start
    assert out.identical is True
    assert elapsed < 0.05, f"快路径耗时 {elapsed:.3f}s，应 < 0.05s"


def test_fast_path_noise_only_is_fast():
    """内容一致但带格式噪声时，应只做 O(n) 归一化，不做 diff。"""
    big = _big_text(3000)
    noisy = big.replace("\n", "\r\n") + "\n\n\u200d"
    start = time.perf_counter()
    out = build_diff(big, noisy)
    elapsed = time.perf_counter() - start
    assert out.identical is True
    assert elapsed < 0.5, f"噪声快路径耗时 {elapsed:.3f}s，应 < 0.5s"


def test_large_real_diff_within_budget():
    """大文本真实差异必须能在可接受时间内完成。"""
    a = _big_text(2000)
    b = a.replace("第 1000 行", "第 1000 行（已修改）")
    start = time.perf_counter()
    out = build_diff(a, b)
    elapsed = time.perf_counter() - start
    assert out.identical is False
    assert out.unified_diff
    assert elapsed < 2.0, f"大文本 diff 耗时 {elapsed:.3f}s，应 < 2.0s"


def test_large_diff_uses_line_similarity():
    """超过阈值的长文本应自动降级为行级相似度，避免 O(n²) 字符级比较。"""
    a = _big_text(1200)
    b = a.replace("第 600 行", "第 600 行（改动）")
    out = build_diff(a, b)
    assert out.similarity_mode == "lines"
    assert 0.0 < out.similarity < 1.0


def test_short_text_uses_char_similarity():
    out = build_diff(BASE, REAL_DIFF_VARIANTS["word_changed"])
    assert out.similarity_mode == "chars"


def test_similarity_public_api_is_normalized():
    """公开 similarity() 对相同内容返回 1.0。"""
    assert similarity(BASE, BASE) == 1.0
    assert similarity("a" * 100, "a" * 100) == 1.0


# ------------------------------------------------------------ API 集成

def _write(registry, agent: str, path: str, content: str) -> None:
    registry.file_manager.write(agent, path, content, auto_backup=False, audit=False)


def test_api_diff_reports_identical_for_noise_only(client, registry):
    """接口层：仅格式噪声差异的文件应返回 identical=true 且无差异内容。"""
    path = "IDENTITY.md"
    _write(registry, "alpha", path, BASE)
    _write(registry, "beta", path, BASE.replace("\n", "\r\n") + "\n\n\u200d")

    res = client.get("/api/diff", params={"a": "alpha", "b": "beta", "file": path})
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["identical"] is True
    assert data["similarity"] == 1.0
    assert data["unified_diff"] == ""
    assert data["noise_kinds"]
    assert data["mode"] == MODE_IGNORE_WHITESPACE


def test_api_diff_strict_mode_reports_difference(client, registry):
    """接口层：strict 口径下同样数据应报出差异。"""
    path = "TOOLS.md"
    _write(registry, "alpha", path, BASE)
    _write(registry, "beta", path, BASE.replace("- 项目一", "- 项目一   "))

    loose = client.get("/api/diff", params={"a": "alpha", "b": "beta", "file": path}).json()["data"]
    assert loose["identical"] is True

    strict = client.get(
        "/api/diff", params={"a": "alpha", "b": "beta", "file": path, "mode": MODE_STRICT},
    ).json()["data"]
    assert strict["identical"] is False
    assert strict["mode"] == MODE_STRICT


def test_api_diff_invalid_mode_falls_back(client, registry):
    path = "IDENTITY.md"
    _write(registry, "alpha", path, BASE)
    _write(registry, "beta", path, BASE)
    data = client.get(
        "/api/diff", params={"a": "alpha", "b": "beta", "file": path, "mode": "bogus"},
    ).json()["data"]
    assert data["mode"] == MODE_IGNORE_WHITESPACE
    assert data["identical"] is True


def test_api_sync_plan_marks_identical_files(client, registry):
    """同步计划：内容一致的文件应带 identical 标记，便于前端提示无需同步。"""
    path = "USER.md"
    _write(registry, "alpha", path, BASE)
    _write(registry, "beta", path, BASE + "\n\n\u200d")

    res = client.post("/api/sync/plan", json={
        "src_agent": "alpha", "dst_agent": "beta", "files": [path],
    })
    assert res.status_code == 200
    item = res.json()["data"]["files"][0]
    assert item["identical"] is True
    assert item["similarity"] == 1.0
    assert item["html_diff"] == ""
