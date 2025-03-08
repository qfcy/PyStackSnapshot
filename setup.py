import sys,os,site,shutil,subprocess,shlex
from setuptools import setup,Extension

try:
    os.chdir(os.path.split(__file__)[0])
    sys.path.append(os.getcwd())
except Exception:pass
sys.path.extend(site.getsitepackages()+[site.getusersitepackages()])
import stack_snapshot

if "sdist" in sys.argv[1:]:
    if not os.path.isfile("README.rst") or \
       (os.stat("README.md").st_mtime > os.stat("README.rst").st_mtime):
        if shutil.which("pandoc"):
            cmd="pandoc -t rst -o README.rst README.md"
            print("Running pandoc:",cmd,"...")
            result=subprocess.run(shlex.split(cmd))
            print("Return code:",result.returncode)
        else:
            print("Pandoc command for generating README.rst is required",
                  file=sys.stderr)
            sys.exit(1)
    long_desc=open("README.rst",encoding="utf-8").read()
else:
    long_desc=""

setup(
    name='stack-snapshot',
    version=stack_snapshot.__version__,
    description=stack_snapshot.__doc__.replace("\n"," "),
    long_description=long_desc,
    author="qfcy",
    author_email="3076711200@qq.com",
    url="https://github.com/qfcy/PySnapshot",
    py_modules=['stack_snapshot'],
    keywords=["stack","dump","exception","debug","bug tracking",
              "stack frame","debugger","heap"],
    classifiers=[
        "Programming Language :: Python",
        "Topic :: Utilities",
        "Topic :: Software Development :: Bug Tracking",
        "Topic :: Software Development :: Debuggers",
        "Topic :: Software Development :: Testing",
        "Topic :: Software Development :: Libraries :: Python Modules"
    ],
    install_requires=["pyobject",
                      'pydetour; python_version >= "3.12"'],
)
