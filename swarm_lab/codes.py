"""Exact verification of linear codes over GF(3) and GF(4).

Candidates are one-generator quasi-cyclic codes: a list of polynomials, one per
circulant block of size k, with the trailing coordinates punctured to reach the
target length. The verifier builds the generator matrix, checks its rank, and
enumerates every codeword up to scalar multiples to find the exact minimum
distance d and the number of codewords of weight d.

Vectors are bit-sliced into two integers whose bit t describes coordinate t.
GF(3) uses planes (value is 1, value is 2). GF(4) encodes c0 + c1*w as the
integer c0 + 2*c1, with w*w = w + 1, and stores the c0 and c1 planes.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

FIELDS = (3, 4)
MAX_K = 14  # Exhaustive enumeration grows as q**k; profile before raising.

_MUL4 = ((0, 0, 0, 0), (0, 1, 2, 3), (0, 2, 3, 1), (0, 3, 1, 2))
_INV4 = (None, 1, 3, 2)


def field_add(q: int, a: int, b: int) -> int:
    return (a + b) % 3 if q == 3 else a ^ b


def field_sub(q: int, a: int, b: int) -> int:
    return (a - b) % 3 if q == 3 else a ^ b


def field_mul(q: int, a: int, b: int) -> int:
    return (a * b) % 3 if q == 3 else _MUL4[a][b]


def field_inv(q: int, a: int) -> int:
    if a == 0:
        raise ZeroDivisionError('zero has no inverse')
    return a if q == 3 else _INV4[a]


def rank(q: int, rows: list[list[int]]) -> int:
    """Row rank over GF(q) by Gaussian elimination."""
    matrix = [list(row) for row in rows]
    width = len(matrix[0]) if matrix else 0
    found = 0
    for column in range(width):
        pivot = next((r for r in range(found, len(matrix)) if matrix[r][column]), None)
        if pivot is None:
            continue
        matrix[found], matrix[pivot] = matrix[pivot], matrix[found]
        scale = field_inv(q, matrix[found][column])
        matrix[found] = [field_mul(q, scale, value) for value in matrix[found]]
        for r in range(len(matrix)):
            if r != found and matrix[r][column]:
                factor = matrix[r][column]
                matrix[r] = [field_sub(q, value, field_mul(q, factor, pivot_value))
                             for value, pivot_value in zip(matrix[r], matrix[found])]
        found += 1
    return found


def _planes(row: list[int]) -> tuple[int, int]:
    """GF(3): (ones, twos). GF(4): (c0, c1). Both read value bits the same way."""
    low = high = 0
    for position, value in enumerate(row):
        if value & 1:
            low |= 1 << position
        if value & 2:
            high |= 1 << position
    return low, high


def _multiples(q: int, plane: tuple[int, int]) -> tuple[tuple[int, int], ...]:
    """Bit-sliced s*row for every nonzero scalar s."""
    a, b = plane
    if q == 3:
        return ((a, b), (b, a))                 # 1*row, 2*row = -row
    return ((a, b), (b, a ^ b), (a ^ b, a))     # 1, w, w^2 times row


def _search3(planes: list[tuple[int, int]]) -> tuple[int, int]:
    multiples = [_multiples(3, plane) for plane in planes]
    k = len(planes)
    best, count = 1 << 30, 0

    def visit(start: int, x1: int, x2: int) -> None:
        nonlocal best, count
        for j in range(start, k):
            for y1, y2 in multiples[j]:
                t = (x1 | y2) ^ (x2 | y1)
                z1, z2 = (x2 | y2) ^ t, (x1 | y1) ^ t
                weight = (z1 | z2).bit_count()
                if weight < best:
                    best, count = weight, 1
                elif weight == best:
                    count += 1
                if j + 1 < k:
                    visit(j + 1, z1, z2)

    for j in range(k):
        x1, x2 = planes[j]
        weight = (x1 | x2).bit_count()
        if weight < best:
            best, count = weight, 1
        elif weight == best:
            count += 1
        visit(j + 1, x1, x2)
    return best, count


def _search4(planes: list[tuple[int, int]]) -> tuple[int, int]:
    multiples = [_multiples(4, plane) for plane in planes]
    k = len(planes)
    best, count = 1 << 30, 0

    def visit(start: int, x0: int, x1: int) -> None:
        nonlocal best, count
        for j in range(start, k):
            for y0, y1 in multiples[j]:
                z0, z1 = x0 ^ y0, x1 ^ y1
                weight = (z0 | z1).bit_count()
                if weight < best:
                    best, count = weight, 1
                elif weight == best:
                    count += 1
                if j + 1 < k:
                    visit(j + 1, z0, z1)

    for j in range(k):
        x0, x1 = planes[j]
        weight = (x0 | x1).bit_count()
        if weight < best:
            best, count = weight, 1
        elif weight == best:
            count += 1
        visit(j + 1, x0, x1)
    return best, count


def minimum_distance(q: int, rows: list[list[int]]) -> tuple[int, int]:
    """Exact (d, number of weight-d codewords) for a full-rank generator matrix.

    Enumerates one representative of each nonzero codeword up to scalar
    multiples, so the count is multiplied by q - 1.
    """
    if q not in FIELDS:
        raise ValueError('only GF(3) and GF(4) are supported')
    if not rows or len(rows) > MAX_K:
        raise ValueError(f'dimension must be in 1..{MAX_K}')
    if rank(q, rows) != len(rows):
        raise ValueError('generator matrix must have full row rank')
    planes = [_planes(row) for row in rows]
    best, count = (_search3 if q == 3 else _search4)(planes)
    return best, count * (q - 1)


@dataclass(frozen=True)
class Target:
    """One best-known-codes table entry, frozen in the target manifest."""
    q: int
    n: int
    k: int
    lower: int
    upper: int

    @property
    def blocks(self) -> int:
        return -(-self.n // self.k)

    @property
    def punctured(self) -> int:
        return self.blocks * self.k - self.n


@dataclass(frozen=True)
class CodeResult:
    valid: bool
    reason: str | None
    d: int | None = None
    min_weight_count: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def qc_generator(target: Target, polynomials: list[list[int]]) -> list[list[int]]:
    """Rows are the k cyclic shifts of the concatenated blocks, then truncated to n."""
    k = target.k
    rows = []
    for shift in range(k):
        row = []
        for poly in polynomials:
            row.extend(poly[(t - shift) % k] for t in range(k))
        rows.append(row[:target.n])
    return rows


def check_polynomials(target: Target, polynomials) -> str | None:
    """Return a rejection reason, or None when the shape and entries are admissible."""
    if not isinstance(polynomials, list) or len(polynomials) != target.blocks:
        return f'expected {target.blocks} polynomials'
    for poly in polynomials:
        if not isinstance(poly, list) or len(poly) != target.k:
            return f'each polynomial needs exactly {target.k} coefficients'
        if any(type(value) is not int or not 0 <= value < target.q for value in poly):
            return f'coefficients must be integers in 0..{target.q - 1}'
    return None


def evaluate(target: Target, polynomials) -> CodeResult:
    """Validate a quasi-cyclic candidate and compute its exact minimum distance."""
    reason = check_polynomials(target, polynomials)
    if reason:
        return CodeResult(False, reason)
    rows = qc_generator(target, polynomials)
    if rank(target.q, rows) != target.k:
        return CodeResult(False, 'generator matrix is rank deficient')
    d, count = minimum_distance(target.q, rows)
    return CodeResult(True, None, d, count)


def better(a: CodeResult, b: CodeResult | None) -> bool:
    """True when a ranks strictly above b: larger d, then fewer weight-d codewords."""
    if not a.valid:
        return False
    if b is None or not b.valid:
        return True
    return (a.d, -a.min_weight_count) > (b.d, -b.min_weight_count)
