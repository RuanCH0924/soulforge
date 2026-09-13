/**
 * 统一的差异视图。
 *
 * 后端已在归一化后判定「有效内容是否一致」：
 * - identical=true  → 不再渲染空的差异框，而是给出明确结论（避免用户误以为工具坏了），
 *   并在仅存在格式噪声时列出被忽略的噪声类型，保证判定过程可见、不被静默掩盖；
 * - identical=false → 渲染高亮差异。
 */
interface DiffViewProps {
  htmlDiff: string;
  identical: boolean;
  noiseKinds?: string[];
  /** 一致时的结论文案 */
  identicalText?: string;
}

/** 噪声类型 → 可读名称 */
const NOISE_LABELS: Record<string, string> = {
  bom: 'UTF-8 BOM',
  line_ending: '换行符风格（CRLF/LF）',
  invisible_char: '零宽 / 不可见字符',
  space_like_char: '全角空格 / 不换行空格',
  trailing_whitespace: '行尾空白',
  multiple_spaces: '连续空白 / Tab 缩进',
  blank_lines: '多余空行',
  edge_blank_lines: '文首 / 文末空行',
};

export function noiseLabel(kinds: string[]): string {
  return kinds.map((k) => NOISE_LABELS[k] ?? k).join('、');
}

export function DiffView({
  htmlDiff,
  identical,
  noiseKinds = [],
  identicalText = '内容完全一致，无差异',
}: DiffViewProps) {
  if (identical) {
    return (
      <div className="diff-identical">
        <span className="diff-identical-badge">✓ {identicalText}</span>
        {noiseKinds.length > 0 && (
          <span className="diff-noise-note">
            原始文件仅存在格式噪声差异（已忽略）：{noiseLabel(noiseKinds)}
          </span>
        )}
      </div>
    );
  }
  if (!htmlDiff) {
    return <div className="diff-identical"><span className="hint">无差异内容</span></div>;
  }
  return <div className="diff-body" dangerouslySetInnerHTML={{ __html: htmlDiff }} />;
}
