"""Module-level workers for the cross-process half of WI-23.

macOS defaults ``multiprocessing`` to *spawn*: the child re-imports the target's
module and looks the function up by qualified name. A closure, a lambda, or a
function defined inside a test body would fail to pickle, and the failure is the
quiet kind -- the parent sees two dead children and an unchanged file, which
looks exactly like "the lock worked". So the workers live here, at module level,
and every caller asserts on ``proc.exitcode`` so that a child which died on
import fails the test instead of passing it.

``tests/fixtures`` is on ``sys.path`` (see ``tests/conftest.py``), and spawn
ships the parent's ``sys.path`` to the child, so this module is importable there.
"""

from __future__ import annotations

from threading import BrokenBarrierError


def add_annotation_at_barrier(
    books_dir: str,
    book_id: str,
    quote: str,
    barrier,
    timeout_s: float,
) -> None:
    """Add one annotation, pausing at ``barrier`` between the load and the save.

    The pause is what widens the read-modify-write window to something a test can
    hit every time. It is deliberately placed by wrapping ``save_annotations`` in
    the child's own module namespace rather than by editing the product code.

    ``barrier.wait`` is given a timeout because a correct implementation makes the
    rendezvous *impossible*: the second writer is parked on the file lock and can
    never arrive. The timeout is the escape from that deadlock, not a window
    manufactured with wall clock -- when the lock is missing, both writers arrive
    at once and the timeout never elapses.
    """
    from reader3_app import notes_service
    from reader3_app.models.annotations import Annotation

    real_save = notes_service.save_annotations

    def save_at_barrier(bd, bid, anns):
        try:
            barrier.wait(timeout_s)
        except BrokenBarrierError:
            pass
        return real_save(bd, bid, anns)

    notes_service.save_annotations = save_at_barrier
    try:
        notes_service.add_annotation(
            books_dir,
            Annotation(book_id=book_id, chapter_index=0, quote=quote),
        )
    except OSError as e:
        # Report the errno by name and exit non-zero, instead of letting
        # multiprocessing print a traceback. An ENOENT traceback carries the
        # string "No such file or directory", which the red-receipt tool greps
        # for across the entire run as evidence that the *test runner* is
        # missing -- and would discard a perfectly real red. The parent still
        # sees exitcode 1 and still fails.
        print(f"child writer for {book_id!r} failed: {type(e).__name__} errno={e.errno}", flush=True)
        raise SystemExit(1) from None


# ---------------------------------------------------------------------------
# 017 WI-12（审计 #23、#24）：两个写者的编排搬进子进程，并且用**事件**而不是耗时
# 来确立争用。
#
# 为什么是「子进程里跑线程」而不是「两个子进程」：这两条用例问的是**一个服务进程里
# 的两个请求**会不会都写成功，判决点是 `_book_write_lock` 里那把 `threading.Lock`。
# 跨进程那一半已经由 `test_notes_concurrent_write.py` 用 flock 守着了，换成两个进程
# 等于把问题换掉。所以线程留着，整场编排挪进一个子进程——父进程 `join(timeout)` 之后
# `kill()`，死锁回归拿到的是一条红，不是一个挂住的 pytest。
#
# 为什么必须是事件：老写法让第一个写者停在 `Barrier(2)` 上等 2 秒超时，再凭「时间到了，
# 那第二个写者应该已经在等锁了吧」往下走。那是推断，不是观察——机器一慢，第二个写者可能
# 还没起步；而无论它到没到，用例都照常变绿。下面这把锁把「有人真的在等这把锁」记成一个
# 正面事件：非阻塞 `acquire` 失败那一刻，锁**确实**被别人持有，这是事实不是猜测。
# ---------------------------------------------------------------------------

#: 子进程内部一切等待的上限。只在真出事时付钱：正常路径上每个 `wait` 都是被事件叫醒的。
CHILD_WAIT_BOUND_S = 20.0


class ObservableBookLock:
    """`threading.Lock` 的壳，额外记下「有人开始等这把锁了」。

    `__enter__` 先做一次非阻塞 `acquire`：拿到了说明没人竞争，直接返回；**拿不到**说明
    此刻锁被别人持有，于是先把 `someone_is_waiting` 立起来、**再**去阻塞。顺序是全部——
    进去之后再记就永远记不上，那正是要观察的那一刻。

    `_book_write_lock` 用的是 `with thread_lock:`，所以只要 `setdefault` 返回的是这个
    对象，它就会走这里。产品代码一行没动。
    """

    def __init__(self) -> None:
        import threading

        self._lock = threading.Lock()
        self.someone_is_waiting = threading.Event()

    def __enter__(self):
        if not self._lock.acquire(False):
            self.someone_is_waiting.set()
            self._lock.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._lock.release()

    # 018 WI-2（ADR-0015 契约 4）：资源层的线程锁改成有界等待——产品代码对注册表里的锁对象
    # 调 `.acquire(False)` 轮询，不再走 `with`。下面三个方法是纯增量的镜像：失败的那一次
    # 非阻塞尝试同样立起 `someone_is_waiting`，然后按调用方原样的参数委托。`__enter__` /
    # `__exit__` 一字未动。
    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        if self._lock.acquire(False):
            return True
        self.someone_is_waiting.set()
        return self._lock.acquire(blocking, timeout)

    def release(self) -> None:
        self._lock.release()

    def locked(self) -> bool:
        return self._lock.locked()


def _install_observable_lock(notes_service, books_dir: str, book_id: str) -> ObservableBookLock:
    """把上面那把锁塞进 `_BOOK_THREAD_LOCKS`，抢在产品代码 `setdefault` 之前。

    键是 `os.path.abspath(_lock_path(...))`，与 `_book_write_lock` 逐字一致；对不上的话
    产品代码会自己建一把普通锁，而这里的观察就会**静悄悄**地永远观察不到东西——所以下面
    的调用方一律断言事件真的立起来过，而不是默认它会。
    """
    import os

    key = os.path.abspath(notes_service._lock_path(books_dir, book_id))
    lock = ObservableBookLock()
    with notes_service._LOCK_REGISTRY_GUARD:
        notes_service._BOOK_THREAD_LOCKS[key] = lock
    return lock


def _classify_in_child(notes_service, exc: BaseException) -> str:
    """与父进程 `_classify` 同一条规矩：按**名字**取冲突类。

    类还不存在时每一次失败都归成 ``error:…``，于是断言在「期望一个 conflict」上失败——
    那是一次关于行为的红，不是一个收集期的错误。
    """
    conflict_cls = getattr(notes_service, "NotesVersionConflict", None)
    if conflict_cls is not None and isinstance(exc, conflict_cls):
        return "conflict"
    return f"error:{type(exc).__name__}: {exc}"


def stage_two_writers(
    books_dir: str,
    book_id: str,
    note_id: str,
    texts,
    shared_version: str,
    mode: str,
    result_path: str,
) -> None:
    """在子进程里把两个写者并排放进同一个窗口，把结局与**证据**写成 JSON。

    两种编排，对应两条用例：

    ``"cas"`` —— 正向。两个写者握着同一个（当时合法的）版本并发进来。第一个进到
    `save_annotations` 的那个**不睡任何时长**，它等的是「有人真的在等这把书级锁」这个
    事件；等到了才往下写。比较若真在锁里，第二个写者此刻正卡在锁上、**还没比过版本**，
    于是它醒来之后读到的是新版本 → 冲突。比较若在锁外，第二个写者早就比完了，两个都成功。

    ``"precheck_outside_lock"`` —— 反向对照，把坏法真的演一遍。锁外预检用一个**开在预检
    点上的** `Barrier(2)` 会合：这个会合点在任何锁之外，因此**一定可达**，正常情况下一秒
    都不会超时。老写法把屏障开在 `save` 里（锁**内**），于是它在正确实现下根本不可达，只能
    靠超时往下走——那条对照因此证明不了「第二个写者已经过了锁外预检」。

    两种模式都把证据一并报回去：事件到底有没有立起来、会合有没有破。没有这一层，一个
    从头到尾没发生过争用的编排会安安静静地变绿。
    """
    import json
    import threading

    from reader3_app import notes_service

    lock = _install_observable_lock(notes_service, books_dir, book_id)
    real_save = notes_service.save_annotations

    evidence = {"mode": mode}
    outcomes = ["not-run", "not-run"]

    if mode == "cas":
        first_in_save = threading.Lock()
        observed = threading.Event()

        def save_waiting_for_contention(bd, bid, anns):
            # 只有**第一个**到这里的写者等。坏实现下两个都会到，第二个不能再等——
            # 它要等的那个人就是它自己。
            if first_in_save.acquire(False):
                if lock.someone_is_waiting.wait(CHILD_WAIT_BOUND_S):
                    observed.set()
            return real_save(bd, bid, anns)

        notes_service.save_annotations = save_waiting_for_contention

        def launch(index: int):
            return notes_service.update_annotation_and_version(
                books_dir, book_id, note_id, texts[index], if_match=shared_version
            )

    elif mode == "precheck_outside_lock":
        rendezvous = threading.Barrier(2)
        broke = threading.Event()
        #: 锁外那次检查比的是什么不重要，重要的是它发生在锁**外**。
        snapshot = json.dumps(_records(books_dir, book_id), sort_keys=True, ensure_ascii=False)

        def launch(index: int):
            current = json.dumps(_records(books_dir, book_id), sort_keys=True, ensure_ascii=False)
            assert current == snapshot, "锁外预检自己就没通过，这一轮编排不成立"
            # 两个写者都过了锁外预检**之后**才允许任何人往下写。会合点在锁外，可达。
            try:
                rendezvous.wait(CHILD_WAIT_BOUND_S)
            except threading.BrokenBarrierError:
                broke.set()
            return notes_service.update_annotation(books_dir, book_id, note_id, texts[index])

    else:  # pragma: no cover - 只会在调用方打错字时走到
        raise SystemExit(f"未知的编排模式：{mode!r}")

    def run(index: int) -> None:
        try:
            launch(index)
            outcomes[index] = "ok"
        except BaseException as exc:  # noqa: BLE001 - 任何失败都要归类，不能只认预期的那种
            outcomes[index] = _classify_in_child(notes_service, exc)

    threads = [
        threading.Thread(target=run, args=(i,), name=f"writer-{i}", daemon=True) for i in range(2)
    ]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join(CHILD_WAIT_BOUND_S)
        evidence["stuck_writers"] = [t.name for t in threads if t.is_alive()]
    finally:
        # 收尾一律在 finally：上面任何一句抛了，也不能把证据连同结论一起丢掉。
        notes_service.save_annotations = real_save
        if mode == "cas":
            evidence["second_writer_blocked_on_the_lock"] = observed.is_set()
            # 放行任何还卡在事件上的写者，免得子进程靠父进程 kill 才退得掉。
            lock.someone_is_waiting.set()
        else:
            evidence["rendezvous_broke"] = broke.is_set()
            rendezvous.abort()

        with open(result_path, "w", encoding="utf-8") as fh:
            json.dump({"outcomes": outcomes, "evidence": evidence}, fh, ensure_ascii=False)


def _records(books_dir: str, book_id: str):
    """盘上的标注，按**未来一次读取**会看到的样子读回来（不经任何缓存）。"""
    import json
    import os

    path = os.path.join(books_dir, book_id, "notes.json")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return list(json.load(fh).get("annotations") or [])
