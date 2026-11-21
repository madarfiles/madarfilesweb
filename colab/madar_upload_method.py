"""«طريقة المحررين» for «جودة تيك توك»: a port of tiktok-quality 1.0.0 (transform.py and its MP4
helpers) by Bastien GIMBERT, itself reverse-engineered from the "TikTok Enhancer" extension.
It rewrites only the MP4 index: SEI stripped from the first frame, ghost samples (10× the frame
count) pointing at one 8-byte filler block, recalculated bitrates, a comment tag, audio handler
"SoundHandler". Pixels and audio samples are untouched. Changes for Madar: errors raise instead of
exiting, no console output, the avcC High-profile bytes are added only when missing, and layouts
the port does not handle are refused (the tool then keeps the normal file).

Original licence:

    MIT License

    Copyright (c) 2026 Bastien GIMBERT

    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.
"""
from __future__ import annotations

import struct
from typing import List, Optional, Tuple


# ---- MP4 parser (tiktok_quality/mp4/parser.py) ----



def read_u32(data: bytes, offset: int) -> int:
    return struct.unpack('>I', data[offset:offset + 4])[0]


def read_u16(data: bytes, offset: int) -> int:
    return struct.unpack('>H', data[offset:offset + 2])[0]


def find_box(data: bytes, box_type: str, offset: int = 0, end: int | None = None) -> Tuple[Optional[int], Optional[int]]:
    """Find a box by type at current level. Returns (position, size) or (None, None)."""
    if end is None:
        end = len(data)
    pos = offset
    while pos + 8 <= end:
        size = read_u32(data, pos)
        btype = data[pos + 4:pos + 8].decode('latin-1')
        if size < 8:
            break
        if btype == box_type:
            return pos, size
        pos += size
    return None, None


def find_box_path(data: bytes, path: List[str], offset: int = 0, end: int | None = None) -> Tuple[Optional[int], Optional[int]]:
    """
    Navigate nested container boxes to find a target.
    Example: find_box_path(data, ['mdia', 'minf', 'stbl'])
    """
    if end is None:
        end = len(data)
    current_offset = offset
    current_end = end

    for i, box_type in enumerate(path):
        pos = current_offset
        while pos + 8 <= current_end:
            size = read_u32(data, pos)
            btype = data[pos + 4:pos + 8].decode('latin-1')
            if size < 8:
                break
            if btype == box_type:
                if i == len(path) - 1:
                    return pos, size
                current_offset = pos + 8
                current_end = pos + size
                break
            pos += size
        else:
            return None, None
    return None, None


def find_track_by_handler(data: bytes, moov_offset: int, moov_size: int, handler: bytes) -> Tuple[Optional[int], Optional[int]]:
    """Find a track by handler type (b'vide', b'soun')."""
    pos = moov_offset + 8
    end = moov_offset + moov_size
    while pos + 8 <= end:
        size = read_u32(data, pos)
        btype = data[pos + 4:pos + 8].decode('latin-1')
        if size < 8:
            break
        if btype == 'trak':
            hdlr_pos, _ = find_box_path(data, ['mdia', 'hdlr'], pos + 8, pos + size)
            if hdlr_pos:
                if data[hdlr_pos + 16:hdlr_pos + 20] == handler:
                    return pos, size
        pos += size
    return None, None


def parse_stts(data: bytes, offset: int) -> List[Tuple[int, int]]:
    """Parse time-to-sample box. Returns [(sample_count, sample_delta), ...]."""
    entry_count = read_u32(data, offset + 12)
    return [
        (read_u32(data, offset + 16 + i * 8), read_u32(data, offset + 20 + i * 8))
        for i in range(entry_count)
    ]


def parse_stsz(data: bytes, offset: int) -> List[int]:
    """Parse sample size box. Returns list of per-sample sizes."""
    uniform = read_u32(data, offset + 12)
    count = read_u32(data, offset + 16)
    if uniform != 0:
        return [uniform] * count
    return [read_u32(data, offset + 20 + i * 4) for i in range(count)]


def parse_stsc(data: bytes, offset: int) -> List[Tuple[int, int, int]]:
    """Parse sample-to-chunk box. Returns [(first_chunk, samples_per_chunk, desc_idx), ...]."""
    entry_count = read_u32(data, offset + 12)
    return [
        (read_u32(data, offset + 16 + i * 12),
         read_u32(data, offset + 20 + i * 12),
         read_u32(data, offset + 24 + i * 12))
        for i in range(entry_count)
    ]


def parse_stco(data: bytes, offset: int) -> List[int]:
    """Parse chunk offset box. Returns list of chunk offsets."""
    entry_count = read_u32(data, offset + 12)
    return [read_u32(data, offset + 16 + i * 4) for i in range(entry_count)]


def parse_nalu_list(sample_data: bytes) -> List[Tuple[int, int, bytes]]:
    """
    Parse NALUs in an AVC sample (4-byte length-prefixed).
    Returns [(nalu_type, nalu_length, full_nalu_with_prefix), ...].
    """
    nalus = []
    pos = 0
    while pos + 4 <= len(sample_data):
        nalu_len = read_u32(sample_data, pos)
        if pos + 4 + nalu_len > len(sample_data):
            break
        nalu_type = sample_data[pos + 4] & 0x1F
        nalus.append((nalu_type, nalu_len, sample_data[pos:pos + 4 + nalu_len]))
        pos += 4 + nalu_len
    return nalus


# ---- MP4 builder (tiktok_quality/mp4/builder.py) ----



def build_box(box_type: str, content: bytes) -> bytes:
    """Build a standard MP4 box: [size:4][type:4][content]."""
    return struct.pack('>I', 8 + len(content)) + box_type.encode('latin-1') + content


def build_ftyp(brand: str = 'isom', minor_version: int = 512,
               compatible: str = 'isomiso2avc1mp41') -> bytes:
    """Build an ftyp box with given brand."""
    content = brand.encode('latin-1') + struct.pack('>I', minor_version) + compatible.encode('latin-1')
    return build_box('ftyp', content)


def build_free() -> bytes:
    """Build a minimal 8-byte free box."""
    return struct.pack('>I', 8) + b'free'


def build_mvhd(original_content: bytes, duration_ms: int) -> bytes:
    """Build mvhd box with updated duration (offset 16 in content)."""
    content = bytearray(original_content)
    struct.pack_into('>I', content, 16, duration_ms)
    return build_box('mvhd', bytes(content))


def build_mdhd(original_content: bytes, duration: int | None = None, language: int | None = None) -> bytes:
    """Build mdhd box, optionally patching duration and language."""
    content = bytearray(original_content)
    if duration is not None:
        struct.pack_into('>I', content, 16, duration)
    if language is not None:
        struct.pack_into('>H', content, 20, language)
    return build_box('mdhd', bytes(content))


def build_tkhd(original_data: bytes, duration_ms: int | None = None) -> bytes:
    """Patch tkhd duration (offset 28). Takes full box bytes."""
    result = bytearray(original_data)
    if duration_ms is not None:
        struct.pack_into('>I', result, 28, duration_ms)
    return bytes(result)


def build_hdlr(handler_type: bytes, name: str) -> bytes:
    """Build an hdlr box with handler type and name."""
    content = (struct.pack('>II', 0, 0) + handler_type + b'\x00' * 12 +
               name.encode('utf-8') + b'\x00')
    return build_box('hdlr', content)


def build_stts(entries: List[Tuple[int, int]]) -> bytes:
    """Build stts box from [(sample_count, sample_delta), ...]."""
    body = b''.join(struct.pack('>II', c, d) for c, d in entries)
    return build_box('stts', struct.pack('>II', 0, len(entries)) + body)


def build_stsc(entries: List[Tuple[int, int, int]]) -> bytes:
    """Build stsc box from [(first_chunk, samples_per_chunk, desc_idx), ...]."""
    body = b''.join(struct.pack('>III', *e) for e in entries)
    return build_box('stsc', struct.pack('>II', 0, len(entries)) + body)


def build_stsz(sample_sizes: List[int]) -> bytes:
    """Build stsz box with variable per-sample sizes."""
    body = b''.join(struct.pack('>I', s) for s in sample_sizes)
    return build_box('stsz', struct.pack('>III', 0, 0, len(sample_sizes)) + body)


def build_stco(offsets: List[int]) -> bytes:
    """Build stco box from list of chunk offsets."""
    body = b''.join(struct.pack('>I', o) for o in offsets)
    return build_box('stco', struct.pack('>II', 0, len(offsets)) + body)


def build_stsd_video(fixed_fields: bytes, avcc: bytes, colr: bytes, pasp: bytes, btrt: bytes) -> bytes:
    """Build video stsd box from sub-components."""
    avc1_content = fixed_fields + avcc + colr + pasp + btrt
    avc1 = struct.pack('>I', 8 + len(avc1_content)) + b'avc1' + avc1_content
    return build_box('stsd', struct.pack('>II', 0, 1) + avc1)


def build_avcc(original_content: bytes, add_high_ext: bool = True) -> bytes:
    """Build avcC box, optionally adding High profile extension."""
    content = original_content
    if add_high_ext:
        content += b'\xfd\xf8\xf8\x00'
    return build_box('avcC', content)


def build_btrt(buffer_size_db: int, max_bitrate: int, avg_bitrate: int) -> bytes:
    """Build btrt (bitrate) box."""
    return build_box('btrt', struct.pack('>III', buffer_size_db, max_bitrate, avg_bitrate))


def build_udta_comment(comment: str) -> bytes:
    """Build udta box with iTunes-style comment metadata."""
    meta_hdlr = build_box('hdlr', struct.pack('>II', 0, 0) + b'mdir' + b'appl' + b'\x00' * 8 + b'\x00')
    data_box = build_box('data', struct.pack('>II', 1, 0) + comment.encode('utf-8'))
    cmt = struct.pack('>I', 8 + len(data_box)) + b'\xa9cmt' + data_box
    ilst = build_box('ilst', cmt)
    meta = build_box('meta', struct.pack('>I', 0) + meta_hdlr + ilst)
    return build_box('udta', meta)


# ---- transform (tiktok_quality/transform.py) ----
# 8-byte filler NAL: length=4, type=0 (filler), empty payload
PADDING_NAL = b'\x00\x00\x00\x04\x00\x00\x00\x00'
PADDING_SIZE = 8

# NALU types to keep in first sample (strip SEI etc.)
KEEP_NALU_TYPES = {1, 5}  # non-IDR slice, IDR slice

# ISO 639-2/T packed 'und'
LANG_UND = 0x55c4


def transform(input_path: str, output_path: str, multiplier: int = 10,
              comment: str = 'TK8vY5VqBA6hUlo1yuGvNA', verbose: bool = False) -> dict:
    """
    Apply the TikTok Enhancer transformation pipeline.

    Args:
        input_path: Path to source MP4 file (H.264/AVC).
        output_path: Path to write the manipulated MP4.
        multiplier: Frame count multiplier (default 10x).
        comment: Metadata comment/signature string.
        verbose: Print progress messages.

    Returns:
        Dict with stats about the transformation.
    """
    with open(input_path, 'rb') as f:
        data = f.read()

    file_size = len(data)
    if verbose:
        print(f"[*] Input: {input_path} ({file_size:,} bytes)")

    # Parse source
    moov_pos, moov_size = find_box(data, 'moov')
    mdat_pos, mdat_size = find_box(data, 'mdat')
    if moov_pos is None or mdat_pos is None:
        raise ValueError('moov/mdat')

    mdat_data_start = mdat_pos + 8

    # Video track
    vt_pos, vt_size = find_track_by_handler(data, moov_pos, moov_size, b'vide')
    if vt_pos is None:
        raise ValueError('no video track')

    vt_start, vt_end = vt_pos + 8, vt_pos + vt_size
    stbl_pos, stbl_size = find_box_path(data, ['mdia', 'minf', 'stbl'], vt_start, vt_end)
    sb_start, sb_end = stbl_pos + 8, stbl_pos + stbl_size

    stco_pos, _ = find_box(data, 'stco', sb_start, sb_end)
    stsz_pos, _ = find_box(data, 'stsz', sb_start, sb_end)
    stsc_pos, _ = find_box(data, 'stsc', sb_start, sb_end)
    stts_pos, _ = find_box(data, 'stts', sb_start, sb_end)
    stsd_pos, stsd_size = find_box(data, 'stsd', sb_start, sb_end)
    stss_pos, stss_size = find_box(data, 'stss', sb_start, sb_end)
    sdtp_pos, sdtp_size = find_box(data, 'sdtp', sb_start, sb_end)
    ctts_pos, ctts_size = find_box(data, 'ctts', sb_start, sb_end)

    if stco_pos is None or b'avcC' not in data[stsd_pos:stsd_pos + stsd_size]:
        raise ValueError('needs H.264 with 32-bit chunk offsets')
    video_chunks = parse_stco(data, stco_pos)
    video_sizes = parse_stsz(data, stsz_pos)
    video_stsc = parse_stsc(data, stsc_pos)
    video_stts = parse_stts(data, stts_pos)

    orig_frames = len(video_sizes)
    time_delta = video_stts[0][1]
    pad_count = orig_frames * (multiplier - 1)
    total_frames = orig_frames + pad_count

    v_mdhd_pos, v_mdhd_size = find_box_path(data, ['mdia', 'mdhd'], vt_start, vt_end)
    v_timescale = read_u32(data, v_mdhd_pos + 20)
    v_duration = read_u32(data, v_mdhd_pos + 24)
    v_duration_sec = v_duration / v_timescale

    if verbose:
        fps = v_timescale / time_delta
        print(f"[*] Video: {orig_frames} frames @ {fps:.0f} fps, {v_duration_sec:.1f}s")
        print(f"[*] Ghost frames: +{pad_count} -> {total_frames} declared")

    # Strip SEI from first sample
    first_off = video_chunks[0]
    first_size = video_sizes[0]
    first_sample = data[first_off:first_off + first_size]

    nalus = parse_nalu_list(first_sample)
    kept = [d for t, _, d in nalus if t in KEEP_NALU_TYPES]
    new_first = b''.join(kept) if kept else first_sample
    new_first_size = len(new_first)
    sei_removed = first_size - new_first_size

    if verbose:
        print(f"[*] First sample: {first_size} -> {new_first_size} bytes (-{sei_removed} SEI)")

    # Audio track
    at_pos, at_size = find_track_by_handler(data, moov_pos, moov_size, b'soun')
    has_audio = at_pos is not None

    if has_audio:
        at_start, at_end = at_pos + 8, at_pos + at_size
        a_stbl_pos, _ = find_box_path(data, ['mdia', 'minf', 'stbl'], at_start, at_end)
        a_sb_start, a_sb_end = a_stbl_pos + 8, a_stbl_pos + _

        a_stco_pos, _ = find_box(data, 'stco', a_sb_start, a_sb_end)
        a_stsz_pos, a_stsz_size = find_box(data, 'stsz', a_sb_start, a_sb_end)
        a_stsc_pos, a_stsc_size = find_box(data, 'stsc', a_sb_start, a_sb_end)
        a_stts_pos, _ = find_box(data, 'stts', a_sb_start, a_sb_end)
        a_stsd_pos, a_stsd_size = find_box(data, 'stsd', a_sb_start, a_sb_end)
        a_sgpd_pos, a_sgpd_size = find_box(data, 'sgpd', a_sb_start, a_sb_end)
        a_sbgp_pos, a_sbgp_size = find_box(data, 'sbgp', a_sb_start, a_sb_end)

        audio_chunks = parse_stco(data, a_stco_pos)
        audio_sizes = parse_stsz(data, a_stsz_pos)
        audio_stts = parse_stts(data, a_stts_pos)

        a_mdhd_pos, a_mdhd_size = find_box_path(data, ['mdia', 'mdhd'], at_start, at_end)
        a_timescale = read_u32(data, a_mdhd_pos + 20)

        # Read audio ELST for timing alignment
        a_elst_pos, _ = find_box_path(data, ['edts', 'elst'], at_start, at_end)
        if a_elst_pos is None or a_stco_pos is None:
            raise ValueError('audio layout')
        a_elst_seg_dur = read_u32(data, a_elst_pos + 16)  # ms
        a_elst_media_time = read_u32(data, a_elst_pos + 20)  # ticks

        new_audio_dur_ms = a_elst_seg_dur
        new_audio_dur = new_audio_dur_ms * a_timescale // 1000

        # STTS: align to mdhd + media_time
        a_delta = audio_stts[0][1]
        a_count = len(audio_sizes)
        target_stts = new_audio_dur + a_elst_media_time
        main_n = a_count - 1
        last_delta = target_stts - main_n * a_delta

        if 0 < last_delta <= a_delta:
            new_a_stts = [(main_n, a_delta), (1, last_delta)]
        else:
            new_a_stts = audio_stts
            new_audio_dur = read_u32(data, a_mdhd_pos + 24)
            new_audio_dur_ms = new_audio_dur * 1000 // a_timescale

        # Bitrates
        total_a_bytes = sum(audio_sizes)
        old_a_ticks = sum(c * d for c, d in audio_stts)
        new_a_ticks = sum(c * d for c, d in new_a_stts)
        old_a_br = total_a_bytes * 8 * a_timescale // old_a_ticks
        new_a_br = total_a_bytes * 8 * a_timescale // new_a_ticks

    # Build new mdat
    mdat_before = data[mdat_data_start:first_off]
    mdat_after = data[first_off + first_size:mdat_pos + mdat_size]
    new_mdat_content = mdat_before + new_first + mdat_after + PADDING_NAL
    new_mdat = struct.pack('>I', 8 + len(new_mdat_content)) + b'mdat' + new_mdat_content

    # Build new moov
    ftyp = build_ftyp()
    free = build_free()

    # MVHD
    mvhd_pos, mvhd_size = find_box(data, 'mvhd', moov_pos + 8, moov_pos + moov_size)
    mvhd_content = data[mvhd_pos + 8:mvhd_pos + mvhd_size]
    v_tkhd_pos, _ = find_box(data, 'tkhd', vt_start, vt_end)
    v_tkhd_dur_ms = read_u32(data, v_tkhd_pos + 28)
    new_mvhd_dur = max(v_tkhd_dur_ms, new_audio_dur_ms) if has_audio else v_tkhd_dur_ms
    mvhd = build_mvhd(mvhd_content, new_mvhd_dur)

    # Video track components
    video_tkhd = data[vt_start:vt_start + read_u32(data, vt_start)]
    edts_pos, edts_size = find_box(data, 'edts', vt_start, vt_end)
    video_edts = data[edts_pos:edts_pos + edts_size] if edts_pos else b''
    video_mdhd = data[v_mdhd_pos:v_mdhd_pos + v_mdhd_size]
    v_hdlr_pos, v_hdlr_size = find_box_path(data, ['mdia', 'hdlr'], vt_start, vt_end)
    video_hdlr = data[v_hdlr_pos:v_hdlr_pos + v_hdlr_size]
    vmhd_pos, vmhd_size = find_box_path(data, ['mdia', 'minf', 'vmhd'], vt_start, vt_end)
    video_vmhd = data[vmhd_pos:vmhd_pos + vmhd_size]
    dinf_pos, dinf_size = find_box_path(data, ['mdia', 'minf', 'dinf'], vt_start, vt_end)
    video_dinf = data[dinf_pos:dinf_pos + dinf_size]

    # Video STSD (avcC + btrt patched)
    stsd_content = data[stsd_pos + 8:stsd_pos + stsd_size]
    avc1_fixed = stsd_content[16:94]

    avcc_rel = stsd_content.find(b'avcC')
    avcc_start = avcc_rel - 4
    avcc_orig_size = read_u32(stsd_content, avcc_start)
    avcc_body = stsd_content[avcc_start + 8:avcc_start + avcc_orig_size]
    avcc_new = build_avcc(avcc_body, add_high_ext=not avcc_body.endswith(b'\xfd\xf8\xf8\x00'))

    colr_box = b''
    colr_rel = stsd_content.find(b'colr')
    if colr_rel >= 0:
        cs = colr_rel - 4
        colr_box = stsd_content[cs:cs + read_u32(stsd_content, cs)]

    pasp_box = b''
    pasp_rel = stsd_content.find(b'pasp')
    if pasp_rel >= 0:
        ps = pasp_rel - 4
        pasp_box = stsd_content[ps:ps + read_u32(stsd_content, ps)]

    total_v_bytes = sum(video_sizes) - first_size + new_first_size
    new_v_avg_br = int(total_v_bytes * 8 / v_duration_sec)
    btrt_rel = stsd_content.find(b'btrt')
    max_br = read_u32(stsd_content, btrt_rel + 8) if btrt_rel >= 0 else new_v_avg_br
    btrt_new = build_btrt(0, max_br, new_v_avg_br)

    video_stsd_new = build_stsd_video(avc1_fixed, avcc_new, colr_box, pasp_box, btrt_new)

    # Video tables
    video_stts_new = build_stts([(orig_frames, time_delta), (pad_count, time_delta)])
    video_stss = data[stss_pos:stss_pos + stss_size] if stss_pos else b''
    video_sdtp = data[sdtp_pos:sdtp_pos + sdtp_size] if sdtp_pos else b''
    video_ctts = data[ctts_pos:ctts_pos + ctts_size] if ctts_pos else b''
    video_stsc_new = build_stsc(list(video_stsc) + [(len(video_chunks) + 1, 1, 1)])
    video_stsz_new = build_stsz([new_first_size] + video_sizes[1:] + [PADDING_SIZE] * pad_count)

    # STCO placeholder
    total_v_chunks = len(video_chunks) + pad_count
    stco_ph_size = 16 + total_v_chunks * 4
    v_stco_ph = struct.pack('>I', stco_ph_size) + b'stco' + b'\x00' * (stco_ph_size - 8)

    v_stbl_parts = [video_stsd_new, video_stts_new]
    if video_stss: v_stbl_parts.append(video_stss)
    if video_sdtp: v_stbl_parts.append(video_sdtp)
    if video_ctts: v_stbl_parts.append(video_ctts)
    v_stbl_parts += [video_stsc_new, video_stsz_new, v_stco_ph]

    video_stbl = build_box('stbl', b''.join(v_stbl_parts))
    video_minf = build_box('minf', video_vmhd + video_dinf + video_stbl)
    video_mdia = build_box('mdia', video_mdhd + video_hdlr + video_minf)
    video_trak = build_box('trak', video_tkhd + video_edts + video_mdia)

    # Audio track
    if has_audio:
        a_tkhd_pos, a_tkhd_size = find_box(data, 'tkhd', at_start, at_end)
        audio_tkhd = build_tkhd(data[a_tkhd_pos:a_tkhd_pos + a_tkhd_size], new_audio_dur_ms)

        a_edts_pos, a_edts_size = find_box(data, 'edts', at_start, at_end)
        audio_edts = data[a_edts_pos:a_edts_pos + a_edts_size] if a_edts_pos else b''

        audio_mdhd = build_mdhd(data[a_mdhd_pos + 8:a_mdhd_pos + a_mdhd_size],
                                duration=new_audio_dur, language=LANG_UND)
        audio_hdlr = build_hdlr(b'soun', 'SoundHandler')

        smhd_pos, smhd_size = find_box_path(data, ['mdia', 'minf', 'smhd'], at_start, at_end)
        audio_smhd = data[smhd_pos:smhd_pos + smhd_size]
        a_dinf_pos, a_dinf_size = find_box_path(data, ['mdia', 'minf', 'dinf'], at_start, at_end)
        audio_dinf = data[a_dinf_pos:a_dinf_pos + a_dinf_size]

        # Patch audio stsd bitrate
        audio_stsd = bytearray(data[a_stsd_pos:a_stsd_pos + a_stsd_size])
        old_br = struct.pack('>I', old_a_br)
        new_br = struct.pack('>I', new_a_br)
        p = 0
        while (idx := audio_stsd.find(old_br, p)) != -1:
            audio_stsd[idx:idx + 4] = new_br
            p = idx + 4
        audio_stsd = bytes(audio_stsd)

        audio_stts_new = build_stts(new_a_stts)
        audio_stsc = data[a_stsc_pos:a_stsc_pos + a_stsc_size]
        audio_stsz = data[a_stsz_pos:a_stsz_pos + a_stsz_size]

        a_stco_ph_size = 16 + len(audio_chunks) * 4
        a_stco_ph = struct.pack('>I', a_stco_ph_size) + b'stco' + b'\x00' * (a_stco_ph_size - 8)

        a_sgpd = data[a_sgpd_pos:a_sgpd_pos + a_sgpd_size] if a_sgpd_pos else b''
        a_sbgp = data[a_sbgp_pos:a_sbgp_pos + a_sbgp_size] if a_sbgp_pos else b''

        audio_stbl = build_box('stbl', audio_stsd + audio_stts_new + audio_stsc +
                               audio_stsz + a_stco_ph + a_sgpd + a_sbgp)
        audio_minf = build_box('minf', audio_smhd + audio_dinf + audio_stbl)
        audio_mdia = build_box('mdia', audio_mdhd + audio_hdlr + audio_minf)
        audio_trak = build_box('trak', audio_tkhd + audio_edts + audio_mdia)
    else:
        audio_trak = b''

    udta = build_udta_comment(comment)
    moov = build_box('moov', mvhd + video_trak + audio_trak + udta)
    moov_size_final = len(moov)

    # Fill STCO offsets
    new_mdat_start = 32 + 8 + moov_size_final + 8
    first_video_rel = first_off - mdat_data_start
    pad_abs = new_mdat_start + len(new_mdat_content) - PADDING_SIZE

    new_v_offsets = []
    for off in video_chunks:
        rel = off - mdat_data_start
        new_v_offsets.append(new_mdat_start + rel if rel <= first_video_rel
                            else new_mdat_start + rel - sei_removed)
    new_v_offsets.extend([pad_abs] * pad_count)

    new_a_offsets = []
    if has_audio:
        for off in audio_chunks:
            rel = off - mdat_data_start
            new_a_offsets.append(new_mdat_start + rel if rel < first_video_rel
                                else new_mdat_start + rel - sei_removed)

    # Rebuild with final STCOs
    v_stbl_parts[-1] = build_stco(new_v_offsets)
    video_stbl = build_box('stbl', b''.join(v_stbl_parts))
    video_minf = build_box('minf', video_vmhd + video_dinf + video_stbl)
    video_mdia = build_box('mdia', video_mdhd + video_hdlr + video_minf)
    video_trak = build_box('trak', video_tkhd + video_edts + video_mdia)

    if has_audio:
        audio_stbl = build_box('stbl', audio_stsd + audio_stts_new + audio_stsc +
                               audio_stsz + build_stco(new_a_offsets) + a_sgpd + a_sbgp)
        audio_minf = build_box('minf', audio_smhd + audio_dinf + audio_stbl)
        audio_mdia = build_box('mdia', audio_mdhd + audio_hdlr + audio_minf)
        audio_trak = build_box('trak', audio_tkhd + audio_edts + audio_mdia)

    moov = build_box('moov', mvhd + video_trak + audio_trak + udta)
    assert len(moov) == moov_size_final

    # Write output
    output = ftyp + free + moov + new_mdat
    with open(output_path, 'wb') as f:
        f.write(output)

    stats = {
        'input_size': file_size,
        'output_size': len(output),
        'size_delta': len(output) - file_size,
        'original_frames': orig_frames,
        'declared_frames': total_frames,
        'ghost_frames': pad_count,
        'multiplier': multiplier,
    }

    if verbose:
        print(f"[+] Output: {output_path} ({len(output):,} bytes)")
        print(f"[+] Delta: {stats['size_delta']:+,} bytes")
        print(f"[+] Frames: {orig_frames} -> {total_frames} (x{multiplier})")

    return stats
