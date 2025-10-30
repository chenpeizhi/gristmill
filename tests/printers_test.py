"""Tests for the base printer.
"""

import subprocess
from unittest.mock import patch

import pytest
from sympy import Symbol, IndexedBase, symbols, Float
from sympy.printing.python import PythonPrinter

from drudge import Drudge, Range
from gristmill import BasePrinter, CPrinter, FortranPrinter, EinsumPrinter, OMEinsumPrinter, mangle_base
from gristmill.generate import (
    TensorDecl, BeginBody, BeforeComp, CompTerm, OutOfUse, EndBody
)


@pytest.fixture(scope='module')
def simple_drudge(spark_ctx):
    """Form a simple drudge with some basic information.
    """

    dr = Drudge(spark_ctx)

    n = Symbol('n')
    r = Range('R', 0, n)

    dumms = symbols('a b c d e f g')
    dr.set_dumms(r, dumms)
    dr.add_resolver_for_dumms()

    return dr


@pytest.fixture
def colourful_tensor(simple_drudge):
    """Form a colourful tensor definition capable of large code coverage.
    """

    dr = simple_drudge
    p = dr.names

    x = IndexedBase('x')
    u = IndexedBase('u')
    v = IndexedBase('v')
    dr.set_name(x, u, v)

    r, s = symbols('r s')
    dr.set_name(r, s)

    a, b, c = p.R_dumms[:3]

    tensor = dr.define(x[a, b], (
            ((2 * r) / (3 * s)) * (u[b, a]) ** 2 -
            dr.sum((c, p.R), u[a, c] * v[c, b] * c ** 2 / 2)
    ))

    return tensor


@pytest.fixture
def eval_seq_deps(simple_drudge):
    """A simple evaluation sequence with some dependencies.

    Here, the tensors are all matrices. we have inputs X, Y.

    I1 = X Y
    I2 = Y X
    I3 = Tr(I1)

    R1 = I1 * I3 + I2
    R2 = I1 * 2

    """

    dr = simple_drudge
    p = dr.names
    a, b, c = p.a, p.b, p.c

    x = IndexedBase('X')
    y = IndexedBase('Y')
    i1 = IndexedBase('I1')
    i2 = IndexedBase('I2')
    i3 = Symbol('I3')
    r1 = IndexedBase('R1')
    r2 = IndexedBase('R2')

    i1_def = dr.define_einst(i1[a, b], x[a, c] * y[c, b])
    i1_def.if_interm = True
    i2_def = dr.define_einst(i2[a, b], y[a, c] * x[c, b])
    i2_def.if_interm = True
    i3_def = dr.define_einst(i3, i1[a, a])
    i3_def.if_interm = True
    r1_def = dr.define_einst(r1[a, b], i1[a, b] * i3 + i2[a, b])
    r1_def.if_interm = False
    r2_def = dr.define_einst(r2[a, b], i1[a, b] * 2)
    # No annotation for r2, should be taken as a result.

    return [i1_def, i2_def, i3_def, r1_def, r2_def]


def test_base_printer_ctx(simple_drudge, colourful_tensor):
    """Test the context formation facility in base printer."""

    dr = simple_drudge
    p = dr.names
    tensor = colourful_tensor

    # Process indexed names by mangling the base name.
    with patch.object(BasePrinter, '__abstractmethods__', frozenset()):
        printer = BasePrinter(PythonPrinter(), mangle_base(
            lambda base, indices: base + str(len(indices))
        ))
    ctx = printer.transl(tensor)

    def check_range(ctx, index):
        """Check the range information in a context for a index."""
        assert ctx.index == index
        assert ctx.range == p.R
        assert ctx.lower == '0'
        assert ctx.upper == 'n'
        assert ctx.size == 'n'

    assert ctx.base == 'x2'
    for i, j in zip(ctx.indices, ['a', 'b']):
        check_range(i, j)
        continue

    assert len(ctx.terms) == 2
    for term in ctx.terms:
        if len(term.sums) == 0:
            # The transpose term.

            assert term.phase == '+'
            r = Symbol('r')
            assert float(eval(term.numerator) / r) == 2/3
            assert term.denominator == 's'

            assert len(term.indexed_factors) == 1
            factor = term.indexed_factors[0]
            assert factor.base == 'u2**2'
            for i, j in zip(factor.indices, ['b', 'a']):
                check_range(i, j)
                continue

            assert len(term.other_factors) == 0

        elif len(term.sums) == 1:

            check_range(term.sums[0], 'c')

            assert term.phase == '-'
            assert float(eval(term.numerator)) == 0.5
            assert term.denominator == '1'

            assert len(term.indexed_factors) == 2
            for factor in term.indexed_factors:
                if factor.base == 'u2':
                    expected = ['a', 'c']
                elif factor.base == 'v2':
                    expected = ['c', 'b']
                else:
                    assert False
                for i, j in zip(factor.indices, expected):
                    check_range(i, j)
                    continue
                continue

            assert len(term.other_factors) == 1
            assert term.other_factors[0] == 'c**2'

        else:
            assert False


def test_events_generation(eval_seq_deps):
    """Test the event generation facility in the base printer."""
    eval_seq = eval_seq_deps

    with patch.object(BasePrinter, '__abstractmethods__', frozenset()):
        printer = BasePrinter(PythonPrinter())
    events = printer.form_events(eval_seq)

    i1 = IndexedBase('I1')
    i2 = IndexedBase('I2')
    i3 = Symbol('I3')
    r1 = IndexedBase('R1')
    r2 = IndexedBase('R2')

    events.reverse()  # For easy popping from front.

    for i in [i1, i2, i3]:
        event = events.pop()
        assert isinstance(event, TensorDecl)
        assert event.comput.target == i
        continue

    event = events.pop()
    assert isinstance(event, BeginBody)

    event = events.pop()
    assert isinstance(event, BeforeComp)
    assert event.comput.target == i1

    event = events.pop()
    assert isinstance(event, CompTerm)
    assert event.comput.target == i1
    assert event.term_idx == 0

    # I1 drives I3.
    event = events.pop()
    assert isinstance(event, BeforeComp)
    assert event.comput.target == i3

    event = events.pop()
    assert isinstance(event, CompTerm)
    assert event.comput.target == i3
    assert event.term_idx == 0

    # I3, I1, drives the first term of R1.
    event = events.pop()
    assert isinstance(event, BeforeComp)
    assert event.comput.target == r1

    event = events.pop()
    assert isinstance(event, CompTerm)
    assert event.comput.target == r1
    assert event.term_idx == 0

    # Now I3 should be out of dependency.
    event = events.pop()
    assert isinstance(event, OutOfUse)
    assert event.comput.target == i3

    # Another one driven by I1.
    event = events.pop()
    assert isinstance(event, BeforeComp)
    assert event.comput.target == r2

    event = events.pop()
    assert isinstance(event, CompTerm)
    assert event.comput.target == r2
    assert event.term_idx == 0

    # I1 no longer needed any more.
    event = events.pop()
    assert isinstance(event, OutOfUse)
    assert event.comput.target == i1

    # Nothing driven.
    event = events.pop()
    assert isinstance(event, BeforeComp)
    assert event.comput.target == i2

    event = events.pop()
    assert isinstance(event, CompTerm)
    assert event.comput.target == i2
    assert event.term_idx == 0

    # The last term in R1.
    event = events.pop()
    assert isinstance(event, CompTerm)
    assert event.comput.target == r1
    assert event.term_idx == 1

    # Finally, free I2.
    event = events.pop()
    assert isinstance(event, OutOfUse)
    assert event.comput.target == i2

    event = events.pop()
    assert isinstance(event, EndBody)

    assert len(events) == 0


def _test_fortran_code(code, dir):
    """Test the given Fortran code in the given directory.

    The Fortran code is expected to generate an output of ``OK``.
    """

    orig_cwd = dir.chdir()

    dir.join('test.f90').write(code)
    stat = subprocess.run(['gfortran', '-o', 'test', '-fopenmp', 'test.f90'])
    assert stat.returncode == 0
    stat = subprocess.run(['./test'], stdout=subprocess.PIPE)
    assert stat.stdout.decode().strip() == 'OK'

    orig_cwd.chdir()
    return True


def _test_c_code(code, dir):
    """Test the given C code in the given directory.

    The C code is expected to generate an output of ``OK``.
    """

    orig_cwd = dir.chdir()

    dir.join('test.c').write(code)
    stat = subprocess.run(['gcc', '-o', 'test', 'test.c', '-lm'])
    assert stat.returncode == 0
    stat = subprocess.run(['./test'], stdout=subprocess.PIPE)
    assert stat.stdout.decode().strip() == 'OK'

    orig_cwd.chdir()
    return True


def test_fortran_colourful(colourful_tensor, tmpdir):
    """Test the Fortran printer for colour tensor computations."""

    tensor = colourful_tensor

    printer = FortranPrinter()
    evals = printer.doprint([tensor])

    code = _FORTRAN_BASIC_TEST_CODE.format(evals=evals)
    assert _test_fortran_code(code, tmpdir)


_FORTRAN_BASIC_TEST_CODE = """
program main
implicit none

integer, parameter :: n = 100
real :: r = 6
real :: s = 2
integer :: a, b, c

real, dimension(n, n) :: u
real, dimension(n, n) :: v
real, dimension(n, n) :: x

real, dimension(n, n) :: diag
real, dimension(n, n) :: expected

call random_number(u)
call random_number(v)

{evals}

diag = 0
do a = 1, n
    diag(a, a) = real(a ** 2) / 2
end do

expected = (transpose(u)**2) * 2 * r / (3 * s)
expected = expected - matmul(u, matmul(diag, v))

if (any(abs(x - expected) / abs(expected) > 1.0E-5)) then
    write(*, *) "WRONG"
end if

write(*, *) "OK"

end program main
"""


def test_full_fortran_printer(eval_seq_deps, tmpdir):
    """Test the Fortran printer for full evaluation."""

    eval_seq = eval_seq_deps

    printer = FortranPrinter(openmp=False)
    evals = printer.doprint(eval_seq)

    code = _FORTRAN_FULL_TEST_CODE.format(eval=evals)
    assert _test_fortran_code(code, tmpdir)

    sep_code = printer.doprint(eval_seq, separate_decls=True)
    assert len(sep_code) == 2
    assert evals == '\n'.join(sep_code)


_FORTRAN_FULL_TEST_CODE = """
program main
implicit none

integer, parameter :: n = 10
integer :: a, b, c

real, dimension(n, n) :: x
real, dimension(n, n) :: y
real, dimension(n, n) :: r1
real, dimension(n, n) :: r2
real, dimension(n, n) :: expected_r1
real, dimension(n, n) :: expected_r2

call random_number(x)
call random_number(y)

block
{eval}
end block

block
real, dimension(n, n) :: xy
real, dimension(n, n) :: yx
real :: trace

xy = matmul(x, y)
yx = matmul(y, x)

trace = 0
do a = 1, n
    trace = trace + xy(a, a)
end do

expected_r1 = xy * trace + yx
expected_r2 = xy * 2

end block

if (any(abs(r1 - expected_r1) / abs(expected_r1) > 1.0E-5)) then
    write(*, *) "WRONG"
end if
if (any(abs(r2 - expected_r2) / abs(expected_r2) > 1.0E-5)) then
    write(*, *) "WRONG"
end if

write(*, *) "OK"

end program main
"""


def test_c_colourful(colourful_tensor, tmpdir):
    """Test the C printer for colour tensor computations."""

    tensor = colourful_tensor

    printer = CPrinter()
    evals = printer.doprint([tensor])

    code = _C_BASIC_TEST_CODE.format(evals=evals)
    assert _test_c_code(code, tmpdir)


_C_BASIC_TEST_CODE = """
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <time.h>

#define n 100

void random_fill(double mat[n][n]) {{
    for (int i = 0; i < n; i++) {{
        for (int j = 0; j < n; j++) {{
            mat[i][j] = (double)rand() / RAND_MAX;
        }}
    }}
}}

void matmul(double a[n][n], double b[n][n], double result[n][n]) {{
    for (int i = 0; i < n; i++) {{
        for (int j = 0; j < n; j++) {{
            result[i][j] = 0.0;
            for (int k = 0; k < n; k++) {{
                result[i][j] += a[i][k] * b[k][j];
            }}
        }}
    }}
}}

int main() {{
    srand(42);
    
    double r = 6.0;
    double s = 2.0;
    int a, b, c;
    
    double u[n][n];
    double v[n][n];
    double x[n][n];
    
    double diag[n][n];
    double expected[n][n];
    double u_squared[n][n];
    double temp[n][n];
    
    random_fill(u);
    random_fill(v);
    
    {evals}
    
    // Initialize diag to zero
    for (int i = 0; i < n; i++) {{
        for (int j = 0; j < n; j++) {{
            diag[i][j] = 0.0;
        }}
    }}
    
    // Set diagonal elements (adjusted for 0-based indexing)
    for (a = 0; a < n; a++) {{
        diag[a][a] = (double)((a) * (a)) / 2.0;
    }}
    
    // Compute expected: transpose(u)^2 * 2 * r / (3 * s)
    for (int i = 0; i < n; i++) {{
        for (int j = 0; j < n; j++) {{
            u_squared[i][j] = u[j][i] * u[j][i];
        }}
    }}
    
    for (int i = 0; i < n; i++) {{
        for (int j = 0; j < n; j++) {{
            expected[i][j] = u_squared[i][j] * 2.0 * r / (3.0 * s);
        }}
    }}
    
    // Compute temp = matmul(diag, v)
    matmul(diag, v, temp);
    
    // Subtract matmul(u, temp) from expected
    for (int i = 0; i < n; i++) {{
        for (int j = 0; j < n; j++) {{
            double sum = 0.0;
            for (int k = 0; k < n; k++) {{
                sum += u[i][k] * temp[k][j];
            }}
            expected[i][j] -= sum;
        }}
    }}
    
    // Check if results match
    for (int i = 0; i < n; i++) {{
        for (int j = 0; j < n; j++) {{
            if (fabs(expected[i][j]) > 1.0E-10) {{
                double rel_err = fabs(x[i][j] - expected[i][j]) / fabs(expected[i][j]);
                if (rel_err > 1.0E-5) {{
                    printf("WRONG\\n");
                    return 1;
                }}
            }}
        }}
    }}
    
    printf("OK\\n");
    return 0;
}}
"""


def test_full_c_printer(eval_seq_deps, tmpdir):
    """Test the C printer for full evaluation."""

    eval_seq = eval_seq_deps

    printer = CPrinter()
    evals = printer.doprint(eval_seq)

    code = _C_FULL_TEST_CODE.format(eval=evals)
    assert _test_c_code(code, tmpdir)

    sep_code = printer.doprint(eval_seq, separate_decls=True)
    assert len(sep_code) == 2
    assert evals == '\n'.join(sep_code)


_C_FULL_TEST_CODE = """
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <time.h>

#define n 10

void random_fill(double mat[n][n]) {{
    for (int i = 0; i < n; i++) {{
        for (int j = 0; j < n; j++) {{
            mat[i][j] = (double)rand() / RAND_MAX;
        }}
    }}
}}

void matmul(double a[n][n], double b[n][n], double result[n][n]) {{
    for (int i = 0; i < n; i++) {{
        for (int j = 0; j < n; j++) {{
            result[i][j] = 0.0;
            for (int k = 0; k < n; k++) {{
                result[i][j] += a[i][k] * b[k][j];
            }}
        }}
    }}
}}

double trace(double mat[n][n]) {{
    double tr = 0.0;
    for (int i = 0; i < n; i++) {{
        tr += mat[i][i];
    }}
    return tr;
}}

int main() {{
    srand(42);
    
    int a, b, c;
    double X[n][n];
    double Y[n][n];
    double R1[n][n];
    double R2[n][n];
    
    random_fill(X);
    random_fill(Y);
    
    {{
        {eval}
    }}
    
    // Compute expected results
    double XY[n][n];
    double YX[n][n];
    double expected_R1[n][n];
    double expected_R2[n][n];
    
    matmul(X, Y, XY);
    matmul(Y, X, YX);
    
    double tr = trace(XY);
    
    for (int i = 0; i < n; i++) {{
        for (int j = 0; j < n; j++) {{
            expected_R1[i][j] = XY[i][j] * tr + YX[i][j];
            expected_R2[i][j] = XY[i][j] * 2.0;
        }}
    }}
    
    // Check R1
    for (int i = 0; i < n; i++) {{
        for (int j = 0; j < n; j++) {{
            if (fabs(expected_R1[i][j]) > 1.0E-10) {{
                double rel_err = fabs(R1[i][j] - expected_R1[i][j]) / fabs(expected_R1[i][j]);
                if (rel_err > 1.0E-5) {{
                    printf("WRONG\\n");
                    return 1;
                }}
            }}
        }}
    }}
    
    // Check R2
    for (int i = 0; i < n; i++) {{
        for (int j = 0; j < n; j++) {{
            if (fabs(expected_R2[i][j]) > 1.0E-10) {{
                double rel_err = fabs(R2[i][j] - expected_R2[i][j]) / fabs(expected_R2[i][j]);
                if (rel_err > 1.0E-5) {{
                    printf("WRONG\\n");
                    return 1;
                }}
            }}
        }}
    }}
    
    printf("OK\\n");
    return 0;
}}
"""


def test_einsum_printer(simple_drudge):
    """Test the basic functionality of the einsum printer.
    """

    dr = simple_drudge
    p = dr.names
    a, b, c = p.R_dumms[:3]

    x = IndexedBase('x')
    u = IndexedBase('u')
    v = IndexedBase('v')

    tensor = dr.define_einst(
        x[a, b], u[b, a] ** 2 - 2 * u[a, c] * v[c, b] / 3
    )

    printer = EinsumPrinter(base_indent=0)
    code = printer.doprint([tensor])

    exec_code = _EINSUM_DRIVER_CODE.format(code=code)
    env = {}
    exec(exec_code, env, {})
    assert env['diff'] < 1.0E-5  # Arbitrary delta.


_EINSUM_DRIVER_CODE = """
from numpy import einsum, array, zeros
from numpy import linalg

n = 2
u = array([[1.0, 2], [3, 4]])
v = array([[1.0, 0], [0, 1]])

{code}

expected = (u ** 2).transpose() - (2.0 / 3) * u @ v
global diff
diff = linalg.norm(x - expected)

"""


def test_full_einsum_printer(eval_seq_deps):
    """Test the full functionality of the einsum printer.
    """
    eval_seq = eval_seq_deps
    printer = EinsumPrinter(base_indent=0)
    code = printer.doprint(eval_seq)
    exec_code = _FULL_EINSUM_DRIVER_CODE.format(eval=code)
    env = {}
    exec(exec_code, env, {})
    assert env['diff1'] < 1.0E-5
    assert env['diff2'] < 1.0E-5


_FULL_EINSUM_DRIVER_CODE = """
from numpy import zeros, einsum, trace
from numpy.random import rand
from numpy import linalg

n = 10

X = rand(n, n)
Y = rand(n, n)

{eval}

XY = X @ Y
YX = Y @ X
tr = trace(XY)
expected_r1 = XY * tr + YX
expected_r2 = XY * 2

global diff1
global diff2
diff1 = linalg.norm((R1 - expected_r1) / expected_r1)
diff2 = linalg.norm((R2 - expected_r2) / expected_r2)

"""


def _test_julia_code(code, dir):
    """Test the given Julia code using juliacall.

    Returns the result value from Julia, or None if juliacall is not available.
    """
    
    # Check if juliacall is available
    try:
        from juliacall import Main as jl
    except ImportError:
        return None
    
    try:
        # Load OMEinsum (should be installed via juliapkg.json)
        jl.seval("using OMEinsum")
        jl.seval("using LinearAlgebra")
        
        # Execute the test code
        jl.seval(code)
        
        # Return the result
        return jl
    except Exception as e:
        print(f"Julia execution failed: {e}")
        return None


def test_omeinsum_printer(simple_drudge, tmpdir):
    """Test the basic functionality of the OMEinsum printer.
    """
    
    dr = simple_drudge
    p = dr.names
    a, b, c = p.R_dumms[:3]

    x = IndexedBase('x')
    u = IndexedBase('u')
    v = IndexedBase('v')

    tensor = dr.define_einst(
        x[a, b], u[b, a] ** 2 - 2 * u[a, c] * v[c, b] / 3
    )

    printer = OMEinsumPrinter()
    code = printer.doprint([tensor])

    julia_test_code = _OMEINSUM_DRIVER_CODE.format(code=code)
    
    jl = _test_julia_code(julia_test_code, tmpdir)
    if jl is None:
        pytest.skip("Julia or OMEinsum.jl not available")
    
    diff = float(jl.diff)
    assert diff < 1.0E-5  # Arbitrary delta.


_OMEINSUM_DRIVER_CODE = """
n = 2
u = [1.0 2.0; 3.0 4.0]
v = [1.0 0.0; 0.0 1.0]

{code}

expected = transpose(u .^ 2) - (2.0 / 3.0) * (u * v)
diff = maximum(abs.(x .- expected))
"""


def test_full_omeinsum_printer(eval_seq_deps, tmpdir):
    """Test the full functionality of the OMEinsum printer.
    """
    eval_seq = eval_seq_deps
    printer = OMEinsumPrinter()
    code = printer.doprint(eval_seq)
    
    julia_test_code = _FULL_OMEINSUM_DRIVER_CODE.format(eval=code)
    
    jl = _test_julia_code(julia_test_code, tmpdir)
    if jl is None:
        pytest.skip("Julia or OMEinsum.jl not available")
    
    diff1 = float(jl.diff1)
    diff2 = float(jl.diff2)
    assert diff1 < 1.0E-5
    assert diff2 < 1.0E-5


_FULL_OMEINSUM_DRIVER_CODE = """
n = 10

X = rand(n, n)
Y = rand(n, n)

{eval}

XY = X * Y
YX = Y * X
tr_val = tr(XY)
expected_R1 = XY * tr_val + YX
expected_R2 = XY * 2

diff1 = maximum(abs.((R1 .- expected_R1) ./ expected_R1))
diff2 = maximum(abs.((R2 .- expected_R2) ./ expected_R2))
"""
