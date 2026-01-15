# cython: language_level=3
# inference_cython_example.pyx
# Example of what Cython version would look like (NOT RECOMMENDED for CoEnv)

cimport cython
from libc.math cimport log2

@cython.boundscheck(False)
@cython.wraparound(False)
cpdef double calculate_entropy_cython(str value):
    """
    Cython-optimized entropy calculation.

    Potential speedup: 5-10x on long strings
    Actual benefit: Minimal (values are short)
    """
    if not value:
        return 0.0

    cdef:
        int length = len(value)
        dict freq = {}
        double entropy = 0.0
        double probability
        int count

    # Count character frequencies
    for char in value:
        if char in freq:
            freq[char] += 1
        else:
            freq[char] = 1

    # Calculate entropy
    for count in freq.values():
        probability = <double>count / <double>length
        if probability > 0:
            entropy -= probability * log2(probability)

    return entropy


@cython.boundscheck(False)
cpdef bint is_secret_cython(str value):
    """
    Cython-optimized secret detection.
    """
    if not value:
        return False

    cdef:
        double entropy
        list secret_prefixes = [
            'sk_', 'pk_', 'AKIA', 'vault:', 'arn:aws:',
            'ghp_', 'gho_', 'ghs_', 'key_', 'token_', 'secret_'
        ]

    # Check entropy (this is where Cython helps most)
    entropy = calculate_entropy_cython(value)
    if entropy > 4.5:
        return True

    # Check prefixes (no real benefit from Cython here)
    for prefix in secret_prefixes:
        if value.startswith(prefix):
            return True

    return False


# Type-optimized version with C types
@cython.boundscheck(False)
@cython.wraparound(False)
cpdef double calculate_entropy_optimized(str value):
    """
    Fully optimized Cython version with C types.

    This would be faster but requires:
    - Compilation for each platform
    - C compiler on user machines
    - More complex build process
    """
    if not value:
        return 0.0

    cdef:
        int i, length = len(value)
        unsigned char[256] freq  # ASCII frequency table
        double entropy = 0.0
        double probability
        int distinct_chars = 0

    # Initialize frequency table
    for i in range(256):
        freq[i] = 0

    # Count frequencies (C-level performance)
    for i in range(length):
        freq[<unsigned char>ord(value[i])] += 1

    # Calculate entropy
    for i in range(256):
        if freq[i] > 0:
            probability = <double>freq[i] / <double>length
            entropy -= probability * log2(probability)
            distinct_chars += 1

    return entropy
