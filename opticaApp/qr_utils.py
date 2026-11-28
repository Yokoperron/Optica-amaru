"""
Generador de códigos QR en formato SVG puro (Byte mode, ECC Level L/M) sin dependencias externas.
Soporta versiones 1 a 6 (hasta 134 bytes en ECC-L), suficiente para tokens y URLs de verificación.
"""

_GF_EXP = [0] * 512
_GF_LOG = [0] * 256
_x = 1
for _i in range(255):
    _GF_EXP[_i] = _x
    _GF_LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _GF_EXP[_i] = _GF_EXP[_i - 255]


def _gf_mul(a, b):
    if a == 0 or b == 0:
        return 0
    return _GF_EXP[_GF_LOG[a] + _GF_LOG[b]]


def _rs_generator_poly(degree):
    poly = [1]
    for i in range(degree):
        next_poly = [0] * (len(poly) + 1)
        factor = _GF_EXP[i]
        for j, coef in enumerate(poly):
            next_poly[j] ^= coef
            next_poly[j + 1] ^= _gf_mul(coef, factor)
        poly = next_poly
    return poly


def _rs_remainder(data, ecc_len):
    gen = _rs_generator_poly(ecc_len)
    res = list(data) + [0] * ecc_len
    for i in range(len(data)):
        coef = res[i]
        if coef != 0:
            for j, g in enumerate(gen):
                res[i + j] ^= _gf_mul(g, coef)
    return res[len(data):]


# Capacidades ECC-L (1 bloque): (version, size, data_codewords, ecc_codewords, alignment_centers)
_VERSION_SPECS_L = [
    (1, 21, 19, 7, []),
    (2, 25, 34, 10, [6, 18]),
    (3, 29, 55, 15, [6, 22]),
    (4, 33, 80, 20, [6, 26]),
    (5, 37, 108, 26, [6, 30]),
    (6, 41, 136, 36, [6, 34]),
]


def _encode_data_bits(payload_bytes):
    # Seleccionar la versión mínima que soporte los bytes + cabecera (4 bits modo + 8 bits longitud + 4 bits terminador)
    length = len(payload_bytes)
    spec = None
    for s in _VERSION_SPECS_L:
        if 16 + length * 8 <= s[2] * 8:
            spec = s
            break
    if spec is None:
        raise ValueError('Payload demasiado largo para el generador QR.')

    version, size, data_cw, ecc_cw, align = spec
    bits = []

    def push_bits(val, count):
        for shift in range(count - 1, -1, -1):
            bits.append((val >> shift) & 1)

    push_bits(0b0100, 4)  # Byte mode
    push_bits(length, 8)
    for b in payload_bytes:
        push_bits(b, 8)

    max_bits = data_cw * 8
    terminator = min(4, max_bits - len(bits))
    push_bits(0, terminator)
    while len(bits) % 8 != 0:
        bits.append(0)

    pad_bytes = [0xEC, 0x11]
    pad_idx = 0
    while len(bits) < max_bits:
        push_bits(pad_bytes[pad_idx % 2], 8)
        pad_idx += 1

    data_bytes = [0] * data_cw
    for i in range(data_cw):
        val = 0
        for b in range(8):
            val = (val << 1) | bits[i * 8 + b]
        data_bytes[i] = val

    ecc_bytes = _rs_remainder(data_bytes, ecc_cw)
    all_bytes = data_bytes + ecc_bytes
    final_bits = []
    for byte in all_bytes:
        for shift in range(7, -1, -1):
            final_bits.append((byte >> shift) & 1)
    return version, size, align, final_bits


def _build_matrix(version, size, align, bit_stream):
    grid = [[None] * size for _ in range(size)]
    is_func = [[False] * size for _ in range(size)]

    def set_func(r, c, val):
        if 0 <= r < size and 0 <= c < size:
            grid[r][c] = 1 if val else 0
            is_func[r][c] = True

    def draw_finder(top, left):
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                r, c = top + dr, left + dc
                if not (0 <= r < size and 0 <= c < size):
                    continue
                if dr in (-1, 7) or dc in (-1, 7):
                    set_func(r, c, 0)
                elif dr in (0, 6) or dc in (0, 6) or (2 <= dr <= 4 and 2 <= dc <= 4):
                    set_func(r, c, 1)
                else:
                    set_func(r, c, 0)

    draw_finder(0, 0)
    draw_finder(0, size - 7)
    draw_finder(size - 7, 0)

    # Alignment patterns
    for r_c in align:
        for c_c in align:
            if (r_c == 6 and c_c == 6) or (r_c == 6 and c_c == size - 7) or (r_c == size - 7 and c_c == 6):
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    val = 1 if (abs(dr) == 2 or abs(dc) == 2 or (dr == 0 and dc == 0)) else 0
                    set_func(r_c + dr, c_c + dc, val)

    # Timing patterns
    for i in range(8, size - 8):
        val = 1 if i % 2 == 0 else 0
        if not is_func[6][i]:
            set_func(6, i, val)
        if not is_func[i][6]:
            set_func(i, 6, val)

    # Dark module + format placeholders
    set_func(size - 8, 8, 1)
    for i in range(9):
        if i != 6:
            set_func(8, i, 0)
            set_func(i, 8, 0)
    for i in range(8):
        set_func(8, size - 1 - i, 0)
    for i in range(7):
        set_func(size - 1 - i, 8, 0)

    # Place data bits (zigzag)
    bit_idx = 0
    upward = True
    col = size - 1
    while col > 0:
        if col == 6:
            col -= 1
        rows = range(size - 1, -1, -1) if upward else range(size)
        for r in rows:
            for c in (col, col - 1):
                if not is_func[r][c]:
                    grid[r][c] = bit_stream[bit_idx] if bit_idx < len(bit_stream) else 0
                    bit_idx += 1
        upward = not upward
        col -= 2

    # Apply mask 0: (r + c) % 2 == 0
    for r in range(size):
        for c in range(size):
            if not is_func[r][c] and (r + c) % 2 == 0:
                grid[r][c] ^= 1

    # Format info for ECC-L (01) and Mask 0 (000) -> 15-bit BCH + XOR 0x5412 = 0x77C4
    fmt_bits = 0x77C4
    for i in range(6):
        bit = (fmt_bits >> (14 - i)) & 1
        set_func(8, i, bit)
        set_func(size - 1 - i, 8, bit)
    set_func(8, 7, (fmt_bits >> 8) & 1)
    set_func(size - 7, 8, (fmt_bits >> 8) & 1)
    set_func(8, 8, (fmt_bits >> 7) & 1)
    set_func(8, size - 8, (fmt_bits >> 7) & 1)
    set_func(7, 8, (fmt_bits >> 6) & 1)
    set_func(8, size - 7, (fmt_bits >> 6) & 1)
    for i in range(6):
        bit = (fmt_bits >> (5 - i)) & 1
        set_func(5 - i, 8, bit)
        set_func(8, size - 6 + i, bit)

    return grid


def generar_qr_svg(texto, tamaño_px=200):
    payload = texto.encode('utf-8')
    version, size, align, bit_stream = _encode_data_bits(payload)
    grid = _build_matrix(version, size, align, bit_stream)

    quiet = 2
    total = size + quiet * 2
    paths = []
    for r in range(size):
        for c in range(size):
            if grid[r][c] == 1:
                x = c + quiet
                y = r + quiet
                paths.append(f'M{x},{y}h1v1h-1z')

    d = ''.join(paths)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total} {total}" '
        f'width="{tamaño_px}" height="{tamaño_px}" role="img" '
        f'aria-label="Código QR de autorización" shape-rendering="crispEdges">'
        f'<rect width="{total}" height="{total}" fill="#ffffff"/>'
        f'<path d="{d}" fill="#0f1b33"/>'
        f'</svg>'
    )
