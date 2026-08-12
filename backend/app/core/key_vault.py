"""KeyVault：LLM API key 的 Fernet 对称加密存储（M12 · 安全护栏）。

密钥来源（优先级）：
1. 环境变量 `SOULFORGE_SECRET`
2. `.soulforge/secrets/key` 文件
3. 首次启动生成并写入 `.soulforge/secrets/key`（chmod 600）

约束（docs/DATA-MODEL.md 2.6）：数据库只存密文，UI 只显示掩码，明文永不落盘/git。
"""
from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path

from cryptography.fernet import Fernet


class KeyVault:
    def __init__(self, data_dir: Path):
        self._fernet = Fernet(self._load_or_create_key(data_dir))

    @staticmethod
    def _normalize(secret: str) -> bytes:
        """把任意字符串转成合法 Fernet key（32 字节 urlsafe base64）。"""
        try:
            Fernet(secret.encode())
            return secret.encode()
        except Exception:
            digest = hashlib.sha256(secret.encode()).digest()
            return base64.urlsafe_b64encode(digest)

    def _load_or_create_key(self, data_dir: Path) -> bytes:
        env = os.environ.get("SOULFORGE_SECRET")
        if env:
            return self._normalize(env)

        secrets_dir = data_dir / "secrets"
        key_file = secrets_dir / "key"
        if key_file.exists():
            return self._normalize(key_file.read_text(encoding="utf-8").strip())

        secrets_dir.mkdir(parents=True, exist_ok=True)
        key = Fernet.generate_key()
        key_file.write_bytes(key)
        try:  # 权限 600（Windows 上 chmod 语义受限，尽力而为）
            os.chmod(key_file, 0o600)
        except OSError:
            pass
        return key

    def encrypt(self, plaintext: str) -> str:
        """加密 API key，返回密文（可安全存 DB）。"""
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """解密 API key，仅供调用 LLM 时内存使用。"""
        return self._fernet.decrypt(ciphertext.encode()).decode()
