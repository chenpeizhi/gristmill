![CircleCI](https://circleci.com/gh/tschijnmo/gristmill.svg?style=shield)
[![Travis CI](https://travis-ci.org/tschijnmo/gristmill.svg?branch=master)](https://travis-ci.org/tschijnmo/gristmill)
[![Coverage Status](https://coveralls.io/repos/github/tschijnmo/gristmill/badge.svg?branch=master)](https://coveralls.io/github/tschijnmo/gristmill?branch=master)

# gristmill

Gristmill is a package built on the
[drudge](https://github.com/tschijnmo/drudge) algebra system for automatic
optimization and code generation of tensor computations. While designed for
quantum chemistry and many-body theory, it is suitable for any scientific
computing problem involving tensors.

The optimizer utilizes advanced algorithms to efficiently parenthesize and
factorize tensor computations, reducing the floating-point operation (FLOP)
count. For example, a matrix chain product

$$
\mathbf{R} = \mathbf{A} \mathbf{B} \mathbf{C}
$$

can be parenthesized as

$$
\mathbf{R} = \left( \mathbf{A} \mathbf{B} \right) \mathbf{C}
$$

or

$$
\mathbf{R} = \mathbf{A} \left( \mathbf{B} \mathbf{C} \right),
$$

depending on which has fewer FLOPs given the shapes of the matrices. General
tensor contractions are supported, with minimal overhead relative to
specialized dynamic programming algorithms for matrix chain products. As an
example, when evaluating the ladder term in coupled cluster doubles (CCD)
residuals

$$
r_{abij} = \sum_{c,d=1}^v \sum_{k,l=1}^o v_{klcd} t_{cdij} t_{abkl},
$$

Gristmill can automatically generate a two-step contraction scheme:

$$
\begin{aligned}
    p_{klij} &= \sum_{c,d=1}^v v_{klcd} t_{cdij}\\
    r_{abij} &= \sum_{k,l=1}^o p_{klij} t_{abkl}
\end{aligned}
$$

Gristmill's algorithm can efficiently handle complicated contractions with,
e.g., twenty factors.

When evaluating sums of multiple contractions, Gristmill factors each term to
reduce computational cost. For example, the coupled cluster singles and doubles
(CCSD) correlation energy

$$
E = \frac{1}{4} \sum_{i,j=1}^o \sum_{a,b=1}^{v} u_{ijab} t^{(2)}_{abij} + \frac{1}{2} \sum_{i,j=1}^o \sum_{a,b=1}^v u_{ijab} t^{(1)}_{ai} t^{(1)}_{bj}
$$

can be automatically simplified into

$$
E = \frac{1}{4} \sum_{i,j=1}^o \sum_{a,b=1}^v u_{ijab} \left(
    t^{(2)}_{abij} + 2 t^{(1)}_{ai} t^{(1)}_{bj},
\right)
$$

which has lower FLOP count.

Additionally, Gristmill includes optimization heuristics such as common
symmetrization, which ensures intermediates that are equivalent by symmetry are
computed only once using the canonicalization capability in
[drudge](https://github.com/tschijnmo/drudge).

The code generator in Gristmill is a component orthogonal to the optimizer.
Both optimized and unoptimized computations can be fed into the code generator
to yield naive Fortran or C code (with optional OpenMP parallelization) or
Python code using NumPy.

Gristmill is developed by Jinmo Zhao and Prof. Gustavo E. Scuseria at Rice
University, supported by the U.S. Department of Energy, Office of Science,
Basic Energy Sciences under Award DE-SC0012575.
