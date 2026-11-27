/* R173 native stream decoder for block-addressable positional postings.
 *
 * Pure decoder kernel, loaded through ctypes (no SQLite linkage).  It exists
 * because profiling attributes ~90% of phrase-query time to unsigned LEB128,
 * byte-aligned fixed-width and bit-packed stream decoding in Python.  Every
 * function validates lengths and returns -1 rather than reading out of bounds;
 * the Python fallback in blocked_positions.py is the reference implementation.
 *
 * Build: cc -O3 -Wall -Wextra -Werror -shared -fPIC cdgbp.c -o cdgbp.so
 */
#include <stddef.h>
#include <stdint.h>
#include <string.h>

static int read_varint(const unsigned char *in, size_t n, size_t *i, uint32_t *out) {
  uint32_t v = 0;
  unsigned shift = 0;
  while (*i < n) {
    unsigned char b = in[(*i)++];
    v |= (uint32_t)(b & 0x7fu) << shift;
    if (!(b & 0x80u)) { *out = v; return 0; }
    shift += 7;
    if (shift > 28) return -1;
  }
  return -1;
}

/* tag 0: unsigned LEB128, tag 1: byte-aligned fixed width, tag 2: bit-packed. */
int cdg_decode_stream(int tag, const unsigned char *in, size_t n, uint32_t count,
                      uint32_t *out) {
  if (count == 0) {
    if (tag == 0) return n == 0 ? 0 : -1;
    if (tag == 1 || tag == 2) return n == 1 ? 0 : -1;
    return -1;
  }
  if (in == NULL || out == NULL) return -1;
  if (tag == 0) {
    size_t i = 0;
    uint32_t k;
    for (k = 0; k < count; k++) {
      uint32_t v;
      if (read_varint(in, n, &i, &v)) return -1;
      out[k] = v;
    }
    return i == n ? 0 : -1;
  }
  if (tag == 1) {
    unsigned w;
    uint32_t k;
    if (n < 1) return -1;
    w = in[0];
    if (w < 1 || w > 4) return -1;
    if (n != 1 + (size_t)w * count) return -1;
    for (k = 0; k < count; k++) {
      const unsigned char *p = in + 1 + (size_t)k * w;
      uint32_t v = 0;
      unsigned j;
      for (j = 0; j < w; j++) v |= (uint32_t)p[j] << (8u * j);
      out[k] = v;
    }
    return 0;
  }
  if (tag == 2) {
    unsigned w;
    size_t need, i = 1;
    uint64_t acc = 0;
    unsigned bits = 0;
    uint32_t k;
    if (n < 1) return -1;
    w = in[0];
    if (w > 32) return -1;
    need = ((size_t)w * count + 7) / 8;
    if (n != 1 + need) return -1;
    if (w == 0) { memset(out, 0, (size_t)count * sizeof(uint32_t)); return 0; }
    for (k = 0; k < count; k++) {
      while (bits < w) { acc |= (uint64_t)in[i++] << bits; bits += 8; }
      out[k] = (uint32_t)(acc & ((((uint64_t)1) << w) - 1u));
      acc >>= w;
      bits -= w;
    }
    return 0;
  }
  return -1;
}

/* Prefix sums for one document-id or position-delta stream.
 * out[k] = initial + sum(in[0..k]); used to rebuild absolute ids without a
 * Python-level loop. */
int cdg_prefix_sum(const uint32_t *in, uint32_t count, uint32_t initial, uint32_t *out) {
  uint32_t k, acc = initial;
  if (count == 0) return 0;
  if (in == NULL || out == NULL) return -1;
  for (k = 0; k < count; k++) {
    acc += in[k];
    out[k] = acc;
  }
  return 0;
}
