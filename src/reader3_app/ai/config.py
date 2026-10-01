from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from typing import Any, Dict, Iterator, Optional, Union


DEFAULT_SETTINGS_PATH = os.environ.get("READER3_AI_SETTINGS", os.path.join("config", "ai_settings.json"))
EXAMPLE_SETTINGS_PATH = os.path.join("config", "ai_settings.example.json")


class AiSettingsError(RuntimeError):
    """Raised when ai_settings.json exists but cannot be understood."""


@dataclass(frozen=True)
class ProviderSettings:
    name: str
    enabled: bool
    model_name: str
    base_url: str
    api_key_configured: bool
    timeout_s: int
    max_retries: int


def default_settings_dict() -> Dict[str, Any]:
    return {
        "default_provider": "anthropic",
        "preferences": {
            "show_timestamps": True,
            "auto_suggest_questions": True,
            "streaming_enabled": True,
            "max_conversation_length": 500,
            # On-disk chat storage:
            # - per_book: books/{book_folder}/ai_conversations/{conversation_id}.json
            # - project_root: {project_root}/conversations/{book_uuid}/{conversation_id}.json
            # - both: write to both locations
            "conversation_disk_storage": "per_book",
            "conversation_project_root_dir": "conversations",
            "theme": "auto",
        },
        "providers": {
            "anthropic": {
                "enabled": True,
                "model_name": "claude-sonnet-4-20250514",
                "api_key": "",
                "timeout_s": 30,
                "max_retries": 3,
            },
            "openai": {
                "enabled": False,
                "base_url": "https://api.openai.com/v1",
                "model_name": "gpt-4o-mini",
                "api_key": "",
                "timeout_s": 30,
                "max_retries": 3,
            },
            "gemini": {
                "enabled": False,
                "model_name": "gemini-1.5-pro",
                "api_key": "",
                "timeout_s": 30,
                "max_retries": 3,
            },
            "ollama": {
                "enabled": False,
                "base_url": "http://localhost:11434",
                "model_name": "qwen3:8b",
                "timeout_s": 60,
                "max_retries": 0,
            },
            "openrouter": {
                "enabled": False,
                "base_url": "https://openrouter.ai/api/v1",
                "model_name": "openai/gpt-4o-mini",
                "api_key": "",
                "timeout_s": 30,
                "max_retries": 3,
            },
        },
    }


def _merge_defaults(settings: Dict[str, Any]) -> Dict[str, Any]:
    merged = default_settings_dict()
    merged.update({k: v for k, v in (settings or {}).items() if k not in ("providers", "preferences")})

    # preferences 和 providers 一样要两级合并。整块 update 的话，磁盘上一份
    # {"preferences": {"theme": "dark"}} 会让 conversation_disk_storage 等键当场
    # 消失——不是回退到默认值，是从这份 settings 里没了，于是「读—改—写」的下一次
    # 保存把用户设过的落盘模式永久抹掉。默认打底，文件里的值优先。
    incoming_prefs = (settings or {}).get("preferences")
    if isinstance(incoming_prefs, dict):
        prefs: Dict[str, Any] = dict(merged.get("preferences") or {})
        prefs.update(incoming_prefs)
        merged["preferences"] = prefs
    elif "preferences" in (settings or {}):
        # 不是 dict 就照原样带上，不在这里新增校验：本函数只管不丢。
        merged["preferences"] = incoming_prefs

    providers: Dict[str, Any] = dict(merged.get("providers") or {})
    for name, provider in (settings.get("providers") or {}).items():
        base = dict(providers.get(name) or {})
        base.update(provider or {})
        providers[name] = base
    merged["providers"] = providers
    return merged


def _read_settings_file(path: str) -> Optional[Dict[str, Any]]:
    """读 ai_settings.json：不存在返回 None，**读不懂就抛**。

    这两件事以前都返回默认值，于是调用方无法分辨「用户还没配过 key」和
    「用户的 key 我读不出来」，把后者也当成前者去覆盖——前端显示「未配置」，
    用户重填一个 provider 保存，其余 provider 的 API key 全没了且不报错。同
    ``ensure_book_uuid`` 的先例：读不懂的用户数据不许当成「没有」。500 是可恢复
    的，删掉用户的密钥不是。OSError（权限、坏盘）同理。
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as e:
        raise AiSettingsError(
            f"{path} is not valid JSON ({e}); refusing to treat it as an empty "
            "configuration -- fix or delete the file"
        ) from e
    except OSError as e:
        raise AiSettingsError(
            f"{path} exists but could not be read ({e}); refusing to treat it as an "
            "empty configuration -- fix or delete the file"
        ) from e
    if not isinstance(raw, dict):
        raise AiSettingsError(
            f"{path} is not a JSON object (got {type(raw).__name__}); refusing to treat "
            "it as an empty configuration -- fix or delete the file"
        )
    return raw


def load_ai_settings(path: str = DEFAULT_SETTINGS_PATH) -> Dict[str, Any]:
    raw = _read_settings_file(path)
    if raw is None:
        # 文件不存在是合法的首次运行状态，不是损坏。把它一并收进抛错，
        # 就是拿一个假 bug 换一个真 bug。
        return default_settings_dict()
    return _merge_defaults(raw)


def save_ai_settings(settings: Dict[str, Any], path: str = DEFAULT_SETTINGS_PATH) -> None:
    # 纵深防御：目标已存在但读不出来时拒写。load_ai_settings() 已经拦了
    # 「读—改—写」那条路，但不经过 load 直接构造 settings 的调用方也不该有
    # 能力把一份我们读不懂的凭据文件抹掉。
    _read_settings_file(path)

    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)

    # 原子写：tmp + os.replace，同 ensure_book_uuid / conversations。
    #
    # 但 tmp 名字用 tempfile.mkstemp(dir=目标同目录) 而**不是** books.py 那种固定的
    # f"{path}.tmp"。这次偏离仓库既有写法是故意的，不是不一致：这个文件装的是
    # 凭据，两个并发写手（两个标签页同时保存设置）抢同一个固定 tmp 名本身就是一条
    # 凭据损坏路径，而 mkstemp 只多一行。顺带的好处：mkstemp 建文件时就是 0600。
    fd, tmp_path = tempfile.mkstemp(prefix=".ai_settings.", suffix=".tmp", dir=directory)
    try:
        try:
            # fdopen 接管 fd，with 退出时关闭它；只有 fdopen 自己抛了，fd 才还在我们手上。
            handle = os.fdopen(fd, "w", encoding="utf-8")
        except BaseException:
            os.close(fd)
            raise
        with handle as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except BaseException:
        # 写到一半失败：旧文件一字未动，顺手把半截 tmp 清掉，不在凭据旁边留残片。
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# 设置文件的 revision（ETag）与全局设置锁（018 WI-3，还 009 债 #51）。
#
# import 放在这里而不是文件顶部是故意的：test_server_patch_seam_ownership.py 的 A15
# 把 load_ai_settings / save_ai_settings 的 def 行钉在 145 / 154，顶部每多一行都会
# 把这两个坐标推走。
# ---------------------------------------------------------------------------
import fcntl  # noqa: E402
import hashlib  # noqa: E402
import hmac  # noqa: E402
import secrets  # noqa: E402
from contextlib import contextmanager  # noqa: E402

#: 每个进程一把随机钥匙，只在内存里。为什么不是裸 sha256：/api/* 没有鉴权
#: （ADR-0012），而文件里除 API key 以外的每个字节都能从 GET + export 重建
#: （json.dump 是确定的），裸摘要就成了离线验证「猜到/泄露的 key 对不对」的神谕。
#: 代价：服务重启后 ETag 全变，客户端吃一次 409 重新加载——往安全的方向失败。
_REVISION_KEY = secrets.token_bytes(32)

#: 与设置文件同目录；0600 创建，永不 unlink（unlink 一个可能有人在等的锁文件，
#: 会让后来者锁住另一个 inode，互斥就破了）。
SETTINGS_LOCK_NAME = ".ai_settings.lock"


def settings_revision(raw: Optional[bytes]) -> str:
    """``HMAC-SHA256(K, b"file:" + raw)``，文件不存在时 ``HMAC-SHA256(K, b"absent")``。

    ``file:`` / ``absent`` 两个前缀把「空文件」和「没有文件」分开：任何 raw 都得不到
    ``b"absent"`` 这条消息。返回 64 位小写 hex。
    """
    message = b"absent" if raw is None else b"file:" + raw
    return hmac.new(_REVISION_KEY, message, hashlib.sha256).hexdigest()


_OWS = " \t"


def _is_etagc(ch: str) -> bool:
    # RFC 7232 etagc = %x21 / %x23-7E / obs-text(%x80-FF)
    code = ord(ch)
    return code == 0x21 or 0x23 <= code <= 0x7E or 0x80 <= code <= 0xFF


def if_match_satisfied(header: str, current: str) -> bool:
    """RFC 7232 If-Match，强比较。

    * ``*`` 恒满足（GET 总能给出一个表示，文件不存在时是默认值）。
    * 逗号分隔的列表里任意一个**强**标签的值等于 ``current`` 即满足；``W/"…"`` 永不满足。
    * 畸形输入抛 ``ValueError``，不返回布尔：空串、未加引号、未闭合、``*`` 混在列表里、
      缺逗号，以及**任何空元素**（开头逗号、结尾逗号、``,,``、``, ,``——裁定 3）。
      路由把它映射成 400。

    这里是手写扫描而不是 ``split(",")``：逗号本身是合法的 etagc，``"a,b"`` 是一个标签。
    """
    text = header.strip(_OWS)
    if not text:
        raise ValueError("empty If-Match header")
    if text == "*":
        return True

    satisfied = False
    i, n = 0, len(text)
    while True:
        while i < n and text[i] in _OWS:
            i += 1
        weak = text.startswith("W/", i)
        if weak:
            i += 2
        if i >= n or text[i] != '"':
            raise ValueError("malformed If-Match header: expected a quoted entity-tag")
        start = i + 1
        j = start
        while j < n and text[j] != '"':
            if not _is_etagc(text[j]):
                raise ValueError("malformed If-Match header: invalid entity-tag character")
            j += 1
        if j >= n:
            raise ValueError("malformed If-Match header: unterminated entity-tag")
        if not weak and text[start:j] == current:
            satisfied = True
        i = j + 1
        while i < n and text[i] in _OWS:
            i += 1
        if i >= n:
            return satisfied
        if text[i] != ",":
            raise ValueError("malformed If-Match header: entity-tags must be comma-separated")
        i += 1  # 逗号之后必须还有一个元素；空元素在下一轮的「expected a quoted entity-tag」里报错


class AiSettingsTransaction:
    """``ai_settings_transaction`` 交出的句柄；只在 with 块里有效（锁在那里持有）。"""

    def __init__(self, path: str) -> None:
        self.path = path

    def read_raw(self) -> Optional[bytes]:
        """磁盘上此刻的原始字节；文件不存在返回 None。读不出来同 load：抛 AiSettingsError 点名文件。"""
        try:
            with open(self.path, "rb") as f:
                return f.read()
        except FileNotFoundError:
            return None
        except OSError as e:
            raise AiSettingsError(
                f"{self.path} exists but could not be read ({e}); refusing to treat it as an "
                "empty configuration -- fix or delete the file"
            ) from e

    def revision(self) -> str:
        """每次调用都重新读盘——不缓存进入时的值，保存之后立刻反映新字节。"""
        return settings_revision(self.read_raw())


@contextmanager
def ai_settings_transaction(
    path: Optional[Union[str, "os.PathLike[str]"]] = None,
    *,
    lock_optional: bool = False,
) -> Iterator[AiSettingsTransaction]:
    """在 ``dirname(path)/.ai_settings.lock`` 上持 ``flock(LOCK_EX)``，交出句柄。

    * ``path`` 在**调用时**解析（缺省读模块全局 ``DEFAULT_SETTINGS_PATH``），不像
      load/save 那样在 import 时冻进默认参数。
    * 先 ``os.makedirs(dirname, exist_ok=True)``，与 save_ai_settings 建目录的方式一致，
      谁先跑都一样。锁文件 ``O_CREAT|O_RDWR`` 0600，永不 unlink。
    * 每次进入都自己 ``os.open``：flock 属于打开文件描述，同进程两个线程各开一次才互斥；
      共享一个模块级 fd 就不互斥了。
    * 阻塞等待；任何退出路径（含异常）都解锁并关闭 fd，异常原样传出。
    * 不碰设置文件本身，也不改它的权限。
    * 建目录或开锁文件失败（config/ 不可写）→ ``AiSettingsError`` 点名锁路径，路由映射成
      带名字的 500。``lock_optional=True``（只给两条 GET）时改为**不持锁**交出句柄：
      写手一律 tmp + os.replace，不加锁读到的也是某个完整版本，ETag 照样按读到的字节算。
    """
    target = os.fspath(path) if path is not None else DEFAULT_SETTINGS_PATH
    directory = os.path.dirname(target) or "."
    lock_path = os.path.join(directory, SETTINGS_LOCK_NAME)
    fd: Optional[int] = None
    try:
        os.makedirs(directory, exist_ok=True)
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC, 0o600)
    except OSError as e:
        if not lock_optional:
            raise AiSettingsError(
                f"could not create the settings lock {lock_path} ({e}); the settings directory "
                "must be writable to save settings"
            ) from e
    if fd is None:
        yield AiSettingsTransaction(target)
        return
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            yield AiSettingsTransaction(target)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def get_provider_settings(
    provider_name: Optional[str],
    *,
    settings: Optional[Dict[str, Any]] = None,
) -> ProviderSettings:
    settings = settings or load_ai_settings()
    provider_name = (provider_name or settings.get("default_provider") or "anthropic").strip()
    providers: Dict[str, Any] = settings.get("providers") or {}
    provider: Dict[str, Any] = providers.get(provider_name) or {}

    enabled = bool(provider.get("enabled", True))
    model_name = str(provider.get("model_name") or "").strip()
    timeout_s_raw = provider.get("timeout_s")
    if timeout_s_raw is None:
        timeout_s_raw = provider.get("timeout")
    timeout_s = int(timeout_s_raw or (60 if provider_name == "ollama" else 30))
    max_retries = int(provider.get("max_retries") or 0)
    base_url = str(provider.get("base_url") or "").strip()
    api_key = provider.get("api_key")

    if not model_name:
        raise ValueError(f"Provider {provider_name} missing model_name")

    api_key_configured = bool(str(api_key or "").strip())
    return ProviderSettings(
        name=provider_name,
        enabled=enabled,
        model_name=model_name,
        base_url=base_url,
        api_key_configured=api_key_configured,
        timeout_s=max(1, min(timeout_s, 300)),
        max_retries=max(0, min(max_retries, 10)),
    )


def get_provider_api_key(
    provider_name: str,
    *,
    settings: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    settings = settings or load_ai_settings()
    providers: Dict[str, Any] = settings.get("providers") or {}
    provider: Dict[str, Any] = providers.get(provider_name) or {}
    api_key = str(provider.get("api_key") or "").strip()
    return api_key or None


def get_provider_base_url(
    provider_name: str,
    *,
    settings: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    settings = settings or load_ai_settings()
    providers: Dict[str, Any] = settings.get("providers") or {}
    provider: Dict[str, Any] = providers.get(provider_name) or {}
    base_url = str(provider.get("base_url") or "").strip()
    return base_url or None
