"""Setup script for gristmill."""

import os.path
import sys
from setuptools import setup, find_packages, Extension

PROJ_ROOT = os.path.dirname(os.path.abspath(__file__))
INCLUDE_DIRS = [
    os.path.join(PROJ_ROOT, 'deps', i, 'include')
    for i in ['cpypp', 'fbitset', 'libparenth']
]

# Platform-specific compiler flags
if sys.platform == "win32":
    # MSVC compiler flags
    COMPILE_FLAGS = ['/std:c++17', '/EHsc', '/bigobj', '/wd4996', '/wd4267', '/Zc:twoPhase-']
else:
    # GCC/Clang compiler flags
    COMPILE_FLAGS = ['-std=gnu++1z']

parenth = Extension(
    'gristmill._parenth',
    ['gristmill/_parenth.cpp'],
    include_dirs=INCLUDE_DIRS,
    extra_compile_args=COMPILE_FLAGS
)

setup(
    packages=find_packages(),
    ext_modules=[parenth]
)
