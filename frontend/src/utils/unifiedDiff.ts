/**
 * unified diff 解析与「按块重建」工具。
 *
 * 后端 `difflib.unified_diff(..., keepends=True)` 产出的标准 unified diff，
 * 这里把它拆成一个个 hunk，前端据此让用户在「应用预设 / AI 整理」的差异预览里
 * 逐块勾选接受/拒绝，并按选中的块把「原内容」重建成「要写入的内容」。
 *
 * 注意：不信任 hunk 头部声明的行数，old 侧行数一律由正文（' ' / '-' 行）统计得出，
 * 以免头部与正文不一致时错位。
 */

export interface DiffHunk {
  /** `@@ -a,b +c,d @@` 头（仅用于展示） */
  header: string;
  /** 旧文件起始行号（1-based） */
  oldStart: number;
  /** 该 hunk 覆盖的旧行数（由正文统计） */
  oldCount: number;
  /** 正文行，保留 ' ' / '+' / '-' 前缀 */
  lines: string[];
}

export interface ParsedDiff {
  /** hunk 之前的文件头（`---` / `+++` 等） */
  header: string[];
  hunks: DiffHunk[];
}

const HUNK_RE = /^@@+ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@/;

/** 解析 unified diff；diff 为空或格式异常时返回空 hunk 列表（调用方按「无改动」处理） */
export function parseUnifiedDiff(diff: string): ParsedDiff {
  const header: string[] = [];
  const hunks: DiffHunk[] = [];
  let current: DiffHunk | null = null;

  for (const raw of diff.split('\n')) {
    const line = raw.endsWith('\r') ? raw.slice(0, -1) : raw;
    if (line.startsWith('@@')) {
      const m = HUNK_RE.exec(line);
      current = { header: line, oldStart: m ? Number(m[1]) : 1, oldCount: 0, lines: [] };
      hunks.push(current);
      continue;
    }
    if (current) {
      if (line.startsWith(' ') || line.startsWith('+') || line.startsWith('-')) {
        current.lines.push(line);
      } else if (line.startsWith('\\')) {
        // "\ No newline at end of file"：忽略
      } else {
        // 非法/多余行（含 diff 末尾的换行空串）：视为该 hunk 结束
        current = null;
      }
    } else if (line !== '') {
      header.push(line);
    }
  }

  for (const h of hunks) h.oldCount = h.lines.filter((l) => l[0] !== '+').length;
  return { header, hunks };
}

/**
 * 按 `accepted` 选择结果，把 `base` 重建成新内容：
 * 接受的 hunk 采用新侧行（' ' / '+'），拒绝的 hunk 保留旧侧行（' ' / '-'）。
 * hunks 必须按 oldStart 升序（difflib 保证）。
 */
export function applyHunks(base: string, hunks: DiffHunk[], accepted: boolean[]): string {
  const baseLines = base.split('\n');
  const out: string[] = [];
  let cursor = 0;

  hunks.forEach((h, i) => {
    const start = Math.max(0, h.oldStart - 1);
    while (cursor < start && cursor < baseLines.length) {
      out.push(baseLines[cursor]);
      cursor += 1;
    }
    if (accepted[i]) {
      for (const l of h.lines) if (l[0] === ' ' || l[0] === '+') out.push(l.slice(1));
    } else {
      for (const l of h.lines) if (l[0] === ' ' || l[0] === '-') out.push(l.slice(1));
    }
    cursor = start + h.oldCount;
  });

  while (cursor < baseLines.length) {
    out.push(baseLines[cursor]);
    cursor += 1;
  }
  return out.join('\n');
}

/**
 * 解析是否「可靠」：全部接受时必须能精确重建出目标内容。
 *
 * 用途：文件末尾无换行等情况下，`difflib` 产出的 diff 会出现行粘连（`-old+new` 连成一行），
 * 此时按块重建会丢行 / 错位。调用方应先做此校验，不可靠时退回「只展示整段 diff、只允许整体应用」。
 */
export function canRebuild(base: string, hunks: DiffHunk[], target: string): boolean {
  if (hunks.length === 0) return false;
  return applyHunks(base, hunks, hunks.map(() => true)) === target;
}
