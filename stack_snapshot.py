"""A library that automatically captures the complete stack frames \
including local and global variables when any exceptions occur.
一个在发生异常时，自动捕获异常发生时的完整栈帧，包括局部、全局变量的库。\
"""
import sys,os,threading,traceback,weakref,atexit
from collections import deque
from types import FunctionType,ModuleType,BuiltinFunctionType
try:
    from pyobject import get_type_flag,set_type_flag,shortrepr
except ImportError:
    if "setup.py" not in sys.argv[0].lower():raise # 仅在setup.py导入本模块时，忽略错误
try:import pydetour
except ImportError:pydetour = None

__version__ = "1.0.4.3"
__all__ = [
    "hack_exc","hack_all_exc","trace_stack","trace_error",
    "hook_sys_exception","reset_sys_excepthook","enable_snapshot",
    "disable_snapshot","is_snapshot_enabled","init"
]
IGNORED_NAMES = ["__new__","__call__","stack_snapshot","_hooker"]
Py_TPFLAGS_HEAPTYPE = 1 << 9 # 来自object.h
Py_TPFLAGS_IMMUTABLETYPE = 1 << 8
IGNORED = (BaseException,) if pydetour is None else () # TODO: 非pydetour模式下，修改BaseException.__new__会导致Cannot recover from the recursive normalization of an exception
GLOBALVAR_IGNORED_TYPES = (FunctionType,ModuleType,BuiltinFunctionType,type)
GLOBALVAR_WHITELIST_NAMES = ["__name__","__file__"]
MAX_VARIABLE_LEN = 20
MAXLENGTH = 150

# -- 核心部分 --
_is_taking_snapshot=threading.local()
_is_taking_snapshot.value=False
def stack_snapshot(start=0):
    # 获取并返回快照
    if _is_taking_snapshot.value or not is_snapshot_enabled():
        return None
    _is_taking_snapshot.value = True # 避免捕获堆栈本身发生的错误，导致无限递归
    try:
        frame=sys._getframe(start)
    except ValueError:
        return []

    result=[]; skip = True
    while frame is not None:
        if frame.f_code.co_name not in IGNORED_NAMES:
            skip = False
        if not skip:result.append(frame)
        frame = frame.f_back
    _is_taking_snapshot.value = False
    return result

_pydetour_unhooks=[]
_unhook_at_finalizing_enabled=False
def _unhook_cleanup():
    for unhook in _pydetour_unhooks:
        unhook()
    _pydetour_unhooks.clear()
def enable_unhook_at_finalizing():
    global _unhook_at_finalizing_enabled
    if _unhook_at_finalizing_enabled:return
    atexit.register(_unhook_cleanup)
    _unhook_at_finalizing_enabled = True

_hacked_excs=weakref.WeakSet()
def hack_exc(exc):
    # 修改异常类exc，使其初始化时自动获取栈帧快照，支持pydetour和非pydetour两种模式

    if exc in _hacked_excs:return # 避免重复修改
    _hacked_excs.add(exc)

    flag = get_type_flag(exc)
    pre_flag = flag
    flag |= Py_TPFLAGS_HEAPTYPE
    flag &= ~Py_TPFLAGS_IMMUTABLETYPE # 去除Py_TPFLAGS_IMMUTABLETYPE
    set_type_flag(exc,flag) # 临时修改对象底层的flag（由于原本内置对象的属性，如ValueError.__new__是不可修改的）

    def __call__(*args,**kw):
        return __new__(exc,*args,**kw)
    def __new__(cls,*args,**kw):
        # 底层的__new__方法
        new_func = cls.__new__ if pydetour else BaseException.__new__
        result = new_func(cls,*args,**kw)
        if not getattr(result,"stack_snapshot",None) and not sys.is_finalizing(): # 避免重复捕获
            # 捕获当前堆栈
            # start=2:跳过本函数和__new__的两层 (无pydetour时)
            result.stack_snapshot = stack_snapshot(0)#start=2 if pydetour is None else 4)
        return result

    if pydetour is not None:
        unhook = pydetour.hook(exc,lambda hookee:__call__)
        _pydetour_unhooks.append(unhook)
        enable_unhook_at_finalizing()
    else:
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

# -- 堆栈输出部分 --
def _check_ignore(name, value):
    if name.startswith("__") and name.endswith("__") and \
        name not in GLOBALVAR_WHITELIST_NAMES:
        return True
    if isinstance(value, GLOBALVAR_IGNORED_TYPES):
        return True
    return False
def _pprint_dict(dct, file=None, do_ignore=False, maxlen=MAXLENGTH):
    if file is None:file = sys.stdout
    if not dct:
        print("<No variables>", file = file)
        return
    items = [item for item in dct
             if not (do_ignore and _check_ignore(item, dct[item]))]
    items.sort()
    length = min(len(max(items, key = len)), MAX_VARIABLE_LEN)
    for item in items:
        print(f"{item: <{length}} = {shortrepr(dct[item], maxlen)}", file = file)

def trace_stack(err,file=None,brief_global_var=True,maxlength=MAXLENGTH):
    # 输出异常的堆栈信息
    if file is None:file = sys.stderr

    if not getattr(err,"stack_snapshot", None):
        tb = err.__traceback__; pre=tb
        while tb:
            pre=tb; tb=tb.tb_next
        snapshot = []
        frame = pre.tb_frame
        while frame:
            snapshot.append(frame)
            frame = frame.f_back
    else:
        snapshot = err.stack_snapshot

    if not snapshot:
        print("No stackframe information.\n", file = file)
        return
    for frame in snapshot:
        if frame.f_locals is not frame.f_globals: # 如果局部变量和全局变量不同（不是模块根部）
            print(f"""Local variables of {frame.f_code.co_name} \
({os.path.split(frame.f_code.co_filename)[-1]}):""", file = file)
            _pprint_dict(frame.f_locals, file = file, maxlen = maxlength)

        if not frame.f_back or frame.f_back.f_globals is not frame.f_globals: # 如果下一帧的全局变量不同
            print(file = file)
            print(f"Global variables of {frame.f_code.co_name}:", file = file)
            _pprint_dict(frame.f_globals, file = file,
                         do_ignore = brief_global_var, maxlen = maxlength)

        print(file = file)

def trace_error(file=None,brief_global_var=True,maxlength=MAXLENGTH):
    # 同时输出异常信息和堆栈
    if file is None:file = sys.stderr

    print("\nError:", file=file)
    traceback.print_exc(file=file)
    print(file = file)
    err = sys.exc_info()[1]
    if err is not None:
        trace_stack(err, file=file, maxlength=maxlength,
                    brief_global_var=brief_global_var)

# -- 替换sys.excepthook部分 --
_pre_excepthook = None
_brief_global_var = True # 是否精简全局变量的输出
_maxlen = MAXLENGTH
def _exceptionhook(exctype, value, tb):
    print(f"\n{'-'*20} Error: {'-'*20}", file = sys.stderr)
    traceback.print_exception(exctype, value=value, tb=tb)
    print(file = sys.stderr)
    trace_stack(value, file = sys.stderr,
                brief_global_var = _brief_global_var, maxlength = _maxlen)
    print(f"{'-'*48}\n", file = sys.stderr)

def hook_sys_exception(brief_global_var = True, maxlength = MAXLENGTH):
    global _pre_excepthook, _brief_global_var, _maxlen
    if _pre_excepthook is not None:
        return # 已经修改过
    _brief_global_var = brief_global_var
    _maxlen = MAXLENGTH
    _pre_excepthook=sys.excepthook
    sys.excepthook=_exceptionhook

def reset_sys_excepthook():
    global _pre_excepthook
    if _pre_excepthook is None:
        return
    sys.excepthook=_pre_excepthook
    _pre_excepthook=None

# -- 接口部分 --
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

def init(ignored=IGNORED, brief_global_var = True, maxlength = MAXLENGTH):
    # 调用init后，默认直接开启堆栈快照捕获
    global _init
    _init = True
    hack_all_exc(ignored)
    hook_sys_exception(brief_global_var, maxlength)


def test():
    def inner():
        raise ValueError

    init()
    try:
        inner()
    except ValueError:
        trace_error()

if __name__=="__main__":test()
