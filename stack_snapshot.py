"""A library that automatically captures the complete stack frames \
including local and global variables when any exceptions occur.
一个在发生异常时，自动捕获异常发生时的完整栈帧，包括局部、全局变量的库。\
"""
import sys,os,threading,traceback,weakref
from pprint import pprint
from collections import deque
try:
    from pyobject import get_type_flag,set_type_flag
except ImportError:
    if "setup.py" not in sys.argv[0].lower():raise

__version__ = "1.0.2"
Py_TPFLAGS_HEAPTYPE = 1 << 9 # 来自object.h
Py_TPFLAGS_IMMUTABLETYPE = 1 << 8
IGNORED = (BaseException,) # TODO: 目前修改BaseException.__new__会导致Cannot recover from the recursive normalization of an exception

# 核心部分
_is_taking_snapshot=threading.local()
_is_taking_snapshot.value=False
def stack_snapshot(start=0):
    # 获取并返回快照
    if _is_taking_snapshot.value or not is_snapshot_enabled():
        return None
    _is_taking_snapshot.value = True # 避免捕获堆栈本身发生的错误，导致无限递归
    result=[]
    frame=sys._getframe(start)
    while frame is not None:
        result.append(frame)
        frame = frame.f_back
    _is_taking_snapshot.value = False
    return result

_hacked_excs=weakref.WeakSet()
def hack_exc(exc):
    # 修改异常类exc，使其初始化时自动获取栈帧快照

    # 避免重复修改
    if exc in _hacked_excs:
        return
    _hacked_excs.add(exc)

    flag = get_type_flag(exc)
    pre_flag = flag
    flag |= Py_TPFLAGS_HEAPTYPE
    flag &= ~Py_TPFLAGS_IMMUTABLETYPE # 去除Py_TPFLAGS_IMMUTABLETYPE
    set_type_flag(exc,flag) # 临时修改对象底层的flag（由于原本内置对象的属性，如ValueError.__new__是不可修改的）

    def __new__(cls,*args,**kw):
        new_func = BaseException.__new__ # 底层的__new__方法
        result = new_func(cls,*args,**kw)
        if not getattr(result,"stack_snapshot",None): # 避免重复捕获
            # 捕获当前堆栈
            result.stack_snapshot = stack_snapshot(start=2) # start=2:跳过本函数和__new__的两层
        return result

    exc.__new__ = __new__ # 修改异常类型的__new__
    pre_flag &= ~Py_TPFLAGS_IMMUTABLETYPE
    set_type_flag(exc,pre_flag) # 恢复原先的flag

def hack_all_exc(ignored=IGNORED):
    # 修改所有已定义的异常类
    que = deque()
    que.append(BaseException)
    while que:
        exc=que.popleft()
        for sub_exc in exc.__subclasses__():
            que.append(sub_exc)
        if exc not in ignored:
            hack_exc(exc)

# 堆栈输出部分
def trace_stack(err,file=None):
    # 输出异常的堆栈信息
    if file is None:
        file = sys.stderr

    if not getattr(err,"stack_snapshot",None):
        print("No stackframe information.\n", file = file)
        return
    for frame in err.stack_snapshot:
        print(f"""Local variables of {frame.f_code.co_name} \
({os.path.split(frame.f_code.co_filename)[-1]}):""", file = file)
        pprint(frame.f_locals, stream = file)
        if not frame.f_back or frame.f_back.f_globals is not frame.f_globals:
            print(f"Global variables of {frame.f_code.co_name}:", file = file)
            pprint(frame.f_globals, stream = file)
        print(file = file)
def trace_error(file=None):
    # 同时输出异常信息和堆栈
    if file is None:
        file = sys.stderr

    print("\nError:", file=file)
    traceback.print_exc(file=file)
    print(file = file)
    err = sys.exc_info()[1]
    if err is not None:
        trace_stack(err, file=file)

# 替换sys.excepthook部分
_pre_excepthook = None
def _exceptionhook(exctype, value, tb):
    print(f"\n{'-'*20} Error: {'-'*20}", file = sys.stderr)
    traceback.print_exception(exctype, value=value, tb=tb)
    print(file = sys.stderr)
    trace_stack(value, file = sys.stderr)
    print(f"{'-'*48}\n", file = sys.stderr)

def hook_sys_exception():
    global _pre_excepthook
    if _pre_excepthook is not None:
        return # 已经修改过
    _pre_excepthook=sys.excepthook
    sys.excepthook=_exceptionhook

def reset_sys_excepthook():
    global _pre_excepthook
    if _pre_excepthook is None:
        return
    sys.excepthook=_pre_excepthook
    _pre_excepthook=None

# 接口部分
_init=False
_enable_take_snapshot_lock=threading.Lock()
_enable_take_snapshot=True
def enable_snapshot():
    if not _init:
        raise ValueError("Must call init() before enabling taking snapshots")
    global _enable_take_snapshot
    with _enable_take_snapshot_lock:
        _enable_take_snapshot=True
def disable_snapshot():
    global _enable_take_snapshot
    with _enable_take_snapshot_lock:
        _enable_take_snapshot=False
def is_snapshot_enabled():
    with _enable_take_snapshot_lock:
        return _enable_take_snapshot

def init(ignored=IGNORED):
    # 调用init后，默认直接开启堆栈快照捕获
    global _init
    _init = True
    hack_all_exc(ignored)
    hook_sys_exception()


def test():
    def inner():
        raise ValueError

    init()
    try:
        inner()
    except ValueError:
        trace_error()

if __name__=="__main__":test()
