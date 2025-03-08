**The English documentation is placed below the Chinese version.**  

`stack-snapshot`是一个在发生异常时，自动捕获异常发生时的完整栈帧，包括**局部、全局变量**的库。  
在Python开发中，仅凭Traceback信息无法得知异常发生时的变量，要修复bug就必须**重现**这个异常。这使得一些生产环境中难以复现的bug几乎**无法**被调试。  
但有了`stack-snapshot`库，异常发生时会自动捕获整个堆栈的所有局部、全局变量，让开发者能够**精准定位异常**，极大地提升你的调试效率。  

## 用途

#### 与AI工具集成
目前，AI生成的代码可能存在不少逻辑缺陷。传统的Traceback输出不具备捕获局部变量的能力，导致依赖Traceback输出，以及日志记录实现的调试，难以精准定位某些类型的错误。  
但`stack-snapshot`库输出的局部变量信息能精准反映错误。只需将局部变量输出信息**粘贴**到**大模型**，如ChatGPT, DeepSeek等，就能让AI生成更精准的代码。  

## 使用示例
```
import stack_snapshot

def inner(x, y):
    return x / y

stack_snapshot.init()

x = 1; y = 0
print(inner(x,y))
```

未启用堆栈快照时：
```python
Traceback (most recent call last):
  File "PyStackSnapshot\test.py", line 9, in <module>
    print(inner(x,y))
  File "PyStackSnapshot\test.py", line 4, in inner
    if y == 0:raise ZeroDivisionError
ZeroDivisionError
```
未启用堆栈快照时，由于`inner`中参数`x`和`y`的具体值未知，使得问题难以定位。  
启用堆栈快照之后：
```python
-------------------- Error: --------------------
Traceback (most recent call last):
  File "PyStackSnapshot\test.py", line 9, in <module>
    print(inner(x,y))
  File "PyStackSnapshot\test.py", line 4, in inner
    if y == 0:raise ZeroDivisionError
ZeroDivisionError

Local variables of inner (test.py):
x = 1
y = 0

Global variables of <module>:
__file__ = 'PyStackSnapshot\\test.py'
__name__ = '__main__'
...
inner    = <function inner at 0x03221810>
x        = 1
y        = 0

-----------------------------------------------
```

另外，也可以手动捕获异常，并手动输出：
```python
import stack_snapshot

def inner(x, y):
    return x / y

stack_snapshot.init()
try:
    print(inner(1,0))
except Exception as err:
    if hasattr(err,"stack_snapshot"):
        print("堆栈深度: ", len(err.stack_snapshot)) # 启用stack_snapshot后，所有的异常对象默认会增加一个stack_snapshot属性
    stack_snapshot.trace_error()
```

## 详细用法

- `stack_snapshot(start=0)`: 返回捕获的当前堆栈的列表（线程安全），`start`为堆栈深度。
- `hack_exc(exc)`: 启用一个异常类的自动堆栈捕获，`exc`为一个异常类，如`ValueError`。
- `hack_all_exc(ignored=IGNORED)`: 启用所有异常类（包括标准库的异常，和继承自标准库的自定义异常类）的自动堆栈捕获，`ignored`为一个列表或元组，表示要忽略的类，默认为`(BaseException,)`。
<br></br>

- `trace_stack(err,file=None,brief_global_var=True,maxlength=150)`: 单独输出异常的堆栈信息，`err`为一个异常对象，如`except Exception as err`得到的`err`变量。
`brief_global_var`为是否精简全局变量的输出（也就是不输出函数、类和已导入模块的变量，并禁用大多数类似`__var__`的双下划线名称）。
`maxlength`为输出变量值的最大长度，用于避免输出过长的变量（如数组等）。
- `trace_error(file=None,brief_global_var=True,maxlength=150)`: 同时输出异常的Traceback和堆栈捕获信息，不需要提供`err`参数。`file`为输出到的类似文件对象，默认为`sys.stderr`。
<br></br>

- `hook_sys_exception(brief_global_var=True,maxlength=150)`: 修改`sys.excepthook`，也就是Python解释器遇到未处理的异常时，自动调用的函数，使得遇到未处理异常时，自动输出堆栈。
- `reset_sys_excepthook()`: 恢复原先的`sys.excepthook`。
<br></br>

- `enable_snapshot()`: 启用异常发生时自动捕获堆栈（线程安全）。
- `disable_snapshot()`: 禁用异常发生时自动捕获堆栈（线程安全）。
- `is_snapshot_enabled()`: 获取自动捕获堆栈是否启用（线程安全）。
<br></br>

- **`init(ignored=IGNORED,brief_global_var=True,maxlength=150)`**: 启用所有异常（包括标准库的异常，和继承自标准库的自定义异常类）的自动捕获堆栈，以及堆栈输出。**（推荐）**

## 工作原理

这是出自[hook.py](hook.py)的`hack_exc`函数（不考虑`pydetour`库的情况下）:
```python
_hacked_excs=weakref.WeakSet()
def hack_exc(exc):
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
```
`hack_exc`函数首先修改对象的flag，使得对象的`__new__`属性能被修改。  
再替换`__new__`方法为自定义的`__new__`函数，最后恢复原先的flag标志。（如果启用`pydetour`，会直接拦截初始化调用如`Exception()`，具体见源码）  

`hack_exc`函数支持非`pydetour`和`pydetour`两种模式。非`pydetour`模式最高支持Python 3.11（由于CPython的内部机制），而`pydetour`模式支持当前最高的Python版本3.14。  

---

`stack-snapshot` is a library that automatically captures the complete stack frames at the time of an exception, including **local and global variables**.  
In Python development, it is often not enough to rely solely on traceback information, as it does not reveal the variable values at the time of the exception. To fix a bug, this means the exception must be **reproduced**, making some hard-to-reproduce bugs in production environments almost **impossible** to debug.  
However, with the `stack-snapshot` library, the entire stack's local and global variables are automatically captured when an exception occurs, allowing developers to **precisely locate exceptions**, significantly enhancing debugging efficiency.

## Usage Scenarios

#### Integration with AI Tools
Currently, AI-generated code may contain various logical flaws. Traditional traceback outputs fail to capture local variable information, making it challenging to accurately identify certain types of errors when relying on traceback outputs and logging for debugging.  
However, the local variable information provided by the `stack-snapshot` library can effectively reflect the errors. Simply **paste** the local variable output into a **large model**, such as ChatGPT or Copilot, to allow the AI to generate more precise code.  

## Example Usage
```python
import stack_snapshot

def inner(x, y):
    return x / y

stack_snapshot.init()

x = 1; y = 0
print(inner(x, y))
```

When stack snapshotting is not enabled:
```python
Traceback (most recent call last):
  File "PyStackSnapshot\test.py", line 9, in <module>
    print(inner(x,y))
  File "PyStackSnapshot\test.py", line 4, in inner
    if y == 0: raise ZeroDivisionError
ZeroDivisionError
```
When stack snapshotting is not enabled, the specific values of the parameters `x` and `y` in `inner` are unknown, making it difficult to pinpoint the issue.  
After enabling stack snapshotting:
```python
-------------------- Error: --------------------
Traceback (most recent call last):
  File "PyStackSnapshot\test.py", line 9, in <module>
    print(inner(x,y))
  File "PyStackSnapshot\test.py", line 4, in inner
    if y == 0: raise ZeroDivisionError
ZeroDivisionError

Local variables of inner (test.py):
x = 1
y = 0

Global variables of <module>:
__file__ = 'PyStackSnapshot\\test.py'
__name__ = '__main__'
...
inner    = <function inner at 0x03221810>
x        = 1
y        = 0

-----------------------------------------------
```

Additionally, exceptions can also be manually captured and output:
```python
import stack_snapshot

def inner(x, y):
    return x / y

stack_snapshot.init()
try:
    print(inner(1, 0))
except Exception as err:
    if hasattr(err, "stack_snapshot"):
        print("Stack depth: ", len(err.stack_snapshot)) # When taking snapshot is enabled, all exception objects automatically have a stack_snapshot attribute added
    stack_snapshot.trace_error()
```

## Detailed Usage

- `stack_snapshot(start=0)`: Returns a list of the captured current stack (thread-safe). The `start` parameter indicates the stack depth.
- `hack_exc(exc)`: Enables automatic stack capturing for an exception class, where `exc` is an exception class such as `ValueError`.
- `hack_all_exc(ignored=IGNORED)`: Enables automatic stack capturing for all exception classes (including standard library exceptions and user-defined exceptions that inherit from standard library exceptions), where `ignored` is a list or tuple indicating which classes to ignore, defaulting to `(BaseException,)`.
<br></br>

- `trace_stack(err, file=None, brief_global_var=True, maxlength=150)`: Outputs the stack information of a specific exception, where `err` is an exception object, like the `err` variable obtained from `except Exception as err`. The `brief_global_var` parameter indicates whether to simplify the output of global variables (i.e., not outputting variables from functions, classes, and imported modules, and disabling most double underscore names like `__var__`). The `maxlength` parameter specifies the maximum length of variable values to avoid excessively long outputs (e.g., for arrays).
- `trace_error(file=None, brief_global_var=True, maxlength=150)`: Outputs both the traceback and stack capturing information for an exception, without needing to provide the `err` parameter. The `file` parameter indicates where to output (similar to a file object), defaulting to `sys.stderr`.
<br></br>

- `hook_sys_exception(brief_global_var=True, maxlength=150)`: Modifies `sys.excepthook`, which is the function automatically called by the Python interpreter when it encounters an unhandled exception, allowing automatic output of the stack when an unhandled exception occurs.
- `reset_sys_excepthook()`: Restores the original `sys.excepthook`.
<br></br>

- `enable_snapshot()`: Enables automatic stack capturing when an exception occurs (thread-safe).
- `disable_snapshot()`: Disables automatic stack capturing when an exception occurs (thread-safe).
- `is_snapshot_enabled()`: Checks if automatic stack capturing is enabled (thread-safe).
<br></br>

- **`init(ignored=IGNORED, brief_global_var=True, maxlength=150)`**: Enables automatic stack capturing for all exceptions (including standard library exceptions and user-defined exceptions that inherit from standard library exceptions) and for stack output. **(Recommended)**

## Working Principle

Here is the `hack_exc` function from [hook.py](hook.py):
```python
_hacked_excs = weakref.WeakSet()
def hack_exc(exc):
    # Prevent repeated modifications
    if exc in _hacked_excs:
        return
    _hacked_excs.add(exc)

    flag = get_type_flag(exc)
    pre_flag = flag
    flag |= Py_TPFLAGS_HEAPTYPE
    flag &= ~Py_TPFLAGS_IMMUTABLETYPE # Remove Py_TPFLAGS_IMMUTABLETYPE
    set_type_flag(exc, flag) # Temporarily modify the underlying flag of the object (the properties of built-in objects like ValueError.__new__ are originally unmodifiable)

    def __new__(cls, *args, **kw):
        new_func = BaseException.__new__ # Underlying __new__ method
        result = new_func(cls, *args, **kw)
        if not getattr(result, "stack_snapshot", None): # Prevent repeated capturing
            # Capture the current stack
            result.stack_snapshot = stack_snapshot(start=2) # start=2: skip this function and two layers of __new__
        return result

    exc.__new__ = __new__ # Replace the exception type's __new__
    pre_flag &= ~Py_TPFLAGS_IMMUTABLETYPE
    set_type_flag(exc, pre_flag) # Restore the original flag
```
The `hack_exc` function first modifies the object's flag to allow the modification of the `__new__` attribute of the object.  
Then, it replaces the `__new__` method with a custom `__new__` function.  
Finally, it restores the original flag.  

Currently, `hack_exc` supports up to Python 3.11 due to internal mechanisms of CPython, while `pydetour` mode supports the latest Python version, 3.14.
