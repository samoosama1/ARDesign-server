# Source - https://stackoverflow.com/a/79600147
# Posted by Mark Adler, modified by community. See post 'Timeline' for change history
# Retrieved 2026-03-30, License - CC BY-SA 4.0

'''
  beagle.py -- detect zip bombs
  Copyright (C) 2025 Mark Adler
  Version 1.0  5 May 2025  Mark Adler

  This software is provided 'as-is', without any express or implied
  warranty.  In no event will the author be held liable for any damages
  arising from the use of this software.

  Permission is granted to anyone to use this software for any purpose,
  including commercial applications, and to alter it and redistribute it
  freely, subject to the following restrictions:

  1. The origin of this software must not be misrepresented; you must not
     claim that you wrote the original software. If you use this software
     in a product, an acknowledgment in the product documentation would be
     appreciated but is not required.
  2. Altered source versions must be plainly marked as such, and must not be
     misrepresented as being the original software.
  3. This notice may not be removed or altered from any source distribution.

  Mark Adler
  madler@alumni.caltech.edu
'''

# Examine a zip file and determine if it has any overlapping records. If it
# does, it is an invalid zip file, and is likely a zip bomb. See David
# Fifield's clever zip bomb construction and examples here:
#
#   https://www.bamsoftware.com/hacks/zipbomb/

import os
import struct


def has_overlapping_entries(zip_file):
    """Check if a ZIP file has overlapping records (zip bomb indicator).

    Args:
        zip_file: A seekable file-like object opened in binary mode.

    Returns:
        True if overlapping records detected (likely zip bomb).
        False if no overlaps (good zip file).
        None if not a valid zip file or unsupported format.
    """
    ends = []

    zip_file.seek(0, os.SEEK_END)
    size = zip_file.tell()

    def is_end(rec, pos):
        nonlocal ends
        end = struct.unpack('<HHHHLLH', rec)
        if end[0] != 0 or end[1] != 0 or pos + 22 + end[6] > size:
            return False
        ends.append((pos, pos + 22 + end[6]))
        end = end[2:6]
        if end[0] == 0xffff or end[1] == 0xffff or \
           end[2] == 0xffffffff or end[3] == 0xffffffff:
            if pos < 20:
                return False
            zip_file.seek(pos - 20, os.SEEK_SET)
            loc = struct.unpack('<LLQL', zip_file.read(20))
            if loc[0] != 0x07064b50 or loc[1] != 0 or loc[3] != 1 or \
               loc[2] + 56 > size:
                return False
            ends.append((pos - 20, pos))
            zip_file.seek(loc[2], os.SEEK_SET)
            end = struct.unpack('<LQHHLLQQQQ', zip_file.read(56))
            if end[0] != 0x06064b50 or end[1] < 44 or end[4] != 0 or \
               end[5] != 0:
                return False
            ends.append((loc[2], loc[2] + 12 + end[1]))
            end = end[6:10]
        if end[0] != end[1] or end[3] + end[2] > size:
            return False
        ends.append((end[3], end[3] + end[2]))
        ends.reverse()
        return end[1:]

    def central():
        block = 8192
        beg = size
        back = 22
        buf = b''
        i = 1
        while True:
            beg -= back
            if beg < 0:
                return False
            zip_file.seek(beg, os.SEEK_SET)
            buf = zip_file.read(back) + buf[:21]
            while i > 0:
                i -= 1
                if buf[i] == 0x50 and buf[i + 1] == 0x4b and \
                   buf[i + 2] == 5 and buf[i + 3] == 6:
                    end = is_end(buf[i + 4:i + 22], beg + i)
                    if end:
                        return end
            back = ((beg - 1) & (block - 1)) + 1
            i = back

    dir_info = central()
    if not dir_info:
        return None

    spans = []
    (num, end, pos) = dir_info
    zip_file.seek(pos, os.SEEK_SET)
    cent = zip_file.read(end)
    i = 0
    while num > 0:
        if i + 46 > end:
            break
        head = struct.unpack('<LHHHHHHLLLHHHHHLL', cent[i:i + 46])
        i += 46
        if head[0] != 0x02014b50:
            break
        skip = head[10] + head[11] + head[12]
        if i + skip > end:
            break
        clen = head[8]
        ulen = head[9]
        disk = head[13]
        off = head[16]
        if clen == 0xffffffff or ulen == 0xffffffff or \
           disk == 0xffff or off == 0xffffffff:
            good = False
            i += head[10]
            xend = i + head[11]
            while i + 4 <= xend:
                (id, data) = struct.unpack('<HH', cent[i:i + 4])
                i += 4
                if i + data > xend:
                    break
                dend = i + data
                if id == 1:
                    if ulen == 0xffffffff:
                        if i + 8 > dend:
                            break
                        ulen = struct.unpack('<Q', cent[i:i + 8])[0]
                        i += 8
                    if clen == 0xffffffff:
                        if i + 8 > dend:
                            break
                        clen = struct.unpack('<Q', cent[i:i + 8])[0]
                        i += 8
                    if off == 0xffffffff:
                        if i + 8 > dend:
                            break
                        off = struct.unpack('<Q', cent[i:i + 8])[0]
                        i += 8
                    if disk == 0xffff:
                        if i + 4 > dend:
                            break
                        disk = struct.unpack('<L', cent[i:i + 4])[0]
                        i += 4
                    if i != dend:
                        break
                    good = True
                    break
                else:
                    i = dend
            if not good:
                break
            i = xend + head[12]
        else:
            i += skip
        if disk != 0:
            break
        if off + 30 > size:
            break
        zip_file.seek(off, os.SEEK_SET)
        local = struct.unpack('<LHHHHHLLLHH', zip_file.read(30))
        if local[0] != 0x04034b50:
            break
        lend = off + 30 + local[9] + local[10] + clen
        if lend > size:
            break
        if local[2] & 8 != 0:
            crc = head[7]
            zip_file.seek(lend, os.SEEK_SET)
            desc = zip_file.read(24)
            d24 = struct.unpack('<LLQQ', desc[:24]) if len(desc) == 24 else ()
            d20 = struct.unpack('<LQQ', desc[:20]) if len(desc) >= 20 else ()
            d16 = struct.unpack('<LLLL', desc[:16]) if len(desc) >= 16 else ()
            d12 = struct.unpack('<LLL', desc[:12]) if len(desc) >= 12 else ()
            if len(desc) == 24 and d24[0] == 0x08074b50 and \
               d24[1] == crc and d24[2] == clen and d24[3] == ulen:
                lend += 24
            elif len(desc) >= 20 and \
                 d20[0] == crc and d20[1] == clen and d20[2] == ulen:
                lend += 20
            elif len(desc) >= 16 and d16[0] == 0x08074b50 and \
                 d16[1] == crc and d16[2] == clen and d16[3] == ulen:
                lend += 16
            elif len(desc) >= 12 and \
                 d12[0] == crc and d12[1] == clen and d12[2] == ulen:
                lend += 12
            else:
                break
        spans.append((off, lend))
        num -= 1
    else:
        if i == end:
            spans += ends
            spans.sort()
            this = spans[0]
            for next_span in spans[1:]:
                if this[1] > next_span[0]:
                    return True
                this = next_span
            return False

    return None
